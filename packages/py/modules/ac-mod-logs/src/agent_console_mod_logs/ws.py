"""WS 토픽 ``logs``(design §4R.4·§4R.9 표 4): 수집으로 새 이벤트가 생길 때마다 ``logs.ingested``.

구독 직후에는 아무것도 보내지 않는다(목록 화면은 REST로 처음 불러오고, 이 알림이 오면
``max_seq``보다 큰 이벤트를 다시 불러온다).
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts.modules import LogsIngestedMessage, LogsIngestedPayload
from agent_console_modkit import (
    Hub,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)

LOGS_TOPIC = "logs"
"""WS 토픽 이름(정확히 일치)."""


def ingested_message(payload: LogsIngestedPayload) -> LogsIngestedMessage:
    return LogsIngestedMessage(type="logs.ingested", payload=payload)


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

    return {LOGS_TOPIC: handle}


__all__ = ["LOGS_TOPIC", "ingested_message", "topic_handlers"]
