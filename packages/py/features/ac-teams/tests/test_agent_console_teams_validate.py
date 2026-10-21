"""validate_team: §R3.1b 규칙, 입구·답변·도달, 상호작용 검증과 제안 데이터.

모두 임의 이름 디스크립터로 확인한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    EdgeSpec,
    Graph,
    InteractionGrant,
    Issue,
    NodeSpec,
    WorkspaceSettings,
)
from agent_console_resources import InMemoryResources
from agent_console_teams import SettingsValidator, TeamIssueCodes, team_plan, validate_team
from agent_console_teams.testing import KITS, Kit

C = TeamIssueCodes
IDS = ["default", "renamed"]


def _agents(*ids: str, **extra: dict[str, Any]) -> dict[str, Agent]:
    return {i: Agent.model_validate({"id": i, "name": i, **extra.get(i, {})}) for i in ids}


WS = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "bk"}})
CAPS = {"bk": BackendCapabilities(subagents=True)}


def _validate(k: Kit, graph: Graph, **kwargs: Any) -> list[Issue]:
    kwargs.setdefault("agents", _agents("lead", "mate", "qa", "c", "be"))
    kwargs.setdefault("workspace", WS)
    kwargs.setdefault("backends", CAPS)
    return validate_team(
        graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        strategies=k.strategies,
        resolve_ports=Kit.resolve_ports,
        **kwargs,
    )


def _codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def _one(issues: list[Issue], code: str) -> Issue:
    found = [i for i in issues if i.code == code]
    assert len(found) == 1, (code, _codes(issues))
    return found[0]


def _base(k: Kit) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.material("guide", "g")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("d1", "invoke", "lead", "mate"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("r1", "attach", "guide", "lead"),
        k.edge("k1", "ask", "lead", "me"),
    ]
    return nodes, edges


# ---------------------------------------------------------------- 통과·입구·답변·도달


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_valid_team_has_no_issues(k: Kit) -> None:
    nodes, edges = _base(k)
    assert _validate(k, k.graph(nodes, edges)) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_entry_is_error_with_suggestion_to_existing_user_node(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead")]
    edges = [k.edge("a1", "exit", "lead", "me")]
    issues = _validate(k, k.graph(nodes, edges))
    issue = _one(issues, C.NO_ENTRY)
    assert issue.severity == "error"
    assert issue.blocks_run is True
    (sug,) = issue.suggestions
    assert sug.patch.add_nodes == []
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["entry"]
    assert (edge.source.node, edge.source.port) == ("me", "mouth")
    assert (edge.target.node, edge.target.port) == ("lead", "inbox")
    # 제안을 적용하면 입구 이슈가 사라진다
    fixed = k.graph(nodes, [*edges, edge])
    assert C.NO_ENTRY not in _codes(_validate(k, fixed))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_entry_suggestion_creates_user_node_when_missing(k: Kit) -> None:
    graph = k.graph([k.worker("solo")], [])
    issues = _validate(k, graph)
    issue = _one(issues, C.NO_ENTRY)
    (sug,) = issue.suggestions
    (node,) = sug.patch.add_nodes
    assert node.type == k["person"]
    (edge,) = sug.patch.add_edges
    assert edge.source.node == node.id
    assert edge.target.node == "solo"
    no_reply = _one(issues, C.NO_REPLY)
    assert no_reply.severity == "warning"
    assert no_reply.blocks_run is False
    (reply,) = no_reply.suggestions
    assert reply.patch.add_edges[0].kind == k["exit"]
    assert reply.patch.add_edges[0].source.node == "solo"
    unreachable = _one(issues, C.UNREACHABLE)
    assert unreachable.node_id == "solo"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_reply_is_warning_and_suggests_sink_nodes(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("qa")]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("h1", "flow", "lead", "qa")]
    issue = _one(_validate(k, k.graph(nodes, edges)), C.NO_REPLY)
    targets = [s.patch.add_edges[0].source.node for s in issue.suggestions]
    assert targets == ["qa"]
    assert issue.suggestions[0].patch.add_edges[0].target.node == "me"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_unreachable_node_warning(k: Kit) -> None:
    nodes, edges = _base(k)
    nodes.append(k.worker("qa"))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.UNREACHABLE)
    assert issue.node_id == "qa"
    assert issue.suggestions[0].patch.add_edges[0].target.node == "qa"


def test_user_node_alone_is_not_unreachable_and_round_trip_is_not_a_cycle() -> None:
    k = Kit()
    nodes = [k.person(), k.person("me2"), k.worker("lead")]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")]
    issues = _validate(k, k.graph(nodes, edges))
    assert issues == []


def test_entry_into_non_executable_node() -> None:
    k = Kit()
    nodes = [k.person(), k.worker("lead"), k.material("guide", "g")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("m2", "entry", "me", "guide", dport="give"),
        k.edge("a1", "exit", "lead", "me"),
    ]
    issues = _validate(k, k.graph(nodes, edges), graph_checks=False)
    assert _one(issues, C.ENTRY_NOT_EXECUTABLE).edge_id == "m2"
    assert _one(issues, C.CONNECTS_MISMATCH).edge_id == "m2"


def test_refs_checked_only_when_lookups_given() -> None:
    k = Kit()
    nodes, edges = _base(k)
    graph = k.graph(nodes, edges)
    issues = _validate(k, graph, agents=_agents("lead"), resources=InMemoryResources([]))
    assert _one(issues, C.AGENT_NOT_FOUND).node_id == "mate"
    assert _one(issues, C.RESOURCE_NOT_FOUND).node_id == "guide"
    assert C.AGENT_NOT_FOUND not in _codes(_validate(k, graph, agents=None))


# ---------------------------------------------------------------- 위임 규칙(§R3.1b)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_member_with_its_own_delegation_exceeds_descriptor_depth(k: Kit) -> None:
    nodes, edges = _base(k)
    nodes.append(k.worker("c"))
    edges.append(k.edge("d2", "invoke", "mate", "c"))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.DELEGATION_TOO_DEEP)
    assert issue.edge_id == "d2"
    assert issue.details["depth"] == 2
    assert issue.details["max_depth"] == 1


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_depth_from_settings_when_descriptor_has_none(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("c")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke2", "lead", "mate"),
        k.edge("d2", "invoke2", "mate", "c"),
    ]
    assert C.DELEGATION_TOO_DEEP not in _codes(_validate(k, k.graph(nodes, edges)))
    limited = k.graph(nodes, edges, settings={"delegation": {"max_depth": 1}})
    issue = _one(_validate(k, limited), C.DELEGATION_TOO_DEEP)
    assert issue.edge_id == "d2"
    # 공통 설정에서도 같은 값을 쓴다(팀 구성이 덮어씀)
    ws = WorkspaceSettings.model_validate(
        {"agent_defaults": {"backend": "bk"}, "delegation": {"max_depth": 1}}
    )
    assert C.DELEGATION_TOO_DEEP in _codes(_validate(k, k.graph(nodes, edges), workspace=ws))
    relaxed = k.graph(nodes, edges, settings={"delegation": {"max_depth": 3}})
    assert C.DELEGATION_TOO_DEEP not in _codes(_validate(k, relaxed, workspace=ws))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_delegation_cycle(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("c")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke2", "lead", "mate"),
        k.edge("d2", "invoke2", "mate", "c"),
        k.edge("d3", "invoke2", "c", "mate"),
    ]
    issues = _validate(k, k.graph(nodes, edges))
    assert _codes(issues).count(C.DELEGATION_CYCLE) == 1


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_member_cannot_send_flow_but_can_reply(k: Kit) -> None:
    nodes, edges = _base(k)
    nodes.append(k.worker("qa"))
    edges += [k.edge("h1", "flow", "mate", "qa"), k.edge("a2", "exit", "mate", "me")]
    issues = _validate(k, k.graph(nodes, edges))
    issue = _one(issues, C.FLOW_FROM_DELEGATE)
    assert issue.edge_id == "h1"
    assert issue.severity == "error"
    # 같은 그래프를 흐름을 허용하는 위임 방식으로 바꾸면 오류가 없다
    edges2 = [e.model_copy(update={"kind": k["invoke2"]}) if e.id == "d1" else e for e in edges]
    assert C.FLOW_FROM_DELEGATE not in _codes(_validate(k, k.graph(nodes, edges2)))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_node_both_scheduled_and_invoked(k: Kit) -> None:
    nodes, edges = _base(k)
    edges.append(k.edge("m2", "entry", "me", "mate"))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.MIXED_INVOCATION)
    assert issue.node_id == "mate"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_mixed_and_unknown_strategies(k: Kit) -> None:
    nodes, edges = _base(k)
    nodes += [k.worker("qa"), k.worker("c")]
    edges += [
        k.edge("d2", "invoke2", "lead", "qa"),
        k.edge("d3", "invoke", "lead", "c", strategy="not-registered"),
    ]
    issues = _validate(k, k.graph(nodes, edges))
    mixed = _one(issues, C.MIXED_STRATEGIES)
    assert mixed.node_id == "lead"
    assert mixed.details["strategies"] == [k["s_inner"], k["s_deep"], "not-registered"]
    assert _one(issues, C.UNKNOWN_STRATEGY).edge_id == "d3"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_backend_capability_required_by_strategy(k: Kit) -> None:
    nodes, edges = _base(k)
    caps = {"bk": BackendCapabilities(subagents=False)}
    issue = _one(_validate(k, k.graph(nodes, edges), backends=caps), C.BACKEND_CAPABILITY_MISSING)
    assert issue.node_id == "lead"
    assert issue.details["capability"] == "subagents"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_member_field_outside_member_fields_is_ignored_warning(k: Kit) -> None:
    nodes, edges = _base(k)
    agents = _agents("lead", "mate", mate={"backend": "other", "model": "m-x"})
    issues = _validate(k, k.graph(nodes, edges), agents=agents)
    issue = _one(issues, C.MEMBER_FIELD_IGNORED)
    assert issue.details == {"field": "backend", "strategy": k["s_inner"]}
    assert issue.node_id == "mate"


def test_flow_cycle_including_review_reject_back_is_graph_cycle() -> None:
    k = Kit()
    review = {"review": {"decisions": [{"id": "ok"}, {"id": "no"}]}}
    nodes = [k.person(), k.person("rv", **review), k.worker("lead"), k.worker("be")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("h1", "flow", "lead", "rv", dport="look"),
        k.edge("h2", "flow", "rv", "be", sport="ok"),
        k.edge("h3", "flow", "rv", "lead", sport="no"),  # 반려를 앞 노드로 되돌림
        k.edge("a1", "exit", "be", "me"),
    ]
    assert "cycle" in _codes(_validate(k, k.graph(nodes, edges)))


# ---------------------------------------------------------------- 상호작용(§R14)


class _Hook:
    """묻는 모드("ask-mode")인데 grant에 perm 종류가 없으면 no_path."""

    def __init__(self, perm: str) -> None:
        self.perm = perm
        self.calls: list[tuple[AgentSettings, InteractionGrant]] = []

    def validate_settings(self, effective: AgentSettings, grant: InteractionGrant) -> list[Issue]:
        self.calls.append((effective, grant))
        options = effective.backend_options or {}
        if options.get("mode") == "ask-mode" and self.perm not in grant.kinds:
            return [
                Issue(
                    severity="warning",
                    code=C.INTERACTION_NO_PATH,
                    message="묻는 모드인데 응답 경로가 없습니다",
                    details={"kinds": [self.perm]},
                )
            ]
        return []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_path_from_backend_hook_with_suggestion(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead")]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")]
    agents = _agents("lead", lead={"backend_options": {"mode": "ask-mode"}})
    hook = _Hook(k["perm"])
    assert isinstance(hook, SettingsValidator)
    graph = k.graph(nodes, edges)
    issues = _validate(k, graph, agents=agents, settings_validators={"bk": hook})
    issue = _one(issues, C.INTERACTION_NO_PATH)
    assert issue.node_id == "lead"
    (sug,) = issue.suggestions
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["ask"]
    assert (edge.source.node, edge.target.node) == ("lead", "me")
    assert hook.calls[0][1] == InteractionGrant()
    # 제안 적용 후에는 훅이 grant를 받고 경고가 사라진다
    fixed = k.graph(nodes, [*edges, edge])
    assert C.INTERACTION_NO_PATH not in _codes(
        _validate(k, fixed, agents=agents, settings_validators={"bk": hook})
    )
    # 훅이 없으면 검사를 건너뛴다
    assert C.INTERACTION_NO_PATH not in _codes(_validate(k, graph, agents=agents))


def test_hook_called_for_delegator_session_grant_only() -> None:
    k = Kit()
    nodes, edges = _base(k)
    edges = [e for e in edges if e.id != "k1"] + [k.edge("k2", "ask", "mate", "me")]
    hook = _Hook(k["perm"])
    _validate(k, k.graph(nodes, edges), settings_validators={"bk": hook})
    assert len(hook.calls) == 1  # 위임받는 mate는 따로 부르지 않는다
    assert hook.calls[0][1].kinds == [k["perm"]]  # member_interaction_kinds로 거른 위임 대상 grant


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_hook_checks_own_session_member_with_its_own_grant(k: Kit) -> None:
    """5.2R.43: 자기 세션 방식(`shares_session` false) 대상은 자기 grant로 따로 검사한다."""
    nodes, edges = _base(k)
    nodes = [*nodes, k.worker("be")]
    edges = [
        *[e for e in edges if e.id != "k1"],
        k.edge("d3", "invoke3", "lead", "be"),
        k.edge("k3", "ask", "be", "me", timeout_seconds=3),
    ]
    hook = _Hook(k["perm"])
    caps = {"bk": BackendCapabilities(subagents=True, host_tools=True)}
    _validate(k, k.graph(nodes, edges), settings_validators={"bk": hook}, backends=caps)
    grants = [grant for _settings, grant in hook.calls]
    assert len(grants) == 2  # lead(위임자 세션) + be(자기 세션). 같은 세션 대상 mate는 없다
    lead_grant, be_grant = grants
    assert lead_grant == InteractionGrant()  # be의 종류·대기 한도가 위임자에게 오지 않는다
    assert be_grant.kinds == [k["q"], k["perm"]]
    assert be_grant.timeout_seconds == 3


def test_hook_exception_becomes_warning() -> None:
    k = Kit()
    nodes, edges = _base(k)

    class Broken:
        def validate_settings(
            self, effective: AgentSettings, grant: InteractionGrant
        ) -> list[Issue]:
            raise RuntimeError("secret-value")

    issues = _validate(k, k.graph(nodes, edges), settings_validators={"bk": Broken()})
    issue = _one(issues, C.VALIDATOR_FAILED)
    assert "secret-value" not in issue.message


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_unsupported_in_delegate_with_narrow_suggestion(k: Kit) -> None:
    nodes, edges = _base(k)
    edges.append(k.edge("k2", "ask", "mate", "me"))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.INTERACTION_UNSUPPORTED_IN_DELEGATE)
    assert issue.edge_id == "k2"
    assert issue.details["kinds"] == [k["q"]]
    (sug,) = issue.suggestions
    assert sug.patch.remove_edge_ids == ["k2"]
    assert sug.patch.add_edges[0].config == {"kinds": [k["perm"]]}
    narrowed = [
        e.model_copy(update={"config": {"kinds": [k["perm"]]}}) if e.id == "k2" else e
        for e in edges
    ]
    assert C.INTERACTION_UNSUPPORTED_IN_DELEGATE not in _codes(
        _validate(k, k.graph(nodes, narrowed))
    )


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_unsupported_by_backend_uses_session_owner_backend(k: Kit) -> None:
    nodes, edges = _base(k)
    edges.append(k.edge("k2", "ask", "mate", "me", kinds=[k["perm"]]))
    caps = {"bk": BackendCapabilities(subagents=True, interactions=[k["q"]])}
    issues = _validate(k, k.graph(nodes, edges), backends=caps)
    found = [i for i in issues if i.code == C.INTERACTION_UNSUPPORTED_BY_BACKEND]
    assert {(i.node_id, i.edge_id) for i in found} == {("lead", "k1"), ("mate", "k2")}
    lead = next(i for i in found if i.node_id == "lead")
    assert lead.suggestions[0].patch.add_edges[0].config == {"kinds": [k["q"]]}
    mate = next(i for i in found if i.node_id == "mate")
    assert mate.suggestions[0].patch.remove_edge_ids == ["k2"]
    assert mate.suggestions[0].patch.add_edges == []


def test_kinds_not_allowed_by_descriptor() -> None:
    k = Kit()
    nodes, edges = _base(k)
    edges = [e for e in edges if e.id != "k1"] + [k.edge("k1", "ask", "lead", "me", kinds=["zzz"])]
    issue = _one(_validate(k, k.graph(nodes, edges)), C.INTERACTION_KINDS_NOT_ALLOWED)
    assert issue.details["kinds"] == ["zzz"]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_review_dead_end_with_reply_suggestion(k: Kit) -> None:
    review = {
        "review": {"decisions": [{"id": "ok", "label": "승인"}, {"id": "no", "label": "반려"}]}
    }
    nodes = [k.person(), k.person("rv", **review), k.worker("lead"), k.worker("be")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("h1", "flow", "lead", "rv", dport="look"),
        k.edge("h2", "flow", "rv", "be", sport="ok"),
        k.edge("a1", "exit", "be", "me"),
    ]
    issues = _validate(k, k.graph(nodes, edges))
    issue = _one(issues, C.REVIEW_DEAD_END)
    assert issue.node_id == "rv"
    assert issue.details["decision"] == "no"
    (sug,) = issue.suggestions
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["exit"]
    assert (edge.source.node, edge.source.port) == ("rv", "no")
    assert edge.target.node == "me"
    fixed = k.graph(nodes, [*edges, edge])
    assert _validate(k, fixed) == []


def test_review_config_on_unscheduled_user_node_is_not_checked() -> None:
    k = Kit()
    review = {"review": {"decisions": [{"id": "ok"}]}}
    nodes = [k.person("me", **review), k.worker("lead")]
    edges = [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")]
    assert C.REVIEW_DEAD_END not in _codes(_validate(k, k.graph(nodes, edges)))


def test_plan_can_be_reused_and_graph_checks_skipped() -> None:
    k = Kit()
    nodes, edges = _base(k)
    graph = k.graph(nodes, edges)
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    assert _validate(k, graph, plan=plan, graph_checks=False) == []
