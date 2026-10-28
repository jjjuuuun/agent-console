"""WS 토픽 ``memory.changed``(design §5.7R.5.2): 항목이 바뀔 때마다 ``memory.changed``(본문 없음).

구독 직후에는 아무것도 보내지 않는다(화면은 REST로 처음 불러오고, 이 알림이 오면 다시 불러온다).

저장소 쓰기는 스레드(REST 동기 처리기·``asyncio.to_thread``)에서도 일어나므로 발행은
``LoopPublisher``가 이벤트 루프 스레드로 옮긴다(허브 큐는 루프 스레드에서만 만진다).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Final

from agent_console_contracts.memory import MemoryChanged
from agent_console_contracts.modules import MemoryChangedMessage
from agent_console_modkit import (
    Hub,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)

MEMORY_TOPIC: Final = "memory.changed"
"""WS 토픽 이름(정확히 일치)."""


def changed_message(payload: MemoryChanged) -> MemoryChangedMessage:
    """변경 알림 → WS 메시지."""
    return MemoryChangedMessage(type="memory.changed", payload=payload)


class LoopPublisher:
    """다른 스레드에서 부른 발행을 이벤트 루프 스레드로 옮긴다.

    ``bind(loop)`` 전이거나 루프가 닫혔으면 바로 부른다(단독 라이브러리 사용·테스트).

    Args:
        publish: 루프 스레드에서 부를 발행 함수.
    """

    def __init__(self, publish: Callable[[MemoryChanged], None]) -> None:
        self._publish = publish
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """발행을 옮길 루프(None = 풀기)."""
        self._loop = loop

    def __call__(self, payload: MemoryChanged) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            self._publish(payload)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._publish(payload)
        else:
            loop.call_soon_threadsafe(self._publish, payload)


def topic_handlers(*, hub: Hub[Any]) -> dict[str, WsTopicHandler]:
    """이 모듈의 WS 토픽 처리기."""

    async def handle(req: WsSubscribeRequest) -> WsForward | WsReject | None:
        async def forward(send: WsSend) -> None:
            sub = hub.subscribe(req.topic)
            try:
                async for message in sub:
                    await send(message)
            finally:
                sub.close()

        return forward

    return {MEMORY_TOPIC: handle}


__all__ = ["MEMORY_TOPIC", "LoopPublisher", "changed_message", "topic_handlers"]
