"""같은 입력 포트로 들어온 엣지별 값(`ctx.incoming`, design §4.3·§R3.2-4, 작업 1R.35).

테스트 전용 노드·엣지 타입만 쓴다(엔진은 노드·연결 이름을 모른다).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts import NodeTypeDescriptor, PortDef, PortSpec
from agent_console_runtime import Incoming, NodeContext, NodeResult
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

_PORTS = PortSpec(inputs=[PortDef(name="in"), PortDef(name="in2")], outputs=[PortDef(name="out")])


class CollectNode:
    """받은 것을 그대로 출력하는 테스트 노드 `t.collect`."""

    descriptor = NodeTypeDescriptor(id="t.collect", title="수집", static_ports=_PORTS)

    def __init__(self) -> None:
        self.seen: dict[str, tuple[dict[str, Any], list[Incoming], list[Incoming]]] = {}

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _PORTS

    def validate(self, config: Mapping[str, Any], ctx: Any) -> list[Any]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        self.seen[ctx.node.id] = (dict(inputs), ctx.incoming("in"), ctx.incoming())
        return NodeResult(status="succeeded", outputs={"out": ctx.node.id})


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


@pytest.fixture
def collect(h: Harness) -> CollectNode:
    node = CollectNode()
    h.registries.node_types.register("t.collect", node)
    return node


async def test_join_all_receives_every_edge_value(
    h: Harness, b: Builders, collect: CollectNode
) -> None:
    g = b.graph(
        [
            b.node("s"),
            b.node("x", outputs={"out": "from-x"}),
            b.node("y", outputs={"out": "from-y"}),
            b.node("j", type="t.collect", join="all"),
        ],
        [
            b.edge("s", "x"),
            b.edge("s", "y"),
            b.edge("x", "j"),
            b.edge("y", "j"),
            b.edge("s", "j", tp="in2"),
        ],
        entries=["s"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    inputs, on_in, everything = collect.seen["j"]
    # 호환: inputs는 포트마다 첫 값(들어오는 엣지 목록 순서)
    assert inputs["in"] == "from-x"
    assert [(i.source_node, i.edge_id, i.value) for i in on_in] == [
        ("x", "x.out->j.in", "from-x"),
        ("y", "y.out->j.in", "from-y"),
    ]
    assert all(i.port == "in" and i.source_port == "out" for i in on_in)
    assert {i.port for i in everything} == {"in", "in2"}
    assert len(everything) == 3


async def test_join_any_receives_only_arrived_values(
    h: Harness, b: Builders, collect: CollectNode
) -> None:
    g = b.graph(
        [
            b.node("s"),
            b.node("fast", outputs={"out": "fast"}),
            b.node("slow", sleep=0.05, outputs={"out": "slow"}),
            b.node("j", type="t.collect"),
        ],
        [b.edge("s", "fast"), b.edge("s", "slow"), b.edge("fast", "j"), b.edge("slow", "j")],
        entries=["s"],
    )
    run = await h.make().run(g)
    assert run.status == "completed"
    _, on_in, _ = collect.seen["j"]
    assert [i.source_node for i in on_in] == ["fast"]


async def test_entry_edge_value_is_incoming(h: Harness, b: Builders, collect: CollectNode) -> None:
    g = b.graph([b.node("j", type="t.collect")], [], entries=["j"])
    await h.make().run(g, {"text": "hi"})
    _, on_in, _ = collect.seen["j"]
    [only] = on_in
    assert only.source_node == "you"
    assert only.source_port == "says"
    assert only.value == {"text": "hi"}
