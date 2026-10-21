"""예제 연결 종류 `example.relay`: entry point 선언·디스크립터·통과 규칙·엔진 실행·연결 규칙.

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 엔진은 `agent_console_runtime.testing`
harness로 띄우고 이 연결 종류를 레지스트리에 직접 등록한다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from agent_console_contracts import EdgeSpec, Endpoint, Graph, NodeSpec, NodeTypeDescriptor
from agent_console_example_edges import AGENT_ROLE, EDGE_TYPE_ID, RelayConfig, RelayEdge
from agent_console_runtime import (
    EDGE_TYPES_GROUP,
    GraphValidationError,
    NodeRunView,
    Registries,
    as_edge_type,
    edge_type_descriptors,
    validate_graph_with,
)
from agent_console_runtime.testing import entry, make_harness, with_entries
from agent_console_teams import TeamIssueCodes, validate_team

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def relay_spec(**config: object) -> EdgeSpec:
    return EdgeSpec(
        id="a.out->b.in",
        source=Endpoint(node="a", port="out"),
        target=Endpoint(node="b", port="in"),
        kind=EDGE_TYPE_ID,
        config=dict(config),
    )


# ---------------------------------------------------------------- 등록·디스크립터


def test_entry_point_declared_in_runtime_group_with_descriptor_id() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][EDGE_TYPES_GROUP]
    assert eps == {EDGE_TYPE_ID: "agent_console_example_edges:RelayEdge"}


def test_descriptor_is_listed_after_registration() -> None:
    regs = Registries()
    regs.edge_types.register(EDGE_TYPE_ID, as_edge_type(RelayEdge))
    [desc] = edge_type_descriptors(regs)
    assert desc.id == EDGE_TYPE_ID
    assert desc.scheduling == "flow"
    assert desc.connects is not None
    assert desc.connects.source == [AGENT_ROLE]
    assert desc.connects.target == [AGENT_ROLE]
    assert desc.config_schema["properties"]["prefix"]["default"] == RelayConfig().prefix


# ---------------------------------------------------------------- 통과 규칙


def passed(view: NodeRunView, spec: EdgeSpec) -> object:
    act = RelayEdge().activates(view, spec)
    assert act is not None
    return act.value


def test_activates_prefixes_text_and_blocks_failed_or_missing_output() -> None:
    edge = RelayEdge()
    ok = NodeRunView(node_id="a", node_type="x", status="succeeded", outputs={"out": "hi"})
    assert passed(ok, relay_spec(prefix="> ")) == "> hi"
    assert passed(ok, relay_spec()) == "[중계] hi"
    assert passed(ok, relay_spec(prefix=3)) == "[중계] hi"  # 틀린 설정 → 기본값
    data = NodeRunView(node_id="a", node_type="x", status="succeeded", outputs={"out": {"k": 1}})
    assert passed(data, relay_spec()) == {"k": 1}
    failed = NodeRunView(node_id="a", node_type="x", status="failed", outputs={"out": "hi"})
    assert edge.activates(failed, relay_spec()) is None
    empty = NodeRunView(node_id="a", node_type="x", status="succeeded", outputs={})
    assert edge.activates(empty, relay_spec()) is None


# ---------------------------------------------------------------- 엔진 실행


async def test_engine_passes_prefixed_value_downstream() -> None:
    h = make_harness()
    h.registries.edge_types.register(EDGE_TYPE_ID, as_edge_type(RelayEdge))
    graph = Graph(
        id="g-relay",
        name="relay",
        nodes=[
            NodeSpec(id="a", type="t.step", config={"outputs": {"out": "hello"}}),
            NodeSpec(id="b", type="t.step", config={}),
        ],
        edges=[relay_spec(prefix="[A→B] ")],
    )
    run = await h.make().run(with_entries(graph, entry("a")), {"in": "x"})
    assert run.status == "completed"
    assert ("b", {"in": "[A→B] hello"}) in h.probe.calls


async def test_removed_plugin_reports_unknown_edge_type_and_blocks_run() -> None:
    """README 주장 고정: 제거(등록 없음)하면 그래프는 남고 검증이 `unknown_edge_type`(error)."""
    h = make_harness()  # 이 연결 종류를 등록하지 않는다
    graph = with_entries(
        Graph(
            id="g-relay",
            name="relay",
            nodes=[
                NodeSpec(id="a", type="t.step", config={}),
                NodeSpec(id="b", type="t.step", config={}),
            ],
            edges=[relay_spec()],
        ),
        entry("a"),
    )
    unknown = [i for i in validate_graph_with(graph, h.registries) if i.code == "unknown_edge_type"]
    assert [(i.severity, i.edge_id) for i in unknown] == [("error", "a.out->b.in")]
    with pytest.raises(GraphValidationError):
        await h.make().start(graph, {"in": "x"})


# ---------------------------------------------------------------- 팀 구성 연결 규칙(connects)


def test_team_rules_follow_connects_roles() -> None:
    """에이전트 역할끼리만 이을 수 있다. 역할은 노드 타입 디스크립터의 문자열이다."""
    agent = NodeTypeDescriptor(id="t.agent", title="에이전트 자리", role=AGENT_ROLE)
    person = NodeTypeDescriptor(id="t.person", title="사람 자리", role="user")

    def team(source_type: str) -> Graph:
        return Graph(
            id="g",
            name="g",
            nodes=[
                NodeSpec(id="a", type=source_type, config={}),
                NodeSpec(id="b", type="t.agent", config={}),
            ],
            edges=[relay_spec()],
        )

    def codes(source_type: str) -> set[str]:
        issues = validate_team(
            team(source_type),
            node_types=[agent, person],
            edge_types=[RelayEdge.descriptor],
            graph_checks=False,
        )
        return {i.code for i in issues}

    assert TeamIssueCodes.CONNECTS_MISMATCH not in codes("t.agent")
    assert TeamIssueCodes.CONNECTS_MISMATCH in codes("t.person")
