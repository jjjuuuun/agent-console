"""중첩 팀 규칙(design §5R.7·§5R.8 `team` 행): 자기·순환 참조, 깊이, 자식 없음·입구 없음, 버전 고정.

노드가 팀 구성을 묶는지는 디스크립터 `binds.kind == TeamConventions.team_kind`로만 정한다.
임의 이름 디스크립터(`KITS`: 기본 이름·바꾼 이름)로 확인한다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import Agent, Graph, Issue, KnownIssueCodes, WorkspaceSettings
from agent_console_teams import (
    DEFAULT_CONVENTIONS,
    TeamConventions,
    TeamIssueCodes,
    find_team,
    merge_overrides,
    team_plan,
    validate_team,
    with_team_settings,
)
from agent_console_teams.testing import KITS, Kit

C = TeamIssueCodes
IDS = ["default", "renamed"]
WS = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "bk"}})
NESTED = (C.TEAM_RECURSIVE, C.TEAM_NESTING_EXCEEDED, C.TEAM_NOT_FOUND, C.TEAM_CHILD_NO_ENTRY)


class Shelf:
    """팀 구성 조회 흉내: (id, 버전) → 그래프. 받은 요청을 기록한다."""

    def __init__(self, *graphs: Graph, versions: Mapping[tuple[str, str], Graph] | None = None):
        self.latest = {g.id: g for g in graphs}
        self.versions = dict(versions or {})
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, team_id: str, version: str | None) -> Graph | None:
        self.calls.append((team_id, version))
        if version is None:
            return self.latest.get(team_id)
        return self.versions.get((team_id, version))


def _team(k: Kit, graph_id: str, *nests: tuple[str, str | None], settings: Any = None) -> Graph:
    """입구 → lead → (nests…) → 답변 사슬 팀 구성."""
    nodes = [k.person(), k.worker("lead")]
    edges = [k.edge("m1", "entry", "me", "lead")]
    prev = "lead"
    for i, (ref, version) in enumerate(nests):
        nid = f"t{i}"
        nodes.append(k.nest(nid, ref, version))
        edges.append(k.edge(f"h{i}", "flow", prev, nid))
        prev = nid
    edges.append(k.edge("a1", "exit", prev, "me"))
    return k.graph(nodes, edges, settings, graph_id=graph_id)


def _no_entry(k: Kit, graph_id: str) -> Graph:
    return k.graph(
        [k.person(), k.worker("lead")], [k.edge("a1", "exit", "lead", "me")], graph_id=graph_id
    )


def _validate(k: Kit, graph: Graph, **kwargs: Any) -> list[Issue]:
    kwargs.setdefault("agents", {"lead": Agent(id="lead", name="lead")})
    kwargs.setdefault("workspace", WS)
    return validate_team(
        graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        strategies=k.strategies,
        resolve_ports=Kit.resolve_ports,
        **kwargs,
    )


def _nested(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.code in NESTED]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_plan_reads_team_refs_and_pinned_versions_from_binds(k: Kit) -> None:
    graph = _team(k, "parent", ("child", None), ("other", "v1"))
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    assert dict(plan.team_refs) == {"t0": "child", "t1": "other"}
    assert dict(plan.team_versions) == {"t1": "v1"}
    assert "t0" in plan.view.executable
    assert not plan.agent_refs.keys() & plan.team_refs.keys()


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_valid_nesting_has_no_issues(k: Kit) -> None:
    shelf = Shelf(_team(k, "child", ("leaf", None)), _team(k, "leaf"))
    issues = _validate(k, _team(k, "parent", ("child", None)), teams=shelf)
    assert _nested(issues) == []
    assert ("child", None) in shelf.calls
    assert ("leaf", None) in shelf.calls


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_self_reference_is_recursive_even_without_lookup(k: Kit) -> None:
    graph = _team(k, "parent", ("parent", None))
    for teams in (None, Shelf(graph)):
        (issue,) = _nested(_validate(k, graph, teams=teams))
        assert issue.code == KnownIssueCodes.TEAM_RECURSIVE
        assert issue.severity == "error"
        assert issue.node_id == "t0"
        assert issue.path == "/nodes/2/config/crew"
        assert issue.details["path"] == ["parent", "parent"]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_cycle_a_b_a_is_recursive(k: Kit) -> None:
    a = _team(k, "a", ("b", None))
    b = _team(k, "b", ("a", None))
    (issue,) = _nested(_validate(k, a, teams=Shelf(a, b)))
    assert issue.code == C.TEAM_RECURSIVE
    assert issue.details["path"] == ["a", "b", "a"]
    assert "a → b → a" in issue.message
    # 손자에서 순환(b → c → b)도 루트 노드에 한 번 알린다
    b2 = _team(k, "b", ("c", None))
    c = _team(k, "c", ("b", None))
    (deep,) = _nested(_validate(k, a, teams=Shelf(a, b2, c)))
    assert deep.details["path"] == ["a", "b", "c", "b"]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_not_found_and_pinned_version(k: Kit) -> None:
    child = _team(k, "child")
    shelf = Shelf(child, versions={("child", "v1"): child})
    (missing,) = _nested(_validate(k, _team(k, "p", ("ghost", None)), teams=shelf))
    assert missing.code == KnownIssueCodes.TEAM_TEAM_NOT_FOUND
    assert missing.details == {"team": "ghost", "version": None}
    # 고정한 버전은 그 버전으로 조회한다
    assert _nested(_validate(k, _team(k, "p", ("child", "v1")), teams=shelf)) == []
    assert ("child", "v1") in shelf.calls
    (gone,) = _nested(_validate(k, _team(k, "p", ("child", "v9")), teams=shelf))
    assert gone.code == C.TEAM_NOT_FOUND
    assert gone.details == {"team": "child", "version": "v9"}
    assert "child@v9" in gone.message


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_pinned_version_decides_the_nested_walk(k: Kit) -> None:
    """최신은 순환이지만 고정 버전은 순환이 아니면 이슈가 없다(버전마다 따로 따라간다)."""
    a = _team(k, "a", ("b", "old"))
    shelf = Shelf(a, _team(k, "b", ("a", None)), versions={("b", "old"): _team(k, "b")})
    assert _nested(_validate(k, a, teams=shelf)) == []
    a_latest = _team(k, "a", ("b", None))
    assert _nested(_validate(k, a_latest, teams=shelf))[0].code == C.TEAM_RECURSIVE


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_child_without_entry(k: Kit) -> None:
    shelf = Shelf(_no_entry(k, "child"))
    (issue,) = _nested(_validate(k, _team(k, "p", ("child", None)), teams=shelf))
    assert issue.code == KnownIssueCodes.TEAM_CHILD_NO_ENTRY
    assert issue.path == "/nodes/2/config/crew"
    assert issue.details["issues"] == [{"code": C.NO_ENTRY, "severity": "error"}]


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_nesting_limit_comes_from_settings(k: Kit) -> None:
    shelf = Shelf(_team(k, "b", ("c", None)), _team(k, "c", ("d", None)), _team(k, "d"))
    a = _team(k, "a", ("b", None))
    # 기본 한도 3: a(0) → b(1) → c(2) → d(3) 허용
    assert _nested(_validate(k, a, teams=shelf)) == []
    # 팀 구성 층 한도 2: d(3) 초과
    tight = _team(k, "a", ("b", None), settings={"delegation": {"max_nesting": 2}})
    (issue,) = _nested(_validate(k, tight, teams=shelf))
    assert issue.code == KnownIssueCodes.TEAM_NESTING_EXCEEDED
    assert issue.details == {"depth": 3, "limit": 2, "path": ["a", "b", "c", "d"]}
    # 공통 층 한도 1 + null(제한 없음)
    ws1 = WorkspaceSettings.model_validate({"delegation": {"max_nesting": 1}})
    assert _nested(_validate(k, a, teams=shelf, workspace=ws1))[0].details["depth"] == 2
    free = WorkspaceSettings.model_validate({"delegation": {"max_nesting": None}})
    assert _nested(_validate(k, a, teams=shelf, workspace=free)) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_without_lookup_child_checks_are_skipped(k: Kit) -> None:
    assert _nested(_validate(k, _team(k, "p", ("ghost", None)))) == []


def test_team_kind_is_data() -> None:
    """정의 종류 이름을 바꾸면 그 이름으로 묶은 노드만 중첩 팀이다."""
    k = KITS[0]
    graph = _team(k, "p", ("p", None))
    other = TeamConventions(team_kind="crew-def")
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types, conventions=other)
    assert dict(plan.team_refs) == {}
    assert _nested(_validate(k, graph, conventions=other)) == []
    assert DEFAULT_CONVENTIONS.team_kind == "graph"


def test_lookup_errors_mean_not_found() -> None:
    def broken(team_id: str, version: str | None) -> Graph | None:
        raise LookupError(team_id)

    assert find_team(broken, "x") is None


def test_with_team_settings_overrides_only_given_values() -> None:
    k = KITS[0]
    base = _team(
        k, "child", settings={"model": "m1", "flow": {"max_iterations": 2, "max_node_runs": 50}}
    )
    out = with_team_settings(base, {"flow": {"max_iterations": 5}, "delegation": {"max_depth": 2}})
    assert out.settings is not None
    dumped = out.settings.model_dump(exclude_unset=True)
    assert dumped["model"] == "m1"
    assert dumped["flow"] == {"max_iterations": 5, "max_node_runs": 50}
    assert dumped["delegation"] == {"max_depth": 2}
    assert base.settings is not None
    assert base.settings.flow is not None
    assert base.settings.flow.max_iterations == 2  # 원본은 그대로
    assert with_team_settings(base, None) is base
    assert with_team_settings(base, {}) is base
    with pytest.raises(ValidationError):
        with_team_settings(base, {"flow": {"max_iterations": "many"}})


def test_merge_overrides_replaces_lists() -> None:
    assert merge_overrides({"a": {"b": 1, "c": [1]}}, {"a": {"c": [2]}}) == {
        "a": {"b": 1, "c": [2]}
    }
