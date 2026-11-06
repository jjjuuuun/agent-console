"""6R.20k 세션 집계(`session_summary`, screen-delegation §14.4.4).

디스크립터·세션 값은 모두 임의 이름이다(값의 뜻·방식 id를 코드가 모르는지 확인).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    GraphSessionSummary,
    NodeTypeDescriptor,
)
from agent_console_teams import edge_sessions, session_summary, team_plan
from agent_console_teams.testing import KITS, Kit

VAL_A, VAL_B, VAL_FLOW = "값-가", "값-나", "흐름-값"


def _strategies(k: Kit) -> dict[str, DelegationStrategyDescriptor]:
    """`s_inner` = VAL_A, `s_deep` = VAL_B(임의 세션 값 방식 2개)."""
    values = {k["s_inner"]: VAL_A, k["s_deep"]: VAL_B}
    out: dict[str, DelegationStrategyDescriptor] = {}
    for s in k.strategies:
        data: dict[str, Any] = s.model_dump(exclude_unset=True)
        if s.id in values:
            data["session"] = values[s.id]
        out[s.id] = DelegationStrategyDescriptor.model_validate(data)
    return out


def _edge_types(k: Kit, *, flow_session: str | None = None) -> list[EdgeTypeDescriptor]:
    return [
        e.model_copy(update={"session": flow_session}) if e.id == k["flow"] else e
        for e in k.edge_types
    ]


def _summary(
    k: Kit,
    nodes: list[Any],
    edges: list[Any],
    *,
    strategies: dict[str, DelegationStrategyDescriptor] | None = None,
    flow_session: str | None = None,
    node_types: list[NodeTypeDescriptor] | None = None,
) -> GraphSessionSummary | None:
    plan = team_plan(
        k.graph(nodes, edges),
        node_types=node_types if node_types is not None else k.node_types,
        edge_types=_edge_types(k, flow_session=flow_session),
    )
    return session_summary(plan, strategies if strategies is not None else _strategies(k))


@pytest.mark.parametrize("k", KITS)
def test_counts_per_value_for_two_arbitrary_strategies(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("a"), k.worker("b"), k.worker("c")]
    edges = [
        k.edge("e0", "entry", "me", "lead"),
        k.edge("d1", "invoke", "lead", "a"),  # VAL_A
        k.edge("d2", "invoke2", "lead", "b"),  # VAL_B
        k.edge("d3", "invoke", "lead", "c"),  # VAL_A
        k.edge("d4", "invoke2", "a", "c"),  # VAL_B → c는 섞임
    ]
    got = _summary(k, nodes, edges)
    # 대상 = lead·a·b·c(입구의 사람은 세션 값 연결에 닿지 않음).
    # a = VAL_A, b = VAL_B, c(섞임)·lead(위임받지 않음) = 어느 값도 아님
    assert got == GraphSessionSummary(nodes=4, delegated={VAL_A: 1, VAL_B: 1})


@pytest.mark.parametrize("k", KITS)
def test_edge_config_override_is_the_effective_strategy(k: Kit) -> None:
    nodes = [k.worker("lead"), k.worker("a")]
    edges = [k.edge("d1", "invoke", "lead", "a", strategy=k["s_deep"])]
    plan = team_plan(k.graph(nodes, edges), node_types=k.node_types, edge_types=k.edge_types)
    assert edge_sessions(plan, _strategies(k)) == {"d1": VAL_B}
    assert _summary(k, nodes, edges) == GraphSessionSummary(nodes=2, delegated={VAL_B: 1})


@pytest.mark.parametrize("k", KITS)
def test_flow_session_touches_nodes_but_is_not_delegated(k: Kit) -> None:
    nodes = [k.worker("a"), k.worker("b"), k.worker("c")]
    edges = [k.edge("f1", "flow", "a", "b"), k.edge("d1", "invoke", "b", "c")]
    got = _summary(k, nodes, edges, flow_session=VAL_FLOW)
    assert got == GraphSessionSummary(nodes=3, delegated={VAL_A: 1})


@pytest.mark.parametrize("k", KITS)
def test_team_without_session_attributes_is_none(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("a")]
    edges = [
        k.edge("e0", "entry", "me", "lead"),
        k.edge("f1", "flow", "lead", "a"),
        k.edge("x1", "exit", "a", "me"),
    ]
    assert _summary(k, nodes, edges) is None


@pytest.mark.parametrize("k", KITS)
def test_strategy_without_session_or_unknown_strategy_is_not_counted(k: Kit) -> None:
    nodes = [k.worker("lead"), k.worker("a")]
    edges = [k.edge("d1", "invoke", "lead", "a")]
    # 속성이 없는 방식(디스크립터를 검증 없이 만든 외부 방식 모양) → 세지 않음
    bare = _strategies(k)
    bare[k["s_inner"]] = bare[k["s_inner"]].model_copy(update={"session": None})
    assert _summary(k, nodes, edges, strategies=bare) is None
    # 모르는 방식(목록에 없음)
    assert _summary(k, nodes, edges, strategies={}) is None


@pytest.mark.parametrize("k", KITS)
def test_nodes_that_do_not_open_sessions_are_skipped(k: Kit) -> None:
    node_types = [
        t.model_copy(update={"opens_session": False}) if t.id == k["person"] else t
        for t in k.node_types
    ]
    nodes = [k.person(), k.worker("a")]
    edges = [k.edge("f1", "flow", "me", "a")]
    got = _summary(k, nodes, edges, flow_session=VAL_FLOW, node_types=node_types)
    assert got == GraphSessionSummary(nodes=1, delegated={})
