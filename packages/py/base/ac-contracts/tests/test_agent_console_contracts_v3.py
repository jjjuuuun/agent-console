"""계약 v3(design §2R.2 표 1~14): 새 모델·필드·문서 상수, 새 설정 묶음의 "생략 = 상속" 왕복,
R0(답변 연결 위치·다시 실행 가능·내보내기 형식에 계약 쪽 이름 기본값 없음),
보류 설정 deprecated 표시.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from agent_console_contracts import (
    CONTRACT_MODELS,
    CONTRACTS_VERSION,
    RUN_ORIGINS,
    AnswerSlot,
    BundlePreview,
    ChatSettings,
    ChatTurn,
    ConversationSummary,
    DefinitionDiff,
    DraftGraphRequest,
    DraftNodeRequest,
    EdgeTypeDescriptor,
    ExporterDescriptor,
    ExportFile,
    ExportPlan,
    ExportRequest,
    ExportResult,
    ExportWriteRequest,
    Graph,
    GraphSummary,
    Interaction,
    KnownIssueCodes,
    KnownResourceSlots,
    NodeTypeDescriptor,
    NotificationSettings,
    QueuedMessage,
    ReplyFields,
    ResourceContentSpec,
    ResourceFile,
    RestoreVersionRequest,
    ResumeOptions,
    ResumeRunRequest,
    Run,
    SecretRuleSettings,
    ServerInfo,
    TeamPlanSummary,
    UiPreferences,
    WorkspaceSettings,
    build_schema,
)

SRC = Path(__file__).resolve().parents[1] / "src" / "agent_console_contracts"


def _string_fixed_values(node: Any) -> set[str]:
    """스키마 안의 문자열 enum·const·default 값(목록 default의 문자열 포함)."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum":
                found |= {v for v in value if isinstance(v, str)}
            elif key in ("const", "default"):
                if isinstance(value, str):
                    found.add(value)
                elif isinstance(value, list):
                    found |= {v for v in value if isinstance(v, str)}
                else:
                    found |= _string_fixed_values(value)
            else:
                found |= _string_fixed_values(value)
    elif isinstance(node, list):
        for item in node:
            found |= _string_fixed_values(item)
    return found - {""}


# ---------------------------------------------------------------- 버전·상수


def test_contracts_version_is_exported() -> None:
    # v3(0.4.0) 뒤 값은 v4 테스트가 확인한다. 여기서는 스키마 상수와 같은지만 본다.
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION


def test_resume_origin_and_document_constants() -> None:
    assert "resume" in RUN_ORIGINS
    assert "resume" in build_schema()["x-constants"]["RUN_ORIGINS"]
    assert KnownResourceSlots.RULES == "rules"
    assert KnownIssueCodes.LIMITS_NOT_ENFORCED == "limits.not_enforced"
    assert KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED == "resource.slot_unsupported"
    assert KnownIssueCodes.SECRET_PLAIN_FOUND == "secret.plain_found"
    # 문서 상수는 이름 → 값 표(KNOWN_ISSUE_CODES)로만 나가고, Issue.code는 열린 문자열 그대로다
    # (5.2R.3 후속에서 "TS로 내보내지 않음"을 바꿈: TS가 값을 손으로 복사하지 않게).
    schema = build_schema()
    table = schema["x-constants"]["KNOWN_ISSUE_CODES"]
    for code in ("limits.not_enforced", "resource.slot_unsupported", "secret.plain_found"):
        assert code in table.values()
    assert "enum" not in schema["$defs"]["Issue"]["properties"]["code"]


def test_new_models_are_in_schema() -> None:
    defs = build_schema()["$defs"]
    for name in [
        "GraphValidationSummary",
        "BundlePreview",
        "ReplyFields",
        "AnswerSlot",
        "EntrySlot",
        "TeamPlanSummary",
        "DraftNodeRequest",
        "DraftGraphRequest",
        "SecretRuleSettings",
        "NotificationSettings",
        "ResumeOptions",
        "ResumeNodeOption",
        "ResumeRunRequest",
        "DefinitionDiff",
        "DiffChange",
        "ContentChange",
        "RestoreVersionRequest",
        "ResourceFile",
        "ExporterDescriptor",
        "ExportSelection",
        "ExportRequest",
        "ExportFile",
        "ExportPlan",
        "ExportRootInfo",
        "ExportWriteRequest",
        "ExportResult",
    ]:
        assert name in defs, name
    assert len(set(CONTRACT_MODELS)) == len(CONTRACT_MODELS)


# ---------------------------------------------------------------- #1 검증 요약, #2 묶음 미리보기


def test_graph_summary_validation_is_optional() -> None:
    base = {"id": "g", "name": "G", "version_hash": "h", "node_count": 1, "edge_count": 0}
    assert GraphSummary.model_validate(base).validation is None  # null = 계산 안 함
    summary = GraphSummary.model_validate(
        {
            **base,
            "validation": {
                "blocks_run": True,
                "error_count": 1,
                "warning_count": 2,
                "codes": ["x.y"],
            },
        }
    )
    assert summary.validation is not None
    assert summary.validation.blocks_run is True
    with pytest.raises(ValidationError):
        GraphSummary.model_validate(
            {**base, "validation": {"blocks_run": False, "error_count": -1}}
        )


def test_bundle_preview_carries_warnings() -> None:
    preview = BundlePreview.model_validate(
        {
            "bundle": {"slots": {"any-slot": [1]}},
            "warnings": [{"severity": "warning", "code": "c", "message": "m"}],
        }
    )
    assert preview.bundle.slots == {"any-slot": [1]}
    assert preview.warnings[0].code == "c"


# ---------------------------------------------------------------- #3 답변 계획(H1)


def test_reply_fields_have_no_contract_key_names() -> None:
    edge = EdgeTypeDescriptor.model_validate({"id": "any-edge", "title": "연결"})
    assert edge.reply_fields is None
    assert ReplyFields().model_dump() == {
        "label": None,
        "order": None,
        "final": None,
        "stream": None,
    }
    props = build_schema()["$defs"]["ReplyFields"]["properties"]
    assert not _string_fixed_values(props)
    declared = EdgeTypeDescriptor.model_validate(
        {"id": "e", "title": "t", "reply_fields": {"label": "/my/label", "final": "/done"}}
    )
    assert declared.reply_fields is not None
    assert declared.reply_fields.label == "/my/label"
    assert declared.reply_fields.order is None
    with pytest.raises(ValidationError):
        ReplyFields.model_validate({"label": "label"})  # JSON Pointer가 아님


def test_answer_slot_defaults_and_team_plan() -> None:
    slot = AnswerSlot.model_validate({"edge_id": "e1", "node_id": "n1"})
    assert (slot.final, slot.stream, slot.label, slot.order) == (True, False, None, None)
    plan = TeamPlanSummary.model_validate(
        {
            "entries": [{"edge_id": "e0", "node_id": "n0"}],
            "answers": [{"edge_id": "e1", "node_id": "n1", "label": "요약", "order": 2}],
            "grants": {"n1": {"kinds": ["k-1"]}},
        }
    )
    assert plan.grants["n1"].kinds == ["k-1"]
    assert plan.answers[0].order == 2


# ---------------------------------------------------------------- #4 대기 표시 이름, #5 초안 요청


def test_interaction_node_label_is_optional() -> None:
    base = {
        "id": "i1",
        "run_id": "r1",
        "node_id": "n1",
        "kind": "k",
        "status": "pending",
        "created_at": 1.0,
    }
    assert Interaction.model_validate(base).node_label is None
    assert Interaction.model_validate({**base, "node_label": "검토"}).node_label == "검토"


def test_draft_requests_carry_unsaved_graph() -> None:
    graph = {"id": "draft", "name": "초안", "nodes": [{"id": "n1", "type": "any"}]}
    assert DraftGraphRequest.model_validate({"graph": graph}).graph.id == "draft"
    req = DraftNodeRequest.model_validate({"graph": graph, "node_id": "n1"})
    assert isinstance(req.graph, Graph)
    with pytest.raises(ValidationError):
        DraftNodeRequest.model_validate({"graph": graph})


# ---------------------------------------------------------------- 생략 = 상속(새 설정 묶음)


@pytest.mark.parametrize(
    "doc",
    [
        {},
        {"secrets": {}},
        {"secrets": {"extra_key_names": ["my_pass"]}},
        {"secrets": {"extra_value_patterns": ["^zz-"], "redact_suspected_in_logs": False}},
        {"ui": {"notifications": {}}},
        {"ui": {"notifications": {"enabled": True, "events": []}}},
        {"ui": {"notifications": {"sound": True, "only_when_hidden": False}}},
        {"chat": {"queue_after_restart": "drop"}},
        {"chat": {"offer_resume": False, "busy_policy": "reject"}},
    ],
)
def test_new_workspace_sections_round_trip(doc: dict[str, Any]) -> None:
    ws = WorkspaceSettings.model_validate(doc)
    assert ws.model_dump(mode="json", exclude_unset=True) == doc
    assert WorkspaceSettings.model_validate(ws.model_dump(exclude_unset=True)) == ws


def test_new_sections_defaults_when_omitted() -> None:
    ws = WorkspaceSettings.model_validate({})
    assert ws.secrets == SecretRuleSettings()
    assert ws.secrets.extra_key_names == []
    assert ws.secrets.redact_suspected_in_logs is True
    assert ws.ui.notifications == NotificationSettings()
    assert ws.ui.notifications.enabled is False
    assert ws.ui.notifications.sound is False
    assert ws.ui.notifications.events == ["interaction.requested"]
    assert ws.ui.notifications.only_when_hidden is True
    assert ws.chat.queue_after_restart == "ask"
    assert ws.chat.offer_resume is True
    # 생략한 기본값은 저장되지 않는다.
    assert UiPreferences.model_validate({}).model_dump(exclude_unset=True) == {}


def test_graph_layer_chat_new_keys_round_trip() -> None:
    doc: dict[str, Any] = {
        "id": "team",
        "name": "팀",
        "settings": {"chat": {"queue_after_restart": "run", "offer_resume": False}},
    }
    graph = Graph.model_validate(doc)
    assert graph.model_dump(mode="json", exclude_unset=True) == doc
    assert graph.settings is not None
    assert graph.settings.chat is not None
    assert graph.settings.chat.busy_policy == "queue"


def test_new_setting_values_validated() -> None:
    with pytest.raises(ValidationError):
        ChatSettings.model_validate({"queue_after_restart": "later"})
    with pytest.raises(ValidationError):
        WorkspaceSettings.model_validate({"secrets": {"extra_key_names": "not-a-list"}})


# ---------------------------------------------------------------- #6 서버 경고, #7 대기열


def test_server_info_warnings() -> None:
    info = ServerInfo.model_validate({"server_version": "1", "contracts_version": "0.3.0"})
    assert info.warnings == []
    info = ServerInfo.model_validate(
        {
            "server_version": "1",
            "contracts_version": "0.3.0",
            "warnings": [
                {
                    "severity": "warning",
                    "code": KnownIssueCodes.SECRET_PLAIN_FOUND,
                    "message": "평문 비밀 의심",
                    "details": {"kind": "agent", "id": "a1", "path": "/backend_options/x"},
                }
            ],
        }
    )
    assert info.warnings[0].details["kind"] == "agent"


def test_queued_message_held() -> None:
    assert QueuedMessage.model_validate({"position": 1}).held is False
    assert QueuedMessage.model_validate({"position": 1, "held": True}).held is True
    base = {"id": "c1", "graph_id": "g", "created_at": 1.0, "updated_at": 1.0}
    assert ConversationSummary.model_validate(base).held == 0
    assert ConversationSummary.model_validate({**base, "queued": 2, "held": 2}).held == 2


# ---------------------------------------------------------------- #8 이어 가기


def test_resume_contracts() -> None:
    run = Run.model_validate(
        {
            "id": "r2",
            "graph_id": "g",
            "graph_version": "h",
            "status": "running",
            "input": {},
            "origin": "resume",
            "resumed_from": "r1",
            "created_at": 1.0,
        }
    )
    assert run.resumed_from == "r1"
    turn = ChatTurn.model_validate(
        {"run_id": "r2", "user_text": "", "status": "running", "resumed_from": "r1"}
    )
    assert turn.resumed_from == "r1"
    options = ResumeOptions.model_validate(
        {
            "run_id": "r1",
            "nodes": [{"node_id": "n1", "label": "검토", "rerunnable": True, "status": "waiting"}],
        }
    )
    assert options.nodes[0].rerunnable is True
    assert ResumeRunRequest.model_validate({"node_ids": ["n1"]}).node_ids == ["n1"]
    with pytest.raises(ValidationError):
        ResumeRunRequest.model_validate({"node_ids": []})


def test_rerunnable_defaults_false_without_type_names() -> None:
    desc = NodeTypeDescriptor.model_validate({"id": "any-type", "title": "T"})
    assert desc.rerunnable is False  # 기본 노드 타입의 값은 플러그인이 선언한다
    prop = build_schema()["$defs"]["NodeTypeDescriptor"]["properties"]["rerunnable"]
    assert prop == {
        "default": False,
        "description": prop["description"],
        "type": "boolean",
    }


# ---------------------------------------------------------------- #9 버전 비교


def test_definition_diff_and_restore() -> None:
    diff = DefinitionDiff.model_validate(
        {
            "kind": "agent",
            "id": "a1",
            "from_hash": "h1",
            "to_hash": "h2",
            "changes": [
                {"op": "replace", "path": "/model", "before": "m1", "after": "m2"},
                {"op": "add", "path": "/backend_options/key", "after": "***", "secret": True},
            ],
            "content_changes": [{"path": "body.md", "before_hash": "a", "after_hash": "b"}],
        }
    )
    assert diff.changes[1].secret is True
    assert diff.changes[1].model_dump(exclude_unset=True) == {
        "op": "add",
        "path": "/backend_options/key",
        "after": "***",
        "secret": True,
    }
    with pytest.raises(ValidationError):
        DefinitionDiff.model_validate(
            {
                "kind": "a",
                "id": "a",
                "from_hash": "1",
                "to_hash": "2",
                "changes": [{"op": "move", "path": "/x"}],
            }
        )
    assert RestoreVersionRequest().message is None


# ---------------------------------------------------------------- #10 여러 파일 본문


def test_multi_file_content() -> None:
    assert ResourceContentSpec().multi_file is False
    assert ResourceContentSpec(multi_file=True).multi_file is True
    f = ResourceFile.model_validate({"path": "scripts/run.sh", "size": 10, "sha256": "ab"})
    assert f.media_type is None
    with pytest.raises(ValidationError):
        ResourceFile.model_validate({"path": "a", "size": -1, "sha256": "ab"})


# ---------------------------------------------------------------- #11 내보내기(X8)


def test_exporter_descriptor_has_no_contract_format_names() -> None:
    desc = ExporterDescriptor.model_validate({"id": "my-format", "title": "내 형식"})
    assert desc.kinds == []
    assert desc.config_schema == {}
    with pytest.raises(ValidationError):
        ExporterDescriptor.model_validate({"title": "id 없음"})
    defs = build_schema()["$defs"]
    for name in ("ExporterDescriptor", "ExportRequest", "ExportSelection"):
        assert not _string_fixed_values(defs[name]), name
    # 기본 형식 이름은 계약 소스에 없다(플러그인이 등록).
    text = (SRC / "exports.py").read_text(encoding="utf-8")
    assert "claude-dir" not in text


def test_export_request_plan_and_write() -> None:
    req = ExportRequest.model_validate(
        {"exporter": "fmt", "items": [{"kind": "agent", "id": "a1"}], "options": {"x": 1}}
    )
    assert req.items[0].kind == "agent"
    plan = ExportPlan.model_validate(
        {
            "files": [{"path": "out/a1.md", "size": 3}],
            "warnings": [{"severity": "info", "code": "c", "message": "m"}],
        }
    )
    assert plan.files[0].action == "create"
    assert req.root is None  # 목적지 없음 = 보관 파일 기준 미리보기
    with_root = ExportRequest.model_validate({"exporter": "fmt", "root": "r1", "subdir": "x"})
    assert (with_root.root, with_root.subdir) == ("r1", "x")
    with pytest.raises(ValidationError):
        ExportWriteRequest.model_validate({"exporter": "fmt"})  # 쓰기는 root 필수
    write = ExportWriteRequest.model_validate(
        {"exporter": "fmt", "items": [], "root": "r1", "subdir": "team"}
    )
    assert write.on_conflict == "fail"  # 안전한 기본값
    assert isinstance(write, ExportRequest)
    with pytest.raises(ValidationError):
        ExportFile.model_validate({"path": "a", "size": 1, "action": "delete"})
    with pytest.raises(ValidationError):
        ExportWriteRequest.model_validate({"exporter": "fmt", "on_conflict": "merge", "root": "r"})
    result = ExportResult.model_validate({"files": [{"path": "a", "size": 1, "action": "skip"}]})
    assert result.files[0].action == "skip"


# ------------------------------------------------ #13 옛 설정 키 읽기


def test_old_console_settings_kept_as_unknown_keys() -> None:
    props = build_schema()["$defs"]["WorkspaceSettings"]["properties"]
    assert props["default_backend"]["deprecated"] is True
    assert "deprecated" not in props["secrets"]
    # 사용자 파일의 값은 모르는 키로 그대로 읽고 쓴다.
    doc = {"default_entry": "g1", "console": {"command_prefix": ":"}}
    ws = WorkspaceSettings.model_validate(doc)
    assert ws.model_dump(mode="json", exclude_unset=True) == doc


# ---------------------------------------------------- 2R.7 추가(플러그인 상태·서브에이전트 칸)


def test_plugin_info_status_is_open_string() -> None:
    from agent_console_contracts import PluginInfo

    assert PluginInfo(name="p").status == "loaded"
    assert PluginInfo(name="p", loaded=False, status="disabled").status == "disabled"
    # 열린 문자열: 모르는 상태 값도 받는다(화면은 그대로 보인다)
    assert PluginInfo(name="p", status="any-new-status").status == "any-new-status"
    with pytest.raises(ValidationError):
        PluginInfo(name="p", status="")


def test_subagent_slots_default_null_without_slot_names() -> None:
    from agent_console_contracts import BackendCapabilities

    caps = BackendCapabilities()
    assert caps.subagent_slots is None  # null = 구분 정보 없음
    schema = BackendCapabilities.model_json_schema()
    assert _string_fixed_values(schema["properties"]["subagent_slots"]) == set()
    assert KnownIssueCodes.RESOURCE_SLOT_SESSION_SHARED == "resource.slot_session_shared"


def test_non_empty_factory_defaults_appear_in_schema() -> None:
    """`default_factory`로 만든 비어 있지 않은 리스트·객체 기본값도 스키마 `default`에 나온다.

    웹은 기본값을 코드에 두지 않고 스키마에서 읽는다(2R.17: `ui.notifications.events`).
    모델 기본값(중첩 설정 묶음)은 하위 스키마의 필드 기본값으로 나오므로 대상이 아니다.
    """
    from pydantic import BaseModel

    from agent_console_contracts import NotificationSettings, build_schema
    from agent_console_contracts.schema import CONTRACT_MODELS

    defs = build_schema()["$defs"]
    checked = 0
    seen: set[type[BaseModel]] = set()
    pending = list(CONTRACT_MODELS)
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, info in model.model_fields.items():
            ann = info.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                pending.append(ann)
            factory = info.default_factory
            if factory is None or (isinstance(factory, type) and issubclass(factory, BaseModel)):
                continue
            value = factory()  # type: ignore[call-arg]
            if not isinstance(value, list | dict) or not value:
                continue
            schema = defs[model.__name__]["properties"][info.alias or name]
            # 모델 목록 기본값(예: 5.2R.56 색 규칙)은 JSON 형태로 비교한다
            assert ann is not None
            dumped = TypeAdapter(ann).dump_python(value, mode="json")
            assert schema.get("default") == dumped, (model.__name__, name)
            assert schema.get("examples"), (model.__name__, name)
            checked += 1
    assert checked >= 1
    events = defs["NotificationSettings"]["properties"]["events"]
    assert events["default"] == NotificationSettings().events == ["interaction.requested"]
    # 생략 = 기본값이며 저장 형식(exclude_unset)에는 나오지 않는다
    assert NotificationSettings.model_validate({}).model_dump(exclude_unset=True) == {}
