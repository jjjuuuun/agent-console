"""``runs.event`` → 수집 예약(디바운스, design §4R.4 "디바운스 1초").

이벤트가 오면 그 Run을 표시하고, 창(``delay`` 초)이 열려 있지 않으면 연다. 창이 닫힐 때 표시된
Run들을 한 번에 넘긴다. 이벤트가 계속 와도 창은 처음 이벤트에서 ``delay`` 뒤에 닫힌다(실행이 길어도
수집이 미뤄지지 않는다). 실행 중인 이벤트 루프가 없거나 ``delay``가 0이면 바로 넘긴다.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Collection

__all__ = ["ScanDebouncer"]


class ScanDebouncer:
    """Run 표시를 모아 ``flush(run_ids)``를 부른다.

    Args:
        flush: 모은 Run id들을 받는 함수(막히지 않아야 한다 — 예: ``logs.ingest.request_scan``).
        delay: 창 길이(초). 0이면 모으지 않는다.
    """

    def __init__(self, flush: Callable[[Collection[str]], None], *, delay: float) -> None:
        if delay < 0:
            raise ValueError("delay는 0 이상이어야 합니다")
        self._flush = flush
        self._delay = delay
        self._pending: set[str] = set()
        self._handle: asyncio.TimerHandle | None = None
        self._closed = False
        self._lock = threading.Lock()

    @property
    def pending(self) -> frozenset[str]:
        """아직 넘기지 않은 Run id."""
        with self._lock:
            return frozenset(self._pending)

    def mark(self, run_id: str) -> None:
        """Run 하나를 표시한다(어느 스레드에서든)."""
        if not run_id:
            return
        with self._lock:
            if self._closed:
                return
            self._pending.add(run_id)
            if self._handle is not None:
                return
            loop = _running_loop()
            if loop is not None and self._delay > 0:
                self._handle = loop.call_later(self._delay, self.fire)
                return
        self.fire()

    def fire(self) -> None:
        """표시된 Run을 지금 넘긴다."""
        with self._lock:
            ids = self._pending
            self._pending = set()
            self._handle = None
        if ids:
            self._flush(ids)

    def close(self) -> None:
        """창을 닫고 표시를 버린다(종료)."""
        with self._lock:
            self._closed = True
            if self._handle is not None:
                self._handle.cancel()
                self._handle = None
            self._pending.clear()


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
