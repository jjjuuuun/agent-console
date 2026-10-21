"""예제 노드 타입 `example.text_transform`: 디스크립터·entry point 선언·검증·실행.

엔진은 `agent_console_runtime.testing` harness로 돌리고, 이 노드를 레지스트리에 직접 등록한다
(설치 없이 실행 가능 — pytest 설정 `pythonpath = ["src"]`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    EdgeConnects,
    EdgeTypeDescriptor,
    Graph,
    NodeSpec,
    NodeTypeDescriptor,
)
from agent_console_example_nodes import (
    IN_PORT,
    NODE_TYPE_ID,
    OUT_PORT,
    TEAM_ROLE,
    ExampleErrorCodes,
    TextTransformConfig,
    TextTransformNode,
    transform_text,
)
from agent_console_runtime import (
    NODE_TYPES_GROUP,
    GraphValidationError,
    Registries,
    as_node_type,
    node_type_descriptors,
    validate_graph_with,
)
from agent_console_runtime.testing import Harness, entry, make_harness, with_entries
from agent_console_teams import DEFAULT_CONVENTIONS, plan_summary, team_plan, validate_team

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def harness_with_node() -> Harness:
    h = make_harness()
    h.registries.node_types.register(NODE_TYPE_ID, as_node_type(TextTransformNode))
    return h


def transform_graph(**config: Any) -> Graph:
    """입구(Run 입력 `IN_PORT` 키) → `example.text_transform` → `t.step`.

    입구는 테스트 전용 입구 엣지(`t.entry`)로 명시한다(엔진은 입구를 추론하지 않는다).
    """
    graph = Graph.model_validate(
        {
            "id": "g-example",
            "name": "example",
            "nodes": [
                {"id": "tx", "type": NODE_TYPE_ID, "config": config},
                {"id": "sink", "type": "t.step", "config": {}},
            ],
            "edges": [
                {
                    "id": "tx.out->sink.in",
                    "source": {"node": "tx", "port": OUT_PORT},
                    "target": {"node": "sink", "port": "in"},
                    "kind": "t.flow",
                }
            ],
        }
    )
    return with_entries(graph, entry("tx", tp=IN_PORT, key=IN_PORT))


# ---------------------------------------------------------------- 등록·디스크립터


def test_entry_point_declared_in_runtime_group_with_descriptor_id() -> None:
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    eps = meta["project"]["entry-points"][NODE_TYPES_GROUP]
    assert eps == {NODE_TYPE_ID: "agent_console_example_nodes:TextTransformNode"}


def test_descriptor_is_listed_after_registration() -> None:
    regs = Registries()
    regs.node_types.register(NODE_TYPE_ID, as_node_type(TextTransformNode))
    [desc] = node_type_descriptors(regs)
    assert desc.id == NODE_TYPE_ID
    assert desc.category == "예제"
    assert desc.ui_hints is not None
    assert desc.ui_hints.icon == "Aa"
    assert desc.ui_hints.color == "#0ea5e9"
    assert desc.static_ports is not None
    assert [p.name for p in desc.static_ports.inputs] == [IN_PORT]
    assert [p.name for p in desc.static_ports.outputs] == [OUT_PORT]
    props = desc.config_schema["properties"]
    assert props["mode"]["enum"] == ["upper", "lower", "title", "keep"]
    assert props["prefix"]["type"] == "string"
    assert props["strip"]["type"] == "boolean"
    assert desc.ui_schema["ui:order"] == ["mode", "prefix", "strip"]


def test_team_meaning_role_without_binds() -> None:
    desc = TextTransformNode.descriptor
    assert desc.role == TEAM_ROLE
    assert desc.binds is None  # 정의에서 만들어지지 않는다(설정 = 노드 config뿐)
    assert desc.rerunnable is True  # 결정적이라 이어 가기에서 다시 실행해도 안전하다


def test_team_composition_message_in_reply_out() -> None:
    """사용자 → (입구) → 텍스트 변환 → (답변) → 사용자. 연결 종류는 역할만 보고 잇는다."""
    person = NodeTypeDescriptor(id="t.person", title="사람 자리", role="user")
    message = EdgeTypeDescriptor(
        id="t.message",
        title="입구",
        scheduling="entry",
        connects=EdgeConnects(source=["user"], target=[TEAM_ROLE]),
    )
    answer = EdgeTypeDescriptor(
        id="t.answer",
        title="답변",
        scheduling="exit",
        connects=EdgeConnects(source=[TEAM_ROLE], target=["user"]),
    )
    graph = Graph.model_validate(
        {
            "id": "g-team",
            "name": "team",
            "nodes": [
                {"id": "u", "type": "t.person", "config": {}},
                {"id": "tx", "type": NODE_TYPE_ID, "config": {"mode": "upper"}},
            ],
            "edges": [
                {
                    "id": "m",
                    "kind": "t.message",
                    "source": {"node": "u", "port": "says"},
                    "target": {"node": "tx", "port": IN_PORT},
                },
                {
                    "id": "r",
                    "kind": "t.answer",
                    "source": {"node": "tx", "port": OUT_PORT},
                    "target": {"node": "u", "port": "hears"},
                },
            ],
        }
    )
    node_types = [person, TextTransformNode.descriptor]
    edge_types = [message, answer]
    issues = validate_team(graph, node_types=node_types, edge_types=edge_types, graph_checks=False)
    assert [i for i in issues if i.severity == "error"] == []
    summary = plan_summary(
        team_plan(
            graph, node_types=node_types, edge_types=edge_types, conventions=DEFAULT_CONVENTIONS
        )
    )
    assert [e.node_id for e in summary.entries] == ["tx"]
    assert [a.node_id for a in summary.answers] == ["tx"]


def test_resolve_ports_is_fixed() -> None:
    node = TextTransformNode()
    assert node.resolve_ports({}) == node.resolve_ports({"mode": "lower"})


# ---------------------------------------------------------------- 순수 변환


@pytest.mark.parametrize(
    ("value", "config", "expected"),
    [
        ("  hello world ", {}, "HELLO WORLD"),
        ("Hello", {"mode": "lower", "prefix": "> "}, "> hello"),
        ("hello world", {"mode": "title"}, "Hello World"),
        ("  keep  ", {"mode": "keep", "strip": False}, "  keep  "),
        (None, {"prefix": "x"}, "x"),
        ({"a": "b"}, {}, '{"A": "B"}'),
    ],
)
def test_transform_text(value: Any, config: dict[str, Any], expected: str) -> None:
    assert transform_text(value, TextTransformConfig.model_validate(config)) == expected


# ---------------------------------------------------------------- 검증


def test_graph_validates_and_noop_config_warns() -> None:
    h = harness_with_node()
    assert validate_graph_with(transform_graph(mode="upper"), h.registries) == []
    issues = validate_graph_with(transform_graph(mode="keep", prefix="", strip=False), h.registries)
    assert [(i.severity, i.code) for i in issues] == [("warning", ExampleErrorCodes.NOOP)]


async def test_removed_plugin_reports_unknown_node_type_and_blocks_run() -> None:
    """README 주장 고정: 제거(등록 없음)하면 그래프는 남고 검증이 `unknown_node_type`(error)."""
    h = make_harness()  # 이 노드를 등록하지 않는다
    issues = validate_graph_with(transform_graph(mode="upper"), h.registries)
    unknown = [i for i in issues if i.code == "unknown_node_type"]
    assert [(i.severity, i.node_id) for i in unknown] == [("error", "tx")]
    with pytest.raises(GraphValidationError):
        await h.make().start(transform_graph(mode="upper"), {IN_PORT: "x"})


def test_schema_rejects_unknown_mode() -> None:
    h = harness_with_node()
    issues = validate_graph_with(transform_graph(mode="shout"), h.registries)
    assert any(i.severity == "error" for i in issues)


# ---------------------------------------------------------------- 실행


async def test_executes_in_graph_and_passes_value_downstream() -> None:
    h = harness_with_node()
    run = await h.make().run(transform_graph(mode="upper", prefix="> "), {IN_PORT: " hi "})
    assert run.status == "completed"
    node_runs = {nr.node_id: nr for nr in h.recorder.runs.list_node_runs(run.id)}
    assert node_runs["tx"].status == "succeeded"
    assert node_runs["tx"].outputs == {OUT_PORT: "> HI"}
    assert h.probe.calls == [("sink", {"in": "> HI"})]


async def test_invalid_config_fails_node_when_validation_is_skipped() -> None:
    h = harness_with_node()
    handle = await h.make().start(transform_graph(mode="shout"), {IN_PORT: "x"}, validate=False)
    run = await handle.wait()
    tx = next(nr for nr in h.recorder.runs.list_node_runs(run.id) if nr.node_id == "tx")
    assert tx.status == "failed"
    assert tx.error is not None
    assert tx.error.code == ExampleErrorCodes.INVALID_CONFIG


def test_node_spec_round_trip() -> None:
    spec = NodeSpec.model_validate({"id": "tx", "type": NODE_TYPE_ID, "config": {"mode": "lower"}})
    assert spec.type == NODE_TYPE_ID
