"""취소 토큰: Run 취소를 실행 중 노드와 백엔드에 전파한다."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

_log = logging.getLogger(__name__)


class OperationCancelledError(Exception):
    """취소 토큰이 취소된 뒤 작업을 계속하려 할 때 `CancelToken.raise_if_cancelled`가 던진다."""


class CancelToken:
    """한 번만 취소되는 협조적 취소 신호.

    - 노드는 `cancelled`를 확인하거나 `await wait()`로 취소를 기다린다.
    - 백엔드는 `on_cancel(callback)`으로 프로세스 종료 같은 정리 동작을 건다
      (예: `lambda: terminate_process_group(proc)`).
    - 엔진은 취소 후 `cancel_grace`초 안에 끝나지 않은 노드 태스크를 asyncio 취소한다.

    스레드 안전하지 않다. 같은 이벤트 루프에서 쓴다.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str | None = None
        self._callbacks: list[Callable[[], object]] = []

    @property
    def cancelled(self) -> bool:
        """취소되었으면 참."""
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        """취소 사유(취소 전에는 None)."""
        return self._reason

    def cancel(self, reason: str = "cancelled") -> bool:
        """취소한다. 처음 취소면 True, 이미 취소됐으면 False.

        등록된 콜백을 등록 순서대로 호출한다. 콜백 예외는 기록만 하고 다음 콜백으로 넘어간다.
        """
        if self._event.is_set():
            return False
        self._reason = reason
        self._event.set()
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            _run_callback(callback)
        return True

    def on_cancel(self, callback: Callable[[], object]) -> Callable[[], None]:
        """취소 시 호출할 콜백을 건다. 이미 취소됐으면 즉시 호출한다.

        Returns:
            콜백 등록을 해제하는 함수(작업이 정상 종료됐을 때 호출).
        """
        if self._event.is_set():
            _run_callback(callback)
            return _noop
        self._callbacks.append(callback)

        def unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unregister

    async def wait(self) -> None:
        """취소될 때까지 기다린다."""
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        """취소됐으면 `OperationCancelledError`."""
        if self._event.is_set():
            raise OperationCancelledError(self._reason or "cancelled")


def _run_callback(callback: Callable[[], object]) -> None:
    try:
        callback()
    except Exception:
        _log.exception("취소 콜백 실패")


def _noop() -> None:
    return None
