"""명령형 hook 전달(design §2R.8): 실행 묶음 `hooks` 칸 항목 → SDK 훅 콜백 또는 `settings` JSON.

- **callback**(기본, 확인된 경로): 항목마다 SDK `HookMatcher(matcher, hooks=[콜백], timeout)`를
  이벤트 이름 아래 건다. 콜백은 명령을 **실행 범위 검사(`ToolGuard.check_command`) 뒤에만** 셸 없이
  하위 프로세스로 돌린다. 입력 = hook 입력 JSON(stdin), 출력 = stdout JSON(있으면 그대로 SDK에
  돌려줌).
  종료 코드 2는 막기(`{"decision": "block", "reason": stderr}`), 그 밖의 0 아닌 코드는 막지 않는
  오류다. 실행마다 `hook.started` → `hook.finished{event, matcher, command_preview, exit_code,
  duration_ms, decision}`를 낸다.
- **settings**(미확인 경로, C1): 명령형 hook 설정을 `settings` 인라인 JSON으로 CLI에 넘긴다. CLI가
  직접 실행하므로 콜백 검사가 없다 — 그래서 넘기기 전에 명령을 실행 범위로 한 번 검사하고 걸리는
  항목은 빼고 경고한다.

이벤트 이름은 항목의 문자열 그대로다(목록 고정 없음). 하위 프로세스 실행은 `HookRunner`로 주입한다.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agent_console_contracts import LogWarningPayload
from agent_console_runtime import BackendEventSink

from ._guard import ToolGuard

__all__ = [
    "BLOCK_EXIT_CODE",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "HookProcess",
    "HookRunner",
    "HookSpec",
    "command_hook",
    "hook_decision",
    "hook_env",
    "hook_settings_json",
    "parse_hooks",
    "subprocess_runner",
]

DEFAULT_HOOK_TIMEOUT_SECONDS = 60.0
"""항목에 `timeout_seconds`가 없을 때 쓰는 시간 제한(설정 `hook_timeout_seconds`로 바꾼다)."""

BLOCK_EXIT_CODE = 2
"""막기로 보는 종료 코드(Claude Code hook 규약)."""

PREVIEW_CHARS = 200
"""이벤트에 싣는 명령 미리보기 길이."""


@dataclass(frozen=True, slots=True)
class HookSpec:
    """`hooks` 칸 항목 하나."""

    name: str
    event: str
    command: str
    matcher: str | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class HookProcess:
    """하위 프로세스 결과. 시간 초과면 `exit_code=None`, `timed_out=True`."""

    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False


class HookRunner(Protocol):
    """명령 실행기(테스트에서 가짜로 바꾼다)."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes,
        cwd: str | None,
        env: Mapping[str, str],
        timeout: float,
    ) -> Awaitable[HookProcess]: ...


async def subprocess_runner(
    argv: Sequence[str],
    *,
    stdin: bytes,
    cwd: str | None,
    env: Mapping[str, str],
    timeout: float,
) -> HookProcess:
    """기본 실행기: 셸 없이(`create_subprocess_exec`) 돌리고 시간이 넘으면 죽인다."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=dict(env),
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return HookProcess(exit_code=None, timed_out=True)
    return HookProcess(exit_code=proc.returncode, stdout=out, stderr=err)


def parse_hooks(items: Sequence[Any]) -> tuple[list[HookSpec], list[LogWarningPayload]]:
    """`hooks` 칸 항목 → `HookSpec` 목록. 모양이 틀린 항목은 빼고 경고(값은 싣지 않음)."""
    specs: list[HookSpec] = []
    warnings: list[LogWarningPayload] = []
    for index, item in enumerate(items):
        event = item.get("event") if isinstance(item, Mapping) else None
        command = item.get("command") if isinstance(item, Mapping) else None
        if not isinstance(event, str) or not event or not isinstance(command, str) or not command:
            warnings.append(
                LogWarningPayload(
                    message="hooks 칸 항목에 event·command가 없어 전달하지 않습니다",
                    details={"slot": "hooks", "index": index},
                )
            )
            continue
        assert isinstance(item, Mapping)
        matcher = item.get("matcher")
        timeout = item.get("timeout_seconds")
        name = item.get("name")
        specs.append(
            HookSpec(
                name=name if isinstance(name, str) and name else f"hook-{index}",
                event=event,
                command=command,
                matcher=matcher if isinstance(matcher, str) and matcher else None,
                timeout_seconds=(
                    float(timeout)
                    if isinstance(timeout, int | float) and not isinstance(timeout, bool)
                    else None
                ),
            )
        )
    return specs, warnings


def hook_env(
    parent: Mapping[str, str], allows: Callable[[str], bool], cwd: str | None
) -> dict[str, str]:
    """hook 하위 프로세스 환경: 정책이 허용하는 부모 키만 + `CLAUDE_PROJECT_DIR`(작업 폴더).
    인증 키 등 백엔드가 CLI에 명시로 넘기는 값은 넣지 않는다."""
    env = {k: v for k, v in parent.items() if allows(k)}
    if cwd:
        env["CLAUDE_PROJECT_DIR"] = cwd
    return env


def hook_decision(output: Any) -> str | None:
    """hook 출력의 결정(`decision` 또는 `hookSpecificOutput.permissionDecision`)."""
    if not isinstance(output, Mapping):
        return None
    decision = output.get("decision")
    if isinstance(decision, str):
        return decision
    specific = output.get("hookSpecificOutput")
    if isinstance(specific, Mapping) and isinstance(specific.get("permissionDecision"), str):
        return str(specific["permissionDecision"])
    return None


def _argv(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def command_hook(
    spec: HookSpec,
    *,
    guard: ToolGuard,
    runner: HookRunner,
    sink: BackendEventSink,
    mask: Callable[[str], str],
    env: Mapping[str, str],
    cwd: str | None,
    default_timeout: float = DEFAULT_HOOK_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    wrap: Callable[[list[str], str | None], list[str]] | None = None,
) -> Callable[[Any, str | None, Any], Awaitable[dict[str, Any]]]:
    """SDK 훅 콜백 하나(`HookCallback` 모양: `(input, tool_use_id, context) -> HookJSONOutput`).

    Args:
        spec: hook 항목.
        guard: 실행 범위 검사기(명령 허용 목록). 걸리면 실행하지 않는다.
        runner: 하위 프로세스 실행기.
        sink: `hook.started`·`hook.finished`·`log.warning`을 낼 곳.
        mask: 비밀 가리기(명령 미리보기·막기 사유).
        env, cwd: 하위 프로세스 환경·작업 폴더.
        default_timeout: 항목에 시간 제한이 없을 때.
        clock: 소요 시간 측정.
        wrap: 실행 인자 감싸기(`(argv, matcher) -> argv`, 예: hook probe). 실행 범위 검사는 원래
            명령으로 한다. None이면 그대로 실행.
    """
    preview = mask(spec.command)[:PREVIEW_CHARS]
    base: dict[str, Any] = {
        "event": spec.event,
        "matcher": spec.matcher,
        "command_preview": preview,
        "hook_type": "command",
        "name": spec.name,
    }
    if wrap is not None:
        base["hook_probe"] = True
    timeout = spec.timeout_seconds or default_timeout

    async def emit(type_: str, extra: Mapping[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await sink.emit(type_, {**base, **extra})

    async def callback(input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        reason = guard.check_command(spec.command)
        if reason is not None:
            await emit(
                "hook.finished",
                {"exit_code": None, "duration_ms": 0, "decision": None, "error": "limits"},
            )
            with contextlib.suppress(Exception):
                await sink.emit(
                    "log.warning",
                    LogWarningPayload(
                        message=f"실행 범위 제한으로 hook 명령을 실행하지 않았습니다: {reason}",
                        details={"hook": spec.name, "event": spec.event},
                    ),
                )
            return {}
        try:
            argv = _argv(spec.command)
        except ValueError:
            argv = []
        if not argv:
            await emit(
                "hook.finished",
                {"exit_code": None, "duration_ms": 0, "decision": None, "error": "invalid"},
            )
            return {}
        if wrap is not None:
            argv = wrap(argv, spec.matcher)
        payload = dict(input_data) if isinstance(input_data, Mapping) else {}
        stdin = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        await emit("hook.started", {"tool_use_id": tool_use_id} if tool_use_id else {})
        started = clock()
        try:
            result = await runner(argv, stdin=stdin, cwd=cwd, env=env, timeout=timeout)
        except OSError as exc:
            await emit(
                "hook.finished",
                {
                    "exit_code": None,
                    "duration_ms": int((clock() - started) * 1000),
                    "decision": None,
                    "error": type(exc).__name__,
                },
            )
            return {}
        duration = int((clock() - started) * 1000)
        output: dict[str, Any] = {}
        if result.exit_code == 0:
            with contextlib.suppress(ValueError, UnicodeDecodeError):
                parsed = json.loads(result.stdout.decode("utf-8")) if result.stdout.strip() else {}
                if isinstance(parsed, dict):
                    output = parsed
        elif result.exit_code == BLOCK_EXIT_CODE:
            text = result.stderr.decode("utf-8", errors="replace").strip()
            output = {"decision": "block", "reason": mask(text) or "hook이 막았습니다"}
        finished: dict[str, Any] = {
            "exit_code": result.exit_code,
            "duration_ms": duration,
            "decision": hook_decision(output),
        }
        if result.timed_out:
            finished["error"] = "timeout"
        await emit("hook.finished", finished)
        return output

    return callback


def hook_settings_json(
    specs: Sequence[HookSpec],
    *,
    guard: ToolGuard,
    default_timeout: float,
    wrap_line: Callable[[str, str | None], str] | None = None,
) -> tuple[str | None, list[LogWarningPayload]]:
    """`settings` 전달용 인라인 JSON(`{"hooks": {이벤트: [{matcher, hooks: [command]}]}}`).

    CLI가 직접 실행하므로 명령을 실행 범위로 미리 검사해 걸리는 항목은 빼고 경고한다.
    `wrap_line`(`(command, matcher) -> command`, 예: hook probe)을 주면 검사를 통과한 명령을 감싼
    한 줄로 넘긴다(검사는 원래 명령으로).
    """
    events: dict[str, list[dict[str, Any]]] = {}
    warnings: list[LogWarningPayload] = []
    for spec in specs:
        reason = guard.check_command(spec.command)
        if reason is not None:
            warnings.append(
                LogWarningPayload(
                    message=f"실행 범위 제한으로 hook을 전달하지 않습니다: {reason}",
                    details={"hook": spec.name, "event": spec.event},
                )
            )
            continue
        entry: dict[str, Any] = {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        wrap_line(spec.command, spec.matcher) if wrap_line else spec.command
                    ),
                    "timeout": spec.timeout_seconds or default_timeout,
                }
            ]
        }
        if spec.matcher:
            entry["matcher"] = spec.matcher
        events.setdefault(spec.event, []).append(entry)
    if not events:
        return None, warnings
    return json.dumps({"hooks": events}, ensure_ascii=False), warnings
