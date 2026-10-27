"""기본 플러그인으로 본 5R.12 검증(design §5R.8): 반려 되돌리기 사이클과 "반복 연결로 바꾸기" 제안.

엔진 검증(`validate_graph_with`, 서버 저장 전 검사 경로)과 팀 검증(`ac-teams.validate_team`) 둘 다
같은 디스크립터 `cycle`로 판단한다. 이 배포의 entry point만 로드한다.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from agent_console_contracts import EdgeSpec, Graph, NodeSpec, WorkspaceSettings
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    Registries,
    load_registries,
    port_resolver,
    validate_graph_with,
)
from agent_console_teams import catalog_from_registries, validate_team

DIST = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
REVIEW = {"review": {"decisions": [{"id": "approved"}, {"id": "rejected"}]}}


def registries() -> Registries:
    eps = [ep for ep in importlib.metadata.distribution(DIST).entry_points if ep.group in GROUPS]
    regs = Registries()
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    return regs


def e(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
        }
    )


def review_graph(back_kind: str) -> Graph:
    def node(nid: str, type: str, **config: Any) -> NodeSpec:
        return NodeSpec.model_validate({"id": nid, "type": type, "label": nid, "config": config})

    return Graph(
        id="team",
        name="검토 반복",
        nodes=[
            node("you", "user"),
            node("w", "agent", agent_ref="writer"),
            node("rv", "user", **REVIEW),
            node("n", "agent", agent_ref="next"),
        ],
        edges=[
            e("m", "you", "says", "w", "in", "message"),
            e("h1", "w", "out", "rv", "review", "handoff"),
            e("ok", "rv", "approved", "n", "in", "handoff"),
            e("back", "rv", "rejected", "w", "in", back_kind),
            e("r2", "n", "out", "you", "hears", "reply"),
        ],
    )


def team_issues(regs: Registries, graph: Graph) -> list[Any]:
    catalog = catalog_from_registries(regs)
    return validate_team(
        graph,
        node_types=catalog.node_types,
        edge_types=catalog.edge_types,
        strategies=catalog.strategies.values(),
        workspace=WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}}),
        resolve_ports=port_resolver(regs),
    )


def test_reject_back_cycle_suggests_cycle_kind_in_engine_and_team_checks() -> None:
    regs = registries()
    graph = review_graph("handoff")
    for issues in (validate_graph_with(graph, regs), team_issues(regs, graph)):
        (cycle,) = [i for i in issues if i.code == "cycle"]
        (sug,) = cycle.suggestions
        assert sug.patch.remove_edge_ids == ["back"]
        (edge,) = sug.patch.add_edges
        desc = regs.edge_types.get(edge.kind).descriptor
        assert desc.cycle is not None  # 이름이 아니라 디스크립터 `cycle`로 고른 종류
        assert (edge.source.port, edge.target.port) == ("rejected", "in")
    fixed = graph.model_copy(update={"edges": [x for x in graph.edges if x.id != "back"] + [edge]})
    assert [i.code for i in validate_graph_with(fixed, regs) if i.severity == "error"] == []
    assert team_issues(regs, fixed) == []
