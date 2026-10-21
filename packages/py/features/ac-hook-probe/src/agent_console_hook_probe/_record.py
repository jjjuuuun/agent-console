"""기록 형식 `hook-probe/1`: 한 번의 hook 실행 = jsonl 한 줄(표준 라이브러리 + 비밀 가림 주입).

기록은 크기를 제한한(`capture_bytes`) 입출력과 비밀 의심 가림을 거친 값만 담는다. 명령 문자열은
원문 대신 해시(`command_digest`)만 남긴다. 기록 실패는 호출자가 삼킨다(hook 결과에 영향 없음).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._decision import derive_decision, parse_hook_output

__all__ = [
    "DEFAULT_CAPTURE_BYTES",
    "RECORD_FORMAT",
    "Capture",
    "ProbeOutcome",
    "append_line",
    "build_record",
    "command_digest",
    "default_redactor",
    "record_file_name",
]

RECORD_FORMAT = "hook-probe/1"
"""기록 한 줄의 `format` 값. 형식이 바뀌면 숫자를 올리고 분류기가 버전별로 읽는다."""

DEFAULT_CAPTURE_BYTES = 80_000
"""스트림(stdin·stdout·stderr)마다 기록에 남기는 최대 바이트(agent_bench `bounded` 80,000자 기준).
원래 명령에는 전부 그대로 전달한다. 이 한도는 기록에만 적용된다."""

CAPTURE_MARGIN_BYTES = 4096
"""한도 뒤로 더 잡아 두는 바이트. 가림을 이 여유까지 포함한 텍스트에 먼저 적용한 뒤 한도로 자르므로
한도 경계에 걸친 비밀(이 길이 이하)도 가려진다."""

PLAIN_FIELDS = frozenset(
    {
        "format",
        "probe_id",
        "form",
        "shell",
        "command_digest",
        "started_at",
        "ended_at",
        "duration_ms",
        "exit_code",
        "signal",
        "forwarded_signal",
        "bytes",
        "truncated",
    }
)
"""probe가 직접 만든 값(입력·인자에서 오지 않음)이라 가림을 거치지 않는 기록 키.
나머지는 모두 가린다."""

Redactor = Callable[[Any], Any]


@dataclass(slots=True)
class Capture:
    """스트림 하나에서 기록용으로 잡아 둔 앞부분과 전체 크기."""

    limit: int = DEFAULT_CAPTURE_BYTES
    margin: int = CAPTURE_MARGIN_BYTES
    data: bytearray = field(default_factory=bytearray)
    total: int = 0

    def add(self, chunk: bytes) -> None:
        """전달한 조각을 센다. 앞 `limit + margin` 바이트만 보관한다."""
        self.total += len(chunk)
        room = self.limit + self.margin - len(self.data)
        if room > 0:
            self.data += chunk[:room]

    @property
    def truncated(self) -> bool:
        """기록 한도(`limit`)보다 실제 전달한 것이 많다."""
        return self.total > self.limit

    def complete(self) -> bytes | None:
        """잘리지 않았으면 전체 바이트, 잘렸으면 None."""
        return None if self.truncated else bytes(self.data)


@dataclass(slots=True)
class ProbeOutcome:
    """감싼 실행 한 번의 결과(기록 재료).

    Attributes:
        exit_code: 원래 명령의 종료 코드(POSIX에서 신호로 끝나면 None, `signal`에 번호).
        signal: 원래 명령을 끝낸 신호 번호(없으면 None).
        started_at, ended_at: 벽시계 시각(epoch 초).
        duration_ms: 단조 시계로 잰 소요 시간.
        error: 실행 자체가 실패했을 때 짧은 사유(예: `spawn_failed: FileNotFoundError`).
        forwarded_signal: probe가 받아서 자식 그룹에 전달한 신호 번호.
    """

    exit_code: int | None
    started_at: float
    ended_at: float
    duration_ms: float
    stdin: Capture
    stdout: Capture
    stderr: Capture
    signal: int | None = None
    error: str | None = None
    forwarded_signal: int | None = None


def command_digest(command: str | Sequence[str]) -> str:
    """명령의 해시(`sha256:<hex>`). 실행 형식이면 인자를 JSON 목록으로 묶어 해시한다."""
    text = command if isinstance(command, str) else json.dumps(list(command), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(capture: Capture, redact: Redactor) -> Any:
    """여유분까지 디코드해 먼저 가리고, 그다음 `limit` 바이트로 자른다(경계에 걸친 비밀 대비)."""
    masked = redact(bytes(capture.data).decode("utf-8", errors="replace"))
    if not isinstance(masked, str) or not capture.truncated:
        return masked
    return masked.encode("utf-8")[: capture.limit].decode("utf-8", errors="ignore")


def _set_pointer(value: Any, pointer: str, replacement: Any) -> Any:
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    if not parts:
        return replacement
    target = value
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = parts[-1]
    if isinstance(target, list):
        target[int(last)] = replacement
    else:
        target[last] = replacement
    return value


def default_redactor() -> Redactor:
    """기본 비밀 의심 가림(`agent-console-secret-rules` 기본 규칙).

    문자열 안 비밀 모양은 그 부분만, 비밀 이름 키 아래 값은 통째로 가린다. 규칙은 이 함수를
    부를 때 가져온다(probe 시작을 가볍게).
    """
    from agent_console_secret_rules import FindingReason, default_rules

    rules = default_rules()

    def redact(value: Any) -> Any:
        masked = rules.redact_value(value)
        if isinstance(masked, dict | list):
            for finding in rules.find_suspected(masked):
                if finding.reason != FindingReason.VALUE_PATTERN:
                    masked = _set_pointer(masked, finding.path, rules.mask)
        return masked

    return redact


def build_record(
    outcome: ProbeOutcome,
    *,
    command: str | Sequence[str],
    form: str,
    shell: str | None,
    matcher: str | None,
    context: Mapping[str, str],
    probe_id: str,
    redact: Redactor,
) -> dict[str, Any]:
    """기록 한 줄(`hook-probe/1`)을 만든다.

    Args:
        outcome: 실행 결과.
        command: 원래 명령(해시만 남긴다).
        form: `shell`(셸 형식) 또는 `exec`(실행 형식).
        shell: 셸 이름(셸 형식일 때).
        matcher: hook 매처(`--matcher`).
        context: 호출자가 붙인 맥락(`--context KEY=VALUE`, 예: run_id·node).
        probe_id: 이 실행의 고유 id.
        redact: 비밀 의심 가림(입출력·사유에 적용).

    Returns:
        JSON으로 직렬화할 수 있는 객체.
    """
    stdin_raw = outcome.stdin.complete()
    hook_input = parse_hook_output(stdin_raw) if stdin_raw is not None else None
    common = hook_input or {}
    event = str(common.get("hook_event_name") or "")
    stdout_raw = outcome.stdout.complete()
    output = parse_hook_output(stdout_raw) if stdout_raw is not None else None
    decision = derive_decision(output, outcome.exit_code, event=event)

    def text_field(name: str) -> str | None:
        value = common.get(name)
        return value if isinstance(value, str) and value else None

    record: dict[str, Any] = {
        "format": RECORD_FORMAT,
        "probe_id": probe_id,
        "event": event or None,
        "session_id": text_field("session_id"),
        "tool_use_id": text_field("tool_use_id"),
        "tool": text_field("tool_name"),
        "agent_id": text_field("agent_id"),
        "agent_type": text_field("agent_type"),
        "cwd": text_field("cwd"),
        "matcher": matcher,
        "context": dict(context),
        "form": form,
        "shell": shell,
        "command_digest": command_digest(command),
        "started_at": outcome.started_at,
        "ended_at": outcome.ended_at,
        "duration_ms": round(outcome.duration_ms, 3),
        "exit_code": outcome.exit_code,
        "signal": outcome.signal,
        "forwarded_signal": outcome.forwarded_signal,
        "error": outcome.error,
        "decision": decision,
        "input": hook_input if hook_input is not None else _text(outcome.stdin, redact),
        "stdout": _text(outcome.stdout, redact),
        "stdout_json": output,
        "stderr": _text(outcome.stderr, redact),
        "bytes": {
            "stdin": outcome.stdin.total,
            "stdout": outcome.stdout.total,
            "stderr": outcome.stderr.total,
        },
        "truncated": {
            "stdin": outcome.stdin.truncated,
            "stdout": outcome.stdout.truncated,
            "stderr": outcome.stderr.truncated,
        },
    }
    # 입력·인자·출력에서 온 모든 값(cwd·matcher·context·세션 id·결정 사유 등)을 가린다.
    # 이미 가린 텍스트를 다시 가려도 결과는 같다.
    return {k: v if k in PLAIN_FIELDS or v is None else redact(v) for k, v in record.items()}


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def record_file_name(session_id: str | None) -> str:
    """기록 파일 이름. 세션마다 한 파일(`<세션>.jsonl`, 세션이 없으면 `no-session.jsonl`).

    세션 id에 파일 이름으로 쓸 수 없는 글자가 있거나 너무 길면 해시로 바꾼다.
    """
    if not session_id:
        return "no-session.jsonl"
    if _UNSAFE.search(session_id) or len(session_id) > 96 or session_id.startswith("."):
        return "s-" + hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32] + ".jsonl"
    return session_id + ".jsonl"


def _lock(fd: int) -> Callable[[], None]:
    """파일 전체 잠금(여러 hook이 동시에 같은 파일에 덧붙일 때 줄이 섞이지 않게)."""
    if sys.platform == "win32":  # pragma: no cover - Windows 전용
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

        def unlock_nt() -> None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

        return unlock_nt
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX)
    return lambda: fcntl.flock(fd, fcntl.LOCK_UN)


def append_line(folder: Path, name: str, record: Mapping[str, Any]) -> Path:
    """`folder/name`에 JSON 한 줄을 덧붙인다(폴더가 없으면 만든다, 한 번의 write).

    Raises:
        OSError: 쓰기 실패(호출자가 삼킨다).
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    line = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        unlock = _lock(fd)
        try:
            view = memoryview(line)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        finally:
            unlock()
    finally:
        os.close(fd)
    return path
