"""5R 검증 규칙(design §5R.8): 사이클 연결·반려 되돌리기·최대 반복·반복 영역 안 위임 대상,
혼합 위임 `composable`, 독립 위임형 방식 규칙(흐름 금지·깊이 = 설정·되묻기 제한 없음).

모두 임의 이름 디스크립터(`KITS`: 기본 이름·바꾼 이름)로 확인한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    BackendCapabilities,
    EdgeSpec,
    Graph,
    Issue,
    KnownIssueCodes,
    NodeSpec,
    WorkspaceSettings,
)
from agent_console_teams import TeamIssueCodes, validate_team
from agent_console_teams.testing import KITS, Kit

C = TeamIssueCodes
IDS = ["default", "renamed"]
WS = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "bk"}})
CAPS = {"bk": BackendCapabilities(subagents=True, host_tools=True)}


def _agents(*ids: str, **extra: dict[str, Any]) -> dict[str, Agent]:
    return {i: Agent.model_validate({"id": i, "name": i, **extra.get(i, {})}) for i in ids}


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


def _review(k: Kit, back: EdgeSpec) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    """작성자(lead) → 사람 검토(rv) → 승인이면 be → 답변, 반려(`no`)는 `back`으로."""
    review = {"review": {"decisions": [{"id": "ok"}, {"id": "no"}]}}
    nodes = [k.person(), k.person("rv", **review), k.worker("lead"), k.worker("be")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("h1", "flow", "lead", "rv", dport="look"),
        k.edge("h2", "flow", "rv", "be", sport="ok"),
        back,
        k.edge("a1", "exit", "be", "me"),
    ]
    return nodes, edges


# ---------------------------------------------------------------- 반복(사이클 연결)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_review_reject_back_with_cycle_edge_is_allowed(k: Kit) -> None:
    nodes, edges = _review(k, k.edge("h3", "loop", "rv", "lead", sport="no"))
    assert _validate(k, k.graph(nodes, edges)) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_cycle_without_cycle_edge_suggests_switching_back_edge(k: Kit) -> None:
    nodes, edges = _review(k, k.edge("h3", "flow", "rv", "lead", sport="no"))
    issues = _validate(k, k.graph(nodes, edges))
    issue = _one(issues, "cycle")
    assert issue.severity == "error"
    (sug,) = issue.suggestions
    assert sug.patch.remove_edge_ids == ["h3"]
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["loop"]  # 디스크립터 `cycle`로 고른 종류(이름 무관)
    assert (edge.id, edge.source.port, edge.target.port) == ("h3", "no", "inbox")
    assert "되감기" in sug.label
    fixed = k.graph(nodes, [e for e in edges if e.id != "h3"] + [edge])
    assert _validate(k, fixed) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_max_iterations_invalid_on_edge(k: Kit) -> None:
    nodes, edges = _review(k, k.edge("h3", "loop", "rv", "lead", sport="no", max_iterations=0))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.MAX_ITERATIONS_INVALID)
    assert issue.code == KnownIssueCodes.FLOW_MAX_ITERATIONS_INVALID
    assert issue.severity == "error"
    assert (issue.edge_id, issue.path) == ("h3", "/max_iterations")
    assert issue.details == {"value": 0, "effective": 0}
    assert "현재 유효 값: 0" in issue.message
    # 엣지 값이 우선한다: 설정에 1 이상이 있어도 엣지 0은 오류
    flowed = k.graph(nodes, edges, settings={"flow": {"max_iterations": 5}})
    assert C.MAX_ITERATIONS_INVALID in _codes(_validate(k, flowed))
    # 엣지 값을 비우면 설정 → 디스크립터 순으로 물려받아 문제없다
    edges2 = [e.model_copy(update={"config": {}}) if e.id == "h3" else e for e in edges]
    assert _validate(k, flowed.model_copy(update={"edges": edges2})) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_max_iterations_not_integer_has_no_effective_value(k: Kit) -> None:
    nodes, edges = _review(k, k.edge("h3", "loop", "rv", "lead", sport="no", max_iterations=True))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.MAX_ITERATIONS_INVALID)
    assert issue.details["effective"] is None
    assert "현재 유효 값: 없음" in issue.message


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_node_invoked_only_inside_loop_region_is_error(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("qa")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke2", "lead", "mate"),  # 흐름을 내보낼 수 있는 위임 방식
        k.edge("h1", "flow", "mate", "qa"),
        k.edge("b1", "loop", "qa", "mate"),
    ]
    issues = _validate(k, k.graph(nodes, edges))
    issue = _one(issues, C.LOOP_INVOKED_ONLY)
    assert (issue.node_id, issue.edge_id) == ("mate", "b1")
    assert issue.details["region"] == ["mate", "qa"]
    assert issue.details["delegation_edges"] == ["d1"]
    # 사이클 연결만 들어오는 것은 "흐름으로도 받음"이 아니다
    assert C.MIXED_INVOCATION not in _codes(issues)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_node_reached_only_by_closing_cycle_edge_is_unreachable(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("qa")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("b1", "loop", "qa", "qa"),
    ]
    issue = _one(_validate(k, k.graph(nodes, edges)), C.UNREACHABLE)
    assert issue.node_id == "qa"


# ---------------------------------------------------------------- 혼합 위임(composable)


def _mixed(k: Kit, second: EdgeSpec) -> tuple[list[NodeSpec], list[EdgeSpec]]:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("qa")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke", "lead", "mate"),
        second,
    ]
    return nodes, edges


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_mixed_composable_strategies_are_allowed(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa"))
    assert _validate(k, k.graph(nodes, edges)) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_mixed_with_non_composable_strategy_suggests_joinable_kind(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke2", "lead", "qa"))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.MIXED_STRATEGIES)
    assert issue.code == KnownIssueCodes.TEAM_MIXED_STRATEGIES
    assert issue.node_id == "lead"
    assert issue.details == {
        "strategies": [k["s_inner"], k["s_deep"]],
        "not_composable": [k["s_deep"]],
    }
    (sug,) = issue.suggestions
    assert sug.id == "compose:d2"
    assert sug.patch.remove_edge_ids == ["d2"]
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["invoke"]  # 이미 쓰는 합칠 수 있는 방식을 먼저 고른다
    assert (edge.source.port, edge.target.port) == ("calls", "called")
    fixed = k.graph(nodes, [*edges[:3], edge])
    assert C.MIXED_STRATEGIES not in _codes(_validate(k, fixed))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_mixed_suggestion_drops_strategy_override(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke", "lead", "qa", strategy=k["s_deep"]))
    issue = _one(_validate(k, k.graph(nodes, edges)), C.MIXED_STRATEGIES)
    (sug,) = issue.suggestions
    (edge,) = sug.patch.add_edges
    assert edge.kind == k["invoke3"]  # 같은 종류는 후보가 아니다
    assert edge.config == {}  # 방식 덮어쓰기 키는 옮기지 않는다
    fixed = k.graph(nodes, [*edges[:3], edge])
    assert C.MIXED_STRATEGIES not in _codes(_validate(k, fixed))


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_unknown_strategy_is_not_composable(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa", strategy="not-registered"))
    issues = _validate(k, k.graph(nodes, edges))
    assert _one(issues, C.MIXED_STRATEGIES).details["not_composable"] == ["not-registered"]
    assert _one(issues, C.UNKNOWN_STRATEGY).edge_id == "d2"


# ---------------------------------------------------------------- 독립 위임형 방식(host 규칙)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_far_member_cannot_send_flow(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa"))
    nodes.append(k.worker("be"))
    edges.append(k.edge("h1", "flow", "qa", "be"))
    assert _one(_validate(k, k.graph(nodes, edges)), C.FLOW_FROM_DELEGATE).edge_id == "h1"


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_far_depth_comes_from_settings_only(k: Kit) -> None:
    nodes = [k.person(), k.worker("lead"), k.worker("mate"), k.worker("c")]
    edges = [
        k.edge("m1", "entry", "me", "lead"),
        k.edge("a1", "exit", "lead", "me"),
        k.edge("d1", "invoke3", "lead", "mate"),
        k.edge("d2", "invoke3", "mate", "c"),
    ]
    assert C.DELEGATION_DEPTH_EXCEEDED not in _codes(_validate(k, k.graph(nodes, edges)))
    limited = k.graph(nodes, edges, settings={"delegation": {"max_depth": 1}})
    issue = _one(_validate(k, limited), C.DELEGATION_DEPTH_EXCEEDED)
    assert issue.code == KnownIssueCodes.DELEGATION_DEPTH_EXCEEDED
    assert issue.edge_id == "d2"
    assert issue.details["path"] == ["lead", "mate", "c"]
    assert "LEAD → MATE → C" in issue.message


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_far_member_interactions_and_fields_are_unrestricted(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa"))
    edges.append(k.edge("k2", "ask", "qa", "me"))
    agents = _agents("lead", "mate", "qa", qa={"backend": "bk", "model": "m-x"})
    issues = _validate(k, k.graph(nodes, edges), agents=agents)
    assert C.INTERACTION_UNSUPPORTED_IN_DELEGATE not in _codes(issues)
    assert C.MEMBER_FIELD_IGNORED not in _codes(issues)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_far_requires_backend_capability_from_descriptor(k: Kit) -> None:
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa"))
    caps = {"bk": BackendCapabilities(subagents=True)}
    issue = _one(_validate(k, k.graph(nodes, edges), backends=caps), C.BACKEND_CAPABILITY_MISSING)
    assert issue.details["capability"] == "host_tools"


# ---------------------------------------------------------------- 연결 의미 검사 주입


def test_edge_checks_are_injected_and_appended() -> None:
    k = Kit()
    nodes, edges = _mixed(k, k.edge("d2", "invoke3", "lead", "qa"))
    graph = k.graph(nodes, edges)
    seen: list[Graph] = []

    def edge_checks(g: Graph) -> list[Issue]:
        seen.append(g)
        return [Issue(severity="warning", code="x.edge", message="m", edge_id="d2")]

    issues = _validate(k, graph, edge_checks=edge_checks)
    assert seen == [graph]
    assert _codes(issues) == ["x.edge"]
