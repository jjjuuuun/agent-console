"""저장 시점 위임 검사(design §5.2R.7, 5.2R.37 B-1).

일반 규칙(방식 config 스키마 `delegation.invalid_config`, 같은 대상 `delegation.duplicate_member`)과
주입한 방식 고유 검사(`validate_team(delegation_checks=)`·`delegation_static_issues`)를 임의 이름
디스크립터(`KITS`: 기본 이름·바꾼 이름)로 확인한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    BackendCapabilities,
    DelegationStrategyDescriptor,
    Graph,
    Issue,
    WorkspaceSettings,
)
from agent_console_teams import (
    DelegationTarget,
    TeamIssueCodes,
    TeamPlan,
    delegation_static_issues,
    team_plan,
    validate_team,
)
from agent_console_teams.testing import KITS, Kit

C = TeamIssueCodes
IDS = ["default", "renamed"]
WS = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "bk"}})
CAPS = {"bk": BackendCapabilities(subagents=True, host_tools=True)}
FAR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"tool_name": {"type": "string", "pattern": "^[a-z_]{1,8}$"}},
    "additionalProperties": False,
}


def _agents(*ids: str) -> dict[str, Agent]:
    return {
        i: Agent.model_validate({"id": i, "name": i, "role": f"{i}-role", "description": f"{i}?"})
        for i in ids
    }


def _strategies(k: Kit, schema: Mapping[str, Any] | None = FAR_SCHEMA) -> list[Any]:
    out: list[DelegationStrategyDescriptor] = []
    for s in k.strategies:
        if s.id == k["s_far"] and schema is not None:
            s = s.model_copy(update={"config_schema": dict(schema)})
        out.append(s)
    return out


def _validate(k: Kit, graph: Graph, **kwargs: Any) -> list[Issue]:
    kwargs.setdefault("agents", _agents("lead", "mate", "qa"))
    kwargs.setdefault("strategies", _strategies(k))
    return validate_team(
        graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        workspace=WS,
        backends=CAPS,
        resolve_ports=Kit.resolve_ports,
        **kwargs,
    )


def k_plan(k: Kit, graph: Graph) -> TeamPlan:
    return team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)


def _codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def _team(k: Kit, *, lead: Mapping[str, Any] | None = None, extra: Sequence[Any] = ()) -> Graph:
    nodes = [k.person(), k.worker("lead", **dict(lead or {})), k.worker("mate"), k.worker("qa")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke", "lead", "mate"),
        k.edge("d2", "invoke3", "lead", "qa"),
        *extra,
    ]
    return k.graph(nodes, edges)


# ---------------------------------------------------------------- 일반 규칙


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_valid_strategy_config_has_no_issue(k: Kit) -> None:
    graph = _team(k, lead={"delegation": {k["s_far"]: {"tool_name": "ask_qa"}}})
    assert _validate(k, graph) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_strategy_config_is_checked_with_descriptor_schema(k: Kit) -> None:
    bad = {"tool_name": "Bad Name!", "extra": 1}
    graph = _team(k, lead={"delegation": {k["s_far"]: bad}})
    issues = [i for i in _validate(k, graph) if i.code == C.DELEGATION_INVALID_CONFIG]
    assert [(i.path, i.details["validator"]) for i in issues] == [
        (f"/delegation/{k['s_far']}", "additionalProperties"),
        (f"/delegation/{k['s_far']}/tool_name", "pattern"),
    ]
    assert {i.node_id for i in issues} == {"lead"}
    assert {i.severity for i in issues} == {"error"}
    assert {i.details["strategy"] for i in issues} == {k["s_far"]}


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_config_of_unknown_strategy_and_non_delegator_is_ignored(k: Kit) -> None:
    graph = _team(k, lead={"delegation": {"nobody": {"x": 1}}})
    assert C.DELEGATION_INVALID_CONFIG not in _codes(_validate(k, graph))
    # 위임자가 아닌 노드의 같은 키는 보지 않는다(그 노드 타입의 다른 뜻일 수 있다)
    nodes = [*graph.nodes, k.worker("solo", delegation={k["s_far"]: {"tool_name": 3}})]
    other = graph.model_copy(update={"nodes": nodes})
    assert C.DELEGATION_INVALID_CONFIG not in _codes(_validate(k, other))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_broken_descriptor_schema_is_warning(k: Kit) -> None:
    graph = _team(k, lead={"delegation": {k["s_far"]: {}}})
    issues = _validate(k, graph, strategies=_strategies(k, {"type": 12}))
    (issue,) = [i for i in issues if i.code == C.DELEGATION_INVALID_CONFIG_SCHEMA]
    assert issue.severity == "warning"
    assert issue.path == f"/delegation/{k['s_far']}"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_same_member_twice_with_same_strategy_is_error(k: Kit) -> None:
    graph = _team(k, extra=[k.edge("d3", "invoke3", "lead", "qa")])
    (issue,) = [i for i in _validate(k, graph) if i.code == C.DELEGATION_DUPLICATE_MEMBER]
    assert issue.severity == "error"
    assert (issue.edge_id, issue.node_id) == ("d3", "qa")
    assert issue.details == {
        "delegator": "lead",
        "member": "qa",
        "strategy": k["s_far"],
        "edges": ["d2", "d3"],
    }


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_same_member_with_strategy_override_counts_by_effective_strategy(k: Kit) -> None:
    # 다른 연결 종류라도 방식 덮어쓰기로 같은 방식이면 중복이다
    graph = _team(k, extra=[k.edge("d3", "invoke", "lead", "qa", strategy=k["s_far"])])
    assert C.DELEGATION_DUPLICATE_MEMBER in _codes(_validate(k, graph))
    # 다른 방식이면 중복이 아니다(합침은 방식이 정한다)
    graph = _team(k, extra=[k.edge("d3", "invoke", "lead", "qa")])
    assert C.DELEGATION_DUPLICATE_MEMBER not in _codes(_validate(k, graph))


# ---------------------------------------------------------------- 방식 고유 검사(주입)


class _Tools:
    """도구 이름을 알리는 방식(config `tool_name`, 기본 `go`) + 연결 config `bad`를 거절."""

    def __init__(self, descriptor: DelegationStrategyDescriptor | None = None) -> None:
        self.descriptor = descriptor
        self.seen: list[tuple[dict[str, Any], list[DelegationTarget]]] = []

    def static_issues(
        self, config: Mapping[str, Any], members: Sequence[DelegationTarget]
    ) -> list[Issue]:
        self.seen.append((dict(config), list(members)))
        out = [
            Issue(
                severity="error", code="t.bad_edge", message="bad", edge_id=m.edge_id, path="/bad"
            )
            for m in members
            if m.config.get("bad")
        ]
        if config.get("tool_name") == "nope":
            out.append(Issue(severity="error", code="t.rule", message="no", path="/tool_name"))
        return out

    def declared_names(
        self, config: Mapping[str, Any], members: Sequence[DelegationTarget]
    ) -> Mapping[str, list[str]]:
        return {"tool": [str(config.get("tool_name", "go"))]}


class _Subs:
    """하위 에이전트 이름 = 대상 노드 id. `static_issues`는 없다(선택 메서드)."""

    def declared_names(
        self, config: Mapping[str, Any], members: Sequence[DelegationTarget]
    ) -> Mapping[str, list[str]]:
        return {"sub": [m.node_id for m in members], "tool": ["go"]}


class _Broken:
    def static_issues(self, config: Mapping[str, Any], members: Sequence[Any]) -> list[Issue]:
        raise RuntimeError("boom")


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_static_issues_are_injected_and_normalized(k: Kit) -> None:
    tools = _Tools()
    graph = _team(k, lead={"delegation": {k["s_far"]: {"tool_name": "nope"}}})
    edges = [
        e.model_copy(update={"config": {"bad": True}}) if e.id == "d2" else e for e in graph.edges
    ]
    graph = graph.model_copy(update={"edges": edges})
    issues = _validate(k, graph, delegation_checks={k["s_far"]: tools})
    edge_issue = next(i for i in issues if i.code == "t.bad_edge")
    assert (edge_issue.edge_id, edge_issue.node_id, edge_issue.path) == ("d2", None, "/bad")
    rule = next(i for i in issues if i.code == "t.rule")
    assert (rule.node_id, rule.path) == ("lead", f"/delegation/{k['s_far']}/tool_name")
    # 대상: 노드 config가 없으면 에이전트 정의의 역할·설명, 연결 config
    ((config, members),) = tools.seen
    assert config == {"tool_name": "nope"}
    assert members == [
        DelegationTarget(
            node_id="qa",
            edge_id="d2",
            agent_id="qa",
            role="qa-role",
            delegate_when="qa?",
            config={"bad": True},
        )
    ]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_composed_strategies_name_collision_is_error(k: Kit) -> None:
    checks = {k["s_far"]: _Tools(), k["s_inner"]: _Subs()}
    issues = _validate(k, _team(k), delegation_checks=checks)
    (issue,) = [i for i in issues if i.code == "delegation.duplicate_tool_names"]
    assert issue.node_id == "lead"
    assert issue.details == {
        "group": "tool",
        "names": ["go"],
        "strategies": [k["s_inner"], k["s_far"]],
    }
    # 방식 config로 이름을 바꾸면 사라진다
    fixed = _team(k, lead={"delegation": {k["s_far"]: {"tool_name": "ask"}}})
    issues = _validate(k, fixed, delegation_checks=checks)
    assert not [i for i in issues if i.code.startswith("delegation.duplicate_")]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_single_strategy_has_no_name_collision(k: Kit) -> None:
    # 한 방식만 쓰면 합치지 않으므로 이름 충돌을 계산하지 않는다
    graph = _team(k, extra=[])
    edges = [e for e in graph.edges if e.id != "d1"]
    single = graph.model_copy(update={"edges": edges})
    checks = {k["s_far"]: _Subs()}
    issues = delegation_static_issues(k_plan(k, single), checks)
    assert issues == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_non_composable_strategy_is_left_out_of_name_collision(k: Kit) -> None:
    desc = DelegationStrategyDescriptor(
        id="x", title="x", member_fields=[], max_depth=None, composable=False
    )
    checks = {k["s_far"]: _Tools(), k["s_inner"]: _Tools(descriptor=desc)}
    issues = delegation_static_issues(k_plan(k, _team(k)), checks)
    assert not [i for i in issues if i.code.startswith("delegation.duplicate_")]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_failing_check_is_warning_and_others_still_run(k: Kit) -> None:
    checks = {k["s_far"]: _Broken(), k["s_inner"]: _Tools()}
    graph = _team(k, lead={"delegation": {k["s_inner"]: {"tool_name": "nope"}}})
    issues = delegation_static_issues(k_plan(k, graph), checks)
    failed = next(i for i in issues if i.code == C.VALIDATOR_FAILED)
    assert failed.severity == "warning"
    assert failed.details == {"strategy": k["s_far"], "method": "static_issues"}
    assert "t.rule" in _codes(issues)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_delegators_filter_and_no_checks(k: Kit) -> None:
    checks = {k["s_far"]: _Tools(), k["s_inner"]: _Subs()}
    plan = k_plan(k, _team(k))
    assert delegation_static_issues(plan, checks, delegators=["mate"]) == []
    assert len(delegation_static_issues(plan, checks, delegators=["lead"])) == 1
    # 주입하지 않으면 방식 고유 검사는 없다(일반 규칙만)
    assert "delegation.duplicate_tool_names" not in _codes(_validate(k, _team(k)))
