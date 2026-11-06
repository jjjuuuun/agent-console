"""세션 집계(순수, `docs/design/screen-delegation.md` §14.4.4 — 팀 목록·팀 개요 요약).

세션 값은 디스크립터의 열린 문자열 `session`이다. 위임 연결(엣지 디스크립터 `invocation`)은 유효
위임 방식(연결 config 덮어쓰기 → 종류 기본, `TeamPlan.delegations`)의 값, 그 밖의 연결은 연결 종류의
값. 값의 뜻(같은 세션·별도 세션 등)은 모른다 — 값별로 센다. 방식·연결 종류 id도 비교하지 않는다.
웹 `features/teams/sessionView.ts`의 `sessionSummary`와 같은 규칙이다.
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_console_contracts import DelegationStrategyDescriptor, GraphSessionSummary

from ._plan import TeamPlan

__all__ = ["edge_sessions", "session_summary"]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def edge_sessions(
    plan: TeamPlan, strategies: Mapping[str, DelegationStrategyDescriptor]
) -> dict[str, str]:
    """엣지 id → 세션 값(값이 있는 엣지만, 그래프 순서).

    위임 연결은 유효 방식의 `session`(방식을 모르거나 값이 없으면 빠짐), 그 밖의 연결은 연결 종류
    디스크립터의 `session`. 디스크립터를 모르는 엣지는 빠진다.
    """
    strategy_of = {link.edge_id: link.strategy for link in plan.delegations}
    out: dict[str, str] = {}
    for edge_id, desc in plan.edge_descriptors.items():
        if desc.invocation is not None:
            strategy = strategies.get(strategy_of.get(edge_id, ""))
            value = _text(strategy.session) if strategy is not None else None
        else:
            value = _text(desc.session)
        if value is not None:
            out[edge_id] = value
    return out


def session_summary(
    plan: TeamPlan, strategies: Mapping[str, DelegationStrategyDescriptor]
) -> GraphSessionSummary | None:
    """팀 구성 하나의 세션 집계.

    집계 대상 = 노드 타입 `opens_session`이 false가 아니고(타입을 모르면 대상) 세션 값이 있는 연결의
    양 끝에 한 번이라도 닿은 노드. 대상마다 들어오는 위임 연결 중 세션 값이 있는 것의 값이
    모두 같으면 그 값에 센다(`delegated`). 없거나 섞이면 `nodes`에만 들어간다.

    Args:
        plan: `team_plan` 결과.
        strategies: 위임 방식 id → 디스크립터(`TeamCatalog.strategies`).

    Returns:
        세션 값이 있는 연결이 하나도 없으면 None(요약을 숨긴다).
    """
    sessions = edge_sessions(plan, strategies)
    if not sessions:
        return None
    touched: set[str] = set()
    for edge_id in sessions:
        edge = plan.edge(edge_id)
        if edge is not None:
            touched.update((edge.source.node, edge.target.node))
    incoming: dict[str, set[str]] = {}
    for link in plan.delegations:
        value = sessions.get(link.edge_id)
        if value is not None:
            incoming.setdefault(link.member, set()).add(value)
    nodes = 0
    delegated: dict[str, int] = {}
    for node in plan.graph.nodes:
        if node.id not in touched or plan.node(node.id) is not node:
            continue
        desc = plan.node_descriptors.get(node.id)
        if desc is not None and desc.opens_session is False:
            continue
        nodes += 1
        values = incoming.get(node.id, set())
        if len(values) == 1:
            (value,) = values
            delegated[value] = delegated.get(value, 0) + 1
    return GraphSessionSummary(nodes=nodes, delegated=delegated)
