"""명령 실행기: 셸 없이 인자 목록으로 실행, 시간 상한·중단 신호(네이티브 폴더 선택 창용)."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

__all__ = [
    "CancelSignal",
    "CommandOutcome",
    "CommandRunner",
    "SubprocessRunner",
]


class CancelSignal(Protocol):
    """중단 신호(`threading.Event`가 그대로 맞는다)."""

    def is_set(self) -> bool:
        """참이면 실행 중인 명령을 끝낸다."""
        ...


@dataclass(frozen=True)
class CommandOutcome:
    """명령 실행 결과.

    Attributes:
        exit_code: 종료 코드. 시간 초과·중단으로 끝낸 경우에도 끝난 뒤 코드(없으면 `None`).
        stdout: 표준 출력 바이트.
        stderr: 표준 오류 바이트.
        timed_out: 시간 상한에 걸려 프로세스를 끝냈는가.
        cancelled: 중단 신호로 프로세스를 끝냈는가.
    """

    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    cancelled: bool = False


class CommandRunner(Protocol):
    """명령 실행기(주입). 실제는 `SubprocessRunner`, 테스트는 가짜.

    셸을 쓰지 않는다. 실행 파일이 없으면 `FileNotFoundError`, 그 밖의 시작 실패는 `OSError`를 낸다.
    시간 상한이 지나거나 `cancel`이 켜지면 프로세스를 끝내고 `timed_out`/`cancelled`를
    표시해 돌려준다.
    """

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
        cancel: CancelSignal | None = None,
    ) -> CommandOutcome:
        """`argv`를 실행한다. `env`는 실행기의 기본 환경에 더할 값이다."""
        ...


class SubprocessRunner:
    """`subprocess`로 실제 명령을 실행한다(`shell=False`, 표준 입력 없음).

    Args:
        base_env: 자식 프로세스 기본 환경. `None`이면 실행할 때의 `os.environ`.
        poll_interval: 중단 신호 확인 간격(초).
        no_console_window: Windows에서 콘솔 창을 만들지 않는다(GUI 창은 그대로 뜬다).
    """

    def __init__(
        self,
        *,
        base_env: Mapping[str, str] | None = None,
        poll_interval: float = 0.2,
        no_console_window: bool = True,
    ) -> None:
        self._base_env = base_env
        self._poll = max(0.01, poll_interval)
        self._no_window = no_console_window

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
        cancel: CancelSignal | None = None,
    ) -> CommandOutcome:
        """명령을 실행하고 끝날 때까지(또는 시간 상한·중단까지) 기다린다."""
        if not argv:
            raise ValueError("argv가 비어 있습니다")
        base = os.environ if self._base_env is None else self._base_env
        child_env = {**base, **env}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if self._no_window else 0
        proc = subprocess.Popen(  # 셸 없이 인자 목록으로 실행한다
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            shell=False,
            creationflags=flags,
        )
        remaining = max(0.0, timeout)
        timed_out = cancelled = False
        while True:
            step = min(self._poll, remaining)
            try:
                out, err = proc.communicate(timeout=step if step > 0 else 0.001)
                break
            except subprocess.TimeoutExpired:
                remaining -= step
                if cancel is not None and cancel.is_set():
                    cancelled = True
                elif remaining <= 0:
                    timed_out = True
                if timed_out or cancelled:
                    proc.kill()
                    out, err = proc.communicate()
                    break
        return CommandOutcome(
            exit_code=proc.returncode,
            stdout=out or b"",
            stderr=err or b"",
            timed_out=timed_out,
            cancelled=cancelled,
        )
