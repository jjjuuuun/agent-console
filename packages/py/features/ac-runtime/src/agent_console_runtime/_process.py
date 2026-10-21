"""프로세스 그룹 시작·종료 유틸(agent_bench `engine.terminate` 이식, 플랫폼 차이 처리).

노드·백엔드가 외부 프로세스를 띄울 때 `process_group_kwargs()`로 새 그룹(세션)을 만들고,
취소·종료 시 `terminate_process_group`(동기 `Popen`) 또는
`aterminate_process_group`(asyncio 하위 프로세스)으로 그룹 전체를 정리한다.

- POSIX: `start_new_session=True` → `killpg(SIGTERM)` → 유예 → `killpg(SIGKILL)`.
  리더가 이미 끝났어도 그룹에 남은 자식까지 정리한다(agent_bench 동작).
- Windows: `CREATE_NEW_PROCESS_GROUP` → `CTRL_BREAK_EVENT` → 유예 →
  `taskkill /T /F`(자식 트리 강제 종료) → 마지막으로 `kill()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
from typing import Any

DEFAULT_GRACE_SECONDS = 2.0
"""SIGTERM(또는 CTRL_BREAK) 후 강제 종료까지 기다리는 기본 시간."""


def process_group_kwargs() -> dict[str, Any]:
    """`subprocess.Popen`·`asyncio.create_subprocess_exec`에 넘길 새 프로세스 그룹 인자."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_group(
    process: subprocess.Popen[Any] | None, *, grace: float = DEFAULT_GRACE_SECONDS
) -> None:
    """`process`가 이끄는 프로세스 그룹을 종료한다(동기, 최대 약 grace의 두 배 대기).

    `process_group_kwargs()`로 시작한 프로세스여야 그룹 전체가 정리된다. None이거나
    이미 정리된 프로세스면 아무 일도 하지 않는다. 예외를 던지지 않는다.
    """
    if process is None:
        return
    if sys.platform == "win32":
        _soft_stop_windows(process)
        _wait(process, grace)
        _kill_tree_windows(process.pid)
        with contextlib.suppress(OSError):
            process.kill()
        _wait(process, grace)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    _wait(process, grace)
    # 리더가 이미 끝났어도 그룹에 남은 프로세스를 정리한다.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    _wait(process, grace)


async def aterminate_process_group(
    process: asyncio.subprocess.Process | None, *, grace: float = DEFAULT_GRACE_SECONDS
) -> None:
    """`terminate_process_group`의 asyncio 하위 프로세스판. 이벤트 루프를 막지 않는다."""
    if process is None:
        return
    if sys.platform == "win32":
        _soft_stop_windows(process)
        await _await_exit(process, grace)
        await asyncio.to_thread(_kill_tree_windows, process.pid)
        with contextlib.suppress(OSError):
            process.kill()
        await _await_exit(process, grace)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    await _await_exit(process, grace)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    await _await_exit(process, grace)


def _wait(process: subprocess.Popen[Any], timeout: float) -> None:
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=timeout)


async def _await_exit(process: asyncio.subprocess.Process, timeout: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout)


def _soft_stop_windows(process: subprocess.Popen[Any] | asyncio.subprocess.Process) -> None:
    if sys.platform == "win32":
        with contextlib.suppress(OSError, ValueError):
            process.send_signal(signal.CTRL_BREAK_EVENT)


def _kill_tree_windows(pid: int) -> None:
    if sys.platform == "win32":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
                check=False,
            )
