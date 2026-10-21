"""JSON Schema 생성·드리프트 검사, 그리고 계약이 특정 노드 타입을 모른다는 것(R0.3)."""

import json
from pathlib import Path
from typing import Any

from agent_console_contracts import (
    CONTRACT_MODELS,
    SCHEMA_FILENAME,
    build_schema,
    check_schemas,
    export_schemas,
    render_schema,
)
from agent_console_contracts.__main__ import main

PHASE1_MODELS = [
    "Agent",
    "Graph",
    "NodeSpec",
    "EdgeSpec",
    "PortSpec",
    "NodeTypeDescriptor",
    "EdgeTypeDescriptor",
    "BackendDescriptor",
    "ModelInfo",
    "Run",
    "NodeRun",
    "RunSnapshot",
    "RunEvent",
    "KnownRunEvent",
    "Usage",
    "ErrorInfo",
    "Issue",
    "WorkspaceSettings",
    "WsClientMessage",
    "WsServerMessage",
    "ErrorResponse",
]

# design.md에 예로 나오는 노드·엣지 타입·백엔드 이름.
# 계약 스키마의 그래프/디스크립터 부분에 나오면 안 된다.
EXAMPLE_EXTENSION_NAMES = {
    "input",
    "router",
    "agent",
    "output",
    "branch",
    "loop",
    "parallel",
    "join",
    "approval",
    "subgraph",
    "command",
    "check",
    "data",
    "on_error",
    "condition",
    "escalate",
    "loop_back",
    "fake",
    "claude-agent-sdk",
    "rule",
    "model",
}
GRAPH_SIDE_DEFS = [
    "Graph",
    "NodeSpec",
    "EdgeSpec",
    "PortSpec",
    "PortDef",
    "Endpoint",
    "NodeTypeDescriptor",
    "EdgeTypeDescriptor",
    "BackendDescriptor",
]


def _fixed_values(node: Any) -> set[str]:
    """스키마 안의 enum/const/default 문자열 값 전부."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                found |= {v for v in value if isinstance(v, str)}
            elif key in ("const", "default") and isinstance(value, str):
                found.add(value)
            else:
                found |= _fixed_values(value)
    elif isinstance(node, list):
        for item in node:
            found |= _fixed_values(item)
    return found


def test_schema_contains_phase1_models() -> None:
    defs = build_schema()["$defs"]
    for name in PHASE1_MODELS:
        assert name in defs, name


def test_schema_is_deterministic() -> None:
    assert render_schema() == render_schema()
    json.loads(render_schema())


def _object_branch(prop: dict[str, Any]) -> dict[str, Any]:
    """nullable(`anyOf [object, null]`)이면 객체 분기를, 아니면 그대로 돌려준다."""
    for branch in prop.get("anyOf", []):
        if branch.get("type") == "object":
            return dict(branch)
    return prop


def test_open_dicts_for_config_attributes_backend_options() -> None:
    defs = build_schema()["$defs"]
    open_object = {"additionalProperties": True, "type": "object"}
    for model, field in [
        ("NodeSpec", "config"),
        ("EdgeSpec", "config"),
        ("Agent", "attributes"),
        ("Agent", "backend_options"),
        ("AgentSettings", "backend_options"),
        ("Graph", "attributes"),
        ("NodeTypeDescriptor", "config_schema"),
        ("Resource", "config"),
        ("Interaction", "payload"),
    ]:
        prop = _object_branch(defs[model]["properties"][field])
        assert {k: prop[k] for k in open_object} == open_object, (model, field)


def test_contract_has_no_specific_node_or_edge_type_names() -> None:
    defs = build_schema()["$defs"]
    for name in GRAPH_SIDE_DEFS:
        leaked = _fixed_values(defs[name]) & EXAMPLE_EXTENSION_NAMES
        assert not leaked, (name, leaked)
    for model, field in [("NodeSpec", "type"), ("EdgeSpec", "kind"), ("NodeTypeDescriptor", "id")]:
        prop = defs[model]["properties"][field]
        assert prop["type"] == "string"
        assert not {"enum", "const", "default"} & prop.keys(), (model, field)


def test_package_source_has_no_example_extension_names() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "agent_console_contracts"
    names = EXAMPLE_EXTENSION_NAMES - {
        "agent",
        "input",
        "model",
        "check",
        "data",
    }  # 필드·kind 이름과 겹치는 일반어 제외
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in names:
            assert f'"{name}"' not in text, (path.name, name)


def test_export_and_check(tmp_path: Path) -> None:
    assert check_schemas(tmp_path) == [tmp_path / SCHEMA_FILENAME]  # 파일 없음 = 드리프트
    written = export_schemas(tmp_path)
    assert written == [tmp_path / SCHEMA_FILENAME]
    assert check_schemas(tmp_path) == []
    written[0].write_text(
        written[0].read_text(encoding="utf-8").replace("Graph", "Grap"), encoding="utf-8"
    )
    assert check_schemas(tmp_path) == written


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert main(["check", str(tmp_path)]) == 1
    assert main(["export", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0


def test_contract_models_are_unique() -> None:
    assert len(set(CONTRACT_MODELS)) == len(CONTRACT_MODELS)


FORM_MODELS = (
    "WorkspaceSettings",
    "Limits",
    "AgentSettings",
    "GraphSettings",
    "ObserveSettings",
    "ChatSettings",
    "EditorSettings",
    "DelegationSettings",
    "InteractionSettings",
    "UsageSettings",
    "UsageSourceSetting",
    "ResourceAttachment",
    "UiPreferences",
    "VersionUiSettings",
    "NotificationSettings",
    "UsageIndicatorSettings",
    "UsageIndicatorColorRule",
    "SecretRuleSettings",
    "CollectorSetting",
    "LogSettings",
    "LogSourceSetting",
    "LogTaxonomy",
    "LogCategory",
    "LogProjectSettings",
    "LogProjectGroup",
    "LogDashboard",
    "LogWidget",
    "LogWidgetQuery",
)


def test_form_schemas_have_display_titles_without_backticks() -> None:
    """설정 폼에 그대로 보이는 모델(워크스페이스·팀 구성·에이전트 설정 층과 그 묶음)의 문구.

    모델 title은 클래스 이름이 아닌 표시명, 모든 속성에 title, 백틱 표기 없음.
    TS 타입 이름은 `$defs` 키로 만들어지므로 title을 바꿔도 타입 이름은 그대로다.
    """
    defs = build_schema()["$defs"]
    for name in FORM_MODELS:
        model = defs[name]
        assert model["title"] != name
        texts = [model["title"], model.get("description", "")]
        for prop_name, prop in model["properties"].items():
            assert prop.get("title"), f"{name}.{prop_name}"
            texts += [prop["title"], prop.get("description", "")]
        assert [t for t in texts if "`" in t] == [], name
