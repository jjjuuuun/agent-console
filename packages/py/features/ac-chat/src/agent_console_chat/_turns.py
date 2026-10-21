"""턴 조립(순수 함수): Run + `run.reply` 이벤트 + 상호작용 → `ChatTurn`, 이벤트 → 세션 맵."""

import json
import logging
from collections.abc import Iterable, Mapping

from pydantic import ValidationError

from agent_console_contracts import (
    AgentSessionStartedPayload,
    ChatReply,
    ChatTurn,
    Interaction,
    Run,
    RunEvent,
    RunReplyPayload,
    SessionRef,
)

from ._ports import EventReader

_log = logging.getLogger(__name__)

REPLY_EVENT = "run.reply"
"""답변 이벤트 type(계약의 알려진 이벤트)."""

SESSION_EVENT = "agent.session_started"
"""백엔드 세션 시작 이벤트 type(계약의 알려진 이벤트)."""


def message_text(run: Run, input_key: str) -> str:
    """Run 입력에서 사용자 메시지 원문을 꺼낸다. 문자열이 아니면 JSON 문자열로."""
    value = run.input.get(input_key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def replies_from_events(events: Iterable[RunEvent]) -> list[ChatReply]:
    """`run.reply` 이벤트를 seq 순서대로 `ChatReply`로 바꾼다. 형식이 틀린 이벤트는 건너뛴다.

    `agent_id`는 이벤트 머리의 `actor`(답변을 낸 에이전트 정의 id)다.
    """
    replies: list[ChatReply] = []
    for event in sorted(events, key=lambda e: e.seq):
        if event.type != REPLY_EVENT:
            continue
        try:
            payload = RunReplyPayload.model_validate(event.payload)
        except ValidationError:
            _log.warning("형식이 틀린 run.reply 건너뜀: run=%s seq=%s", event.run_id, event.seq)
            continue
        replies.append(
            ChatReply(
                edge_id=payload.edge_id,
                node_id=payload.node_id,
                agent_id=event.actor,
                label=payload.label,
                order=payload.order,
                final=payload.final,
                text=payload.text,
            )
        )
    return replies


def sessions_from_events(events: Iterable[RunEvent]) -> dict[str, SessionRef]:
    """노드별 마지막 백엔드 세션(`agent.session_started`, `node_path == [노드]`).

    위임받은 서브에이전트(`node_path` 길이 2 이상)는 위임자 세션 안에서 돌므로 따로 저장하지 않는다.
    """
    sessions: dict[str, SessionRef] = {}
    for event in sorted(events, key=lambda e: e.seq):
        if event.type != SESSION_EVENT or len(event.node_path) != 1:
            continue
        try:
            payload = AgentSessionStartedPayload.model_validate(event.payload)
        except ValidationError:
            _log.warning("형식이 틀린 세션 이벤트 건너뜀: run=%s seq=%s", event.run_id, event.seq)
            continue
        sessions[event.node_path[0]] = SessionRef(
            backend=payload.backend, session_id=payload.session_id
        )
    return sessions


def prune_sessions(
    sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
) -> dict[str, SessionRef]:
    """팀 구성에 있는 노드의 세션만 남긴다(팀 구성 전환·노드 삭제 시)."""
    keep = set(node_ids)
    return {node_id: ref for node_id, ref in sessions.items() if node_id in keep}


class RootRunSessions:
    """기본 `TurnSessions`: 턴 Run 자기 이벤트의 노드 세션(키 = 노드 id, `sessions_from_events`).

    자식 Run(중첩 실행)의 세션은 모르므로 모으지 않는다 — 그런 실행을 하는 조립은 자기 규칙을
    주입한다(예: `agent-console-link-chat-runs`의 경로 키 규칙).

    Args:
        events: 이벤트 조회(없으면 아무것도 모으지 않는다).
    """

    def __init__(self, events: EventReader | None) -> None:
        self._events = events

    def collect(self, run: Run) -> dict[str, SessionRef]:
        return sessions_from_events(self._events.list(run.id) if self._events is not None else [])

    def prune(
        self, sessions: Mapping[str, SessionRef], node_ids: Iterable[str]
    ) -> dict[str, SessionRef]:
        return prune_sessions(sessions, node_ids)


def assemble_turn(
    run: Run,
    events: Iterable[RunEvent],
    interactions: Iterable[Interaction],
    *,
    input_key: str,
) -> ChatTurn:
    """턴 하나를 만든다.

    Args:
        run: 턴 Run.
        events: 그 Run의 이벤트(답변 추출, 다른 type은 무시).
        interactions: 그 Run에서 열린 상호작용(대기·닫힘 모두). `created_at` 순으로 정렬한다.
        input_key: Run 입력에서 메시지 본문을 꺼낼 키.
    """
    return ChatTurn(
        run_id=run.id,
        user_text=message_text(run, input_key),
        replies=replies_from_events(events),
        interactions=sorted(interactions, key=lambda i: (i.created_at, i.id)),
        status=run.status,
        usage=run.totals,
        started_at=run.started_at if run.started_at is not None else run.created_at,
        ended_at=run.ended_at,
        resumed_from=run.resumed_from,
    )


def first_message_title(text: str, max_chars: int) -> str:
    """첫 메시지로 만든 대화 제목: 공백을 한 칸으로 줄이고 앞 `max_chars`자."""
    return " ".join(text.split())[:max_chars].rstrip()
