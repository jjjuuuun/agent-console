"""WS 토픽 처리기(design §5.3, §R14.4): ``run:<id>``·``interactions``.

- ``run:<id>``: 버스 구독을 먼저 연 뒤 저장소에서 ``since_seq`` 다음을 재생하고, seq로 중복을
  버린다.
  실시간 이벤트에 빈 seq가 보이면(느린 구독자라 버려짐) 저장소에서 메운다(저장 후 발행 원칙).
- ``interactions``(전역): 허브 구독을 먼저 연 뒤 현재 대기 목록을 ``interaction.updated``로 하나씩
  보내고, 이후 상태가 바뀔 때마다 보낸다(재구독하면 대기 목록을 다시 보낸다).
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts import (
    ErrorCodes,
    InteractionUpdatedMessage,
    InteractionUpdatedPayload,
    RunEvent,
    RunEventMessage,
)
from agent_console_modkit import (
    Hub,
    WsForward,
    WsReject,
    WsSend,
    WsSubscribeRequest,
    WsTopicHandler,
)
from agent_console_runtime import InMemoryEventBus

from .interactions import INTERACTIONS_TOPIC, InteractionService
from .service import RunService

RUN_TOPIC = "run"
"""WS 토픽 접두: ``run:<id>`` → ``run.event``."""


def topic_handlers(
    service: RunService,
    *,
    bus: InMemoryEventBus,
    events: Any,
    interactions: InteractionService,
    hub: Hub[Any],
) -> dict[str, WsTopicHandler]:
    """이 모듈의 WS 토픽 처리기(키가 ``:``로 끝나면 접두)."""

    async def run_topic(req: WsSubscribeRequest) -> WsForward | WsReject | None:
        run_id = req.target
        if service.current_run(run_id) is None:
            return WsReject(ErrorCodes.NOT_FOUND, f"Run이 없습니다: {run_id}")

        async def forward(send: WsSend) -> None:
            await _forward_run(bus, events, send, run_id, req.since_seq)

        return forward

    async def interactions_topic(_: WsSubscribeRequest) -> WsForward | WsReject | None:
        async def forward(send: WsSend) -> None:
            await _forward_interactions(hub, interactions, send)

        return forward

    return {f"{RUN_TOPIC}:": run_topic, INTERACTIONS_TOPIC: interactions_topic}


async def _forward_run(
    bus: InMemoryEventBus, events: Any, send: WsSend, run_id: str, since: int
) -> None:
    sub = bus.subscribe(run_id=run_id)  # 재생 전에 먼저 연다(경합 없음)
    last = since
    try:
        last = await _replay(events, send, run_id, last, upto=None)
        while True:
            event = await sub.get()
            if event is None:
                return
            if event.seq <= last:
                continue
            if event.seq > last + 1:  # 버려진 이벤트: 저장소에서 메운다
                last = await _replay(events, send, run_id, last, upto=event.seq - 1)
            await _send_event(send, event)
            last = event.seq
    finally:
        sub.close()


async def _replay(events: Any, send: WsSend, run_id: str, since: int, *, upto: int | None) -> int:
    last = since
    for event in events.list(run_id, since_seq=since):
        if upto is not None and event.seq > upto:
            break
        await _send_event(send, event)
        last = event.seq
    return last


async def _send_event(send: WsSend, event: RunEvent) -> None:
    await send(RunEventMessage(type="run.event", payload=event))


async def _forward_interactions(
    hub: Hub[Any], interactions: InteractionService, send: WsSend
) -> None:
    sub = hub.subscribe(INTERACTIONS_TOPIC)  # 대기 목록보다 먼저 연다
    try:
        for interaction in interactions.pending():
            await send(
                InteractionUpdatedMessage(
                    type="interaction.updated",
                    payload=InteractionUpdatedPayload(interaction=interaction),
                )
            )
        async for message in sub:
            await send(message)
    finally:
        sub.close()


__all__ = ["RUN_TOPIC", "topic_handlers"]
