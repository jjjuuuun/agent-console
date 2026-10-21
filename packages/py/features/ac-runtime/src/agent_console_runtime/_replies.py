"""엣지 평가와 답변(`run.reply`) 발행 도우미(내부).

엔진과 `NodeContext.emit_replies`가 함께 쓴다.
"""

from __future__ import annotations

import json
from typing import Any

from agent_console_contracts import (
    EdgeSkippedPayload,
    EdgeSpec,
    LogWarningPayload,
    RunEvent,
    RunReplyPayload,
)

from ._interfaces import Activation, Blocked, NodeRunView, Reply
from ._journal import RunJournal
from ._registries import Registries


def activate_edge(
    journal: RunJournal,
    registries: Registries,
    edge: EdgeSpec,
    view: NodeRunView,
    *,
    node_path: list[str],
    attempt: int | None,
) -> Activation | None:
    """엣지 타입의 `activates`를 부른다. 예외(모르는 타입 포함)는 `log.warning`을 내고 None.

    엣지 타입이 준 `warnings`는 `log.warning`으로 낸다. `Blocked`(사유·근거가 있는 dead-path)는
    `edge.skipped{edge_id, source, target, kind, reason, condition}`를 내고 None으로 바꾼다.
    통과 근거(`Activation.condition`)는 호출자가 `edge.traversed`에 싣는다.
    """
    try:
        result = registries.edge_types.get(edge.kind).activates(view, edge)
    except Exception as exc:
        journal.event(
            "log.warning",
            LogWarningPayload(
                message=f"엣지 {edge.id} 평가 실패: {type(exc).__name__}: {exc}",
                details={"edge_id": edge.id, "kind": edge.kind},
            ),
            node_path=node_path,
            attempt=attempt,
        )
        return None
    if isinstance(result, Activation | Blocked):
        for warning in result.warnings:
            journal.event(
                "log.warning",
                LogWarningPayload(
                    message=warning.message,
                    details={**warning.details, "edge_id": edge.id, "kind": edge.kind},
                ),
                node_path=node_path,
                attempt=attempt,
            )
    if isinstance(result, Blocked):
        journal.event(
            "edge.skipped",
            EdgeSkippedPayload(
                edge_id=edge.id,
                source=edge.source,
                target=edge.target,
                kind=edge.kind,
                reason=result.reason,
                condition=result.condition,
            ),
            node_path=node_path,
            attempt=attempt,
        )
        return None
    return result


def reply_payload(edge: EdgeSpec, activation: Activation) -> RunReplyPayload:
    """답변 엣지 통과 값 → `run.reply` payload(`Reply`면 그 필드, 아니면 텍스트로 바꿈)."""
    value = activation.value
    if isinstance(value, Reply):
        return RunReplyPayload(
            edge_id=edge.id,
            node_id=edge.source.node,
            label=value.label,
            order=value.order,
            final=value.final,
            text=value.text,
        )
    return RunReplyPayload(edge_id=edge.id, node_id=edge.source.node, text=reply_text(value))


def reply_text(value: Any) -> str:
    """답변 값 → 텍스트. 문자열은 그대로, None은 빈 문자열, 그 밖은 JSON(실패하면 `str`)."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def emit_replies(
    journal: RunJournal,
    registries: Registries,
    edges: list[EdgeSpec],
    view: NodeRunView,
    *,
    node_path: list[str],
    attempt: int | None,
    actor: str | None,
) -> list[RunEvent]:
    """답변 엣지들을 평가해 통과한 것마다 `run.reply`를 낸다(엣지 순서대로)."""
    events: list[RunEvent] = []
    for edge in edges:
        activation = activate_edge(
            journal, registries, edge, view, node_path=node_path, attempt=attempt
        )
        if activation is None:
            continue
        events.append(
            journal.event(
                "run.reply",
                reply_payload(edge, activation),
                node_path=node_path,
                attempt=attempt,
                actor=actor,
            )
        )
    return events
