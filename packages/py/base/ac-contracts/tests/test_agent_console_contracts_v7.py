"""계약 v7(design §5.2R.3 표 1~11, 0.8.0).

프로젝트, 오류 해결 데이터, 백엔드 사전 점검, 사용량 출처, 프리셋 요약, 위임 방식 같은 세션 여부,
모듈 옵션 보기, `x-ui` 도우미.

- 새 필드는 모두 선택이다. `UsageIndicatorSettings.value_mode` 기본값만 `used`로 바뀌었다
  (사용자 지시).
- phase-5r(0.7.0) 계약으로 읽고 쓴 결과(`fixtures/phase5r_reference.json`)와 dump·해시를 비교한다
  (기존 YAML·스냅샷·5R DB 무수정 읽기).
- "생략 = 상속" 왕복을 `project`·`editor.auto_connect_io`로 넓힌다.
"""

import hashlib
import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import agent_console_contracts as contracts
from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    X_UI,
    X_UI_TIERS,
    Agent,
    ApplyPresetRequest,
    BackendDescriptor,
    BackendUnresolvedDetails,
    Conversation,
    ConversationSummary,
    CreateConversationRequest,
    CreateRunRequest,
    DefinitionMove,
    DelegationStrategyDescriptor,
    DeletePlan,
    EditorSettings,
    ErrorCodes,
    ErrorInfo,
    Fix,
    FixAction,
    Graph,
    GraphSettings,
    GraphSummary,
    ImportRequest,
    Issue,
    KnownIssueCodes,
    KnownSuggestionIds,
    ModuleOptionsView,
    MovePlan,
    PresetSummary,
    Project,
    ProjectCreate,
    ProjectPreferences,
    ProjectUpdate,
    Resource,
    ResourceSummary,
    Run,
    UiHints,
    UsageIndicatorSettings,
    UsageSourceDescriptor,
    UsageSourceInfo,
    WorkspaceSettings,
    XUiKeys,
    build_schema,
    x_ui,
)
from agent_console_contracts import projects as projects_module

RUN: dict[str, Any] = {
    "id": "r1",
    "graph_id": "g",
    "graph_version": "v",
    "status": "completed",
    "input": {},
    "origin": "api",
    "created_at": 1.0,
}


def _sha(doc: Any) -> str:
    text = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 버전·하위 모듈


def test_contracts_version_is_v7() -> None:
    assert CONTRACTS_VERSION == "0.8.0"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.8.0"
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    assert CONTRACT_VERSIONS == {
        "common": "1.3.0",
        "resources": "1.1.0",
        "logs": "1.0.0",
        "definitions": "1.3.0",
        "runs": "1.3.0",
        "usage": "1.1.0",
        "projects": "1.0.0",
        "chat": "1.1.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "modules": "1.2.0",
    }


def test_projects_submodule_sits_with_runs_and_usage() -> None:
    order = list(CONTRACT_SUBMODULES)
    assert order.index("definitions") < order.index("projects") < order.index("chat")
    grouped = build_schema()["x-modules"]
    assert {
        "Project",
        "ProjectCreate",
        "ProjectUpdate",
        "MovePlan",
        "MovePlanRequest",
        "DefinitionMove",
        "DefinitionKey",
        "DeletePlan",
        "ProjectDeleteMode",
    } <= set(grouped["projects"])
    # 공통 설정 섹션은 definitions가 갖고 projects는 다시 내보내기만 한다
    assert "ProjectPreferences" in grouped["definitions"]
    assert projects_module.ProjectPreferences is ProjectPreferences
    assert {"Fix", "FixAction", "FixTarget"} <= set(grouped["common"])
    assert {"BackendUnresolvedDetails", "UnresolvedBackendNode"} <= set(grouped["runs"])
    assert {"UsageSetupSnippet", "UsageWindowInfo"} <= set(grouped["usage"])
    assert "ModuleOptionsView" in grouped["modules"]


def test_projects_submodule_is_usable_alone() -> None:
    for name in projects_module.__all__:
        assert getattr(projects_module, name) is getattr(contracts, name)


# ---------------------------------------------------------------- 표 1: 프로젝트


def test_project_defaults_and_round_trip() -> None:
    doc = {"id": "app", "name": "앱"}
    project = Project.model_validate(doc)
    assert project.kind == "project"
    assert project.working_directory is None
    assert project.log_projects == []
    assert project.settings is None
    assert project.model_dump(mode="json", exclude_unset=True) == doc
    full = {
        "kind": "project",
        "id": "app",
        "name": "앱",
        "description": "d",
        "working_directory": "/w",
        "log_projects": ["grp", "~ungrouped"],
        "settings": {"model": "zz-model"},
        "labels": ["x"],
        "attributes": {"k": 1},
        "zz_kept": True,
    }
    assert Project.model_validate(full).model_dump(mode="json", exclude_unset=True) == full
    with pytest.raises(ValidationError):
        Project.model_validate({"id": "bad id", "name": "n"})


def test_project_create_and_update() -> None:
    created = ProjectCreate.model_validate({"id": "p", "name": "P"})
    assert "kind" not in ProjectCreate.model_fields
    assert created.id == "p"
    update = ProjectUpdate.model_validate({"working_directory": None})
    assert update.model_dump(exclude_unset=True) == {"working_directory": None}
    assert ProjectUpdate().model_dump(exclude_unset=True) == {}


def test_move_plan_uses_from_alias() -> None:
    plan = MovePlan.model_validate(
        {
            "target": {"kind": "agent", "id": "a"},
            "to": None,
            "moves": [
                {"kind": "agent", "id": "a", "from": "p", "to": None, "required": True},
                {"kind": "resource", "id": "r", "from": "p"},
            ],
            "warnings": [{"severity": "warning", "code": "zz", "message": "m"}],
        }
    )
    assert plan.moves[0].from_ == "p"
    assert plan.moves[1].required is False
    dumped = plan.model_dump(mode="json", exclude_unset=True)
    assert dumped["moves"][0]["from"] == "p"
    assert DefinitionMove.model_validate({"kind": "k", "id": "i"}).from_ is None


def test_delete_plan_default_mode() -> None:
    plan = DeletePlan.model_validate({"project_id": "p"})
    assert plan.default_mode == "move_to_shared"
    with pytest.raises(ValidationError):
        DeletePlan.model_validate({"project_id": "p", "default_mode": "zz"})


def test_project_preferences() -> None:
    prefs = ProjectPreferences()
    assert prefs.fallback == "project"
    assert prefs.new_definition_scope == {}
    doc = {"new_definition_scope": {"agent": "shared", "zz-kind": "project"}}
    assert ProjectPreferences.model_validate(doc).model_dump(exclude_unset=True) == doc
    with pytest.raises(ValidationError):
        ProjectPreferences.model_validate({"fallback": "zz"})


# ---------------------------------------------------------------- 표 2: 정의 범위(생략 = 공용)


@pytest.mark.parametrize(
    ("model", "base"),
    [
        (Agent, {"id": "a", "name": "A"}),
        (Graph, {"id": "g", "name": "G"}),
        (Resource, {"id": "r", "type": "zz", "name": "R"}),
    ],
)
def test_definition_project_omitted_is_shared(model: type[BaseModel], base: dict[str, Any]) -> None:
    plain = model.model_validate(base)
    assert plain.__dict__["project"] is None
    # 지정하지 않으면 전체 직렬화(정의 해시 입력)에도 나타나지 않는다
    assert "project" not in plain.model_dump(mode="json")
    assert "project" not in json.loads(plain.model_dump_json())
    for value in ("p1", None):
        doc = {**base, "project": value}
        obj = model.model_validate(doc)
        assert obj.model_dump(mode="json", exclude_unset=True) == doc
        assert obj.model_dump(mode="json")["project"] == value
    with pytest.raises(ValidationError):
        model.model_validate({**base, "project": "bad id"})


def test_definition_schemas_keep_project_property() -> None:
    """직렬화 훅이 스키마를 일반 객체로 바꾸지 않는다(폼·OpenAPI·TS 생성)."""
    for model in (Agent, Graph, Resource):
        for mode in ("validation", "serialization"):
            schema = model.model_json_schema(mode=mode)
            assert "project" in schema["properties"], (model.__name__, mode)
    defs = build_schema()["$defs"]
    for name in ("Agent", "Graph", "Resource"):
        assert defs[name]["properties"]["project"]["x-ui"]["tier"] == "basic"


def test_summaries_carry_project() -> None:
    summary = GraphSummary.model_validate(
        {"id": "g", "name": "g", "version_hash": "h", "node_count": 0, "edge_count": 0}
    )
    assert summary.project is None
    resource = ResourceSummary.model_validate(
        {"id": "r", "type": "t", "name": "n", "version_hash": "h", "project": "p"}
    )
    assert resource.project == "p"


def test_workspace_projects_section_is_optional() -> None:
    settings = WorkspaceSettings.model_validate({})
    assert settings.projects is None
    assert "projects" not in settings.model_dump(exclude_unset=True)
    layer = {"projects": {"fallback": "shared"}}
    assert WorkspaceSettings.model_validate(layer).model_dump(exclude_unset=True) == layer


def test_apply_and_import_requests_take_project() -> None:
    assert ApplyPresetRequest().project is None
    assert ApplyPresetRequest.model_validate({"project": "p"}).project == "p"
    assert ImportRequest.model_validate({"source": "s"}).project is None
    assert ImportRequest.model_validate({"source": "s", "project": "p"}).project == "p"
    with pytest.raises(ValidationError):
        ApplyPresetRequest.model_validate({"project": "bad id"})


# ---------------------------------------------------------------- 표 3: 실행·대화 project_id


def test_run_and_conversation_project_id() -> None:
    assert Run.model_validate(RUN).project_id is None
    assert Run.model_validate({**RUN, "project_id": "p"}).project_id == "p"
    assert CreateRunRequest.model_validate({"graph_id": "g"}).project_id is None
    conv = {"id": "c", "graph_id": "g", "created_at": 1.0, "updated_at": 1.0}
    assert Conversation.model_validate(conv).project_id is None
    assert ConversationSummary.model_validate({**conv, "project_id": "p"}).project_id == "p"
    assert CreateConversationRequest.model_validate({"graph_id": "g", "project_id": "p"}).project_id
    # 불투명 문자열: 정의 id 규칙(slug)을 강제하지 않는다
    assert Run.model_validate({**RUN, "project_id": "삭제된 프로젝트"}).project_id


# ---------------------------------------------------------------- 표 4·5: 오류 해결·사전 점검


def test_fix_on_error_and_issue_defaults_to_none() -> None:
    plain_error = ErrorInfo.model_validate({"code": "c", "message": "m"})
    plain_issue = Issue.model_validate({"severity": "error", "code": "c", "message": "m"})
    assert plain_error.fix is None
    assert plain_issue.fix is None
    # 지정하지 않으면 전송 형식(전체 직렬화)에도 없다(0.7.0 이하와 같은 오류 본문)
    assert plain_error.model_dump(mode="json") == {"code": "c", "message": "m", "details": {}}
    assert "fix" not in plain_issue.model_dump(mode="json")
    assert "fix" not in json.loads(plain_error.model_dump_json())
    for model in (ErrorInfo, Issue):
        assert "fix" in model.model_json_schema(mode="serialization")["properties"]
    fix = {
        "actions": [
            {"label": "노드에서 지정", "target": {"role": "zz-graphs", "id": "g", "section": "n1"}},
            {"label": "기본값으로", "target": {"role": "zz-settings"}, "focus": "/backend"},
        ]
    }
    err = ErrorInfo.model_validate({"code": "c", "message": "m", "fix": fix})
    assert err.model_dump(mode="json", exclude_unset=True)["fix"] == fix
    assert Fix.model_validate({}).actions == []
    with pytest.raises(ValidationError):
        FixAction.model_validate({"label": "x", "target": {"role": "r"}, "focus": "backend"})
    with pytest.raises(ValidationError):
        FixAction.model_validate({"label": "x", "target": {"role": ""}})


def test_backend_unresolved_error() -> None:
    assert ErrorCodes.BACKEND_UNRESOLVED == "backend.unresolved"
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_UNRESOLVED] == 422
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"]["BACKEND_UNRESOLVED"] == "backend.unresolved"
    details = BackendUnresolvedDetails.model_validate(
        {
            "nodes": [{"id": "n1", "label": "조사"}, {"id": "n2"}],
            "options": [{"id": "zz-backend", "title": "가짜"}],
        }
    )
    assert details.nodes[1].label == ""
    assert details.options[0].cost_note == ""
    # ErrorInfo.details(열린 객체)에 그대로 싣고 다시 읽는다
    err = ErrorInfo(code="backend.unresolved", message="m", details=details.model_dump(mode="json"))
    assert BackendUnresolvedDetails.model_validate(err.details) == details


def test_backend_descriptor_cost_note_and_badge() -> None:
    desc = BackendDescriptor.model_validate({"id": "zz", "title": "t"})
    assert desc.cost_note == ""
    assert desc.ui_hints is None
    badged = BackendDescriptor.model_validate(
        {"id": "zz", "title": "t", "cost_note": "구독", "ui_hints": {"badge": "체험"}}
    )
    assert badged.ui_hints is not None
    assert badged.ui_hints.badge == "체험"
    assert UiHints().badge is None


# ---------------------------------------------------------------- 표 6: 편집기 auto_connect_io


@pytest.mark.parametrize(
    "layer",
    [
        {"editor": {}},
        {"editor": {"auto_connect_io": False}},
        {"editor": {"auto_connect_io": None}},
        {"editor": {"auto_connect_io": True, "default_edge_shape": "auto", "zz": 1}},
    ],
)
def test_auto_connect_io_round_trip_on_both_layers(layer: dict[str, Any]) -> None:
    assert WorkspaceSettings.model_validate(layer).model_dump(mode="json", exclude_unset=True) == (
        layer
    )
    assert GraphSettings.model_validate(layer).model_dump(mode="json", exclude_unset=True) == layer


def test_auto_connect_io_omitted_means_on_and_is_not_serialized_on_graph_layer() -> None:
    assert EditorSettings().auto_connect_io is None  # 생략 = 켬(웹이 해석)
    graph = Graph.model_validate({"id": "g", "name": "g", "settings": {"editor": {}}})
    full = graph.model_dump(mode="json")
    assert "auto_connect_io" not in full["settings"]["editor"]
    set_graph = Graph.model_validate(
        {"id": "g", "name": "g", "settings": {"editor": {"auto_connect_io": False}}}
    )
    assert set_graph.model_dump(mode="json")["settings"]["editor"]["auto_connect_io"] is False
    description = build_schema()["$defs"]["EditorSettings"]["properties"]["default_edge_shape"]
    assert "자동 경로" in description["description"]


# ---------------------------------------------------------------- 표 7: 사용량


def test_value_mode_default_is_used_but_explicit_value_is_kept() -> None:
    assert UsageIndicatorSettings().value_mode == "used"
    explicit = {"ui": {"usage_indicator": {"value_mode": "remaining"}}}
    settings = WorkspaceSettings.model_validate(explicit)
    assert settings.ui.usage_indicator.value_mode == "remaining"
    assert settings.model_dump(mode="json", exclude_unset=True) == explicit
    schema = build_schema()["$defs"]["UsageIndicatorSettings"]["properties"]["value_mode"]
    assert schema["default"] == "used"


def test_usage_source_descriptor_new_fields() -> None:
    desc = UsageSourceDescriptor.model_validate({"id": "zz", "title": "t", "trust": "official"})
    assert (desc.auto_enable, desc.needs_setup, desc.test_only) == (False, False, False)
    assert desc.setup_snippets == []
    assert desc.windows == []
    full = UsageSourceDescriptor.model_validate(
        {
            "id": "zz",
            "title": "t",
            "trust": "observed",
            "auto_enable": True,
            "needs_setup": True,
            "setup_snippets": [
                {"id": "s", "title": "상태 줄", "text": "{agent_console_cmd} -o {output_path}"}
            ],
            "windows": [{"id": "five_hour", "title": "5시간 창", "short_title": "5h"}],
        }
    )
    assert full.setup_snippets[0].shell == ""
    assert full.windows[0].short_title == "5h"
    info = UsageSourceInfo.model_validate({"descriptor": {"id": "zz", "title": "t", "trust": "x"}})
    assert info.last_received_at is None


# ---------------------------------------------------------------- 표 8·9·10


def test_preset_summary_start_fields() -> None:
    summary = PresetSummary.model_validate({"id": "p", "name": "n"})
    assert summary.badges == []
    assert summary.featured is None
    assert summary.start_graph is None
    doc = {"id": "p", "name": "n", "badges": ["추천"], "featured": 1, "start_graph": "team"}
    assert PresetSummary.model_validate(doc).model_dump(exclude_unset=True) == doc


def test_delegation_shares_session_defaults_true() -> None:
    desc = DelegationStrategyDescriptor.model_validate(
        {"id": "zz", "title": "t", "member_fields": [], "max_depth": None}
    )
    assert desc.shares_session is True
    other = DelegationStrategyDescriptor.model_validate(
        {"id": "zz", "title": "t", "member_fields": [], "max_depth": None, "shares_session": False}
    )
    assert other.shares_session is False


def test_module_options_view_schema_alias() -> None:
    view = ModuleOptionsView.model_validate(
        {"module_id": "mod-zz", "schema": {"type": "object"}, "values": {"k": "[REDACTED]"}}
    )
    assert view.schema_ == {"type": "object"}
    assert view.model_dump(mode="json")["schema"] == {"type": "object"}
    assert view.yaml_snippet == ""
    assert ModuleOptionsView.model_validate({"module_id": "m"}).schema_ is None


# ---------------------------------------------------------------- 표 11: x-ui 도우미


def test_x_ui_helper() -> None:
    assert X_UI == "x-ui"
    assert X_UI_TIERS == ("basic", "advanced")
    assert x_ui() == {"x-ui": {}}
    assert x_ui(tier="advanced", when="w", group="g", order=2, unit="초") == {
        "x-ui": {"tier": "advanced", "when": "w", "group": "g", "order": 2, "unit": "초"}
    }
    # example은 None도 값이다
    assert x_ui(example=None) == {"x-ui": {XUiKeys.EXAMPLE: None}}
    assert x_ui(tier="basic") is not x_ui(tier="basic")
    with pytest.raises(ValueError, match="tier"):
        x_ui(tier="zz")  # type: ignore[arg-type]
    constants = build_schema()["x-constants"]
    assert constants["X_UI"] == "x-ui"
    assert constants["X_UI_TIERS"] == ["basic", "advanced"]


def test_x_ui_reaches_json_schema() -> None:
    props = build_schema()["$defs"]["EditorSettings"]["properties"]
    assert props["auto_connect_io"]["x-ui"]["tier"] == "advanced"
    prefs = build_schema()["$defs"]["ProjectPreferences"]["properties"]
    assert prefs["new_definition_scope"]["x-ui"]["example"] == {"agent": "shared"}


def test_v7_issue_codes_are_documented_constants() -> None:
    assert {
        KnownIssueCodes.BACKEND_UNRESOLVED,
        KnownIssueCodes.PROJECT_SHARED_USES_PROJECT,
        KnownIssueCodes.PROJECT_CROSS_PROJECT,
        KnownIssueCodes.PROJECT_UNKNOWN,
        KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE,
        KnownIssueCodes.PROJECT_DEFINITIONS_UNAVAILABLE,
    } == {
        "backend.unresolved",
        "project.shared_uses_project",
        "project.cross_project",
        "project.unknown",
        "project.references_unavailable",
        "project.definitions_unavailable",
    }
    assert KnownSuggestionIds.PROJECT_MOVE_TO_SHARED == "project.move_to_shared"


def test_known_issue_codes_and_suggestion_ids_reach_x_constants() -> None:
    """TS가 값을 손으로 복사하지 않도록 이름 → 값 표로 내보낸다(5.2R.3 후속)."""
    constants = build_schema()["x-constants"]
    issue_codes = {k: v for k, v in vars(KnownIssueCodes).items() if k.isupper()}
    assert constants["KNOWN_ISSUE_CODES"] == issue_codes
    assert list(constants["KNOWN_ISSUE_CODES"]) == list(issue_codes)  # 정의 순서 유지(결정적)
    assert constants["KNOWN_ISSUE_CODES"]["PROJECT_REFERENCES_UNAVAILABLE"] == (
        "project.references_unavailable"
    )
    assert constants["KNOWN_SUGGESTION_IDS"] == {"PROJECT_MOVE_TO_SHARED": "project.move_to_shared"}
    # 이슈 코드는 열린 문자열이다: 표는 문서 상수일 뿐 Issue.code 스키마는 그대로 string.
    assert build_schema()["$defs"]["Issue"]["properties"]["code"]["type"] == "string"


def test_rest_models_are_in_schema() -> None:
    defs = build_schema()["$defs"]
    for name in (
        "Project",
        "ProjectCreate",
        "ProjectUpdate",
        "MovePlan",
        "MovePlanRequest",
        "DeletePlan",
        "ProjectPreferences",
        "BackendUnresolvedDetails",
        "ModuleOptionsView",
        "Fix",
    ):
        assert name in defs, name
