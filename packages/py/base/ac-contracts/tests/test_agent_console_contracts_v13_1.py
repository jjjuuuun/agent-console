"""계약 0.13.1(계약 후속, 더하기만): `common` 1.9.0·`definitions` 1.6.0·`sdd` 1.0.1.

- `SecretRuleSettings.weak_key_names`(선택, null = 기본 데이터): 0.13.0 설정이 그대로 읽힌다.
- 문서 상수 `fake.session_missing`·`records.session_archive_failed`·`run.move_busy`
  (+ 0.13.0부터 있던 `sdd.automation_skipped`)가 스키마 `x-constants`로 나간다.
- `ParsedTask.issues` 설명이 X43 선택 메서드 `task_issues`를 말한다.
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    ErrorCodes,
    KnownIssueCodes,
    SecretRuleSettings,
    WorkspaceSettings,
)
from agent_console_contracts.schema import build_schema
from agent_console_contracts.schema_help import contract_form_roots, lint_contract_help


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_13_1() -> None:
    """0.13.1에서 정한 버전 이상이다(정확한 지금 값은 0.13.2 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 13, 1)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0131 = {
        "common": "1.9.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.6.0",
        "runs": "1.7.0",
        "usage": "1.1.0",
        "projects": "3.1.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.0.1",
        "modules": "1.4.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0131)
    for sub, version in v0131.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_weak_key_names_is_optional_and_null_by_default() -> None:
    old = WorkspaceSettings.model_validate({"secrets": {"extra_key_names": ["deploy_key"]}})
    assert old.secrets.weak_key_names is None
    assert "weak_key_names" not in old.model_dump(mode="json", exclude_unset=True)["secrets"]
    assert SecretRuleSettings(weak_key_names=[]).weak_key_names == []
    assert SecretRuleSettings.model_validate({"weak_key_names": ["key", "id"]}).weak_key_names == [
        "key",
        "id",
    ]
    prop = build_schema()["$defs"]["SecretRuleSettings"]["properties"]["weak_key_names"]
    assert prop["x-ui"]["tier"] == "advanced"
    assert prop["default"] is None


def test_weak_key_names_passes_help_lint() -> None:
    assert "WorkspaceSettings" in contract_form_roots()
    issues = [i for i in lint_contract_help() if "SecretRuleSettings" in i.path]
    assert issues == []


def test_new_document_constants() -> None:
    assert ErrorCodes.FAKE_SESSION_MISSING == "fake.session_missing"
    # HTTP 응답 코드가 아니다
    assert ErrorCodes.FAKE_SESSION_MISSING not in HTTP_STATUS_BY_ERROR_CODE
    assert KnownIssueCodes.RECORDS_SESSION_ARCHIVE_FAILED == "records.session_archive_failed"
    assert KnownIssueCodes.RUN_MOVE_BUSY == "run.move_busy"
    assert KnownIssueCodes.SDD_AUTOMATION_SKIPPED == "sdd.automation_skipped"
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"]["FAKE_SESSION_MISSING"] == "fake.session_missing"
    issues = constants["KNOWN_ISSUE_CODES"]
    assert issues["RECORDS_SESSION_ARCHIVE_FAILED"] == "records.session_archive_failed"
    assert issues["RUN_MOVE_BUSY"] == "run.move_busy"
    assert issues["SDD_AUTOMATION_SKIPPED"] == "sdd.automation_skipped"


def test_parsed_task_issues_mentions_task_issues() -> None:
    prop = build_schema()["$defs"]["ParsedTask"]["properties"]["issues"]
    assert "task_issues" in prop["description"]
