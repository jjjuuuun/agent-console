"""메모리 이벤트 버스: `EventSink` 구현 + 구독(WS 팬아웃·콘솔 세션용)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable

from agent_console_contracts import RunEvent

type EventFilter = Callable[[RunEvent], bool]


class Subscription:
    """구독 하나. `async for event in sub` 또는 `await sub.get()`. `close()`로 해제."""

    def __init__(self, bus: InMemoryEventBus, accept: EventFilter, maxsize: int) -> None:
        self._bus = bus
        self._accept = accept
        self._queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize)
        self.dropped = 0
        """큐가 가득 차 버려진 이벤트 수(느린 구독자는 `since_seq` 재생으로 따라잡는다)."""
        self.closed = False

    def _offer(self, event: RunEvent) -> None:
        if self.closed or not self._accept(event):
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1

    async def get(self) -> RunEvent | None:
        """다음 이벤트. 닫혔으면 None."""
        if self.closed and self._queue.empty():
            return None
        return await self._queue.get()

    def close(self) -> None:
        """구독을 해제한다. 기다리던 `get`은 None을 받는다."""
        if self.closed:
            return
        self.closed = True
        self._bus._remove(self)
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

    def __aiter__(self) -> AsyncIterator[RunEvent]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[RunEvent]:
        while True:
            event = await self.get()
            if event is None:
                return
            yield event


class InMemoryEventBus:
    """프로세스 안 이벤트 버스. `publish`는 막히지 않는다(같은 이벤트 루프에서 쓴다)."""

    def __init__(self, *, maxsize: int = 10_000) -> None:
        self._subs: list[Subscription] = []
        self._maxsize = maxsize

    def publish(self, event: RunEvent) -> None:
        """모든 구독자에게 전달한다."""
        for sub in list(self._subs):
            sub._offer(event)

    def subscribe(
        self, *, run_id: str | None = None, accept: EventFilter | None = None
    ) -> Subscription:
        """구독을 만든다. `run_id`를 주면 그 Run의 이벤트만, `accept`로 더 거를 수 있다."""

        def match(event: RunEvent) -> bool:
            if run_id is not None and event.run_id != run_id:
                return False
            return accept(event) if accept is not None else True

        sub = Subscription(self, match, self._maxsize)
        self._subs.append(sub)
        return sub

    def _remove(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    @property
    def subscriber_count(self) -> int:
        """현재 구독자 수."""
        return len(self._subs)
