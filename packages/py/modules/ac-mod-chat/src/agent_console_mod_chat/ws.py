"""WS 토픽 ``conversation:<id>``(design §5.3, §R5.1): 구독 직후 현재 요약을 한 번 보내고, 이후 바뀔
때마다 ``conversation.updated``(새 턴·제목·상태·대기열·대기 상호작용 수). 대화가 없으면
``not_found``.

대화 id만 받으므로(구독에 ``?project=``가 없다) 서비스의 선택 메서드 ``service_of``가 그 대화를 가진
공간을 찾는다. 아직 이 프로세스에서 열지 않은 프로젝트 기록 DB의 대화도 ``locate``로 찾는다(요청
11/07 후속, 디스크를 읽으므로 작업 스레드에서).
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_console_chat import ChatService, ConversationNotFoundError
from agent_console_contracts import (
    ConversationSummary,
    ConversationUpdatedMessage,
    ConversationUpdatedPayload,
    ErrorCodes,
)
from agent_console_modkit import (
    Hub,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)

CONVERSATION_TOPIC = "conversation"
"""WS 토픽 접두: ``conversation:<id>`` → ``conversation.updated``."""


def conversation_topic(conversation_id: str) -> str:
    return f"{CONVERSATION_TOPIC}:{conversation_id}"


def updated_message(summary: ConversationSummary) -> ConversationUpdatedMessage:
    return ConversationUpdatedMessage(
        type="conversation.updated",
        payload=ConversationUpdatedPayload(conversation=summary),
    )


def topic_handlers(service: ChatService, *, hub: Hub[Any]) -> dict[str, WsTopicHandler]:
    """이 모듈의 WS 토픽 처리기(키가 ``:``로 끝나면 접두).

    대화 서비스에 선택 메서드 ``service_of``(대화 id → 그 대화를 가진 서비스, 프로젝트 기록 공간
    포함 - 5.7R.33y2)가 있으면 그것으로 찾는다."""

    async def owner(conversation_id: str) -> ChatService:
        method = getattr(service, "service_of", None)
        if not callable(method):
            return service
        found: ChatService = await asyncio.to_thread(method, conversation_id)
        return found

    async def handle(req: WsSubscribeRequest) -> WsForward | WsReject | None:
        chat = await owner(req.target)
        try:
            chat.get(req.target)
        except ConversationNotFoundError:
            return WsReject(ErrorCodes.NOT_FOUND, "대화가 없습니다")

        async def forward(send: WsSend) -> None:
            sub = hub.subscribe(req.topic)  # 현재 요약을 보내기 전에 연다(경합 없음)
            try:
                await send(updated_message(chat.summary(req.target)))
                async for message in sub:
                    await send(message)
            finally:
                sub.close()

        return forward

    return {f"{CONVERSATION_TOPIC}:": handle}


__all__ = ["CONVERSATION_TOPIC", "conversation_topic", "topic_handlers", "updated_message"]
