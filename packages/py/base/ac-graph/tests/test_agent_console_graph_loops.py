"""반복 영역·사이클 연결 술어(design §5R.4). 연결 종류 이름은 테스트 전용 임의 이름이다."""

from typing import Any

import pytest

from agent_console_contracts import (
    CyclePolicy,
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
    LoopRegion,
    descriptor_cycle_edge,
    effective_max_iterations,
    loop_regions,
    validate_graph,
)

STEP = NodeTypeDescriptor(
    id="zz-step",
    title="단계",
    static_ports=PortSpec(inputs=[PortDef(name="i")], outputs=[PortDef(name="o")]),
)
WIRE = EdgeTypeDescriptor(id="zz-wire", title="선")
# 이름이 반복을 뜻하지 않는 사이클 연결: 엔진·검증은 디스크립터 `cycle`만 본다.
AGAIN = EdgeTypeDescriptor(
    id="zz-again",
    title="다시",
    cycle=CyclePolicy(max_iterations=4),
    config_schema={
        "type": "object",
        "properties": {CYCLE_LIMIT_CONFIG_KEY: {"type": "integer", "minimum": 1}},
    },
)
SIDE = EdgeTypeDescriptor(
    id="zz-side", title="곁", scheduling="none", cycle=CyclePolicy(max_iterations=1)
)
EDGE_TYPES = [WIRE, AGAIN, SIDE]


def n(nid: str) -> NodeSpec:
    return NodeSpec(id=nid, type=STEP.id)


def e(src: str, dst: str, kind: str = WIRE.id, **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": f"{src}->{dst}:{kind}",
            "source": {"node": src, "port": "o"},
            "target": {"node": dst, "port": "i"},
            "kind": kind,
            "config": config,
        }
    )


def g(nodes: str, edges: list[EdgeSpec]) -> Graph:
    return Graph(id="g", name="g", nodes=[n(x) for x in nodes], edges=edges)


def codes(graph: Graph) -> list[str]:
    issues = validate_graph(graph, [STEP], EDGE_TYPES, cycle_edge=descriptor_cycle_edge)
    return [i.code for i in issues]


# ---------------------------------------------------------------- 술어·검증


def test_predicate_reads_descriptor_cycle_only() -> None:
    edge = e("a", "b", AGAIN.id)
    assert descriptor_cycle_edge(edge, AGAIN) is True
    assert descriptor_cycle_edge(edge, WIRE) is False


def test_cycle_closed_by_cycle_edge_is_allowed() -> None:
    assert codes(g("ab", [e("a", "b"), e("b", "a", AGAIN.id)])) == []
    # 자기 자신으로 돌아가는 사이클 연결
    assert codes(g("a", [e("a", "a", AGAIN.id)])) == []


def test_cycle_without_cycle_edge_is_error() -> None:
    assert codes(g("ab", [e("a", "b"), e("b", "a")])) == [GraphIssueCodes.CYCLE]


def test_every_cycle_needs_its_own_cycle_edge() -> None:
    # a→b→a는 사이클 연결로 닫혔지만 b→c→b는 아니다.
    graph = g("abc", [e("a", "b"), e("b", "a", AGAIN.id), e("b", "c"), e("c", "b")])
    issues = validate_graph(graph, [STEP], EDGE_TYPES, cycle_edge=descriptor_cycle_edge)
    assert [(i.code, i.details["nodes"]) for i in issues] == [(GraphIssueCodes.CYCLE, ["b", "c"])]


def test_without_predicate_cycle_edge_is_still_a_cycle() -> None:
    graph = g("ab", [e("a", "b"), e("b", "a", AGAIN.id)])
    assert [i.code for i in validate_graph(graph, [STEP], EDGE_TYPES)] == [GraphIssueCodes.CYCLE]


# ---------------------------------------------------------------- 반복 영역


def test_two_node_region() -> None:
    graph = g("ab", [e("a", "b"), e("b", "a", AGAIN.id)])
    assert loop_regions(graph, EDGE_TYPES) == {
        "b->a:zz-again": LoopRegion(edge_id="b->a:zz-again", nodes=("a", "b"), entry="a", exit="b")
    }


def test_region_excludes_nodes_off_the_loop_path() -> None:
    # x → a → b → c, c ⇢ a(사이클), b → d(영역 밖으로 나감)
    graph = g(
        "xabcd",
        [e("x", "a"), e("a", "b"), e("b", "c"), e("c", "a", AGAIN.id), e("b", "d")],
    )
    region = loop_regions(graph, EDGE_TYPES)["c->a:zz-again"]
    assert region.nodes == ("a", "b", "c")
    assert (region.entry, region.exit) == ("a", "c")


def test_parallel_branches_inside_region() -> None:
    graph = g(
        "abcd",
        [e("a", "b"), e("a", "c"), e("b", "d"), e("c", "d"), e("d", "a", AGAIN.id)],
    )
    assert loop_regions(graph, EDGE_TYPES)["d->a:zz-again"].nodes == ("a", "b", "c", "d")


def test_nested_regions() -> None:
    # 바깥 a→b→c→d ⇢ a, 안쪽 c ⇢ b
    graph = g(
        "abcd",
        [
            e("a", "b"),
            e("b", "c"),
            e("c", "d"),
            e("d", "a", AGAIN.id),
            e("c", "b", AGAIN.id),
        ],
    )
    regions = loop_regions(graph, EDGE_TYPES)
    assert regions["d->a:zz-again"].nodes == ("a", "b", "c", "d")
    assert regions["c->b:zz-again"].nodes == ("b", "c")


def test_self_loop_region() -> None:
    graph = g("ab", [e("a", "b"), e("b", "b", AGAIN.id)])
    assert loop_regions(graph, EDGE_TYPES)["b->b:zz-again"].nodes == ("b",)


def test_forward_cycle_edge_and_non_flow_edges_have_no_region() -> None:
    graph = g(
        "abc",
        [e("a", "b", AGAIN.id), e("b", "c"), e("c", "a", SIDE.id), e("a", "zz", AGAIN.id)],
    )
    assert loop_regions(graph, EDGE_TYPES) == {}


def test_unknown_kind_is_followed_as_flow() -> None:
    graph = g("ab", [e("a", "b", "zz-unknown"), e("b", "a", AGAIN.id)])
    assert loop_regions(graph, EDGE_TYPES)["b->a:zz-again"].nodes == ("a", "b")


# ---------------------------------------------------------------- 최대 반복 상속


@pytest.mark.parametrize(
    ("config", "settings", "expected"),
    [
        ({}, None, 4),
        ({}, 2, 2),
        ({CYCLE_LIMIT_CONFIG_KEY: 7}, 2, 7),
        ({CYCLE_LIMIT_CONFIG_KEY: None}, 2, 2),
        ({CYCLE_LIMIT_CONFIG_KEY: 0}, 2, 0),
        ({CYCLE_LIMIT_CONFIG_KEY: "3"}, 2, None),
        ({CYCLE_LIMIT_CONFIG_KEY: True}, 2, None),
    ],
)
def test_effective_max_iterations_order(
    config: dict[str, Any], settings: int | None, expected: int | None
) -> None:
    assert effective_max_iterations(e("b", "a", AGAIN.id, **config), AGAIN, settings) == expected


def test_effective_max_iterations_none_for_non_cycle_kind() -> None:
    edge = e("a", "b").model_copy(update={"config": {CYCLE_LIMIT_CONFIG_KEY: 3}})
    assert effective_max_iterations(edge, WIRE, 5) is None
