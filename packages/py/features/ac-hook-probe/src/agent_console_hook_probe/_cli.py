"""`agent-console-hook-probe` 진입점(표준 라이브러리만, 가져오기 비용을 작게).

    agent-console-hook-probe --out DIR [--matcher M] [--shell SH] [--exec]
                             [--context KEY=VALUE ...] [--capture-bytes N] -- <명령>

`--` 뒤가 인자 하나면 셸 형식(원래 명령 문자열을 셸로), 여럿이거나 `--exec`면 실행 형식(셸 없이).
probe 자신의 사용법 오류는 종료 코드 1(Claude Code에서 "막지 않는 오류")로 끝난다. 2(차단)를 쓰지
않는 것은 probe 설정 실수가 도구 호출을 막지 않게 하기 위해서다.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from ._probe import SPAWN_FAILED_EXIT_CODE, ProbeIO, run_probe
from ._record import (
    DEFAULT_CAPTURE_BYTES,
    ProbeOutcome,
    append_line,
    build_record,
    default_redactor,
    record_file_name,
)
from ._shell import default_shell_name, exec_invocation, shell_invocation

__all__ = ["USAGE_EXIT_CODE", "ProbeUsageError", "main", "parse_args"]

USAGE_EXIT_CODE = 1
"""probe 사용법 오류의 종료 코드(막지 않는 오류)."""

PROG = "agent-console-hook-probe"


class ProbeUsageError(ValueError):
    """probe 인자가 잘못됐다."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ProbeUsageError(message)


def _parser() -> _Parser:
    parser = _Parser(
        prog=PROG,
        description="hook 명령을 감싸 그대로 실행하고 입출력·결정·소요 시간을 jsonl로 남긴다.",
        usage=f"{PROG} --out DIR [--matcher M] [--shell SH] [--exec] "
        "[--context KEY=VALUE] [--capture-bytes N] -- <명령>",
    )
    parser.add_argument("--out", required=True, help="기록 폴더(세션마다 <세션>.jsonl)")
    parser.add_argument("--matcher", default=None, help="기록에 남길 hook 매처")
    parser.add_argument(
        "--shell", default=None, help="셸 이름(sh·bash·powershell·pwsh·cmd) 또는 셸 실행 파일"
    )
    parser.add_argument("--exec", dest="exec_form", action="store_true", help="셸 없이 실행")
    parser.add_argument(
        "--context", action="append", default=[], metavar="KEY=VALUE", help="기록에 붙일 맥락"
    )
    parser.add_argument(
        "--capture-bytes",
        type=int,
        default=DEFAULT_CAPTURE_BYTES,
        help=f"스트림마다 기록에 남길 최대 바이트(기본 {DEFAULT_CAPTURE_BYTES})",
    )
    return parser


def parse_args(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    """probe 인자와 원래 명령(`--` 뒤)을 나눈다.

    Raises:
        ProbeUsageError: `--`가 없거나 명령이 비었거나 옵션이 잘못됐을 때.
    """
    args = list(argv)
    if "--" not in args:
        raise ProbeUsageError("원래 명령 앞에 `--`가 필요합니다.")
    split = args.index("--")
    options, command = args[:split], args[split + 1 :]
    if not command or (len(command) == 1 and not command[0].strip()):
        raise ProbeUsageError("`--` 뒤에 실행할 명령이 없습니다.")
    ns = _parser().parse_args(options)
    if ns.capture_bytes < 0:
        raise ProbeUsageError("--capture-bytes는 0 이상이어야 합니다.")
    for item in ns.context:
        if "=" not in item or not item.split("=", 1)[0]:
            raise ProbeUsageError(f"--context는 KEY=VALUE 형식입니다: {item!r}")
    return ns, command


def _reraise_signal(signum: int) -> None:  # pragma: no cover - 프로세스를 끝낸다
    """자식이 신호로 끝났으면 probe도 같은 신호로 끝낸다(부모가 보는 결과를 같게)."""
    with contextlib.suppress(OSError, ValueError):  # SIGKILL은 처리기를 바꿀 수 없다
        signal.signal(signum, signal.SIG_DFL)
    with contextlib.suppress(OSError, ValueError):
        os.kill(os.getpid(), signum)


def main(
    argv: Sequence[str] | None = None,
    *,
    io: ProbeIO = ProbeIO(),  # noqa: B008 - 불변 값
    handle_signals: bool = True,
    redactor: Callable[[], Callable[[Any], Any]] = default_redactor,
    reraise_signal: Callable[[int], None] = _reraise_signal,
) -> int:
    """probe 한 번 실행. 반환값은 원래 명령의 종료 코드(그대로 프로세스 종료 코드가 된다).

    Args:
        argv: 인자(기본 `sys.argv[1:]`).
        io: 중계할 파일 기술자.
        handle_signals: 종료 신호를 자식 그룹에 전달한다.
        redactor: 비밀 의심 가림을 만드는 함수(기록할 때 부른다).
        reraise_signal: 자식이 신호로 끝났을 때 probe도 같은 신호로 끝내는 함수.
    """
    try:
        ns, command = parse_args(sys.argv[1:] if argv is None else argv)
    except ProbeUsageError as exc:
        os.write(io.stderr, f"{PROG}: {exc}\n".encode())
        return USAGE_EXIT_CODE
    exec_form = ns.exec_form or len(command) > 1
    shell: str | None = None
    if exec_form:
        invocation: list[str] | str = exec_invocation(command)
        original: str | list[str] = list(command)
    else:
        shell = ns.shell or default_shell_name()
        invocation = shell_invocation(command[0], shell)
        original = command[0]
    outcome = run_probe(
        invocation, io=io, capture_bytes=ns.capture_bytes, handle_signals=handle_signals
    )
    if outcome.error is not None:
        os.write(io.stderr, f"{PROG}: 명령을 실행하지 못했습니다 ({outcome.error})\n".encode())
    _record(ns, outcome, original, "exec" if exec_form else "shell", shell, redactor)
    if outcome.signal is not None:
        reraise_signal(outcome.signal)
        return 128 + outcome.signal
    if outcome.exit_code is None:
        return SPAWN_FAILED_EXIT_CODE
    return outcome.exit_code


def _record(
    ns: argparse.Namespace,
    outcome: ProbeOutcome,
    original: str | list[str],
    form: str,
    shell: str | None,
    redactor: Callable[[], Callable[[Any], Any]],
) -> None:
    """기록을 남긴다. 어떤 실패도 hook 결과(출력·종료 코드)에 영향을 주지 않는다."""
    try:
        context = dict(item.split("=", 1) for item in ns.context)
        record = build_record(
            outcome,
            command=original,
            form=form,
            shell=shell,
            matcher=ns.matcher,
            context=context,
            probe_id=uuid.uuid4().hex,
            redact=redactor(),
        )
        append_line(Path(ns.out), record_file_name(record.get("session_id")), record)
    except Exception:  # 기록 실패는 조용히(설계 §4R.7)
        return
