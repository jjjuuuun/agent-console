"""사이클 오류의 "반복 연결로 바꾸기" 제안(design §5R.4, 화면 S2). 연결 종류 이름은 임의다."""

from typing import Any

from agent_console_contracts import (
    CyclePolicy,
    EdgeConnects,
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
)
from agent_console_graph import (
    CYCLE_LIMIT_CONFIG_KEY,
    GraphIssueCodes,
    descriptor_cycle_edge,
    validate_graph,
)

PORTS = PortSpec(inputs=[PortDef(name="i")], outputs=[PortDef(name="o")])
STEP = NodeTypeDescriptor(id="qq-step", title="단계", role="r-step", static_ports=PORTS)
OTHER = NodeTypeDescriptor(id="qq-other", title="딴것", role="r-other", static_ports=PORTS)
WIRE = EdgeTypeDescriptor(
    id="qq-wire",
    title="선",
    config_schema={"type": "object", "properties": {"note": {"type": "string"}}},
)
# 이름이 반복을 뜻하지 않는 사이클 연결 두 개: 첫째는 r-other끼리만 잇는다.
NARROW = EdgeTypeDescriptor(
    id="qq-narrow",
    title="좁은 되감기",
    cycle=CyclePolicy(max_iterations=2),
    connects=EdgeConnects(source=["r-other"], target=["r-other"]),
)
AGAIN = EdgeTypeDescriptor(
    id="qq-again",
    title="되감기",
    cycle=CyclePolicy(max_iterations=4),
    config_schema={
        "type": "object",
        "properties": {
            CYCLE_LIMIT_CONFIG_KEY: {"type": "integer", "minimum": 1},
            "note": {"type": "string"},
        },
        "additionalProperties": False,
    },
)
START = EdgeTypeDescriptor(id="qq-start", title="시작", scheduling="entry")


def n(nid: str, desc: NodeTypeDescriptor = STEP) -> NodeSpec:
    return NodeSpec(id=nid, type=desc.id, label=nid.upper())


def e(src: str, dst: str, kind: str = WIRE.id, **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": f"{src}-{dst}",
            "source": {"node": src, "port": "o"},
            "target": {"node": dst, "port": "i"},
            "kind": kind,
            "config": config,
        }
    )


def run(graph: Graph, edge_types: list[EdgeTypeDescriptor], **kw: Any) -> list[Any]:
    return validate_graph(graph, [STEP, OTHER], edge_types, **kw)


def test_back_edge_gets_replace_suggestion_with_same_ports() -> None:
    graph = Graph(
        id="g",
        name="g",
        nodes=[n("u"), n("a"), n("b"), n("c")],
        edges=[e("u", "a", START.id), e("a", "b"), e("b", "c"), e("c", "a", note="x", extra=1)],
    )
    kinds = [START, WIRE, NARROW, AGAIN]
    (issue,) = run(graph, kinds, cycle_edge=descriptor_cycle_edge)
    assert issue.code == GraphIssueCodes.CYCLE
    assert issue.details["nodes"] == ["a", "b", "c"]
    assert "사이클" in issue.message
    assert "A → B → C → A" in issue.message
    (sug,) = issue.suggestions
    assert sug.label == "'C → A' 연결을 '되감기'(으)로 바꾸기"
    assert sug.patch.remove_edge_ids == ["c-a"]
    (edge,) = sug.patch.add_edges
    assert edge.kind == AGAIN.id  # NARROW는 connects가 맞지 않는다
    assert (edge.id, edge.source, edge.target) == (
        "c-a",
        graph.edges[3].source,
        graph.edges[3].target,
    )
    assert edge.config == {"note": "x"}  # 새 종류 스키마가 선언한 키만
    fixed = graph.model_copy(update={"edges": [*graph.edges[:3], edge]})
    assert run(fixed, kinds, cycle_edge=descriptor_cycle_edge) == []


def test_head_is_node_entered_from_outside() -> None:
    # 바깥에서 b로 들어오면 되돌아가는 연결은 a → b다(그래프 순서상 a가 먼저여도).
    graph = Graph(
        id="g",
        name="g",
        nodes=[n("a"), n("b"), n("x")],
        edges=[e("x", "b"), e("b", "a"), e("a", "b")],
    )
    (issue,) = run(graph, [WIRE, AGAIN], cycle_edge=descriptor_cycle_edge)
    assert [s.patch.remove_edge_ids for s in issue.suggestions] == [["a-b"]]


def test_connects_selects_kind_by_roles() -> None:
    graph = Graph(
        id="g", name="g", nodes=[n("a", OTHER), n("b", OTHER)], edges=[e("a", "b"), e("b", "a")]
    )
    (issue,) = run(graph, [WIRE, NARROW, AGAIN], cycle_edge=descriptor_cycle_edge)
    assert issue.suggestions[0].patch.add_edges[0].kind == NARROW.id


def test_no_suggestion_without_cycle_kind_or_predicate() -> None:
    graph = Graph(id="g", name="g", nodes=[n("a"), n("b")], edges=[e("a", "b"), e("b", "a")])
    (issue,) = run(graph, [WIRE], cycle_edge=descriptor_cycle_edge)
    assert issue.suggestions == []
    # 노드는 이름(label)으로 부르고 id는 details에만 둔다(5.2R.5)
    assert issue.message == "흐름이 되돌아 도는 사이클이 있습니다: A → B → A"
    assert issue.details == {"nodes": ["a", "b"]}
    (issue,) = run(graph, [WIRE, AGAIN])
    assert issue.suggestions == []


def test_self_loop_suggestion() -> None:
    graph = Graph(id="g", name="g", nodes=[n("a")], edges=[e("a", "a")])
    (issue,) = run(graph, [WIRE, AGAIN], cycle_edge=descriptor_cycle_edge)
    (sug,) = issue.suggestions
    assert sug.patch.remove_edge_ids == ["a-a"]


def test_custom_predicate_decides_kind() -> None:
    """술어가 디스크립터 대신 다른 기준을 쓰면 제안도 그 기준을 따른다."""
    graph = Graph(id="g", name="g", nodes=[n("a"), n("b")], edges=[e("a", "b"), e("b", "a")])
    titled = EdgeTypeDescriptor(id="qq-titled", title="표시된")

    def pred(edge: EdgeSpec, desc: EdgeTypeDescriptor) -> bool:
        return desc.id == titled.id

    (issue,) = run(graph, [WIRE, AGAIN, titled], cycle_edge=pred)
    assert issue.suggestions[0].patch.add_edges[0].kind == titled.id
