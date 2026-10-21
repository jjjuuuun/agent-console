"""예제 상호작용 종류 `example.sign_off`와 허용 연결 `example.ask_sign_off`.

- entry point 선언(두 그룹), 로더 검사기 통과
- 팀 구성: 허용 연결이 있는 노드만 이 종류 grant를 받는다
- 엔진: 이 종류의 요청이 열리고 응답이 `response_schema`로 검증된다
"""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import pytest

from agent_console_contracts import EdgeSpec, Endpoint, Graph, NodeSpec, NodeTypeDescriptor
from agent_console_example_interactions import (
    EDGE_TYPE_ID,
    INTERACTION_KIND_ID,
    RENDERER,
    SIGN_OFF,
    AskSignOffEdge,
)
from agent_console_runtime import (
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    GraphRuntime,
    NodeRunView,
    ResponseValidationError,
    as_edge_type,
    as_interaction_kind,
    validate_graph_with,
)
from agent_console_runtime.testing import BUILDERS, make_harness
from agent_console_teams import DEFAULT_CONVENTIONS, team_plan

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_entry_points_declared() -> None:
    eps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    assert eps[INTERACTION_KINDS_GROUP] == {
        INTERACTION_KIND_ID: "agent_console_example_interactions:SIGN_OFF"
    }
    assert eps[EDGE_TYPES_GROUP] == {
        EDGE_TYPE_ID: "agent_console_example_interactions:AskSignOffEdge"
    }


def test_loader_validators_accept_plugin_objects() -> None:
    kind = as_interaction_kind(SIGN_OFF)
    assert kind.descriptor.id == INTERACTION_KIND_ID
    assert kind.descriptor.ui_hints is not None
    assert kind.descriptor.ui_hints.renderer == RENDERER
    edge = as_edge_type(AskSignOffEdge)
    assert edge.descriptor.scheduling == "none"
    assert edge.descriptor.interaction is not None
    assert edge.descriptor.interaction.kinds == [INTERACTION_KIND_ID]
    view = NodeRunView(node_id="a", node_type="x", status="succeeded", outputs={"out": "v"})
    spec = EdgeSpec(
        id="e",
        source=Endpoint(node="a", port="out"),
        target=Endpoint(node="u", port="asks"),
        kind=EDGE_TYPE_ID,
    )
    assert edge.activates(view, spec) is None


def test_only_nodes_with_grant_edge_may_open_sign_off() -> None:
    agent = NodeTypeDescriptor(id="t.agent", title="에이전트 자리", role="agent")
    person = NodeTypeDescriptor(id="t.person", title="사람 자리", role="user")
    graph = Graph(
        id="g",
        name="g",
        nodes=[
            NodeSpec(id="u", type="t.person", config={}),
            NodeSpec(id="a", type="t.agent", config={}),
            NodeSpec(id="b", type="t.agent", config={}),
        ],
        edges=[
            EdgeSpec(
                id="grant",
                source=Endpoint(node="a", port="out"),
                target=Endpoint(node="u", port="asks"),
                kind=EDGE_TYPE_ID,
            )
        ],
    )
    plan = team_plan(
        graph,
        node_types=[agent, person],
        edge_types=[AskSignOffEdge.descriptor],
        conventions=DEFAULT_CONVENTIONS,
    )
    assert plan.grants["a"].kinds == [INTERACTION_KIND_ID]
    assert "b" not in plan.grants


async def test_engine_opens_request_and_validates_response() -> None:
    h = make_harness()
    h.registries.interaction_kinds.register(INTERACTION_KIND_ID, as_interaction_kind(SIGN_OFF))
    rt: GraphRuntime = h.make()
    graph = BUILDERS.graph(
        [
            BUILDERS.node(
                "a",
                type="t.asker",
                asks=[{"kind": INTERACTION_KIND_ID, "title": "서명", "payload": {"text": "v2"}}],
            )
        ],
        [],
        entries=["a"],
    )
    handle = await rt.start(graph)
    try:
        for _ in range(500):
            if rt.pending(run_id=handle.run_id):
                break
            await asyncio.sleep(0.001)
        [pending] = rt.pending(run_id=handle.run_id)
        assert pending.kind == INTERACTION_KIND_ID
        assert pending.response_schema == SIGN_OFF.response_schema
        with pytest.raises(ResponseValidationError):
            await rt.respond(handle.run_id, pending.id, {"note": "승인 여부 없음"})
        await rt.respond(handle.run_id, pending.id, {"approved": True, "note": "확인"})
        run = await handle.wait()
        assert run.status == "completed"
    finally:
        await asyncio.wait_for(rt.shutdown(), 5)


def test_removed_plugin_reports_unknown_edge_type_and_kind_disappears() -> None:
    """README 주장 고정: 제거(등록 없음)하면 허용 연결은 `unknown_edge_type`(error), 종류는 없다."""
    h = make_harness()  # 두 플러그인 모두 등록하지 않는다
    grant = EdgeSpec(
        id="grant",
        source=Endpoint(node="a", port="out"),
        target=Endpoint(node="b", port="in"),
        kind=EDGE_TYPE_ID,
    )
    graph = BUILDERS.graph(
        [BUILDERS.node("a", type="t.step"), BUILDERS.node("b", type="t.step")],
        [grant],
        entries=["a"],
    )
    unknown = [i for i in validate_graph_with(graph, h.registries) if i.code == "unknown_edge_type"]
    assert [(i.severity, i.edge_id) for i in unknown] == [("error", "grant")]
    assert INTERACTION_KIND_ID not in {e.key for e in h.registries.interaction_kinds.list()}
