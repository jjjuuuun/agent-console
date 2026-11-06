"""WS 토픽 ``memory.changed``(design §5.7R.5.2): 항목이 바뀔 때마다 ``memory.changed``(본문 없음).

구독 직후에는 아무것도 보내지 않는다(화면은 REST로 처음 불러오고, 이 알림이 오면 다시 불러온다).

저장소 쓰기는 스레드(REST 동기 처리기·``asyncio.to_thread``)에서도 일어나므로 발행은
``LoopPublisher``가 이벤트 루프 스레드로 옮긴다(허브 큐는 루프 스레드에서만 만진다).
``LoopPublisher``는 키트(``agent_console_modkit``) 것을 그대로 다시 내보낸다(7R.4).
"""

from __future__ import annotations

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
from agent_console_modkit import LoopPublisher as KitLoopPublisher

MEMORY_TOPIC: Final = "memory.changed"
"""WS 토픽 이름(정확히 일치)."""


LoopPublisher = KitLoopPublisher[MemoryChanged]
"""``MemoryChanged``용 키트 ``LoopPublisher``(옛 이름 그대로, 중복 검사 없음, 7R.4)."""


def changed_message(payload: MemoryChanged) -> MemoryChangedMessage:
    """변경 알림 → WS 메시지."""
    return MemoryChangedMessage(type="memory.changed", payload=payload)


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
