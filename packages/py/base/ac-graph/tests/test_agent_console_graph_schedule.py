"""schedule_view: 엣지 `scheduling`·노드 `executable`로만 입구·답변·스케줄 대상을 계산한다.

엣지·노드 타입 이름은 일부러 의미 없는 문자열을 쓴다
(이름이 아니라 디스크립터 속성으로 동작함을 보인다).
"""

from typing import Any

from agent_console_contracts import (
    EdgeScheduling,
    EdgeTypeDescriptor,
    Graph,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
)
from agent_console_graph import (
    GraphIssueCodes,
    non_flow_edges,
    schedule_view,
    topology,
    validate_graph,
)

_PORTS = PortSpec(inputs=[PortDef(name="i")], outputs=[PortDef(name="o")])
WORKER = NodeTypeDescriptor(id="q.worker", title="w", static_ports=_PORTS)
PERSON = NodeTypeDescriptor(id="q.person", title="p", static_ports=_PORTS)
INERT = NodeTypeDescriptor(id="q.inert", title="r", static_ports=_PORTS, executable=False)
NODE_TYPES = [WORKER, PERSON, INERT]


def etype(eid: str, scheduling: EdgeScheduling) -> EdgeTypeDescriptor:
    return EdgeTypeDescriptor(id=eid, title=eid, scheduling=scheduling)


EDGE_TYPES = [
    etype("x.in", "entry"),
    etype("x.go", "flow"),
    etype("x.out", "exit"),
    etype("x.tie", "none"),
]


def make(nodes: list[tuple[str, str]], edges: list[tuple[str, str, str]]) -> Graph:
    doc: dict[str, Any] = {
        "id": "g",
        "name": "g",
        "nodes": [{"id": n, "type": t} for n, t in nodes],
        "edges": [
            {
                "id": f"{s}-{k}-{d}",
                "source": {"node": s, "port": "o"},
                "target": {"node": d, "port": "i"},
                "kind": k,
            }
            for s, k, d in edges
        ],
    }
    return Graph.model_validate(doc)


def test_entry_only_from_explicit_entry_edges() -> None:
    # a는 들어오는 엣지가 없지만 입구가 아니다. 입구는 entry 엣지가 가리키는 b뿐.
    g = make(
        [("u", "q.person"), ("a", "q.worker"), ("b", "q.worker"), ("c", "q.worker")],
        [("u", "x.in", "b"), ("b", "x.go", "c"), ("a", "x.go", "c")],
    )
    view = schedule_view(g, NODE_TYPES, EDGE_TYPES)
    assert view.entry_nodes == ("b",)
    assert view.scheduled == ("b", "c")  # u·a: entry·flow로 들어오는 엣지가 없다
    assert view.incoming["b"] == ("u-x.in-b",)
    assert view.incoming["c"] == ("b-x.go-c", "a-x.go-c")
    assert view.outgoing["a"] == ("a-x.go-c",)


def test_no_entry_edge_means_no_entry_nodes() -> None:
    g = make([("a", "q.worker"), ("b", "q.worker")], [("a", "x.go", "b")])
    view = schedule_view(g, NODE_TYPES, EDGE_TYPES)
    assert view.entry_nodes == ()
    assert view.scheduled == ("b",)


def test_non_executable_nodes_are_never_scheduled_or_entries() -> None:
    g = make(
        [("u", "q.person"), ("r", "q.inert"), ("a", "q.worker")],
        [("u", "x.in", "r"), ("r", "x.tie", "a"), ("u", "x.in", "a")],
    )
    view = schedule_view(g, NODE_TYPES, EDGE_TYPES)
    assert view.executable == frozenset({"u", "a"})
    assert view.entry_nodes == ("a",)
    assert view.scheduled == ("a",)
    assert view.none_edges == ("r-x.tie-a",)


def test_exit_and_none_edges_leave_topology_and_cycles() -> None:
    # u → a → u(답변)는 순환이 아니다. a ↔ b none 연결도 순환이 아니다.
    g = make(
        [("u", "q.person"), ("a", "q.worker"), ("b", "q.worker")],
        [("u", "x.in", "a"), ("a", "x.out", "u"), ("a", "x.tie", "b"), ("b", "x.tie", "a")],
    )
    view = schedule_view(g, NODE_TYPES, EDGE_TYPES)
    assert view.topology.is_dag
    assert view.exit_nodes == ("a",)
    assert view.exits["a"] == ("a-x.out-u",)
    assert view.scheduling["a-x.out-u"] == "exit"
    assert validate_graph(g, NODE_TYPES, EDGE_TYPES) == []
    assert topology(g, ignore_edge=non_flow_edges(EDGE_TYPES)).is_dag
    assert not topology(g).is_dag  # 술어 없이 보면 사이클로 보인다


def test_flow_cycle_is_still_an_error() -> None:
    g = make(
        [("u", "q.person"), ("a", "q.worker"), ("b", "q.worker")],
        [("u", "x.in", "a"), ("a", "x.go", "b"), ("b", "x.go", "a")],
    )
    codes = [i.code for i in validate_graph(g, NODE_TYPES, EDGE_TYPES)]
    assert codes == [GraphIssueCodes.CYCLE]
    assert schedule_view(g, NODE_TYPES, EDGE_TYPES).topology.cycles == (("a", "b"),)


def test_unknown_types_are_left_out() -> None:
    g = make(
        [("u", "q.person"), ("a", "zz.unknown"), ("b", "q.worker")],
        [("u", "x.in", "a"), ("u", "zz.edge", "b")],
    )
    view = schedule_view(g, NODE_TYPES, EDGE_TYPES)
    assert view.entry_nodes == ()  # 모르는 노드 타입은 실행할 수 없는 노드로 본다
    assert view.scheduled == ()
    assert "u-zz.edge-b" not in view.scheduling


def test_scheduling_uses_latest_edge_type_version() -> None:
    old = EdgeTypeDescriptor(id="x.v", title="v", version=1, scheduling="flow")
    new = EdgeTypeDescriptor(id="x.v", title="v", version=2, scheduling="entry")
    g = make([("u", "q.person"), ("a", "q.worker")], [("u", "x.v", "a")])
    assert schedule_view(g, NODE_TYPES, [new, old]).entry_nodes == ("a",)
