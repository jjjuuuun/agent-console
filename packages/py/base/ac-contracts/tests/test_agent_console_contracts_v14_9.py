"""계약 0.14.9(6R.31, 더하기만): `sdd` 1.3.0·`memory` 1.2.0·`common` 1.15.0.

- 작업 문법 `TaskSyntax.status_pattern`·`status_format`·`field_format`(생략 = 앞 층·패키지 기본).
- 실행 프로필 `RunProfile.document_state_on` = `DocumentStateOnRun{document, to}`
  (생략 = 바꾸지 않음).
- 메모리 설정 `MemoryRetentionSettings.auto` = `MemoryRetentionAuto{library, projects,
  exclude_projects}`(생략 = 공용·프로젝트 모두, 뺄 것 없음).
- 이슈 코드 `sdd.status_pattern_ignored`(문법 검사 경고)·`sdd.document_state_not_applied`(info).

새 필드를 생략한 0.14.8 문서가 그대로 읽히고, 모델 왕복·모르는 키 보존이 유지되는지 본다.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    DocumentStateOnRun,
    KnownIssueCodes,
    MemoryRetentionAuto,
    MemoryRetentionSettings,
    MemorySettings,
    RunProfile,
    SpecRules,
    TaskSyntax,
)
from agent_console_contracts.memory import MemoryRetentionAuto as SubpathMemoryRetentionAuto
from agent_console_contracts.schema import build_schema
from agent_console_contracts.schema_help import lint_contract_help
from agent_console_contracts.sdd import DocumentStateOnRun as SubpathDocumentStateOnRun


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_9() -> None:
    """0.14.9에서 정한 버전 이상이다(정확한 지금 값은 0.15.0 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 9)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0149 = {
        "common": "1.15.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "3.6.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.2.0",
        "sdd": "1.3.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }
    assert set(v0149) <= set(CONTRACT_VERSIONS)  # 0.16.0: 하위 모듈 i18n이 늘었다
    for sub, version in v0149.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_new_models_are_exported_from_subpaths() -> None:
    assert SubpathDocumentStateOnRun is DocumentStateOnRun
    assert SubpathMemoryRetentionAuto is MemoryRetentionAuto


# ---------------------------------------------------------------- 작업 문법


_OLD_TASK_SYNTAX: dict[str, Any] = {
    "list_item": "checkbox",
    "id_pattern": r"^(?P<id>[0-9A-Za-z][\w.\-]*)\s+",
    "field_pattern": r"\[(?P<key>[\w\-]+):\s*(?P<value>[^\]]*)\]",
}


def test_old_task_syntax_reads_with_new_fields_unset() -> None:
    syntax = TaskSyntax.model_validate(_OLD_TASK_SYNTAX)
    assert syntax.status_pattern is None
    assert syntax.status_format is None
    assert syntax.field_format is None
    # 생략한 키는 저장 원문에 나오지 않는다(병합 = 앞 층·패키지 기본).
    assert syntax.model_dump(exclude_unset=True) == _OLD_TASK_SYNTAX


def test_task_syntax_round_trip_with_head_word_status() -> None:
    raw = {
        "list_item": "any",
        "status_pattern": r"^(?P<status>TODO|DOING|DONE):?\s+",
        "status_format": "{marker}: ",
        "field_format": "({key}={value})",
        "future_key": {"kept": True},
    }
    syntax = TaskSyntax.model_validate(raw)
    assert syntax.status_pattern == raw["status_pattern"]
    assert syntax.status_format == "{marker}: "
    assert syntax.field_format == "({key}={value})"
    dumped = syntax.model_dump(mode="json", exclude_unset=True)
    assert dumped == raw  # 모르는 키 보존
    assert TaskSyntax.model_validate(dumped) == syntax


# ---------------------------------------------------------------- 실행 프로필


_OLD_PROFILE: dict[str, Any] = {
    "id": "implement",
    "title": "구현",
    "graph": "dev-team",
    "status_on": {"started": "doing", "succeeded": "review"},
}


def test_old_profile_reads_without_document_state_on() -> None:
    profile = RunProfile.model_validate(_OLD_PROFILE)
    assert profile.document_state_on == {}
    assert profile.model_dump(exclude_unset=True) == _OLD_PROFILE


def test_profile_document_state_on_round_trip() -> None:
    raw = {
        **_OLD_PROFILE,
        "document_state_on": {
            "succeeded": {"document": "design", "to": "review", "note_x": 1},
            "failed": {"document": "design", "to": "draft"},
        },
    }
    profile = RunProfile.model_validate(raw)
    change = profile.document_state_on["succeeded"]
    assert isinstance(change, DocumentStateOnRun)
    assert (change.document, change.to) == ("design", "review")
    dumped = profile.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped == raw  # 항목 안의 모르는 키도 보존
    assert RunProfile.model_validate(dumped) == profile


@pytest.mark.parametrize(
    "bad",
    [{"to": "review"}, {"document": "design"}, {"document": "", "to": "review"}],
)
def test_document_state_on_run_requires_document_and_state(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DocumentStateOnRun.model_validate(bad)


def test_rules_with_profiles_round_trip() -> None:
    raw = {
        "document_states": [{"id": "draft"}, {"id": "review"}],
        "transitions": [{"from": "draft", "to": "review", "by": ["human", "run"]}],
        "profiles": [
            {**_OLD_PROFILE, "document_state_on": {"succeeded": {"document": "d", "to": "review"}}}
        ],
        "syntax": {"task": {"status_pattern": r"^(?P<status>\w+)\s"}},
    }
    rules = SpecRules.model_validate(raw)
    dumped = rules.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped == raw
    assert SpecRules.model_validate(dumped) == rules


# ---------------------------------------------------------------- 메모리 자동 정리 대상


def test_old_memory_settings_read_with_default_auto() -> None:
    old = {"retention": {"rules": [], "kept": "x"}, "secrets": "redact"}
    settings = MemorySettings.model_validate(old)
    auto = settings.retention.auto
    assert (auto.library, auto.projects, auto.exclude_projects) == (True, True, [])
    # 생략 = 기본값, 저장 원문에 넣지 않는다.
    assert settings.model_dump(exclude_unset=True) == old
    assert MemoryRetentionSettings().model_dump(exclude_unset=True) == {}


def test_memory_retention_auto_round_trip() -> None:
    raw = {
        "rules": [],
        "auto": {"library": False, "projects": True, "exclude_projects": ["p1"], "extra": 2},
    }
    retention = MemoryRetentionSettings.model_validate(raw)
    assert retention.auto.library is False
    assert retention.auto.exclude_projects == ["p1"]
    dumped = retention.model_dump(mode="json", exclude_unset=True)
    assert dumped == raw
    assert MemoryRetentionSettings.model_validate(dumped) == retention


def test_memory_retention_auto_rejects_empty_project_id() -> None:
    with pytest.raises(ValidationError):
        MemoryRetentionAuto.model_validate({"exclude_projects": [""]})


# ---------------------------------------------------------------- 이슈 코드·스키마


def test_new_issue_codes() -> None:
    assert KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED == "sdd.status_pattern_ignored"
    assert KnownIssueCodes.SDD_DOCUMENT_STATE_NOT_APPLIED == "sdd.document_state_not_applied"
    codes = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    assert codes["SDD_STATUS_PATTERN_IGNORED"] == "sdd.status_pattern_ignored"
    assert codes["SDD_DOCUMENT_STATE_NOT_APPLIED"] == "sdd.document_state_not_applied"


def test_schema_has_new_fields_and_form_help() -> None:
    schema = build_schema()
    defs = schema["$defs"]
    task = defs["TaskSyntax"]["properties"]
    for key in ("status_pattern", "status_format", "field_format"):
        assert key in task
        assert key not in defs["TaskSyntax"].get("required", [])
        assert task[key]["x-ui"]["tier"] == "advanced"
    assert task["status_pattern"]["x-ui"]["widget"] == "regex"
    profile = defs["RunProfile"]
    assert "document_state_on" in profile["properties"]
    assert "document_state_on" not in profile.get("required", [])
    assert set(defs["DocumentStateOnRun"]["required"]) == {"document", "to"}
    assert defs["DocumentStateOnRun"]["properties"]["to"]["x-ui"]["widget"] == "state-ref"
    retention = defs["MemoryRetentionSettings"]
    assert "auto" in retention["properties"]
    assert "auto" not in retention.get("required", [])
    auto = defs["MemoryRetentionAuto"]["properties"]
    assert auto["library"]["default"] is True
    assert auto["projects"]["default"] is True
    assert auto["exclude_projects"]["default"] == []
    for prop in auto.values():
        assert prop["x-ui"]["when"]
    assert "MemoryRetentionAuto" in schema["x-modules"]["memory"]
    assert "DocumentStateOnRun" in schema["x-modules"]["sdd"]


def test_new_form_models_pass_schema_help_lint() -> None:
    names = {"TaskSyntax", "RunProfile", "DocumentStateOnRun", "MemoryRetentionAuto"}
    names |= {"MemoryRetentionSettings"}
    issues = [i for i in lint_contract_help() if i.path.split("/")[2] in names]
    assert issues == []
