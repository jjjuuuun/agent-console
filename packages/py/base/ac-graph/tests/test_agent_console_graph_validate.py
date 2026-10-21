"""validate_graph 수용 기준(R2.1, R2.2, R2.3). 노드·엣지 타입은 테스트 전용 임의 이름이다."""

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts import (
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    Issue,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
)
from agent_console_graph import GraphIssueCodes as C
from agent_console_graph import validate_graph

SRC = NodeTypeDescriptor(
    id="zz-source",
    title="소스",
    static_ports=PortSpec(outputs=[PortDef(name="o")]),
)
PIPE = NodeTypeDescriptor(
    id="zz-pipe",
    title="파이프",
    config_schema={
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 0}, "a/b": {"type": "string"}},
        "additionalProperties": False,
    },
    static_ports=PortSpec(inputs=[PortDef(name="i")], outputs=[PortDef(name="o")]),
)
FAN = NodeTypeDescriptor(
    id="zz-fan",
    title="동적 출력",
    config_schema={
        "type": "object",
        "properties": {"outs": {"type": "array", "items": {"type": "string"}}},
        "required": ["outs"],
    },
    dynamic_ports=True,
)
WIRE = EdgeTypeDescriptor(id="zz-wire", title="선")
BACK = EdgeTypeDescriptor(
    id="zz-back", title="되돌림", config_schema={"type": "object", "required": ["max"]}
)
NODE_TYPES = [SRC, PIPE, FAN]
EDGE_TYPES = [WIRE, BACK]


def fan_resolver(desc: NodeTypeDescriptor, config: Mapping[str, Any]) -> PortSpec:
    assert desc.id == "zz-fan"
    return PortSpec(inputs=[PortDef(name="i")], outputs=[PortDef(name=p) for p in config["outs"]])


def n(nid: str, ntype: str, **kw: Any) -> NodeSpec:
    return NodeSpec.model_validate({"id": nid, "type": ntype, **kw})


def e(eid: str, src: str, dst: str, kind: str = "zz-wire", **kw: Any) -> EdgeSpec:
    s_node, s_port = src.split(".")
    t_node, t_port = dst.split(".")
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": s_node, "port": s_port},
            "target": {"node": t_node, "port": t_port},
            "kind": kind,
            **kw,
        }
    )


def g(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> Graph:
    return Graph(id="g", name="g", nodes=nodes, edges=edges)


def run(graph: Graph, **kw: Any) -> list[Issue]:
    kw.setdefault("resolve_ports", fan_resolver)
    return validate_graph(graph, NODE_TYPES, EDGE_TYPES, **kw)


def codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def test_valid_graph_has_no_issues() -> None:
    graph = g(
        [
            n("a", "zz-source"),
            n("b", "zz-pipe", config={"n": 1}),
            n("c", "zz-fan", config={"outs": ["x", "y"]}),
        ],
        [e("e1", "a.o", "b.i"), e("e2", "b.o", "c.i")],
    )
    assert run(graph) == []


def test_unknown_node_and_edge_types() -> None:
    graph = g([n("a", "zz-source"), n("b", "no-such")], [e("e1", "a.o", "b.i", kind="nope")])
    issues = run(graph)
    assert codes(issues) == [C.UNKNOWN_NODE_TYPE, C.UNKNOWN_EDGE_TYPE]
    assert issues[0].node_id == "b"
    assert issues[0].severity == "error"
    assert issues[1].edge_id == "e1"


def test_type_version_selection() -> None:
    v2 = PIPE.model_copy(
        update={"version": 2, "config_schema": {"type": "object", "required": ["z"]}}
    )
    types = [SRC, PIPE, v2]
    latest = g([n("b", "zz-pipe")], [])
    assert codes(validate_graph(latest, types, EDGE_TYPES)) == [C.INVALID_CONFIG]
    pinned = g([n("b", "zz-pipe", type_version=1)], [])
    assert validate_graph(pinned, types, EDGE_TYPES) == []
    missing = g([n("b", "zz-pipe", type_version=9)], [])
    assert codes(validate_graph(missing, types, EDGE_TYPES)) == [C.UNKNOWN_NODE_TYPE]


def test_config_schema_violations_have_config_pointer() -> None:
    graph = g([n("b", "zz-pipe", config={"n": -1, "a/b": 3, "extra": True})], [])
    issues = run(graph)
    assert codes(issues) == [C.INVALID_CONFIG] * 3
    assert all(i.node_id == "b" for i in issues)
    assert sorted(i.path or "" for i in issues) == ["", "/a~1b", "/n"]


def test_edge_config_is_validated() -> None:
    graph = g(
        [n("a", "zz-source"), n("b", "zz-pipe")],
        [e("e1", "a.o", "b.i", kind="zz-back")],
    )
    issues = run(graph)
    assert codes(issues) == [C.INVALID_CONFIG]
    assert issues[0].edge_id == "e1"
    assert issues[0].node_id is None
    assert issues[0].path == ""


def test_invalid_type_schema_is_reported_not_raised() -> None:
    broken = NodeTypeDescriptor(id="zz-broken", title="x", config_schema={"type": 12})
    issues = validate_graph(g([n("x", "zz-broken")], []), [broken], [])
    assert codes(issues) == [C.INVALID_CONFIG_SCHEMA]


def test_nonexistent_ports_and_nodes() -> None:
    graph = g(
        [n("a", "zz-source"), n("b", "zz-pipe")],
        [
            e("e1", "a.nope", "b.i"),
            e("e2", "a.o", "b.o"),  # 타깃은 입력 포트여야 한다
            e("e3", "ghost.o", "b.i"),
        ],
    )
    issues = run(graph)
    assert codes(issues) == [C.UNKNOWN_PORT, C.UNKNOWN_PORT, C.UNKNOWN_NODE]
    assert issues[0].details["end"] == "source"
    assert issues[0].details["available"] == ["o"]
    assert issues[1].details["end"] == "target"
    assert issues[2].details == {"end": "source", "node": "ghost"}


def test_dynamic_ports_use_resolver_result() -> None:
    nodes = [n("f", "zz-fan", config={"outs": ["left", "right"]}), n("b", "zz-pipe")]
    ok = g(nodes, [e("e1", "f.left", "b.i")])
    assert run(ok) == []
    bad = g(nodes, [e("e1", "f.middle", "b.i")])
    issues = run(bad)
    assert codes(issues) == [C.UNKNOWN_PORT]
    assert issues[0].details["available"] == ["left", "right"]


def test_dynamic_ports_without_resolver_warns_and_skips_port_check() -> None:
    graph = g(
        [n("f", "zz-fan", config={"outs": []}), n("b", "zz-pipe")],
        [e("e1", "f.whatever", "b.i")],
    )
    issues = validate_graph(graph, NODE_TYPES, EDGE_TYPES)
    assert codes(issues) == [C.PORTS_UNRESOLVED]
    assert issues[0].severity == "warning"


def test_resolver_failure_becomes_issue() -> None:
    def boom(desc: NodeTypeDescriptor, config: Mapping[str, Any]) -> PortSpec:
        raise RuntimeError("bad")

    graph = g([n("f", "zz-fan", config={"outs": []})], [])
    issues = run(graph, resolve_ports=boom)
    assert codes(issues) == [C.PORT_RESOLUTION_FAILED]
    assert issues[0].node_id == "f"


def test_invalid_config_skips_port_check_for_its_edges() -> None:
    graph = g(
        [n("f", "zz-fan", config={}), n("b", "zz-pipe")],
        [e("e1", "f.x", "b.i")],
    )
    assert codes(run(graph)) == [C.INVALID_CONFIG]


def test_duplicate_ids() -> None:
    graph = g(
        [n("a", "zz-source"), n("a", "zz-source"), n("b", "zz-pipe")],
        [e("e1", "a.o", "b.i"), e("e1", "a.o", "b.i")],
    )
    issues = run(graph)
    assert codes(issues) == [C.DUPLICATE_NODE_ID, C.DUPLICATE_EDGE_ID]
    assert issues[0].node_id == "a"
    assert issues[1].edge_id == "e1"


def test_cycle_is_error_by_default() -> None:
    graph = g(
        [n("a", "zz-source"), n("b", "zz-pipe"), n("c", "zz-pipe")],
        [e("e1", "a.o", "b.i"), e("e2", "b.o", "c.i"), e("e3", "c.o", "b.i")],
    )
    issues = run(graph)
    assert codes(issues) == [C.CYCLE]
    assert issues[0].details == {"nodes": ["b", "c"]}
    assert issues[0].node_id is None
    assert issues[0].edge_id is None


def test_self_loop_is_cycle() -> None:
    graph = g([n("b", "zz-pipe")], [e("e1", "b.o", "b.i")])
    assert codes(run(graph)) == [C.CYCLE]


def test_cycle_allowed_by_edge_type_predicate() -> None:
    graph = g(
        [n("b", "zz-pipe"), n("c", "zz-pipe")],
        [e("e1", "b.o", "c.i"), e("e2", "c.o", "b.i", kind="zz-back", config={"max": 3})],
    )
    assert codes(run(graph)) == [C.CYCLE]

    def allows(edge: EdgeSpec, desc: EdgeTypeDescriptor) -> bool:
        return desc.id == "zz-back"  # 실제로는 디스크립터 속성(데이터)으로 판단한다

    assert run(graph, cycle_edge=allows) == []


def test_validate_node_hook_runs_only_on_schema_valid_nodes() -> None:
    seen: list[str] = []

    def hook(node: NodeSpec, desc: NodeTypeDescriptor) -> list[Issue]:
        seen.append(node.id)
        return [Issue(severity="warning", code="custom", message="m", path="/n")]

    graph = g([n("ok", "zz-pipe", config={"n": 1}), n("bad", "zz-pipe", config={"n": "x"})], [])
    issues = run(graph, validate_node=hook)
    assert seen == ["ok"]
    custom = [i for i in issues if i.code == "custom"]
    assert len(custom) == 1
    assert custom[0].node_id == "ok"


@pytest.mark.parametrize("empty", [[], ()])
def test_empty_graph_and_empty_catalogs(empty: list[Any]) -> None:
    assert validate_graph(g([], []), empty, empty) == []


@pytest.mark.parametrize(
    "ref",
    [
        "#/nope",  # 로컬 포인터가 가리키는 곳이 없다
        "http://example.invalid/s.json",  # 외부 문서: 가져오지 않고 해석 불가로 처리
        "other.json#/x",
    ],
)
def test_unresolvable_ref_is_reported_not_raised(ref: str) -> None:
    desc = NodeTypeDescriptor(
        id="zz-ref",
        title="ref",
        config_schema={"type": "object", "properties": {"x": {"$ref": ref}}},
    )
    edge = EdgeTypeDescriptor(id="zz-ref-edge", title="e", config_schema=desc.config_schema)
    graph = g(
        [n("a", "zz-ref", config={"x": 1}), n("b", "zz-ref", config={"x": 2})],
        [e("e1", "a.o", "b.i", kind="zz-ref-edge", config={"x": 1})],
    )
    issues = validate_graph(graph, [desc], [edge])
    assert codes(issues) == [C.INVALID_CONFIG_SCHEMA] * 3
    assert [(i.node_id, i.edge_id) for i in issues] == [("a", None), ("b", None), (None, "e1")]
    assert all(i.path == "" for i in issues)


def test_local_defs_ref_is_resolved() -> None:
    desc = NodeTypeDescriptor(
        id="zz-defs",
        title="defs",
        config_schema={
            "type": "object",
            "$defs": {"pos": {"type": "integer", "minimum": 0}},
            "properties": {"x": {"$ref": "#/$defs/pos"}},
        },
    )
    ok = g([n("a", "zz-defs", config={"x": 1})], [])
    assert validate_graph(ok, [desc], []) == []
    bad = g([n("a", "zz-defs", config={"x": -1})], [])
    issues = validate_graph(bad, [desc], [])
    assert codes(issues) == [C.INVALID_CONFIG]
    assert issues[0].path == "/x"


def test_large_graph_validates_quickly() -> None:
    count = 5000
    nodes = [n("s", "zz-source")] + [n(f"p{i}", "zz-pipe", config={"n": i}) for i in range(count)]
    edges = [e("e0", "s.o", "p0.i")] + [
        e(f"e{i}", f"p{i - 1}.o", f"p{i}.i") for i in range(1, count)
    ]
    assert run(g(nodes, edges)) == []
