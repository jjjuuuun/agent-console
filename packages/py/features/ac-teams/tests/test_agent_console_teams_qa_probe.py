"""QA 반례: 입구 추론 금지, 제안 패치 적용 가능성(id 충돌·포트), blocks_run."""

from __future__ import annotations

import pytest

from agent_console_contracts import Graph, Issue
from agent_console_graph import validate_graph
from agent_console_teams import TeamIssueCodes as C
from agent_console_teams import team_plan, validate_team
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]


def _run(k: Kit, graph: Graph) -> list[Issue]:
    return validate_team(
        graph,
        node_types=k.node_types,
        edge_types=k.edge_types,
        strategies=k.strategies,
        resolve_ports=Kit.resolve_ports,
    )


def _apply(graph: Graph, patch) -> Graph:  # type: ignore[no-untyped-def]
    data = graph.model_dump(exclude_unset=True)
    drop = set(patch.remove_edge_ids)
    data["edges"] = [e for e in data["edges"] if e["id"] not in drop]
    data["edges"] += [e.model_dump(exclude_unset=True) for e in patch.add_edges]
    data["nodes"] += [n.model_dump(exclude_unset=True) for n in patch.add_nodes]
    return Graph.model_validate(data)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_agent_without_incoming_is_not_entry_even_with_outgoing_only(k: Kit) -> None:
    nodes = [k.person(), k.worker("a"), k.worker("b")]
    edges = [k.edge("f", "flow", "a", "b"), k.edge("x", "exit", "b", "me")]
    plan = team_plan(k.graph(nodes, edges), node_types=k.node_types, edge_types=k.edge_types)
    assert plan.entry_nodes == ()
    codes = [i.code for i in _run(k, k.graph(nodes, edges))]
    assert C.NO_ENTRY in codes
    assert codes.count(C.UNREACHABLE) == 1  # a only


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_user_node_without_edges_is_not_entry(k: Kit) -> None:
    g = k.graph([k.person(), k.worker("a")], [])
    plan = team_plan(g, node_types=k.node_types, edge_types=k.edge_types)
    assert plan.entry_nodes == ()
    assert plan.answer_nodes == ()


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_all_suggestions_apply_cleanly(k: Kit) -> None:
    # id 충돌을 일부러 만든다: 새로 만들 사용자 노드 id(=노드 타입 id)와 엣지 id가 이미 있다.
    nodes = [k.worker(k["person"]), k.worker("solo"), k.worker("sink")]
    edges = [
        k.edge(f"{k['entry']}-solo", "flow", k["person"], "solo"),
        k.edge("fl", "flow", "solo", "sink"),
    ]
    g = k.graph(nodes, edges)
    issues = _run(k, g)
    n = 0
    for issue in issues:
        for sug in issue.suggestions:
            n += 1
            fixed = _apply(g, sug.patch)
            ids = [x.id for x in fixed.nodes]
            assert len(ids) == len(set(ids)), (issue.code, ids)
            eids = [x.id for x in fixed.edges]
            assert len(eids) == len(set(eids)), (issue.code, eids)
            errs = [
                i
                for i in validate_graph(
                    g, k.node_types, k.edge_types, resolve_ports=Kit.resolve_ports
                )
                if i.severity == "error"
            ]
            after = [
                i
                for i in validate_graph(
                    fixed, k.node_types, k.edge_types, resolve_ports=Kit.resolve_ports
                )
                if i.severity == "error"
            ]
            old = {i.code for i in errs}
            assert not [i for i in after if i.code not in old], [i.model_dump() for i in after]
    assert n > 0
