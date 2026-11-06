"""계약 0.13.0(6R.3, design §6R.6·§6R.18): 하위 모듈 `sdd` 1.0.0, `runs`·`chat`·`logs`·`modules`·
`common` minor.

- 모델 왕복: YAML 예(문서 틀·스펙) → 모델 → JSON → 모델이 같다.
- 모르는 키 보존: `SpecTemplate`·`SpecDefinition`(최상위·규칙 안).
- 0.12 응답 읽기: 기존 모델에 더한 필드는 모두 선택이다.
- `LabelDisplay`에 웹 경로 문자열 필드가 없다.
"""

import io
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from ruamel.yaml import YAML

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    RUN_LABEL_LIMITS,
    RUN_ORIGINS,
    X_UI,
    ConversationPage,
    CreateConversationRequest,
    CreateRunRequest,
    ErrorCodes,
    KnownIssueCodes,
    KnownUiWidgets,
    LabelDisplay,
    LabelDisplayTarget,
    LogSourceInfo,
    ModuleInfo,
    Run,
    RunPage,
    SddChangedMessage,
    WsServerMessage,
    build_schema,
    run_label_problems,
    sdd,
    x_ui,
)
from agent_console_contracts.schema_help import contract_form_roots, lint_contract_help

# ---------------------------------------------------------------- 버전


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_13_0() -> None:
    """0.13.0에서 정한 버전 이상이다(정확한 지금 값은 0.13.1 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 13, 0)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0130 = {
        "common": "1.8.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.5.0",
        "runs": "1.7.0",
        "usage": "1.1.0",
        "projects": "3.1.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.0.0",
        "modules": "1.4.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0130)
    for sub, version in v0130.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_new_models_live_in_their_submodules() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        # §6R.6
        "SpecTemplate",
        "SpecDefinition",
        "SpecDocument",
        "SpecRules",
        "SpecSyntax",
        "TaskSyntax",
        "TaskStatusSpec",
        "RequirementSyntax",
        "StageSyntax",
        "DocumentStateSpec",
        "StateTransition",
        "SpecGate",
        "RunProfile",
        "VerificationConfig",
        "AutomationConfig",
        "SpecSummary",
        "SpecView",
        "SpecIndex",
        "ParsedTask",
        "ParsedRequirement",
        "ParsedStage",
        "EffectiveSyntax",
        "SpecCreateRequest",
        "SpecImportRequest",
        "SpecExportRequest",
        "SpecExportResult",
        "DocumentStateChange",
        "TaskPatch",
        "TaskPatchResult",
        "TaskAction",
        "TaskActionRequest",
        "TaskActionResult",
        "BulkStartRequest",
        "BulkStartResult",
        "TaskLink",
        "TaskPlan",
        "TraceMatrix",
        "TraceRow",
        "VerificationResult",
        "SddChanged",
        "SddSettings",
        # §6R.18 Q2·Q5~Q9·Q13
        "SddInfo",
        "SddCapabilities",
        "SddLimits",
        "SpecTemplateSummary",
        "TemplateVariable",
        "BulkActionsRequest",
        "BulkActionsResult",
        "AutomationState",
        "SaveAsTemplateRequest",
        "SaveAsTemplateResult",
        "ImportFileListing",
        "ImportFile",
        "SddGateBlockedDetails",
    } <= set(grouped["sdd"])
    assert {"LabelDisplay", "LabelDisplayTarget"} <= set(grouped["common"])
    assert "RunPage" in grouped["runs"]
    assert "ConversationPage" in grouped["chat"]
    assert "SddChangedMessage" in grouped["modules"]


# ---------------------------------------------------------------- 문서 틀·스펙 YAML 왕복

_TEMPLATE_YAML = """\
kind: spec-template
id: sdd-basic
name: 요구 → 설계 → 작업
description: 예시 틀
documents:
  - {id: requirements, title: 요구사항, file: requirements.md, roles: [requirements]}
  - {id: design, title: 설계, file: design.md}
  - {id: tasks, title: 작업, file: tasks.md, roles: [tasks]}
rules:
  document_states:
    - {id: draft, label: 초안}
    - {id: review, label: 검토 중}
    - {id: approved, label: 승인됨, tone: success}
  initial_document_state: draft
  transitions:
    - {from: draft, to: review, by: [human, run]}
    - {from: review, to: approved, by: [human]}
    - {from: "*", to: draft, by: [human]}
  task_statuses:
    - {id: todo, label: 할 일, marker: " "}
    - {id: doing, label: 진행 중, marker: "~"}
    - {id: done, label: 완료, marker: [x, X], done: true}
  gates:
    - id: design-approved
      applies_to: [run]
      require: {all: [{path: /documents/design/state, op: eq, value: approved}]}
      message: 설계가 승인되기 전에는 작업을 실행하지 않습니다
  run_profiles:
    - id: implement
      title: 구현
      graph: dev-team
      when: {all: [{path: /task/fields/owner, op: exists}]}
      input: {request: "작업 {task_id} {task_title}"}
      purpose: implement
      status_on: {started: doing, succeeded: done}
  verification: {purposes: [verify], result_map: {succeeded: pass, failed: fail}}
  automation: {enabled: false, profile: implement, max_parallel: 2, max_failures: 3, scope: stage}
  syntax:
    task: {id_pattern: '^(?P<id>\\S+)\\s+', roles: {depends: dependencies}}
    stage: {heading_levels: [2, 3]}
content: {file: requirements.md}
"""

_SPEC_YAML = """\
kind: spec
id: payments-v2
name: 결제 v2
documents:
  - id: requirements
    title: 요구사항
    file: requirements.md
    roles: [requirements]
    state: approved
    state_changed: {by: human, at: 1793000000}
  - id: design
    title: 설계
    file: design.md
    state: review
    state_changed: {by: run, run_id: r-1, at: 1793000100}
  - {id: tasks, title: 작업, file: tasks.md, roles: [tasks], state: draft}
rules: {}
attributes: {}
"""


def _load(text: str) -> Any:
    return YAML(typ="safe").load(io.StringIO(text))


@pytest.mark.parametrize(
    ("model", "text"),
    [(sdd.SpecTemplate, _TEMPLATE_YAML), (sdd.SpecDefinition, _SPEC_YAML)],
)
def test_yaml_round_trip(model: type[BaseModel], text: str) -> None:
    raw = _load(text)
    doc = model.model_validate(raw)
    data = doc.model_dump(mode="json", exclude_unset=True)
    assert data == raw  # 저장 형식(exclude_unset)이 원본과 같다
    again = model.model_validate_json(doc.model_dump_json())
    assert again == doc


def test_template_fields_parse() -> None:
    tpl = sdd.SpecTemplate.model_validate(_load(_TEMPLATE_YAML))
    rules = tpl.rules
    assert [d.id for d in tpl.documents] == ["requirements", "design", "tasks"]
    assert rules.transitions is not None
    assert rules.transitions[2].from_ == "*"
    assert rules.task_statuses is not None
    assert rules.task_statuses[2].marker == ["x", "X"]
    assert rules.gates is not None
    assert rules.gates[0].require.all is not None
    profile = (rules.run_profiles or [])[0]
    assert profile.status_on == {"started": "doing", "succeeded": "done"}
    assert profile.when is not None
    assert rules.automation is not None
    assert rules.automation.scope == "stage"
    assert rules.syntax is not None
    assert rules.syntax.task is not None
    # 생략한 규칙 키는 None(= 사용자 설정·기본 문법을 따름), 빈 목록과 구분한다.
    empty = sdd.SpecRules()
    assert empty.document_states is None
    assert empty.run_profiles is None
    assert empty.syntax is None
    with pytest.raises(ValidationError):
        sdd.AutomationConfig.model_validate({"scope": "everything"})


def test_unknown_keys_are_preserved() -> None:
    raw = _load(_TEMPLATE_YAML)
    raw["future_key"] = {"x": 1}
    raw["rules"]["future_rule"] = [1, 2]
    raw["documents"][0]["extra"] = "keep"
    raw["rules"]["run_profiles"][0]["retry"] = 2
    for model in (sdd.SpecTemplate, sdd.SpecDefinition):
        doc = model.model_validate(raw)
        out = doc.model_dump(mode="json", exclude_unset=True)
        assert out["future_key"] == {"x": 1}
        assert out["rules"]["future_rule"] == [1, 2]
        assert out["documents"][0]["extra"] == "keep"
        assert out["rules"]["run_profiles"][0]["retry"] == 2


def test_state_transition_uses_from_key() -> None:
    t = sdd.StateTransition.model_validate({"from": "a", "to": "b"})
    assert t.model_dump() == {"from": "a", "to": "b", "by": []}
    schema = build_schema()["$defs"]["StateTransition"]
    assert "from" in schema["properties"]
    assert "from_" not in schema["properties"]


# ---------------------------------------------------------------- 규칙 폼 x-ui(Q11)


def test_rules_schema_carries_widgets_item_titles_and_order() -> None:
    defs = build_schema()["$defs"]

    def ui(model: str, field: str) -> dict[str, Any]:
        value: dict[str, Any] = defs[model]["properties"][field][X_UI]
        return value

    assert ui("SpecGate", "require")["widget"] == KnownUiWidgets.CONDITION
    assert ui("RunProfile", "when")["widget"] == KnownUiWidgets.CONDITION
    assert ui("TaskSyntax", "id_pattern")["widget"] == KnownUiWidgets.REGEX
    assert ui("RunProfile", "input")["widget"] == KnownUiWidgets.TEMPLATE_TEXT
    assert ui("RunProfile", "graph")["widget"] == KnownUiWidgets.GRAPH_REF
    assert ui("AutomationConfig", "profile")["widget"] == KnownUiWidgets.PROFILE_REF
    assert ui("StateTransition", "from")["widget"] == KnownUiWidgets.STATE_REF
    assert ui("RunProfile", "status_on")["widget"] == KnownUiWidgets.STATUS_REF
    assert ui("TaskStatusSpec", "tone")["widget"] == KnownUiWidgets.TONE
    assert ui("SpecRules", "run_profiles")["itemTitle"] == "/title"
    assert ui("SpecRules", "document_states")["itemTitle"] == "/label"
    assert isinstance(ui("SpecRules", "document_states")["order"], int)
    assert x_ui(item_title="/id") == {X_UI: {"itemTitle": "/id"}}


def test_known_ui_widgets_constant() -> None:
    widgets = build_schema()["x-constants"]["KNOWN_UI_WIDGETS"]
    new = {
        "condition",
        "regex",
        "template-text",
        "graph-ref",
        "profile-ref",
        "state-ref",
        "status-ref",
        "tone",
    }
    assert new <= set(widgets.values())
    # 이미 쓰던 계약 위젯 이름도 문서 상수에 있다.
    assert {"condition-list", "memory-scope-kinds", "architecture-profiles"} <= set(
        widgets.values()
    )


def test_sdd_form_models_pass_schema_help_lint() -> None:
    roots = set(contract_form_roots())
    assert {"SpecTemplate", "SpecDefinition", "SddSettings", "SpecRules", "SpecSyntax"} <= roots
    sdd_names = set(build_schema()["x-modules"]["sdd"])
    issues = [i for i in lint_contract_help() if i.path.split("/")[2] in sdd_names]
    assert issues == []


# ---------------------------------------------------------------- 보기 모델


def test_views_fill_labels_and_optional_state() -> None:
    info = sdd.TaskStatusInfo(id="todo", label="할 일", markers=[" "])
    assert info.label == "할 일"
    with pytest.raises(ValidationError):
        sdd.TaskStatusInfo.model_validate({"id": "todo"})  # 보기에서는 label 필수
    spec = sdd.SpecDefinition.model_validate(_load(_SPEC_YAML))
    view = sdd.SpecView(spec=spec, version_hash="abc", directory=".agent-console/specs/payments-v2")
    assert view.automation_state is None
    assert view.index.tasks == []
    summary = sdd.SpecSummary.model_validate({"id": "s"})
    assert summary.current_stage is None
    assert summary.updated_at is None
    assert summary.directory == ""
    state = sdd.AutomationState(enabled=True, running=False, stopped_reason="user")
    assert state.stopped_reason == sdd.KnownAutomationStopReasons.USER


def test_info_capabilities_and_label_display_copy() -> None:
    display = LabelDisplay(
        key="sdd.spec",
        title="스펙",
        target=LabelDisplayTarget(role="sdd", id_from="sdd.spec"),
    )
    info = sdd.SddInfo(
        spec_root=".agent-console/specs",
        limits=sdd.SddLimits(max_bulk_start=10, max_tasks=20000),
        label_display=[display],
    )
    assert info.capabilities.runs is False
    assert info.capabilities.templates is False
    assert info.label_display[0].target is not None


def test_bulk_actions_and_save_as_template_models() -> None:
    res = sdd.BulkActionsResult.model_validate(
        {
            "actions": [{"integration": "runs", "id": "implement", "label": "구현"}],
            "per_task": {"2.1": [{"integration": "runs", "id": "implement"}]},
        }
    )
    assert res.per_task["2.1"][0].id == "implement"
    req = sdd.SaveAsTemplateRequest(name="새 틀")
    assert req.on_conflict == "fail"
    assert req.include_content is False
    assert req.target is None
    with pytest.raises(ValidationError):
        sdd.SaveAsTemplateRequest.model_validate({"name": "x", "on_conflict": "merge"})
    result = sdd.SaveAsTemplateResult(template_id="t", status="renamed")
    assert result.target.project_id is None  # 기본 = 라이브러리
    details = sdd.SddGateBlockedDetails(gate_id="g", document_ids=["design"])
    assert details.message == ""
    listing = sdd.ImportFileListing.model_validate(
        {"files": [{"name": "a.md", "size": 3, "title_guess": "A"}]}
    )
    assert listing.path == ""
    assert listing.truncated is False


def test_document_constants() -> None:
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_DOCUMENT_ROLES"] == {"REQUIREMENTS": "requirements", "TASKS": "tasks"}
    assert set(constants["KNOWN_GATE_TARGETS"].values()) == {"run", "task_status", "document_state"}
    assert set(constants["KNOWN_TRANSITION_ACTORS"].values()) == {"human", "run", "agent"}
    assert set(constants["KNOWN_AUTOMATION_STOP_REASONS"].values()) == {
        "user",
        "stage_done",
        "spec_done",
        "failures",
        "link_disabled",
    }
    assert set(constants["KNOWN_TRACE_GAPS"].values()) == {
        "no_task",
        "no_run",
        "not_verified",
        "verification_failed",
        "task_not_done",
    }
    assert constants["KNOWN_TASK_LINK_KINDS"] == {"RUN": "run"}
    assert set(constants["KNOWN_SYNTAX_SOURCES"].values()) == {"default", "settings", "spec"}


def test_error_and_issue_codes() -> None:
    expected = {
        ErrorCodes.SDD_NOT_FOUND: 404,
        ErrorCodes.SDD_DOCUMENT_MISSING: 404,
        ErrorCodes.SDD_TEMPLATE_EXISTS: 409,
        ErrorCodes.SDD_GATE_BLOCKED: 422,
        ErrorCodes.SDD_TASK_CHANGED: 409,
        ErrorCodes.SDD_TRANSITION_DENIED: 403,
        ErrorCodes.SDD_ACTION_UNAVAILABLE: 409,
        ErrorCodes.SDD_SPACES_UNAVAILABLE: 409,
        ErrorCodes.SDD_CONFIG_READONLY: 409,
        ErrorCodes.SDD_SECRET_REJECTED: 422,
    }
    for code, status in expected.items():
        assert code.startswith("sdd.")
        assert HTTP_STATUS_BY_ERROR_CODE[code] == status, code
    for name in (
        "SDD_DUPLICATE_TASK_ID",
        "SDD_UNKNOWN_DEPENDENCY",
        "SDD_DEPENDENCY_CYCLE",
        "SDD_UNKNOWN_STATUS_MARKER",
        "SDD_RANGE_UNRESOLVED",
        "SDD_STATUS_NOT_APPLIED",
        "SDD_SYNTAX_MISSING",
        "SDD_PROFILE_GRAPH_MISSING",
        "SDD_SECRET_SUSPECT",
        "SDD_ACTION_UNAVAILABLE",
        "SDD_DOCUMENT_MISSING",
    ):
        assert getattr(KnownIssueCodes, name).startswith("sdd."), name


# ---------------------------------------------------------------- runs·chat·logs·modules·common


def test_run_labels_and_page() -> None:
    assert "sdd" in RUN_ORIGINS
    assert RUN_LABEL_LIMITS == {"max_labels": 16, "max_key_length": 64, "max_value_length": 256}
    req = CreateRunRequest(graph_id="g", labels={"sdd.spec": "p", "sdd.task": "2.1"})
    assert req.labels["sdd.task"] == "2.1"
    too_many = {f"k{i}": "v" for i in range(17)}
    for bad in (too_many, {"x" * 65: "v"}, {"k": "v" * 257}, {"": "v"}):
        assert run_label_problems(bad)
        with pytest.raises(ValidationError):
            CreateRunRequest(graph_id="g", labels=bad)
    page = RunPage.model_validate({"items": [], "source": "project"})
    assert page.next_cursor is None
    with pytest.raises(ValidationError):
        RunPage.model_validate({"items": [], "source": "other"})
    assert ConversationPage.model_validate({"source": "app"}).items == []


def test_0_12_responses_still_read() -> None:
    run = Run.model_validate(
        {
            "id": "r",
            "graph_id": "g",
            "graph_version": "v",
            "status": "completed",
            "input": {},
            "origin": "web",
            "created_at": 1.0,
        }
    )
    assert run.labels == {}
    module = ModuleInfo.model_validate(
        {"id": "mod-x", "kind": "feature", "version": "0.1.0", "status": "active"}
    )
    assert module.description is None
    assert module.label_display == []
    source = LogSourceInfo.model_validate(
        {"descriptor": {"id": "s", "title": "출처", "format": "jsonl"}, "enabled": True}
    )
    assert source.default_effective is None


def test_create_conversation_request_rejects_unknown_keys() -> None:
    ok = CreateConversationRequest.model_validate(
        {"graph_id": "g", "title": "t", "project_id": "p"}
    )
    assert ok.project_id == "p"
    with pytest.raises(ValidationError):
        CreateConversationRequest.model_validate({"graph_id": "g", "project": "p"})


def test_label_display_has_no_web_path_field() -> None:
    """라벨 표시 규칙은 웹 경로를 담지 않는다(역할 + id로 웹이 라우트 데이터로 푼다)."""
    forbidden = {"href", "path", "url", "route", "link", "to"}
    for model in (LabelDisplay, LabelDisplayTarget):
        assert not set(model.model_fields) & forbidden, model.__name__
        schema_props = set(build_schema()["$defs"][model.__name__]["properties"])
        assert not schema_props & forbidden, model.__name__
    assert set(LabelDisplay.model_fields) == {"key", "title", "target", "group", "order"}
    assert set(LabelDisplayTarget.model_fields) == {"role", "id_from", "query"}


def test_sdd_changed_ws_message() -> None:
    msg = WsServerMessage.model_validate(
        {"type": "sdd.changed", "payload": {"spec_id": "s", "space": {"project_id": "p1"}}}
    )
    assert isinstance(msg.root, SddChangedMessage)
    assert msg.root.payload.space.project_id == "p1"
