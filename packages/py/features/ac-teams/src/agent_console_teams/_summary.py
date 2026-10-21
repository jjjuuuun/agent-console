"""화면용 요약(순수): 답변 계획 `plan_summary`, 검증 요약 `validation_summary` (design §2R.6).

답변 연결의 속성(label·order·final·stream)은 **엣지 타입 디스크립터 `reply_fields`**(엣지 config
기준 JSON Pointer)로 읽는다. 이 모듈에는 config 키 이름이 없다(H1). 값이 config에 없으면 그 위치의
엣지 `config_schema` 기본값("생략 = 상속"), 그것도 없으면 계약 기본 규칙(label = 엣지 label,
order 없음, final = true, stream = false)을 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from agent_console_contracts import (
    AnswerSlot,
    EdgeSpec,
    EdgeTypeDescriptor,
    EntrySlot,
    GraphValidationSummary,
    Issue,
    TeamPlanSummary,
)
from agent_console_settings import MISSING, PointerError, get_at, schema_annotation

from ._plan import TeamPlan
from ._run import blocks_run

__all__ = ["plan_summary", "reply_value", "validation_summary"]

_DEFAULT_KEY = "default"
"""JSON Schema 기본값 키워드."""


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def reply_value(
    edge: EdgeSpec,
    descriptor: EdgeTypeDescriptor | None,
    field: str,
    accept: Callable[[Any], bool],
) -> Any:
    """답변 연결 속성 하나를 읽는다: config 값 → config 스키마 기본값 → `None`.

    Args:
        edge: 답변 연결.
        descriptor: 그 엣지 타입 디스크립터(없으면 `None`).
        field: `ReplyFields`의 필드 이름(`label`·`order`·`final`·`stream`).
        accept: 값 형식 검사. 형식이 틀린 값은 없는 것으로 본다.

    Returns:
        읽은 값. 디스크립터가 이 속성의 위치를 선언하지 않았거나 값이 없으면 `None`.
    """
    fields = descriptor.reply_fields if descriptor is not None else None
    pointer = getattr(fields, field, None) if fields is not None else None
    if not isinstance(pointer, str):
        return None
    try:
        value = get_at(edge.config, pointer, MISSING)
    except PointerError:
        return None
    if value is not MISSING and accept(value):
        return value
    default = schema_annotation(
        descriptor.config_schema if descriptor else None, pointer, _DEFAULT_KEY
    )
    return default if accept(default) else None


def _answer(plan: TeamPlan, edge_id: str) -> AnswerSlot | None:
    edge = plan.edge(edge_id)
    if edge is None:
        return None
    desc = plan.edge_descriptors.get(edge_id)
    node_id = edge.source.node
    label = reply_value(edge, desc, "label", _is_text)
    order = reply_value(edge, desc, "order", _is_int)
    final = reply_value(edge, desc, "final", _is_bool)
    stream = reply_value(edge, desc, "stream", _is_bool)
    return AnswerSlot(
        edge_id=edge_id,
        node_id=node_id,
        agent_id=plan.agent_refs.get(node_id),
        label=label if label is not None else (edge.label or None),
        order=order,
        final=True if final is None else final,
        stream=False if stream is None else stream,
    )


def plan_summary(plan: TeamPlan) -> TeamPlanSummary:
    """팀 구성 실행 계획 요약(입구·답변 자리·노드별 허용 상호작용). 순서는 그래프 순서다.

    - 입구: `scheduling=entry` 연결마다 도착 노드와 그 표시 이름.
    - 답변: `scheduling=exit` 연결마다 출발 노드, 묶인 에이전트, `reply_fields`로 읽은 속성.
    - grants: `team_plan`의 노드별 허용 상호작용.
    """
    entries: list[EntrySlot] = []
    for edge_id in plan.entries:
        edge = plan.edge(edge_id)
        if edge is None:
            continue
        node_id = edge.target.node
        entries.append(EntrySlot(edge_id=edge_id, node_id=node_id, label=plan.label_of(node_id)))
    answers = [a for eid in plan.answers if (a := _answer(plan, eid)) is not None]
    return TeamPlanSummary(entries=entries, answers=answers, grants=dict(plan.grants))


def validation_summary(
    issues: Iterable[Issue], *, is_blocking: Callable[[Issue], bool] = blocks_run
) -> GraphValidationSummary:
    """검증 이슈 목록(엔진 + 팀, `merge_validation` 결과) → 목록 화면용 요약.

    Args:
        issues: 합친 검증 이슈.
        is_blocking: 실행 차단 판정(기본 `blocks_run`).
    """
    items = list(issues)
    counts: Mapping[str, int] = {
        sev: sum(1 for i in items if i.severity == sev) for sev in ("error", "warning")
    }
    return GraphValidationSummary(
        blocks_run=any(is_blocking(i) for i in items),
        error_count=counts["error"],
        warning_count=counts["warning"],
        codes=list(dict.fromkeys(i.code for i in items)),
    )
