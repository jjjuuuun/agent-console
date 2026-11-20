"""배경 스레드 작업 문(`WorkGate`): 종료 훅이 진행 중인 스레드 작업을 기다리게 한다.

모듈은 막히는 일(수집·정리)을 ``asyncio.to_thread``로 돌린다. 배경 작업을 취소해도 이미 시작한
스레드는 끝까지 가므로, 종료 훅이 자원(DB·색인)을 닫는 동안 그 스레드가 닫힌 자원을 쓸 수 있다.
`WorkGate`는 스레드 작업 수를 세고, ``close()`` 뒤에는 새 작업 대신 ``stopped()`` 값을 돌려준다.
종료 훅은 ``await gate.close_and_wait(timeout)``으로 진행 중인 작업이 끝나기를 기다린 뒤 닫는다.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

DEFAULT_WORK_WAIT = 30.0
"""`WorkGate.close_and_wait`의 기본 기다림 상한(초)."""


class WorkGate:
    """스레드 작업 수 세기 + 닫힘 표시(스레드 안전).

    >>> gate = WorkGate()
    >>> gate.run(lambda: "done", lambda: "stopped")
    'done'
    >>> gate.close()
    >>> gate.run(lambda: "done", lambda: "stopped")
    'stopped'
    >>> gate.wait_idle(0)
    True
    >>> gate.reopen()
    >>> gate.closed
    False
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._busy = 0
        self._closed = False

    @property
    def closed(self) -> bool:
        """``close()`` 뒤인가(작업 안에서 남은 일을 멈출지 볼 때 쓴다)."""
        return self._closed

    @property
    def busy(self) -> int:
        """지금 진행 중인 작업 수."""
        with self._cond:
            return self._busy

    def run[T](self, fn: Callable[[], T], stopped: Callable[[], T] | None = None) -> T:
        """``fn``을 작업 하나로 세며 부른다(막히는 호출, 보통 스레드에서).

        닫힌 뒤에는 ``fn`` 대신 ``stopped()``를 돌려준다. ``stopped``가 없으면 닫힌 뒤에도
        ``fn``을 부른다(끝날 때까지 ``close_and_wait``가 기다린다).
        """
        with self._cond:
            if self._closed and stopped is not None:
                return stopped()
            self._busy += 1
        try:
            return fn()
        finally:
            with self._cond:
                self._busy -= 1
                self._cond.notify_all()

    def close(self) -> None:
        """새 작업을 받지 않는다(진행 중인 작업은 끝까지 간다). 여러 번 불러도 된다."""
        with self._cond:
            self._closed = True

    def reopen(self) -> None:
        """다시 작업을 받는다(모듈을 다시 시작할 때)."""
        with self._cond:
            self._closed = False

    def wait_idle(self, timeout: float) -> bool:
        """진행 중인 작업이 0이 될 때까지 최대 ``timeout``초 기다린다(막히는 호출). 참 = 0."""
        with self._cond:
            return self._cond.wait_for(lambda: self._busy == 0, timeout)

    async def close_and_wait(self, timeout: float = DEFAULT_WORK_WAIT) -> bool:
        """닫고 진행 중인 작업이 끝나기를 기다린다(이벤트 루프를 막지 않는다).

        Returns:
            상한 안에 모두 끝났으면 참(거짓이면 호출자가 경고를 남긴다).
        """
        self.close()
        if self.busy == 0:
            return True
        return await asyncio.to_thread(self.wait_idle, timeout)


__all__ = ["DEFAULT_WORK_WAIT", "WorkGate"]
