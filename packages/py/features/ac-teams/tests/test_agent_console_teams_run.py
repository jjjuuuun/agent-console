"""실행 경로의 팀 쪽 판단(design §2R.1): 엔진 없이 이슈 목록·plan만으로."""

from __future__ import annotations

import pytest

from agent_console_contracts import (
    DelegationSettings,
    FlowSettings,
    InteractionSettings,
    Issue,
    WorkspaceSettings,
)
from agent_console_teams import (
    DEFAULT_EQUIVALENTS,
    TeamIssueCodes,
    blocks_run,
    delegation_settings,
    merge_validation,
    prepare_run,
    run_blockers,
    team_plan,
    team_rules_apply,
)
from agent_console_teams.testing import KITS, Kit


def _i(code: str, severity: str = "error", node: str | None = None, **kw: object) -> Issue:
    return Issue.model_validate(
        {"code": code, "severity": severity, "message": code, "node_id": node, **kw}
    )


def test_blocks_run_prefers_flag_then_severity() -> None:
    assert blocks_run(_i("x", "error")) is True
    assert blocks_run(_i("x", "warning")) is False
    assert blocks_run(_i("x", "warning", blocks_run=True)) is True
    assert blocks_run(_i("x", "error", blocks_run=False)) is False


def test_team_rules_apply_only_without_unknown_type_errors() -> None:
    assert team_rules_apply([]) is True
    assert team_rules_apply([_i("config.invalid"), _i("unknown_x", "warning")]) is True
    assert team_rules_apply([_i("unknown_node_type")]) is False
    assert team_rules_apply([_i("odd.code")], skip_prefixes=("odd.",)) is False


def test_merge_drops_equivalent_team_issue_on_same_node_only() -> None:
    engine = [_i("agent.not_found", node="a"), _i("other.warn", "warning", node="b")]
    team = [
        _i(TeamIssueCodes.AGENT_NOT_FOUND, node="a"),  # 같은 노드, 같은 뜻 → 뺀다
        _i(TeamIssueCodes.AGENT_NOT_FOUND, node="c"),  # 다른 노드 → 남긴다
        _i(TeamIssueCodes.NO_REPLY, "warning"),
    ]
    merged = merge_validation(engine, team)
    assert [(i.code, i.node_id) for i in merged] == [
        ("agent.not_found", "a"),
        ("other.warn", "b"),
        (TeamIssueCodes.AGENT_NOT_FOUND, "c"),
        (TeamIssueCodes.NO_REPLY, None),
    ]


def test_merge_keeps_team_issue_when_engine_issue_is_not_equivalent() -> None:
    engine = [_i("config.invalid", node="a"), _i("agent.not_found", "warning", node="b")]
    team = [
        _i(TeamIssueCodes.AGENT_NOT_FOUND, node="a"),
        _i(TeamIssueCodes.AGENT_NOT_FOUND, node="b"),
    ]
    # 다른 뜻의 error, 같은 뜻이지만 warning → 둘 다 남긴다
    assert len(merge_validation(engine, team)) == 4


def test_merge_equivalents_are_data() -> None:
    engine = [_i("mine.missing.thing", node="n")]
    team = [_i("team.custom", node="n"), _i(TeamIssueCodes.AGENT_NOT_FOUND, node="n")]
    merged = merge_validation(engine, team, equivalents={"team.custom": "mine.missing"})
    assert [i.code for i in merged] == ["mine.missing.thing", TeamIssueCodes.AGENT_NOT_FOUND]
    assert dict(DEFAULT_EQUIVALENTS) == {TeamIssueCodes.AGENT_NOT_FOUND: "agent.not_found"}
    with pytest.raises(TypeError):
        DEFAULT_EQUIVALENTS["x"] = "y"  # type: ignore[index]


def test_run_blockers_are_blocking_issues_after_merge() -> None:
    engine = [_i("agent.not_found", node="a"), _i("engine.warn", "warning")]
    team = [
        _i(TeamIssueCodes.AGENT_NOT_FOUND, node="a"),
        _i(TeamIssueCodes.NO_REPLY, "warning", blocks_run=False),
        _i(TeamIssueCodes.NO_ENTRY, blocks_run=True),
    ]
    assert [i.code for i in run_blockers(engine, team)] == [
        "agent.not_found",
        TeamIssueCodes.NO_ENTRY,
    ]
    assert run_blockers([_i("w", "warning")], [_i("x", "error", blocks_run=False)]) == []


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_prepare_run_grants_and_layered_interaction_settings(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead")]
    edges = [
        k.edge("e1", "entry", "me", "lead"),
        k.edge("k1", "ask", "lead", "me", kinds=[k["q"]], timeout_seconds=5),
    ]
    graph = k.graph(nodes, edges, settings={"interaction": {"on_timeout": "cancel_run"}})
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    workspace = WorkspaceSettings.model_validate({"interaction": {"timeout_seconds": 90}})

    prep = prepare_run(graph, plan, workspace)
    assert dict(prep.grants) == dict(plan.grants)
    assert prep.grants["lead"].kinds == [k["q"]]
    assert prep.interaction_settings == InteractionSettings(
        timeout_seconds=90, on_timeout="cancel_run"
    )

    defaults = prepare_run(
        k.graph(nodes, []),
        team_plan(k.graph(nodes, []), node_types=k.node_types, edge_types=k.edge_types),
        None,
    )
    assert dict(defaults.grants) == {}
    assert defaults.interaction_settings == InteractionSettings()
    assert defaults.flow_settings == FlowSettings()


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_prepare_run_layered_flow_settings(k: Kit) -> None:
    """반복·실행 한도(`flow`, design §5R.4): 기본값 → 공통 → 팀 구성, 생략 = 상속."""
    nodes = [k.person(), k.worker("lead")]
    graph = k.graph(nodes, [], settings={"flow": {"max_iterations": 2}})
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    workspace = WorkspaceSettings.model_validate({"flow": {"max_node_runs": 50}})

    prep = prepare_run(graph, plan, workspace)
    assert prep.flow_settings == FlowSettings(max_iterations=2, max_node_runs=50)


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_prepare_run_layered_delegation_settings(k: Kit) -> None:
    """위임 설정(`delegation`, design §5R.6): 기본값 → 공통 → 팀 구성. 엔진 실행 중 깊이 한도."""
    nodes = [k.person(), k.worker("lead")]
    graph = k.graph(nodes, [], settings={"delegation": {"max_depth": 2}})
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    workspace = WorkspaceSettings.model_validate({"delegation": {"max_depth": 5, "max_nesting": 4}})

    prep = prepare_run(graph, plan, workspace)
    assert prep.delegation_settings == DelegationSettings(max_depth=2, max_nesting=4)
    assert delegation_settings(workspace, None) == DelegationSettings(max_depth=5, max_nesting=4)
    assert prepare_run(
        graph.model_copy(update={"settings": None}), plan, None
    ).delegation_settings == (DelegationSettings())


@pytest.mark.parametrize("k", KITS, ids=["default", "renamed"])
def test_prepare_run_grants_follow_shares_session(k: Kit) -> None:
    """5.2R.43: 위임 방식을 주면 엔진 대기 grant가 세션 단위다(같은 세션 대상만 더한다)."""
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("far")]
    edges = [
        k.edge("e1", "entry", "me", "lead"),
        k.edge("d1", "invoke", "lead", "mate"),
        k.edge("d3", "invoke3", "lead", "far"),
        k.edge("k1", "ask", "mate", "me", timeout_seconds=10),
        k.edge("k3", "ask", "far", "me", timeout_seconds=3),
    ]
    graph = k.graph(nodes, edges)
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    prep = prepare_run(graph, plan, None, strategies=k.strategy_map)
    assert prep.grants["lead"].kinds == [k["perm"]]
    assert prep.grants["lead"].timeout_seconds == 10  # 같은 세션 mate 것, far의 3초는 아니다
    assert prep.grants["far"].timeout_seconds == 3  # 자기 세션 대상은 자기 값
    # 방식을 주지 않으면 노드 자신의 연결 grant(옛 동작)
    legacy = prepare_run(graph, plan, None)
    assert "lead" not in legacy.grants
