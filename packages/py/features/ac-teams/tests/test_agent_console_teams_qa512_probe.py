"""QA 5R.12 반례: 제안 적용 후 재검증, 다중 노드 사이클, 맞는 종류 없음, 숨김 종류, 중복 이슈."""

from __future__ import annotations

import pytest

from agent_console_contracts import Graph, Issue, UiHints
from agent_console_teams import validate_team
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]


def _run(k: Kit, g: Graph, edge_types=None, **kw) -> list[Issue]:  # type: ignore[no-untyped-def]
    return validate_team(
        g,
        node_types=k.node_types,
        edge_types=edge_types if edge_types is not None else k.edge_types,
        strategies=k.strategies,
        resolve_ports=Kit.resolve_ports,
        **kw,
    )


def _tri(k: Kit, kind: str = "flow"):  # type: ignore[no-untyped-def]
    nodes = [k.person(), k.worker("a"), k.worker("b"), k.worker("c")]
    edges = [
        k.edge("m1", "entry", "me", "a"),
        k.edge("f1", "flow", "a", "b"),
        k.edge("f2", "flow", "b", "c"),
        k.edge("f3", kind, "c", "a"),
        k.edge("x1", "exit", "c", "me"),
    ]
    return nodes, edges


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_three_node_cycle_one_issue_one_suggestion_fixes_it(k: Kit) -> None:
    nodes, edges = _tri(k)
    g = k.graph(nodes, edges)
    cyc = [i for i in _run(k, g) if i.code == "cycle"]
    assert len(cyc) == 1
    (sug,) = cyc[0].suggestions
    assert sug.patch.remove_edge_ids == ["f3"]
    (new,) = sug.patch.add_edges
    assert (new.id, new.source.node, new.target.node) == ("f3", "c", "a")
    assert new.kind == k["loop"]
    fixed = k.graph(nodes, [e for e in edges if e.id != "f3"] + [new])
    assert _run(k, fixed) == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_self_loop_flow_suggestion_fixes(k: Kit) -> None:
    nodes = [k.person(), k.worker("a")]
    edges = [
        k.edge("m1", "entry", "me", "a"),
        k.edge("s", "flow", "a", "a"),
        k.edge("x1", "exit", "a", "me"),
    ]
    g = k.graph(nodes, edges)
    (cyc,) = [i for i in _run(k, g) if i.code == "cycle"]
    (new,) = cyc.suggestions[0].patch.add_edges
    fixed = k.graph(nodes, [edges[0], new, edges[2]])
    assert [i for i in _run(k, fixed) if i.severity == "error"] == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_cycle_kind_means_no_suggestion(k: Kit) -> None:
    nodes, edges = _tri(k)
    kinds = [e for e in k.edge_types if e.cycle is None]
    (cyc,) = [i for i in _run(k, k.graph(nodes, edges), edge_types=kinds) if i.code == "cycle"]
    assert cyc.suggestions == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_hidden_cycle_kind_not_suggested(k: Kit) -> None:
    nodes, edges = _tri(k)
    kinds = [
        e.model_copy(update={"ui_hints": UiHints(hidden=True)}) if e.cycle else e
        for e in k.edge_types
    ]
    (cyc,) = [i for i in _run(k, k.graph(nodes, edges), edge_types=kinds) if i.code == "cycle"]
    assert cyc.suggestions == []


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_edge_checks_not_duplicated_with_graph_checks(k: Kit) -> None:
    nodes, edges = _tri(k, "loop")
    g = k.graph(nodes, edges)
    base = _run(k, g)
    assert base == []
    again = _run(k, g, edge_checks=lambda _g: [])
    assert again == base


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_no_presets_needed_cycle_edge_keeps_config(k: Kit) -> None:
    nodes, edges = _tri(k, "loop")
    edges[3] = k.edge("f3", "loop", "c", "a", max_iterations=2)
    assert _run(k, k.graph(nodes, edges)) == []
