"""계약 v9(design §5.7R.5, 0.10.0): 하위 모듈 `memory` 1.0.0, `modules` 1.3.0(WS `memory.changed`).

- 메모리 사용자 데이터(설정 섹션·범위 종류·리소스 접근 설정·정리 규칙)는 YAML 예시 → 모델 → JSON
  왕복에서 적은 값과 모르는 키가 그대로 남는다.
- 실행 이벤트 `memory.*` payload에는 본문·검색어 원문 필드가 없다(크기·해시만).
- `runs`의 알려진 이벤트 목록은 바뀌지 않는다(메모리 이벤트는 `memory` 하위 모듈 문서 상수).
- 범위 종류·도구 이름은 데이터다: 계약은 이름을 모르고, 도구 기본 이름은 패키지 데이터에서 온다.
"""

import json
from io import StringIO
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

import agent_console_contracts as root
from agent_console_contracts import (
    CONTRACT_SUBMODULES,
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    KNOWN_RUN_EVENT_TYPES,
    X_UI,
    ErrorCodes,
    KnownIssueCodes,
    RunEvent,
    WsServerMessage,
    XUiKeys,
    build_schema,
    parse_run_event,
)
from agent_console_contracts import memory as mem
from agent_console_contracts.schema_help import contract_form_roots, lint_schema_help

# 사용자가 손으로 쓴 설정 섹션 memory(design §5.7R.1.4). 범위 종류 이름은 일부러 기본과 다른 임의
# 이름이고, 모든 층에 모르는 키(`x-*`)를 둔다.
SETTINGS_YAML = """\
include_default_scope_kinds: false
secrets: redact
max_versions_per_entry: 7
x-settings-note: 사용자 메모
scope_kinds:
  zz-default-kind: null
  zz-notes: {label: 노트, description: 에이전트 노트, id: "{/graph_id}/{/agent_id}", x-kind: 1}
  zz-everyone: {label: 모두}
retention:
  x-retention-note: kept
  rules:
    - id: zz-stale
      when:
        all: [{path: /tags, op: contains, value: 임시}, {path: /idle_days, op: gte, value: 30}]
      action: archive
      description: 오래된 임시 기록
      x-rule-note: [1, 2]
"""

# 리소스 종류 memory의 config(design §5.7R.1.3).
ACCESS_YAML = """\
scopes:
  - {kind: zz-notes, access: [read, search, write], x-scope-note: a}
  - {kind: zz-everyone, access: [read]}
default_scope: zz-notes
max_result_chars: 1200
x-access-note: {nested: true}
tools:
  search: {name: zz_find, description: 찾기, x-tool-note: 1}
  write: {name: zz_put, description: 쓰기}
"""


def _yaml_load(text: str) -> Any:
    return YAML(typ="safe").load(StringIO(text))


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _author(kind: str = "agent") -> dict[str, Any]:
    return {"kind": kind, "agent_id": "a1", "node_id": "n1", "run_id": "r1", "graph_id": "g1"}


def _entry(**extra: Any) -> dict[str, Any]:
    return {
        "id": "e1",
        "scope": {"kind": "zz-notes", "id": "g1"},
        "key": "결정/api-버전",
        "version": 2,
        "bytes": 12,
        "sha256": "ab" * 32,
        "created_at": 1.0,
        "created_by": _author(),
        "updated_at": 2.0,
        "updated_by": _author("user"),
        **extra,
    }


# ---------------------------------------------------------------- 버전·하위 모듈


def test_contracts_version_is_v9() -> None:
    assert CONTRACTS_VERSION == "0.10.0"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.10.0"
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS
    assert CONTRACT_VERSIONS == {
        "common": "1.4.0",
        "resources": "1.1.0",
        "logs": "1.0.0",
        "definitions": "1.3.0",
        "runs": "1.4.0",
        "usage": "1.1.0",
        "projects": "1.0.0",
        "chat": "1.1.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.0.0",
        "modules": "1.3.0",
    }


def test_memory_submodule_sits_with_architecture() -> None:
    order = list(CONTRACT_SUBMODULES)
    assert order.index("runs") < order.index("memory") < order.index("modules")
    assert order.index("definitions") < order.index("memory")
    grouped = build_schema()["x-modules"]
    assert {
        "MemorySettings",
        "MemoryAccessConfig",
        "MemoryScopeKindSpec",
        "MemoryScopeKindInfo",
        "MemoryScopeRef",
        "MemoryAuthor",
        "MemoryEntry",
        "MemoryEntrySummary",
        "MemoryEntryPage",
        "MemoryVersion",
        "MemoryVersionSummary",
        "MemoryScopeSummary",
        "MemoryWriteRequest",
        "MemoryMoveRequest",
        "MemoryRetentionRule",
        "MemoryRetentionPlan",
        "MemoryRetentionResult",
        "MemoryImportResult",
        "MemoryEventPayload",
        "MemoryChanged",
    } <= set(grouped["memory"])
    assert "MemoryChangedMessage" in grouped["modules"]
    assert "ConditionSpec" in grouped["runs"]
    assert "Issue" in grouped["definitions"]
    for name in mem.__all__:
        assert getattr(root, name) is getattr(mem, name), name


# ---------------------------------------------------------------- 사용자 데이터 왕복


@pytest.mark.parametrize(
    ("model", "text"),
    [(mem.MemorySettings, SETTINGS_YAML), (mem.MemoryAccessConfig, ACCESS_YAML)],
)
def test_user_data_yaml_round_trip_keeps_everything(model: Any, text: str) -> None:
    """YAML 예시 → 모델 → JSON → 모델: 적은 값과 모르는 키가 그대로 남는다."""
    data = _yaml_load(text)
    parsed = model.model_validate(data)
    dumped = _dump(parsed)
    assert dumped == json.loads(json.dumps(data))
    again = model.model_validate(json.loads(json.dumps(dumped)))
    assert again == parsed
    assert _dump(again) == dumped


def test_unknown_keys_are_preserved_at_every_level() -> None:
    settings = _dump(mem.MemorySettings.model_validate(_yaml_load(SETTINGS_YAML)))
    assert settings["x-settings-note"] == "사용자 메모"
    assert settings["scope_kinds"]["zz-notes"]["x-kind"] == 1
    assert settings["retention"]["x-retention-note"] == "kept"
    assert settings["retention"]["rules"][0]["x-rule-note"] == [1, 2]
    access = _dump(mem.MemoryAccessConfig.model_validate(_yaml_load(ACCESS_YAML)))
    assert access["x-access-note"] == {"nested": True}
    assert access["scopes"][0]["x-scope-note"] == "a"
    assert access["tools"]["search"]["x-tool-note"] == 1


def test_null_scope_kind_means_remove_and_survives_round_trip() -> None:
    settings = mem.MemorySettings.model_validate(_yaml_load(SETTINGS_YAML))
    assert settings.scope_kinds["zz-default-kind"] is None
    assert _dump(settings)["scope_kinds"]["zz-default-kind"] is None
    spec = settings.scope_kinds["zz-everyone"]
    assert spec is not None
    assert (spec.label, spec.description, spec.id) == ("모두", "", "")


def test_settings_defaults_and_omit_unset() -> None:
    empty = mem.MemorySettings()
    assert empty.include_default_scope_kinds is True
    assert empty.scope_kinds == {}
    assert empty.secrets == "reject"
    assert empty.max_versions_per_entry == 50
    assert empty.retention.rules == []  # 패키지 기본은 아무것도 자동으로 정리하지 않는다
    assert _dump(empty) == {}
    with pytest.raises(ValidationError):
        mem.MemorySettings.model_validate({"secrets": "zz-unknown"})
    with pytest.raises(ValidationError):
        mem.MemorySettings.model_validate({"max_versions_per_entry": 0})


def test_retention_rule_uses_condition_spec() -> None:
    settings = mem.MemorySettings.model_validate(_yaml_load(SETTINGS_YAML))
    rule = settings.retention.rules[0]
    assert rule.when.all is not None
    assert [item.op for item in rule.when.all] == ["contains", "gte"]
    assert mem.MemoryRetentionRule.model_validate({"id": "r", "when": {}}).action == "archive"
    with pytest.raises(ValidationError):
        mem.MemoryRetentionRule.model_validate({"id": "r", "when": {}, "action": "zz-burn"})


# ---------------------------------------------------------------- 접근 설정: 이름은 데이터


def test_access_defaults_come_from_package_data() -> None:
    """도구 이름·설명·결과 머리 줄 기본값은 코드가 아니라 패키지 데이터에서 온다."""
    data = mem.memory_access_defaults()
    config = mem.MemoryAccessConfig()
    assert config.scopes == []  # 범위 권한은 기본으로 하나도 주지 않는다(opt-in)
    assert config.default_scope is None
    assert config.result_header == data["result_header"]
    assert config.max_result_chars == data["max_result_chars"]
    for op in mem.MEMORY_ACCESS_OPS:
        tool = getattr(config.tools, op)
        assert tool.model_dump() == data["tools"][op], op
    assert set(data["tools"]) == set(mem.MEMORY_ACCESS_OPS)
    # 스키마 기본값도 같은 데이터다(폼이 기본값을 보인다)
    defs = build_schema()["$defs"]
    assert defs["MemoryTools"]["properties"]["write"]["default"] == data["tools"]["write"]
    assert (
        defs["MemoryAccessConfig"]["properties"]["result_header"]["default"]
        == (data["result_header"])
    )


def test_access_config_tool_names_are_data() -> None:
    config = mem.MemoryAccessConfig.model_validate(_yaml_load(ACCESS_YAML))
    assert config.tools.search.name == "zz_find"
    assert config.tools.write.name == "zz_put"
    # 적지 않은 동작은 기본값
    assert config.tools.read.name == mem.memory_access_defaults()["tools"]["read"]["name"]
    assert [s.kind for s in config.scopes] == ["zz-notes", "zz-everyone"]
    assert config.scopes[1].access == ["read"]
    with pytest.raises(ValidationError):
        mem.MemoryToolText.model_validate({"name": "bad name!", "description": ""})
    with pytest.raises(ValidationError):
        mem.MemoryScopeAccess.model_validate({"kind": "zz", "access": ["zz-fly"]})
    assert mem.MemoryScopeAccess.model_validate({"kind": "zz"}).access == ["read", "search"]


def test_memory_forms_help_is_complete() -> None:
    """설정 폼 뿌리에 들어가고, 모든 필드에 라벨·설명·분류가 있다(도움말 린트 0건)."""
    roots = contract_form_roots()
    names = ("MemorySettings", "MemoryAccessConfig", "MemoryScopeKindSpec", "MemoryRetentionRule")
    assert set(names) <= set(roots)
    issues = lint_schema_help(build_schema(), roots=names, objects=True)
    assert issues == []
    defs = build_schema()["$defs"]
    kind = defs["MemoryScopeAccess"]["properties"]["kind"]
    assert kind[X_UI][XUiKeys.WIDGET] == "memory-scope-kind"
    assert defs["MemoryAccessConfig"]["properties"]["default_scope"][X_UI][XUiKeys.WIDGET] == (
        "memory-scope-kind"
    )


# ---------------------------------------------------------------- 항목·버전·범위


def test_scope_ref_text_form() -> None:
    ref = mem.MemoryScopeRef(kind="zz-notes", id="g1/a1")
    assert ref.to_text() == "zz-notes:g1/a1"
    assert mem.MemoryScopeRef.parse(ref.to_text()) == ref
    assert mem.MemoryScopeRef.parse("zz-everyone:") == mem.MemoryScopeRef(kind="zz-everyone")
    assert mem.MemoryScopeRef.parse("zz:a:b").id == "a:b"
    with pytest.raises(ValidationError):
        mem.MemoryScopeRef.parse(":g1")
    assert build_schema()["x-constants"]["MEMORY_SCOPE_SEPARATOR"] == mem.MEMORY_SCOPE_SEPARATOR


def test_entry_summary_version_round_trip() -> None:
    entry = mem.MemoryEntry.model_validate(_entry(content="본문", tags=["임시"]))
    assert entry.content_type == mem.MEMORY_DEFAULT_CONTENT_TYPE
    assert entry.created_by.kind == "agent"
    assert entry.updated_by.kind == "user"
    assert mem.MemoryEntry.model_validate(entry.model_dump(mode="json")) == entry
    summary = mem.MemoryEntrySummary.model_validate(_entry(preview="본"))
    assert "content" not in mem.MemoryEntrySummary.model_fields
    page = mem.MemoryEntryPage(items=[summary], next_cursor="c2")
    assert mem.MemoryEntryPage.model_validate(page.model_dump(mode="json")) == page
    version = mem.MemoryVersion.model_validate(
        {
            "entry_id": "e1",
            "version": 1,
            "op": "create",
            "scope": {"kind": "zz-notes", "id": "g1"},
            "key": "k",
            "bytes": 3,
            "sha256": "00",
            "author": {"kind": "system", "label": "zz-stale"},
            "at": 1.5,
        }
        | {"content": "abc"}
    )
    assert version.author.label == "zz-stale"
    with pytest.raises(ValidationError):
        mem.MemoryEntry.model_validate(_entry(content="x", version=0))
    # 쓴 주체 종류는 열린 문자열(팀 모드 등이 더함), 알려진 값은 문서 상수
    assert mem.MemoryAuthor.model_validate({"kind": "zz-robot"}).kind == "zz-robot"
    assert mem.KnownMemoryAuthorKinds.SYSTEM == "system"
    with pytest.raises(ValidationError):
        mem.MemoryAuthor.model_validate({"kind": ""})


def test_move_request_needs_a_target() -> None:
    assert mem.MemoryMoveRequest(to_key="new").to_key == "new"
    assert mem.MemoryMoveRequest(to_scope=mem.MemoryScopeRef(kind="zz")).to_scope is not None
    with pytest.raises(ValidationError):
        mem.MemoryMoveRequest()


def test_scope_kind_info_and_context_fields() -> None:
    info = mem.MemoryScopeKindInfo(
        kind="zz-notes", label="노트", id="{/graph_id}", origin="user", context_fields=["graph_id"]
    )
    assert mem.MemoryScopeKindInfo.model_validate(info.model_dump(mode="json")) == info
    assert set(info.context_fields) <= set(mem.MEMORY_CONTEXT_FIELDS)
    constants = build_schema()["x-constants"]
    assert constants["MEMORY_CONTEXT_FIELDS"] == list(mem.MEMORY_CONTEXT_FIELDS)
    assert set(constants["KNOWN_MEMORY_CONTEXT_FIELDS"].values()) <= set(mem.MEMORY_CONTEXT_FIELDS)
    assert {"project_id", "graph_id", "agent_id", "node_path"} <= set(mem.MEMORY_CONTEXT_FIELDS)
    computed = mem.MemoryScopeKindInfo(kind="zz-week", label="주", origin="plugin:zz")
    assert computed.id is None
    assert computed.context_fields == []


# ---------------------------------------------------------------- 이벤트: 본문 없음


def test_event_payload_has_no_body_or_query_text() -> None:
    """payload는 크기·해시만 싣는다. 본문·검색어 원문 필드가 없다(design C1)."""
    fields = set(mem.MemoryEventPayload.model_fields)
    assert fields == {
        "op",
        "status",
        "scope",
        "key",
        "entry_id",
        "version",
        "bytes",
        "sha256",
        "results",
        "query_chars",
        "query_sha256",
        "tool",
        "tool_use_id",
        "duration_ms",
    }
    assert not fields & {"content", "query", "text", "body", "preview", "q"}
    # 모르는 필드(예: 실수로 넣은 본문)는 읽을 때 버려진다
    payload = mem.MemoryEventPayload.model_validate(
        {"op": "search", "status": "ok", "query": "비밀 검색어", "results": 2, "query_chars": 6}
    )
    assert "비밀 검색어" not in json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    changed = set(mem.MemoryChanged.model_fields)
    assert not changed & {"content", "query", "text", "body", "preview"}


def test_memory_event_types_stay_out_of_runs() -> None:
    assert mem.KNOWN_MEMORY_EVENT_TYPES == (
        "memory.read",
        "memory.search",
        "memory.write",
        "memory.delete",
    )
    assert not set(mem.KNOWN_MEMORY_EVENT_TYPES) & set(KNOWN_RUN_EVENT_TYPES)
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_RUN_EVENT_TYPES"] == list(KNOWN_RUN_EVENT_TYPES)
    assert constants["KNOWN_MEMORY_EVENT_TYPES"] == list(mem.KNOWN_MEMORY_EVENT_TYPES)
    # RunEvent type은 열린 문자열: 메모리 이벤트는 일반 RunEvent로 읽히고 payload를 따로 읽는다
    raw = {
        "type": "memory.write",
        "event_id": "ev1",
        "run_id": "r1",
        "node_path": [],
        "seq": 3,
        "ts": 1.0,
        "node_id": "n1",
        "payload": {"op": "write", "status": "ok", "key": "k", "bytes": 4, "sha256": "ff"},
    }
    event = parse_run_event(raw)
    assert type(event) is RunEvent
    assert mem.MemoryEventPayload.model_validate(event.payload).bytes == 4


def test_memory_changed_ws_message() -> None:
    message = WsServerMessage.model_validate(
        {
            "type": "memory.changed",
            "payload": {
                "scope": {"kind": "zz-notes", "id": "g1"},
                "key": "k",
                "entry_id": "e1",
                "version": 3,
                "op": "purge",
                "author_kind": "user",
            },
        }
    )
    assert message.root.type == "memory.changed"
    assert isinstance(message.root.payload, mem.MemoryChanged)


# ---------------------------------------------------------------- 상수


def test_memory_error_and_issue_codes() -> None:
    for code in (
        ErrorCodes.MEMORY_INVALID_KEY,
        ErrorCodes.MEMORY_TOO_LARGE,
        ErrorCodes.MEMORY_SECRET_REJECTED,
    ):
        assert HTTP_STATUS_BY_ERROR_CODE[code] == 422
    table = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    statuses = get_args(mem.MemoryEventStatus)
    # ok·error 밖의 상태는 사유 코드 `memory.<상태>`가 문서 상수에 있다
    for status in statuses:
        if status in ("ok", "error"):
            continue
        assert f"memory.{status}" in table.values(), status
    assert table["TOOLS_PROVIDER_FAILED"] == "tools.provider_failed"
    assert table["TOOLS_DUPLICATE_NAME"] == "tools.duplicate_name"
    assert table["TOOLS_BACKEND_CAPABILITY_MISSING"] == "tools.backend_capability_missing"
    assert KnownIssueCodes.ARCHITECTURE_CONDITION_PATH_UNLISTED == (
        "architecture.condition_path_unlisted"
    )
    assert KnownIssueCodes.MEMORY_STORAGE_MEMORY == "memory.storage_memory"
    assert KnownIssueCodes.MEMORY_SETTINGS_INVALID == "memory.settings_invalid"
    assert KnownIssueCodes.MEMORY_UNKNOWN_SCOPE_KIND == "memory.unknown_scope_kind"


def test_secret_rejected_details_carry_location_not_value() -> None:
    details = mem.MemorySecretRejectedDetails(field="tags", rules=["zz-token"])
    assert details.model_dump() == {"field": "tags", "rules": ["zz-token"]}
    assert set(mem.MemorySecretRejectedDetails.model_fields) == {"field", "rules"}
    assert mem.MemorySecretRejectedDetails().field is None
    with pytest.raises(ValidationError):
        mem.MemorySecretRejectedDetails.model_validate({"field": "zz-where"})


def test_tag_list_sorts_and_import_dry_run() -> None:
    tags = mem.MemoryTagList(tags=[mem.MemoryTagCount(tag="임시", entries=3)])
    assert mem.MemoryTagList.model_validate(tags.model_dump(mode="json")) == tags
    assert build_schema()["x-constants"]["MEMORY_ENTRY_SORTS"] == list(mem.MEMORY_ENTRY_SORTS)
    assert mem.MemoryImportResult().dry_run is False
    assert mem.MemoryImportResult(dry_run=True, created=2).created == 2
