"""상호작용 조회·응답·알림(``interactions.port``, design §R14.4·§R14.5).

로직은 엔진(``GraphRuntime.respond``)과 저장소에 있다. 여기서는 그것을 잇고, 상호작용이 열리거나
닫히면 WS 허브 토픽(``interactions``)과 모듈 토픽(``interactions.updated``)으로 알린다.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol

from agent_console_contracts import (
    Interaction,
    InteractionStatus,
    InteractionUpdatedMessage,
    InteractionUpdatedPayload,
    RunEvent,
)
from agent_console_modkit import Hub

INTERACTIONS_TOPIC = "interactions"
"""WS 전역 토픽: 대기 상호작용 변화(``interaction.updated``)."""

INTERACTION_EVENT_PREFIX = "interaction."
"""상호작용이 바뀐 실행 이벤트 형식 접두."""

_log = logging.getLogger("agent_console_mod_runs")


class InteractionStore(Protocol):
    """저장소 상호작용 리포지토리의 쓰는 부분."""

    def get(self, interaction_id: str) -> Interaction | None: ...

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> list[Interaction]: ...


class Responder(Protocol):
    """엔진의 응답 경로(``GraphRuntime.respond``)."""

    async def respond(
        self,
        run_id: str,
        interaction_id: str,
        response: Mapping[str, Any],
        *,
        by: str = "user",
    ) -> Interaction: ...


def interaction_id_of(event: RunEvent) -> str | None:
    """``interaction.*`` 이벤트의 상호작용 id.

    ``payload.interaction_id`` 또는 ``payload.interaction.id``(없으면 None).
    """
    found = event.payload.get("interaction_id")
    if found is None:
        nested = event.payload.get("interaction")
        found = nested.get("id") if isinstance(nested, Mapping) else None
    return found if isinstance(found, str) else None


class InteractionService:
    """상호작용 조회·응답과 알림.

    Args:
        store: 저장소 상호작용 리포지토리.
        responder: 엔진 응답 경로.
        hub: WS 허브(``interactions`` 토픽에 ``InteractionUpdatedMessage``).
        notify: 모듈 토픽 발행 함수(``interactions.updated``).
    """

    def __init__(
        self,
        store: InteractionStore,
        responder: Responder,
        *,
        hub: Hub[Any] | None = None,
        notify: Callable[[Interaction], None] = lambda _i: None,
    ) -> None:
        self._store = store
        self._responder = responder
        self._hub = hub
        self._notify = notify

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
        root_run_id: str | None = None,
    ) -> list[Interaction]:
        """조건에 맞는 상호작용(오래된 순). ``root_run_id`` = 그 Run과 아래 모든 자식 Run의 것
        (루트 기준으로 모으기, design §5R.11)."""
        return self._store.list(
            run_id=run_id, conversation_id=conversation_id, status=status, root_run_id=root_run_id
        )

    def get(self, interaction_id: str) -> Interaction | None:
        return self._store.get(interaction_id)

    def pending(self) -> builtins.list[Interaction]:
        """대기 중인 상호작용(오래된 순)."""
        return self._store.list(status="pending")

    async def respond(
        self,
        run_id: str,
        interaction_id: str,
        response: Mapping[str, Any],
        *,
        by: str = "user",
    ) -> Interaction:
        """응답한다(엔진이 검증·닫기). 동시에 답하면 하나만 성공한다.

        Raises:
            UnknownInteractionError: 없다.
            InteractionClosedError: 이미 닫혔다.
            ResponseValidationError: 응답 형식 오류.
        """
        return await self._responder.respond(run_id, interaction_id, response, by=by)

    def publish(self, interaction: Interaction) -> None:
        """WS ``interactions`` 토픽과 모듈 토픽 ``interactions.updated``로 알린다."""
        if self._hub is not None:
            self._hub.publish(
                INTERACTIONS_TOPIC,
                InteractionUpdatedMessage(
                    type="interaction.updated",
                    payload=InteractionUpdatedPayload(interaction=interaction),
                ),
            )
        self._notify(interaction)

    def on_event(self, event: RunEvent) -> None:
        """실행 이벤트 하나를 본다: ``interaction.*``이면 저장본을 읽어 알린다."""
        if not event.type.startswith(INTERACTION_EVENT_PREFIX):
            return
        interaction_id = interaction_id_of(event)
        stored = self._store.get(interaction_id) if interaction_id is not None else None
        if stored is not None:
            self.publish(stored)


__all__ = [
    "INTERACTIONS_TOPIC",
    "INTERACTION_EVENT_PREFIX",
    "InteractionService",
    "InteractionStore",
    "Responder",
    "interaction_id_of",
]
