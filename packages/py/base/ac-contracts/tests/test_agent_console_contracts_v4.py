"""계약 v4(design §3R.3 표 1~7, 0.5.0): 모듈 정보·기능 꺼짐 오류, 기능별 하위 모듈·버전·import 규칙,
화면 배치(layout) 모델, 편집기 기본값·디스크립터 힌트, 사용량 부분 조회, 버전 비교 설정.

"생략 = 상속" 왕복은 layout(3)과 버전 비교 설정(7)으로 넓힌다.
"""

import ast
import importlib
from pathlib import Path
from typing import Any

import pytest

import agent_console_contracts as root
from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    USAGE_REPORT_PARTS,
    EdgeLayout,
    EdgeSpec,
    EditorSettings,
    ErrorCodes,
    FeatureUnavailableDetails,
    Graph,
    GraphUiLayout,
    KnownModuleStatus,
    ModuleInfo,
    NodeLayout,
    NodeSpec,
    UiHints,
    UiPreferences,
    UsageReport,
    VersionUiSettings,
    WorkspaceSettings,
    build_schema,
    submodule_definitions,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_contracts"

# 하위 모듈이 import해도 되는 다른 하위 모듈(design §3R.3-2). import-linter layers 계약과 같은
# 내용을 패키지 안에서도 검사한다(패키지를 저장소 밖으로 가져가도 규칙이 남도록).
# 0.6.0(design §4R.9): `logs`는 `resources`와 같은 층(둘 다 `common`만 씀)이고
# `definitions`가 쓴다.
_BELOW_DEFINITIONS = {"common", "resources", "logs"}
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "common": set(),
    "resources": {"common"},
    "logs": {"common"},
    "definitions": _BELOW_DEFINITIONS,
    "runs": _BELOW_DEFINITIONS | {"definitions"},
    "usage": _BELOW_DEFINITIONS | {"definitions"},
    # 0.8.0(design §5.2R.3): projects는 runs·usage와 같은 층(definitions까지만 쓴다)
    "projects": _BELOW_DEFINITIONS | {"definitions"},
    "chat": _BELOW_DEFINITIONS | {"definitions", "runs", "usage"},
    "exports": _BELOW_DEFINITIONS | {"definitions", "runs", "usage"},
    "imports": _BELOW_DEFINITIONS | {"definitions", "runs", "usage"},
    # 0.9.0(design §5.5R.2.4): architecture는 chat·exports·imports와 같은 층
    "architecture": _BELOW_DEFINITIONS | {"definitions", "runs"},
    # 0.10.0(design §5.7R.5): memory도 같은 층(runs의 조건·definitions의 이슈만 쓴다)
    "memory": _BELOW_DEFINITIONS | {"definitions", "runs"},
    "modules": {
        "common",
        "resources",
        "logs",
        "definitions",
        "runs",
        "usage",
        "projects",
        "chat",
        "exports",
        "imports",
        # 0.10.0: WS 메시지 `memory.changed`의 payload
        "memory",
    },
}


# ---------------------------------------------------------------- 1. 버전·하위 모듈


def test_contracts_version_is_in_schema() -> None:
    """버전 값 자체는 v7 테스트가 고정한다(0.8.0)."""
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    assert constants["USAGE_REPORT_PARTS"] == ["windows", "tokens"]


def test_contract_versions_cover_every_submodule() -> None:
    assert list(CONTRACT_VERSIONS) == list(CONTRACT_SUBMODULES)
    assert set(CONTRACT_SUBMODULES) == {
        "common",
        "definitions",
        "runs",
        "chat",
        "usage",
        "resources",
        "exports",
        "imports",
        "logs",
        "modules",
        "projects",
        "architecture",
        "memory",
    }
    for version in CONTRACT_VERSIONS.values():
        major, minor, patch = version.split(".")
        assert all(part.isdigit() for part in (major, minor, patch)), version


@pytest.mark.parametrize("sub", CONTRACT_SUBMODULES)
def test_submodule_exports_are_reachable_from_root(sub: str) -> None:
    """하위 모듈의 공개 이름은 루트에서도 같은 객체다(루트 export 호환)."""
    module = importlib.import_module(f"agent_console_contracts.{sub}")
    assert module.__all__, sub
    for name in module.__all__:
        if name in root.__all__:
            assert getattr(root, name) is getattr(module, name), (sub, name)


def test_every_schema_model_belongs_to_one_submodule() -> None:
    schema = build_schema()
    grouped = schema["x-modules"]
    assert list(grouped) == list(CONTRACT_SUBMODULES)
    flat = [name for names in grouped.values() for name in names]
    assert sorted(flat) == sorted(schema["$defs"])
    assert len(flat) == len(set(flat))
    assert "Conversation" in grouped["chat"]
    assert "ModuleInfo" in grouped["modules"]
    assert "NodeLayout" in grouped["definitions"]
    assert "UsageReport" in grouped["usage"]
    with pytest.raises(ValueError, match="하위 모듈"):
        submodule_definitions(["NoSuchModel"])


def _imported_submodules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    package_parts = path.relative_to(SRC).parts
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (
                node.level == 0
                and node.module
                and node.module.startswith("agent_console_contracts")
            ):
                parts = node.module.split(".")[1:]
            elif node.level > 0:
                base = list(package_parts[:-1])[: len(package_parts) - node.level]
                parts = base + (node.module.split(".") if node.module else [])
                if not node.module:
                    found |= {alias.name for alias in node.names}
                    continue
            else:
                continue
            if parts:
                found.add(parts[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("agent_console_contracts."):
                    found.add(alias.name.split(".")[1])
    return found & set(CONTRACT_SUBMODULES)


@pytest.mark.parametrize("sub", CONTRACT_SUBMODULES)
def test_submodule_import_rules(sub: str) -> None:
    files = [SRC / f"{sub}.py"] if (SRC / f"{sub}.py").exists() else list((SRC / sub).rglob("*.py"))
    assert files, sub
    for path in files:
        used = _imported_submodules(path) - {sub}
        assert used <= ALLOWED_IMPORTS[sub], (path.name, used - ALLOWED_IMPORTS[sub])


# ---------------------------------------------------------------- 1. 모듈 정보·기능 꺼짐


def test_module_info_defaults_and_open_status() -> None:
    info = ModuleInfo.model_validate(
        {"id": "zz-mod", "kind": "zz-kind", "version": "0.1.0", "status": "zz-new-state"}
    )
    assert info.status == "zz-new-state"
    assert (info.contracts, info.web_roles, info.provides, info.requires) == ({}, [], [], [])
    assert info.reason is None
    full = ModuleInfo(
        id="m",
        kind="feature",
        version="1.2.3",
        contracts={"chat": CONTRACT_VERSIONS["chat"]},
        status=KnownModuleStatus.UNSATISFIED,
        reason="missing port",
        web_roles=["conversations"],
        provides=["chat.conversations"],
        requires=["chat.turn_launcher"],
    )
    assert ModuleInfo.model_validate(full.model_dump(mode="json")) == full
    defs = build_schema()["$defs"]
    assert defs["ModuleInfo"]["properties"]["status"] == {"$ref": "#/$defs/ModuleStatus"}
    assert defs["ModuleStatus"]["type"] == "string"
    assert "enum" not in defs["ModuleStatus"]
    # 문서 상수는 스키마 상수로 내보내지 않는다
    assert "unsatisfied" not in repr(build_schema()["x-constants"])
    assert {
        KnownModuleStatus.ACTIVE,
        KnownModuleStatus.DISABLED,
        KnownModuleStatus.UNSATISFIED,
        KnownModuleStatus.FAILED,
        KnownModuleStatus.CONFLICT,
    } == {"active", "disabled", "unsatisfied", "failed", "conflict"}


def test_feature_unavailable_error_code() -> None:
    assert ErrorCodes.FEATURE_UNAVAILABLE == "feature_unavailable"
    assert HTTP_STATUS_BY_ERROR_CODE["feature_unavailable"] == 409
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"]["FEATURE_UNAVAILABLE"] == "feature_unavailable"
    details = FeatureUnavailableDetails(module="mod-chat", port="chat.turn_launcher")
    assert details.model_dump() == {"module": "mod-chat", "port": "chat.turn_launcher"}


# ---------------------------------------------------------------- 3. 화면 배치(layout)

NODE: dict[str, Any] = {"id": "n", "type": "zz-type"}
EDGE: dict[str, Any] = {
    "id": "e",
    "source": {"node": "a", "port": "o"},
    "target": {"node": "b", "port": "i"},
    "kind": "zz-kind",
}


def test_layout_is_optional_and_absent_when_omitted() -> None:
    node = NodeSpec.model_validate(NODE)
    edge = EdgeSpec.model_validate(EDGE)
    assert node.layout is None
    assert edge.layout is None
    assert "layout" not in node.model_dump(exclude_unset=True)
    assert "layout" not in edge.model_dump(exclude_unset=True)


@pytest.mark.parametrize(
    "layout",
    [
        {"direction": "tb"},
        {"ports": {"in:in": "left", "out:result": "zz-side"}},
        {"direction": "zz-dir", "zz-future": {"kept": [1, 2]}},
    ],
)
def test_node_layout_round_trip_omitted_is_inherited(layout: dict[str, Any]) -> None:
    node = NodeSpec.model_validate({**NODE, "layout": layout})
    assert node.model_dump(mode="json", exclude_unset=True)["layout"] == layout


@pytest.mark.parametrize(
    "layout",
    [
        {"shape": "smoothstep"},
        {"waypoints": [{"x": 560, "y": 280}, {"x": 560.5, "y": 72}], "label_t": 0.3},
        {"bend": 0.5, "radius": 12, "label_offset": {"x": -4, "y": 8}},
        {"shape": "zz-plugin-shape", "zz-future": "kept"},
    ],
)
def test_edge_layout_round_trip_omitted_is_inherited(layout: dict[str, Any]) -> None:
    edge = EdgeSpec.model_validate({**EDGE, "layout": layout})
    assert edge.model_dump(mode="json", exclude_unset=True)["layout"] == layout


def test_layout_values_are_not_limited_by_contract() -> None:
    """범위·개수 제한은 편집기 규칙이다. 손으로 고친 YAML이 읽기 실패가 되지 않는다."""
    edge = EdgeLayout.model_validate(
        {
            "shape": "",
            "waypoints": [{"x": i, "y": -i} for i in range(40)],
            "bend": 7.5,
            "radius": -3,
            "label_t": 1.8,
        }
    )
    assert edge.waypoints is not None
    assert len(edge.waypoints) == 40
    node = NodeLayout.model_validate({"direction": "", "ports": {"zz": "zz"}})
    assert node.ports == {"zz": "zz"}
    defs = build_schema()["$defs"]
    for name in ("NodeLayout", "EdgeLayout", "GraphUiLayout"):
        text = repr(defs[name])
        for keyword in ("enum", "minimum", "maximum", "maxItems", "exclusiveMinimum"):
            assert f"'{keyword}'" not in text, (name, keyword)


def test_graph_ui_layout_documents_graph_ui_key() -> None:
    doc = {
        "kind": "graph",
        "id": "g",
        "name": "g",
        "ui": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout": {"direction": "tb", "edge_shape_by_kind": {"zz-kind": "step"}},
        },
    }
    graph = Graph.model_validate(doc)
    # Graph.ui는 열린 객체로 남는다(다른 키 보존)
    assert graph.model_dump(mode="json", exclude_unset=True) == doc
    layout = GraphUiLayout.model_validate(graph.ui["layout"])
    assert layout.direction == "tb"
    assert layout.edge_shape is None
    assert layout.model_dump(exclude_unset=True) == graph.ui["layout"]
    assert build_schema()["$defs"]["Graph"]["properties"]["ui"]["type"] == "object"


def test_editor_defaults_and_descriptor_hints() -> None:
    editor = EditorSettings()
    assert editor.default_direction is None
    assert editor.default_edge_shape is None
    settings = WorkspaceSettings.model_validate(
        {"editor": {"default_direction": "tb", "default_edge_shape": "zz-shape"}}
    )
    assert settings.model_dump(mode="json", exclude_unset=True)["editor"] == {
        "default_direction": "tb",
        "default_edge_shape": "zz-shape",
    }
    hints = UiHints(direction="tb", edge_shape="zz-shape")
    assert hints.model_dump(exclude_none=True) == {"direction": "tb", "edge_shape": "zz-shape"}
    defs = build_schema()["$defs"]
    for name, field in [
        ("EditorSettings", "default_direction"),
        ("EditorSettings", "default_edge_shape"),
        ("UiHints", "direction"),
        ("UiHints", "edge_shape"),
    ]:
        prop = defs[name]["properties"][field]
        assert "enum" not in repr(prop), (name, field)
        assert prop.get("default") is None


# ---------------------------------------------------------------- 6. 사용량 부분 조회


def test_usage_report_parts_null_means_not_requested() -> None:
    assert USAGE_REPORT_PARTS == ("windows", "tokens")
    full = UsageReport(generated_at=1.0)
    assert (full.windows, full.rollups) == ([], [])
    windows_only = UsageReport.model_validate({"windows": [], "rollups": None, "generated_at": 1})
    assert windows_only.rollups is None
    assert windows_only.windows == []
    dumped = windows_only.model_dump(mode="json")
    assert dumped["rollups"] is None
    assert UsageReport.model_validate(dumped) == windows_only
    props = build_schema()["$defs"]["UsageReport"]["properties"]
    for field in ("windows", "rollups"):
        assert {"type": "null"} in props[field]["anyOf"], field


# ---------------------------------------------------------------- 7. 버전 비교 설정


def test_version_ui_settings_omitted_is_inherited() -> None:
    prefs = UiPreferences()
    assert prefs.versions.item_label_keys is None
    assert "versions" not in prefs.model_dump(exclude_unset=True)
    settings = WorkspaceSettings.model_validate({"ui": {"versions": {}}})
    assert settings.ui.versions.item_label_keys is None
    assert settings.model_dump(mode="json", exclude_unset=True) == {"ui": {"versions": {}}}


@pytest.mark.parametrize("keys", [["title", "id"], [], ["zz-key"]])
def test_version_ui_settings_round_trip(keys: list[str]) -> None:
    doc = {"ui": {"versions": {"item_label_keys": keys}}}
    settings = WorkspaceSettings.model_validate(doc)
    assert settings.model_dump(mode="json", exclude_unset=True) == doc
    assert VersionUiSettings.model_validate(doc["ui"]["versions"]).item_label_keys == keys
    prop = build_schema()["$defs"]["VersionUiSettings"]["properties"]["item_label_keys"]
    assert prop.get("default") is None
