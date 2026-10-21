"""WS 토픽 문자열별 메시지 팬아웃(호스트 기본 서비스 ``ws_hub``, design §3R.1.2).

기능 모듈은 자기 WS 토픽(예: ``conversation:<id>``)의 "현재 상태 요약" 메시지를 여기로 발행하고,
``ModuleParts.ws_topics`` 처리기가 구독해 소켓으로 보낸다.

발행은 막히지 않는다(같은 이벤트 루프, `put_nowait`). 느린 구독자의 큐가 차면 그 메시지를 버리고
`dropped`를 센다. 이 토픽들은 "현재 상태 요약"이라 다음 메시지·재구독으로 따라잡는다.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class HubSubscription[T]:
    """구독 하나. `async for message in sub`. `close()`로 해제."""

    def __init__(self, hub: Hub[T], topic: str, maxsize: int) -> None:
        self._hub = hub
        self.topic = topic
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize)
        self.dropped = 0
        self.closed = False

    def offer(self, message: T) -> None:
        if self.closed:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self.dropped += 1

    async def get(self) -> T | None:
        """다음 메시지. 닫혔으면 None."""
        if self.closed and self._queue.empty():
            return None
        return await self._queue.get()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._hub._remove(self)
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[T]:
        while True:
            message = await self.get()
            if message is None:
                return
            yield message


class Hub[T]:
    """토픽 문자열 → 구독자 목록. 메시지 형식은 모른다."""

    def __init__(self, *, maxsize: int = 1000) -> None:
        self._subs: dict[str, list[HubSubscription[T]]] = {}
        self._maxsize = maxsize

    def subscribe(self, topic: str) -> HubSubscription[T]:
        sub = HubSubscription(self, topic, self._maxsize)
        self._subs.setdefault(topic, []).append(sub)
        return sub

    def publish(self, topic: str, message: T) -> None:
        for sub in list(self._subs.get(topic, ())):
            sub.offer(message)

    def _remove(self, sub: HubSubscription[T]) -> None:
        subs = self._subs.get(sub.topic)
        if subs is not None and sub in subs:
            subs.remove(sub)
            if not subs:
                del self._subs[sub.topic]

    def subscriber_count(self, topic: str | None = None) -> int:
        if topic is not None:
            return len(self._subs.get(topic, ()))
        return sum(len(v) for v in self._subs.values())


__all__ = ["Hub", "HubSubscription"]
