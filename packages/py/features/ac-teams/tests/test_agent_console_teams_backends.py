"""resolve_backends·unresolved_backends: 실행 백엔드 사전 점검(5.2R.4, 해결 순서 불변).

노드·에이전트·팀 구성·공통(`agent_defaults.backend`)·옛 `default_backend`·인자 대체값 각 층에서
정해지는지, 모두 비면 세션 주인 노드만 막는지, 이름을 바꾼 디스크립터·백엔드로도 같은지 본다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    Graph,
    NodeSpec,
    NodeTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_teams import (
    DEFAULT_CONVENTIONS,
    TeamPlan,
    UnresolvedBackend,
    backend_nodes,
    node_display_name,
    resolve_backends,
    team_plan,
    unresolved_backends,
)
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]
BACKEND = "zz-engine"  # 코드에 백엔드 이름이 없다: 임의 이름으로 동작


def _plan(k: Kit, graph: Graph, extra: list[NodeTypeDescriptor] | None = None) -> TeamPlan:
    return team_plan(graph, node_types=[*k.node_types, *(extra or [])], edge_types=k.edge_types)


def _team(k: Kit, team: dict[str, Any] | None = None, **node_config: Any) -> Graph:
    nodes = [k.person(), k.worker("lead", who="pl", **node_config)]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")]
    return k.graph(nodes, edges, settings=team)


def _agent(**settings: Any) -> dict[str, Agent]:
    return {"pl": Agent.model_validate({"id": "pl", "name": "기획자", **settings})}


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_each_layer_resolves(k: Kit) -> None:
    # 노드 층
    plan = _plan(k, _team(k, settings={"backend": BACKEND}))
    assert resolve_backends(plan, agents=_agent()) == {"lead": BACKEND}
    # 에이전트 층
    plan = _plan(k, _team(k))
    assert resolve_backends(plan, agents=_agent(backend=BACKEND)) == {"lead": BACKEND}
    # 팀 구성 층
    plan = _plan(k, _team(k, {"backend": BACKEND}))
    assert resolve_backends(plan, agents=_agent()) == {"lead": BACKEND}
    # 공통 층
    plan = _plan(k, _team(k))
    common = WorkspaceSettings.model_validate({"agent_defaults": {"backend": BACKEND}})
    assert resolve_backends(plan, agents=_agent(), workspace=common) == {"lead": BACKEND}
    # 옛 default_backend(공통 층 읽기 호환)
    legacy = WorkspaceSettings.model_validate({"default_backend": BACKEND})
    assert resolve_backends(plan, agents=_agent(), workspace=legacy) == {"lead": BACKEND}
    # 인자 대체값(마지막)
    assert resolve_backends(plan, agents=_agent(), default_backend=BACKEND) == {"lead": BACKEND}
    # 모두 비면 None
    assert resolve_backends(plan, agents=_agent()) == {"lead": None}


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_order_is_unchanged_node_wins_over_lower_layers(k: Kit) -> None:
    graph = _team(k, {"backend": "team-b"}, settings={"backend": "node-b"})
    common = WorkspaceSettings.model_validate(
        {"agent_defaults": {"backend": "common-b"}, "default_backend": "legacy-b"}
    )
    plan = _plan(k, graph)
    got = resolve_backends(
        plan, agents=_agent(backend="agent-b"), workspace=common, default_backend="arg-b"
    )
    assert got == {"lead": "node-b"}
    # 노드를 비우면 에이전트 → 팀 구성 → 공통 → 인자 순
    plan = _plan(k, _team(k, {"backend": "team-b"}))
    assert resolve_backends(plan, agents=_agent(backend="agent-b"), workspace=common) == {
        "lead": "agent-b"
    }
    assert resolve_backends(plan, agents=_agent(), workspace=common) == {"lead": "team-b"}
    plan = _plan(k, _team(k))
    assert resolve_backends(plan, agents=_agent(), workspace=common, default_backend="x") == {
        "lead": "common-b"
    }


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_unresolved_names_node_by_label_then_agent_name(k: Kit) -> None:
    plan = _plan(k, _team(k))
    agents = _agent()
    resolved = resolve_backends(plan, agents=agents)
    assert unresolved_backends(plan, resolved, agents=agents) == [UnresolvedBackend("lead", "LEAD")]
    # label이 없으면 에이전트 정의 이름 → 정의 id → 노드 id
    bare = k.graph(
        [k.person(), NodeSpec(id="n1", type=k["worker"], config={"who": "pl"})],
        [k.edge("m1", "entry", "me", "n1"), k.edge("a1", "exit", "n1", "me")],
    )
    plan = _plan(k, bare)
    assert node_display_name(plan, "n1", agents) == "기획자"
    assert node_display_name(plan, "n1", {}) == "pl"
    [item] = unresolved_backends(plan, resolve_backends(plan, agents=agents), agents=agents)
    assert (item.node_id, item.label) == ("n1", "기획자")


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_delegated_member_runs_in_owner_session(k: Kit) -> None:
    """위임받는 노드는 위임자 세션에서 돈다: 자기 값이 비어도 위임자가 정해져 있으면 막지 않는다."""
    nodes = [
        k.person(),
        k.worker("lead", who="pl", settings={"backend": BACKEND}),
        k.worker("helper", who="pl"),
    ]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke", "lead", "helper"),
    ]
    plan = _plan(k, k.graph(nodes, edges))
    resolved = resolve_backends(plan, agents=_agent())
    assert resolved == {"lead": BACKEND, "helper": None}
    assert unresolved_backends(plan, resolved) == []
    # 위임자도 비면 위임자 하나만(중복 없이)
    nodes[1] = k.worker("lead", who="pl")
    plan = _plan(k, k.graph(nodes, edges))
    resolved = resolve_backends(plan, agents=_agent())
    assert [u.node_id for u in unresolved_backends(plan, resolved)] == ["lead"]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_backend_nodes_by_descriptor(k: Kit) -> None:
    """에이전트 정의에 묶인 실행 가능 노드 + 능력을 선언한 노드. 사람·자료·중첩 팀은 아니다."""
    custom = NodeTypeDescriptor(
        id="zz-tool",
        title="도구",
        role="w-role",
        capabilities=[DEFAULT_CONVENTIONS.backend_capability],
    )
    nodes = [
        k.person(),
        k.worker("lead", who="pl"),
        k.material("doc", "memo"),
        k.nest("crew", "child"),
        NodeSpec(id="tool", type="zz-tool", label="도구"),
    ]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")]
    plan = _plan(k, k.graph(nodes, edges), [custom])
    assert backend_nodes(plan) == ["lead", "tool"]
    resolved = resolve_backends(plan, default_backend=BACKEND)
    assert resolved == {"lead": BACKEND, "tool": BACKEND}
    assert unresolved_backends(plan, resolved) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_own_session_member_is_checked_with_strategies(k: Kit) -> None:
    """자기 세션을 여는 방식(`shares_session` false)의 대상은 스스로 세션 주인이다: 방식
    디스크립터를 넘기면 위임자의 백엔드가 정해져 있어도 대상의 빈 백엔드를 실행 전에 막는다.
    방식 id는 Kit 이름표를 따르므로(`renamed`) 코드에 방식 이름이 없다."""
    nodes = [
        k.person(),
        k.worker("lead", who="pl", settings={"backend": BACKEND}),
        k.worker("far", who="pl"),
    ]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke3", "lead", "far"),
    ]
    plan = _plan(k, k.graph(nodes, edges))
    strategies = k.strategy_map
    assert strategies[k["s_far"]].shares_session is False
    resolved = resolve_backends(plan, agents=_agent(), strategies=strategies)
    assert resolved == {"lead": BACKEND, "far": None}
    # 방식을 주지 않으면 옛 동작(모든 위임을 같은 세션으로 본다)
    assert unresolved_backends(plan, resolved) == []
    got = unresolved_backends(plan, resolved, agents=_agent(), strategies=strategies)
    assert got == [UnresolvedBackend("far", "FAR")]
    # 대상에 백엔드를 정하면 막지 않는다
    nodes[2] = k.worker("far", who="pl", settings={"backend": BACKEND})
    plan = _plan(k, k.graph(nodes, edges))
    resolved = resolve_backends(plan, agents=_agent(), strategies=strategies)
    assert unresolved_backends(plan, resolved, strategies=strategies) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_same_session_member_still_skipped_with_strategies(k: Kit) -> None:
    """같은 세션 방식(`shares_session` true)의 대상은 방식을 넘겨도 위임자 세션에서 돈다."""
    nodes = [
        k.person(),
        k.worker("lead", who="pl", settings={"backend": BACKEND}),
        k.worker("helper", who="pl"),
    ]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke", "lead", "helper"),
    ]
    plan = _plan(k, k.graph(nodes, edges))
    strategies = k.strategy_map
    resolved = resolve_backends(plan, agents=_agent(), strategies=strategies)
    assert unresolved_backends(plan, resolved, strategies=strategies) == []
