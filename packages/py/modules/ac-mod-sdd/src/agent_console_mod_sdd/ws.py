"""WS 토픽 ``sdd.changed``(design §6R.7): 스펙 저장·작업 고치기·외부 변경·자동 진행 상태 변화 뒤
``sdd.changed``(본문 없음, 계약 ``SddChangedMessage``).

구독 직후에는 아무것도 보내지 않는다(화면은 REST로 처음 불러오고, 이 알림이 오면 다시 불러온다).
발행은 다른 스레드(공간 저장 알림 등)에서도 올 수 있어 ``bind``한 이벤트 루프 스레드로 옮긴다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from agent_console_contracts.modules import SddChangedMessage
from agent_console_contracts.sdd import SddChanged
from agent_console_modkit import (
    Hub,
    LoopPublisher,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)

SDD_TOPIC: Final = "sdd.changed"
"""WS 토픽 이름(정확히 일치)."""


def changed_message(payload: SddChanged) -> SddChangedMessage:
    """변경 알림 → WS 메시지."""
    return SddChangedMessage(type="sdd.changed", payload=payload)


def change_key(payload: SddChanged) -> tuple[Any, ...] | None:
    """중복 판정 키: (공간, 스펙, 버전, 자동 진행, 삭제). 자동 진행 알림은 늘 낸다(None)."""
    if payload.automation:
        return None
    return (
        payload.space.project_id,
        payload.spec_id,
        payload.version_hash,
        payload.automation,
        payload.deleted,
    )


class ChangePublisher(LoopPublisher[SddChanged]):
    """``SddChanged``를 허브에 낸다. 같은 알림이 바로 이어 오면 한 번만 낸다(모듈 쓰기 + 저장소
    저장 알림이 같은 변경을 두 번 알릴 수 있다). 키트 ``LoopPublisher``에 ``change_key``를 묶은 것
    (7R.4).

    Args:
        publish: 루프 스레드에서 부를 발행 함수(예: 허브 ``publish``).
    """

    def __init__(self, publish: Callable[[SddChanged], None]) -> None:
        super().__init__(publish, key=change_key)


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

    return {SDD_TOPIC: handle}


__all__ = ["SDD_TOPIC", "ChangePublisher", "change_key", "changed_message", "topic_handlers"]
