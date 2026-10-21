"""hook 명령을 probe로 감싼 실행 인자를 만든다(표준 라이브러리만).

호출자(예: claude-sdk 백엔드, 4R.9)가 원래 명령 대신 이 인자로 hook을 돌리면 probe가 원래 명령을
그대로 실행하면서 기록을 남긴다. 사용자 설정 파일은 고치지 않는다.
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

__all__ = ["default_probe_command", "wrap_command", "wrap_command_line"]


def default_probe_command() -> list[str]:
    """기본 probe 실행 인자: 지금 파이썬으로 `-m agent_console_hook_probe`."""
    return [sys.executable, "-m", "agent_console_hook_probe"]


def wrap_command(
    command: str | Sequence[str],
    *,
    out: str | Path,
    probe: Sequence[str] | None = None,
    matcher: str | None = None,
    shell: str | None = None,
    context: Mapping[str, str] | None = None,
    capture_bytes: int | None = None,
) -> list[str]:
    """원래 명령을 probe로 감싼 인자 목록.

    Args:
        command: 문자열이면 셸 형식(Claude Code가 셸로 돌리는 명령), 인자 목록이면 실행 형식
            (셸 없이 그대로 실행, `--exec`).
        out: 기록 폴더.
        probe: probe 실행 인자(기본 `default_probe_command()`, 설치자 옵션으로 바꾼다).
        matcher: 기록에 남길 hook 매처.
        shell: 셸 형식일 때 셸 이름·경로(기본은 Claude Code 규칙).
        context: 기록에 붙일 맥락(`KEY=VALUE`, 예: run_id·node).
        capture_bytes: 스트림마다 기록에 남길 최대 바이트.

    Returns:
        `[*probe, --out, DIR, ..., --, <명령>]`.

    Raises:
        ValueError: 실행 형식인데 인자가 비었을 때, 맥락 키에 `=`가 있을 때.
    """
    argv = [*(probe if probe is not None else default_probe_command()), "--out", str(out)]
    if matcher is not None:
        argv += ["--matcher", matcher]
    if shell is not None:
        argv += ["--shell", shell]
    if capture_bytes is not None:
        argv += ["--capture-bytes", str(capture_bytes)]
    for key, value in (context or {}).items():
        if not key or "=" in key:
            raise ValueError(f"맥락 키가 잘못됐습니다: {key!r}")
        argv += ["--context", f"{key}={value}"]
    if isinstance(command, str):
        return [*argv, "--", command]
    if not command:
        raise ValueError("실행할 명령이 없습니다.")
    return [*argv, "--exec", "--", *command]


def wrap_command_line(
    command: str | Sequence[str],
    *,
    out: str | Path,
    probe: Sequence[str] | None = None,
    matcher: str | None = None,
    shell: str | None = None,
    context: Mapping[str, str] | None = None,
    capture_bytes: int | None = None,
    quote: Callable[[Sequence[str]], str] = shlex.join,
) -> str:
    """`wrap_command` 결과를 셸 명령 한 줄로(설정 파일의 `command` 문자열용).

    Args:
        quote: 인자 목록 → 명령 줄(기본 POSIX `shlex.join`; Claude Code는 Windows에서도 Git Bash를
            먼저 쓴다. PowerShell이면 호출자가 맞는 함수를 준다).
        나머지: `wrap_command`와 같다.
    """
    return quote(
        wrap_command(
            command,
            out=out,
            probe=probe,
            matcher=matcher,
            shell=shell,
            context=context,
            capture_bytes=capture_bytes,
        )
    )
