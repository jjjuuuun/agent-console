"""정의·런타임·WS 모델의 검증 규칙."""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Agent,
    CreateRunRequest,
    ErrorCodes,
    ErrorResponse,
    Graph,
    Issue,
    NodeRun,
    NodeTypeDescriptor,
    Usage,
    WorkspaceSettings,
    WsClientMessage,
    WsServerMessage,
)

GRAPH_YAML_LIKE: dict[str, Any] = {
    "kind": "graph",
    "id": "minimal",
    "name": "최소 흐름",
    "inputs": [{"name": "in", "schema": {"type": "string"}}],
    "nodes": [
        {
            "id": "n1",
            "type": "type-a",
            "config": {"anything": [1, 2]},
            "position": {"x": 0, "y": 0},
        },
        {"id": "n2", "type": "type-b", "type_version": 2, "join": "all"},
    ],
    "edges": [
        {
            "id": "e1",
            "source": {"node": "n1", "port": "out"},
            "target": {"node": "n2", "port": "in"},
            "kind": "kind-x",
        }
    ],
    "user_extra": {"keep": True},
}


def test_graph_round_trip_preserves_config_and_unknown_fields() -> None:
    graph = Graph.model_validate(GRAPH_YAML_LIKE)
    assert graph.nodes[0].config == {"anything": [1, 2]}
    assert graph.inputs[0].schema_ == {"type": "string"}
    dumped = graph.model_dump(exclude_defaults=True)
    assert dumped["user_extra"] == {"keep": True}  # 손으로 고친 YAML 필드 보존
    assert dumped["inputs"][0]["schema"] == {"type": "string"}  # alias로 직렬화
    assert Graph.model_validate(dumped) == graph


def test_definition_id_is_slug() -> None:
    with pytest.raises(ValidationError):
        Graph(id="has space", name="x")
    with pytest.raises(ValidationError):
        Agent(id="../escape", name="x")
    assert Agent(id="spec-writer_2", name="작성자").kind == "agent"


def test_edge_kind_has_no_default() -> None:
    with pytest.raises(ValidationError):
        Graph.model_validate(
            {
                "id": "g",
                "name": "g",
                "edges": [
                    {
                        "id": "e",
                        "source": {"node": "a", "port": "o"},
                        "target": {"node": "b", "port": "i"},
                    }
                ],
            }
        )


def test_settings_defaults_work_without_any_data() -> None:
    settings = WorkspaceSettings()
    assert settings.agent_defaults is not None


def test_removed_console_keys_are_kept_as_unknown() -> None:
    """계약에 없는 옛 키(`console`·`default_entry`)도 파일 값은 모르는 키로 보존한다."""
    doc = {"default_entry": "g1", "console": {"command_prefix": ":"}}
    settings = WorkspaceSettings.model_validate(doc)
    dumped = settings.model_dump(exclude_unset=True)
    assert dumped["default_entry"] == "g1"
    assert dumped["console"] == {"command_prefix": ":"}


def test_issue_path_is_json_pointer() -> None:
    Issue(severity="error", code="schema", message="m", node_id="n1", path="/categories/0/port")
    Issue(severity="info", code="c", message="m", path="")
    with pytest.raises(ValidationError):
        Issue(severity="error", code="c", message="m", path="categories/0")
    with pytest.raises(ValidationError):
        Issue.model_validate({"severity": "fatal", "code": "c", "message": "m"})


def test_usage_accepts_extra_numeric_keys() -> None:
    usage = Usage.model_validate({"input_tokens": 3, "output_tokens": 4, "reasoning_tokens": 7})
    assert usage.model_dump(exclude_none=True) == {
        "input_tokens": 3,
        "output_tokens": 4,
        "reasoning_tokens": 7,
    }


def test_node_run_waiting_and_attempt() -> None:
    nr = NodeRun(run_id="r", node_id="n", status="waiting", attempt=2, iteration=1)
    assert nr.status == "waiting"
    with pytest.raises(ValidationError):
        NodeRun(run_id="r", node_id="n", status="succeeded", attempt=0)


def test_descriptor_optional_ui_hints() -> None:
    d = NodeTypeDescriptor(id="t", title="T")
    assert d.ui_hints is None
    d2 = NodeTypeDescriptor.model_validate(
        {"id": "t", "title": "T", "ui_hints": {"icon": "🙂", "color": "#123456", "future": 1}}
    )
    assert d2.ui_hints is not None
    assert d2.ui_hints.icon == "🙂"


def test_ws_unions_discriminate_by_type() -> None:
    client = WsClientMessage.model_validate(
        {"type": "subscribe", "id": "1", "payload": {"topic": "run:r1", "since_seq": 5}}
    )
    assert client.root.type == "subscribe"
    server = WsServerMessage.model_validate(
        {"type": "error", "payload": {"code": "bad_request", "message": "m"}}
    )
    assert server.root.type == "error"
    with pytest.raises(ValidationError):
        WsClientMessage.model_validate({"type": "shell.exec", "payload": {}})


def test_error_response_and_conflict_status() -> None:
    body = ErrorResponse.model_validate(
        {
            "error": {
                "code": ErrorCodes.VERSION_CONFLICT,
                "message": "충돌",
                "details": {"current_version_hash": "abc"},
            }
        }
    )
    assert HTTP_STATUS_BY_ERROR_CODE[body.error.code] == 412
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.VERSION_REQUIRED] == 428


def test_create_run_request_defaults() -> None:
    req = CreateRunRequest(graph_id="g")
    assert req.origin == "api"
    assert req.input == {}
