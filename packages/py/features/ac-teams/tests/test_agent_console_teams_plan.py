"""team_plan: 명시된 입구·답변, 위임 대상, 리소스 첨부, 노드별 grant — 임의 이름 디스크립터로."""

from __future__ import annotations

import pytest

from agent_console_contracts import Agent, EdgeSpec, InteractionGrant, NodeSpec
from agent_console_teams import (
    TeamConventions,
    TeamPlan,
    describe_member,
    runs_in_own_session,
    session_grant,
    session_owner,
    shares_session,
    team_plan,
)
from agent_console_teams.testing import KITS, Kit


def _plan(kit: Kit, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> TeamPlan:
    return team_plan(kit.graph(nodes, edges), node_types=kit.node_types, edge_types=kit.edge_types)


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_entries_and_answers_are_only_explicit_edges(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("lonely")]
    edges = [
        k.edge("m1", "entry", "me", "mate"),  # 팀원이 입구
        k.edge("h1", "flow", "mate", "lead"),
        k.edge("a1", "exit", "mate", "me"),  # 중간 노드도 답변
        k.edge("a2", "exit", "lead", "me"),
    ]
    plan = _plan(k, nodes, edges)
    assert plan.entries == ("m1",)
    assert plan.entry_nodes == ("mate",)
    assert plan.answers == ("a1", "a2")
    assert plan.answer_nodes == ("lead", "mate")  # 노드 순서
    # 들어오는 연결 없는 "lonely"는 모양상 입구처럼 보여도 입구가 아니다
    assert "lonely" not in plan.entry_nodes
    assert "lonely" not in plan.view.scheduled
    assert plan.outside == frozenset({"me"})


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_no_entry_edge_means_no_entry_even_for_single_node(k: Kit) -> None:
    plan = _plan(k, [k.worker("solo")], [])
    assert plan.entry_nodes == ()
    assert plan.answers == ()


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_delegations_with_strategy_override_and_member_profile(k: Kit) -> None:
    nodes = [
        k.worker("lead"),
        k.worker("be", who="backend", role="서버 담당", delegate_when="API 작업"),
        k.worker("qa"),
    ]
    edges = [
        k.edge("d1", "invoke", "lead", "be"),
        k.edge("d2", "invoke", "lead", "qa", strategy=k["s_other"]),
    ]
    plan = _plan(k, nodes, edges)
    links = plan.delegates_of["lead"]
    assert [(link.member, link.strategy) for link in links] == [
        ("be", k["s_inner"]),
        ("qa", k["s_other"]),
    ]
    assert plan.callees == frozenset({"be", "qa"})
    assert plan.callers_of["be"][0].delegator == "lead"
    assert plan.agent_refs == {"lead": "lead", "be": "backend", "qa": "qa"}

    be = describe_member(links[0])
    assert (be.role, be.delegate_when) == ("서버 담당", "API 작업")
    agent = Agent(id="qa", name="QA", role="검증", description="끝나면 검증")
    qa = describe_member(links[1], agent)
    assert (qa.role, qa.delegate_when) == ("검증", "끝나면 검증")


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_resource_attachments_from_bound_resource_nodes(k: Kit) -> None:
    nodes = [k.worker("lead"), k.material("guide", "team-md"), k.material("tip", "tip-1")]
    edges = [
        k.edge("r1", "attach", "guide", "lead"),
        k.edge("r2", "attach", "tip", "lead", mode="replace", config_override={"title": "T"}),
    ]
    plan = _plan(k, nodes, edges)
    atts = plan.attachments_of["lead"]
    assert [(a.edge_id, a.attachment.ref, a.attachment.mode) for a in atts] == [
        ("r1", "team-md", "add"),
        ("r2", "tip-1", "replace"),
    ]
    assert atts[1].attachment.config_override == {"title": "T"}
    assert plan.resource_refs == {"guide": "team-md", "tip": "tip-1"}
    assert "guide" not in plan.view.executable


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_grants_union_narrowing_and_timeout(k: Kit) -> None:
    nodes = [k.person(), k.person("you"), k.worker("lead"), k.worker("mate")]
    edges = [
        k.edge("k1", "ask", "lead", "me", kinds=[k["perm"]], timeout_seconds=60),
        k.edge("k2", "ask", "lead", "you", timeout_seconds=30, on_timeout="cancel_run"),
        k.edge("k3", "ask", "mate", "me", kinds=[k["q"], "nope"]),
    ]
    plan = _plan(k, nodes, edges)
    assert plan.grants["lead"] == InteractionGrant(
        kinds=[k["perm"], k["q"]], timeout_seconds=30, on_timeout="cancel_run"
    )
    assert plan.grant_edges["lead"] == ("k1", "k2")
    assert plan.grants["mate"].kinds == [k["q"]]  # 디스크립터에 없는 종류는 버린다
    assert plan.grants["mate"].timeout_seconds is None
    assert "me" not in plan.grants


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_session_grant_filters_member_kinds_by_strategy(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate")]
    edges = [
        k.edge("d1", "invoke", "lead", "mate"),
        k.edge("k1", "ask", "mate", "me", timeout_seconds=10),
    ]
    plan = _plan(k, nodes, edges)
    grant = session_grant(plan, "lead", k.strategy_map)
    assert grant is not None
    assert grant.kinds == [k["perm"]]  # 위임 방식 member_interaction_kinds로 거름
    assert grant.timeout_seconds == 10
    # 위임 방식을 모르면 거르지 않는다
    unfiltered = session_grant(plan, "lead", {})
    assert unfiltered is not None
    assert unfiltered.kinds == [k["q"], k["perm"]]
    assert session_grant(plan, "me", k.strategy_map) is None


def test_unknown_types_and_dangling_edges_are_ignored() -> None:
    k = Kit()
    nodes = [k.person(), k.worker("lead")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("x1", "entry", "me", "ghost"),
    ]
    graph = k.graph(nodes, edges).model_copy(
        update={
            "edges": [
                *k.graph(nodes, edges).edges,
                k.edge("u1", "flow", "lead", "me").model_copy(update={"kind": "unknown-kind"}),
            ]
        }
    )
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    assert set(plan.edge_descriptors) == {"m1"}
    assert plan.entries == ("m1",)


def test_conventions_change_config_keys() -> None:
    k = Kit()
    conv = TeamConventions(edge_kinds_key="only", edge_strategy_key="via")
    nodes = [k.person(), k.worker("lead"), k.worker("mate")]
    edges = [
        k.edge("k1", "ask", "lead", "me", only=[k["q"]], kinds=[k["perm"]]),
        k.edge("d1", "invoke", "lead", "mate", via=k["s_other"]),
    ]
    plan = team_plan(
        k.graph(nodes, edges), node_types=k.node_types, edge_types=k.edge_types, conventions=conv
    )
    assert plan.grants["lead"].kinds == [k["q"]]
    assert plan.delegates_of["lead"][0].strategy == k["s_other"]


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_session_grant_skips_members_of_own_session_strategies(k: Kit) -> None:
    """5.2R.43(J-10): `shares_session` false 방식의 대상 종류·대기 한도는 위임자 세션에 없다."""
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("far")]
    edges = [
        k.edge("d1", "invoke", "lead", "mate"),  # 같은 세션 방식
        k.edge("d3", "invoke3", "lead", "far"),  # 자기 세션 방식(shares_session false)
        k.edge("k1", "ask", "mate", "me", timeout_seconds=10, on_timeout="expire"),
        k.edge("k3", "ask", "far", "me", timeout_seconds=3, on_timeout="cancel_run"),
    ]
    plan = _plan(k, nodes, edges)
    strategies = k.strategy_map
    assert strategies[k["s_far"]].shares_session is False
    assert strategies[k["s_inner"]].shares_session is True
    grant = session_grant(plan, "lead", strategies)
    assert grant is not None
    assert grant.kinds == [k["perm"]]  # mate 것만(방식 필터), far의 q·perm은 없다
    assert grant.timeout_seconds == 10  # far의 더 짧은 3초가 위임자에게 오지 않는다
    assert grant.on_timeout == "expire"
    # 자기 세션 대상은 자기 grant 그대로
    own = session_grant(plan, "far", strategies)
    assert own is not None
    assert own.kinds == [k["q"], k["perm"]]
    assert own.timeout_seconds == 3
    # 같은 세션 여부
    (to_mate, to_far) = plan.delegates_of["lead"]
    assert shares_session(to_mate, strategies) is True
    assert shares_session(to_far, strategies) is False
    assert shares_session(to_far, {}) is True  # 방식을 모르면 계약 기본값(true)
    assert runs_in_own_session(plan, "lead", strategies) is True
    assert runs_in_own_session(plan, "mate", strategies) is False
    assert runs_in_own_session(plan, "far", strategies) is True
    assert session_owner(plan, "mate", strategies) == "lead"
    assert session_owner(plan, "far", strategies) == "far"
    assert session_owner(plan, "far") == "lead"  # 방식을 주지 않으면 옛 동작


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_session_grant_none_when_only_own_session_members_ask(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("far")]
    edges = [
        k.edge("d3", "invoke3", "lead", "far"),
        k.edge("k3", "ask", "far", "me", timeout_seconds=3),
    ]
    plan = _plan(k, nodes, edges)
    assert session_grant(plan, "lead", k.strategy_map) is None
    # 방식 디스크립터를 모르면 같은 세션으로 본다(기존 외부 방식 동작 유지)
    legacy = session_grant(plan, "lead", {})
    assert legacy is not None
    assert legacy.timeout_seconds == 3
