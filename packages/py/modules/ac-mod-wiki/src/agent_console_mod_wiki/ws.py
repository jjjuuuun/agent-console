"""WS 토픽 ``wiki.changed``(design §7R.7).

페이지 쓰기·옮기기·지우기·되돌리기·가져오기·외부 변경 감지·위키 정의 저장 뒤에 낸다(본문 없음, 계약
``WikiChangedMessage``).

저장소(``WikiRepository``)는 알림을 내지 않는다. 모듈이 결과를 보고 키트 ``LoopPublisher``로 낸다
(REST 처리기·주기 검사 스레드에서 온 알림을 바인드한 이벤트 루프로 옮기고, 같은 묶음이 바로 이어
오면 한 번만). 미리보기·dry_run은 알리지 않는다. 구독 직후에는 아무것도 보내지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any, Final

from agent_console_contracts.modules import WikiChangedMessage
from agent_console_contracts.wiki import WikiChanged
from agent_console_modkit import (
    Hub,
    LoopPublisher,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)

WIKI_TOPIC: Final = "wiki.changed"
"""WS 토픽 이름(정확히 일치)."""


def changed_message(payload: WikiChanged) -> WikiChangedMessage:
    """변경 알림 → WS 메시지."""
    return WikiChangedMessage(type="wiki.changed", payload=payload)


def change_key(payload: WikiChanged) -> Hashable:
    """중복 판정 키: (공간, 위키, 경로들, 지움, 외부)."""
    return (
        payload.space.project_id,
        payload.wiki_id,
        tuple(payload.paths),
        payload.deleted,
        payload.external,
    )


def change_publisher(publish: Callable[[WikiChanged], None]) -> LoopPublisher[WikiChanged]:
    """``WikiChanged``를 ``publish``로 내는 발행기(같은 묶음 연속은 한 번)."""
    return LoopPublisher(publish, key=change_key)


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

    return {WIKI_TOPIC: handle}


__all__ = ["WIKI_TOPIC", "change_key", "change_publisher", "changed_message", "topic_handlers"]
