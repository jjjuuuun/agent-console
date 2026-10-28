"""계약 0.12.1(design §PI.4.6·§PI.16, 5.7R.33c3).

하위 계약: `projects` 3.1.0·`runs` 1.5.0·`chat` 1.2.0·`common` 1.7.0.

더하기만 한다: 0.12.0 서버가 보낸 응답(새 필드 없음)이 그대로 읽히고, 새 필드는 모두 선택이다.
- 프로젝트 기록 DB 상태(`records_state`·`records_writable`·`records_issue`), 옮기기,
  쓸 수 없는 이유.
- 폴더 확인 `existing`·`suggested_id`·`config_dir`, `ProjectView.config_dir`, 설정 파일 다시 만들기.
- `Run.host_id`, 대화 이어 가기 상태, 전송 요청 `on_missing_session`, 대기열 `held_reason`.
- 새 오류·이슈 코드와 문서 상수가 스키마 상수(→ TS)로 나간다. 상태·이유 값은 열린 문자열(R0).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    ConversationSessions,
    ErrorCodes,
    ExistingProjectProbe,
    FolderCheck,
    KnownExistingProjectStates,
    KnownIssueCodes,
    KnownProjectRecordsStates,
    KnownQueueHoldReasons,
    KnownRecordsUnavailableReasons,
    KnownSessionStates,
    ManifestResetRequest,
    ManifestResetResult,
    PostMessageRequest,
    ProjectRecordsUnavailableDetails,
    ProjectView,
    QueuedMessage,
    RecordsMoveRequest,
    RecordsMoveResult,
    Run,
    build_schema,
)

# ---------------------------------------------------------------- 버전


def test_contracts_version_is_0_12_1() -> None:
    assert CONTRACTS_VERSION == "0.12.1"
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == "0.12.1"
    assert CONTRACT_VERSIONS == {
        "common": "1.7.0",
        "resources": "1.1.0",
        "logs": "1.1.0",
        "definitions": "1.4.0",
        "runs": "1.5.0",
        "usage": "1.1.0",
        "projects": "3.1.0",
        "chat": "1.2.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "modules": "1.3.0",
    }


def test_new_models_live_in_their_submodules() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        "ExistingProjectProbe",
        "ManifestResetRequest",
        "ManifestResetResult",
        "ProjectRecordsUnavailableDetails",
        "RecordsMoveRequest",
        "RecordsMoveResult",
    } <= set(grouped["projects"])
    assert {"ConversationSessions", "SessionStatus"} <= set(grouped["chat"])


# ---------------------------------------------------------------- 0.12.0 응답 읽기(선택 필드)

_V0120_VIEW: dict[str, Any] = {
    "project": {"id": "p", "name": "P", "folder": "/p"},
    "status": "ready",
    "config_writable": True,
    "manifest_id": "p",
    "kinds": ["graph"],
    "issues": [],
}


def test_v0120_project_view_reads_with_defaults() -> None:
    view = ProjectView.model_validate(_V0120_VIEW)
    assert view.config_dir is None
    assert view.records_state == KnownProjectRecordsStates.READY
    assert view.records_writable is True  # 보내지 않은 옛 서버는 막지 않는다
    assert view.records_issue is None


def test_v0120_folder_check_reads_with_defaults() -> None:
    check = FolderCheck.model_validate({"input": "/p", "path": "/p", "status": "ok"})
    assert check.existing is None
    assert check.suggested_id is None
    assert check.config_dir is None


def test_v0120_run_and_chat_read_with_defaults() -> None:
    run = Run.model_validate(
        {
            "id": "r",
            "graph_id": "g",
            "graph_version": "v",
            "status": "running",
            "input": {},
            "origin": "web",
            "created_at": 1.0,
        }
    )
    assert run.host_id is None
    assert PostMessageRequest.model_validate({"text": "hi"}).on_missing_session == "fail"
    queued = QueuedMessage.model_validate({"position": 1, "held": True})
    assert queued.held_reason is None


# ---------------------------------------------------------------- 기록 DB 상태


def test_project_view_records_fields_round_trip() -> None:
    view = ProjectView.model_validate(
        {
            **_V0120_VIEW,
            "config_dir": ".agent-console",
            "records_state": "zz-future-state",  # 열린 문자열
            "records_writable": False,
            "records_issue": {
                "severity": "warning",
                "code": "project.records_unavailable",
                "message": "m",
                "details": {"project_id": "p", "reason": "newer"},
            },
        }
    )
    assert view.records_state == "zz-future-state"
    assert view.records_writable is False
    assert view.records_issue is not None
    details = ProjectRecordsUnavailableDetails.model_validate(view.records_issue.details)
    assert details.reason == KnownRecordsUnavailableReasons.NEWER
    assert details.backup_path is None
    dumped = view.model_dump(mode="json")
    assert dumped["config_dir"] == ".agent-console"
    assert ProjectView.model_validate(dumped) == view


def test_records_unavailable_details_open_reason() -> None:
    d = ProjectRecordsUnavailableDetails.model_validate(
        {"project_id": "p", "reason": "zz-reason", "backup_path": "/b.sqlite3"}
    )
    assert d.reason == "zz-reason"
    with pytest.raises(ValidationError):
        ProjectRecordsUnavailableDetails.model_validate({"project_id": "p"})


@pytest.mark.parametrize(
    ("body", "ok"),
    [
        ({"project_id": "p", "select": "project"}, True),
        ({"project_id": "p", "select": "null"}, True),
        ({"project_id": "p", "select": "ids", "ids": ["r1"]}, True),
        ({"project_id": "p", "select": "ids"}, False),
        ({"project_id": "p", "select": "project", "ids": ["r1"]}, False),
        ({"project_id": "p", "select": "zz"}, False),
        ({"select": "project"}, False),
    ],
)
def test_records_move_request_selectors(body: dict[str, Any], ok: bool) -> None:
    if ok:
        req = RecordsMoveRequest.model_validate(body)
        assert req.remove_source is True
    else:
        with pytest.raises(ValidationError):
            RecordsMoveRequest.model_validate(body)


def test_records_move_result_defaults() -> None:
    result = RecordsMoveResult.model_validate({})
    assert (result.moved, result.skipped, result.failed) == (0, 0, [])
    with pytest.raises(ValidationError):
        RecordsMoveResult.model_validate({"moved": -1})


# ---------------------------------------------------------------- 폴더 확인·다시 만들기(§PI.16 ①·③)


def test_folder_check_existing_found_and_invalid() -> None:
    found = FolderCheck.model_validate(
        {
            "input": "/p",
            "path": "/p",
            "status": "ok",
            "config_dir": ".agent-console",
            "suggested_id": "payments-2",
            "existing": {"state": "found", "id": "payments", "name": "결제", "definitions": 3},
        }
    )
    assert found.existing is not None
    assert found.existing.state == KnownExistingProjectStates.FOUND
    assert found.existing.definitions == 3
    assert found.suggested_id == "payments-2"
    invalid = ExistingProjectProbe.model_validate(
        {
            "state": "invalid",
            "issue": {"severity": "error", "code": "project.manifest_invalid", "message": "m"},
        }
    )
    assert invalid.definitions == 0
    assert invalid.name is None
    assert invalid.issue is not None
    with pytest.raises(ValidationError):
        ExistingProjectProbe.model_validate({"state": "found", "definitions": -1})
    with pytest.raises(ValidationError):
        FolderCheck.model_validate({"input": "x", "status": "ok", "suggested_id": "bad id!"})


def test_folder_check_carries_no_file_names() -> None:
    props = build_schema()["$defs"]["ExistingProjectProbe"]["properties"]
    assert set(props) == {"state", "id", "name", "description", "definitions", "issue"}


def test_manifest_reset_models() -> None:
    req = ManifestResetRequest.model_validate({"name": "결제"})
    assert req.description is None
    with pytest.raises(ValidationError):
        ManifestResetRequest.model_validate({"name": ""})
    res = ManifestResetResult.model_validate(
        {"project": _V0120_VIEW, "backup_path": "/p/.agent-console/.state/backups/project-x.yaml"}
    )
    assert res.project.project.id == "p"


# ---------------------------------------------------------------- 대화 이어 가기·대기열


def test_conversation_sessions_and_states_are_open() -> None:
    sessions = ConversationSessions.model_validate(
        {
            "conversation_id": "c",
            "continuable": False,
            "items": [
                {"node_id": "n1", "backend": "claude", "session_id": "s", "state": "missing"},
                {"node_id": "n2", "backend": "zz-backend", "state": "zz-state"},
            ],
        }
    )
    assert sessions.items[0].state == KnownSessionStates.MISSING
    assert sessions.items[1].session_id is None
    with pytest.raises(ValidationError):
        ConversationSessions.model_validate({"conversation_id": "c"})


def test_post_message_on_missing_session() -> None:
    assert (
        PostMessageRequest.model_validate(
            {"text": "t", "on_missing_session": "fresh"}
        ).on_missing_session
        == "fresh"
    )
    with pytest.raises(ValidationError):
        PostMessageRequest.model_validate({"text": "t", "on_missing_session": "zz"})


def test_queued_message_held_reason_open() -> None:
    q = QueuedMessage.model_validate({"position": 1, "held": True, "held_reason": "other_host"})
    assert q.held_reason == KnownQueueHoldReasons.OTHER_HOST


def test_run_host_id() -> None:
    props = build_schema()["$defs"]["Run"]["properties"]
    assert "host_id" in props
    assert "host_id" not in build_schema()["$defs"]["Run"].get("required", [])


# ---------------------------------------------------------------- 상수·코드


def test_document_constants_exported() -> None:
    constants = build_schema()["x-constants"]
    assert set(constants["KNOWN_PROJECT_RECORDS_STATES"].values()) == {
        "absent",
        "ready",
        "newer",
        "unavailable",
    }
    assert set(constants["KNOWN_RECORDS_UNAVAILABLE_REASONS"].values()) == {
        "folder_missing",
        "readonly",
        "newer",
        "busy",
        "corrupt",
        "migration_failed",
        "link_disabled",
    }
    assert set(constants["KNOWN_EXISTING_PROJECT_STATES"].values()) == {"found", "invalid"}
    assert set(constants["KNOWN_SESSION_STATES"].values()) == {
        "available",
        "relocatable",
        "archived",
        "missing",
        "not_applicable",
    }
    assert set(constants["KNOWN_QUEUE_HOLD_REASONS"].values()) == {"restart", "other_host"}


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("PROJECT_RECORDS_UNAVAILABLE", "project.records_unavailable"),
        ("CHAT_SESSION_UNAVAILABLE", "chat.session_unavailable"),
    ],
)
def test_new_error_codes_are_409(name: str, code: str) -> None:
    assert getattr(ErrorCodes, name) == code
    assert getattr(KnownIssueCodes, name) == code
    assert HTTP_STATUS_BY_ERROR_CODE[code] == 409
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"][name] == code
    assert constants["KNOWN_ISSUE_CODES"][name] == code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("PROJECT_NETWORK_FS", "project.network_fs"),
        ("PROJECT_GITIGNORE_OUTDATED", "project.gitignore_outdated"),
        ("RUN_OTHER_HOST", "run.other_host"),
    ],
)
def test_new_info_codes_are_issue_only(name: str, code: str) -> None:
    assert getattr(KnownIssueCodes, name) == code
    assert not hasattr(ErrorCodes, name)
    assert code not in HTTP_STATUS_BY_ERROR_CODE
    assert build_schema()["x-constants"]["KNOWN_ISSUE_CODES"][name] == code


def test_memory_network_fs_stays_as_deprecated_alias() -> None:
    codes = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    assert codes["PROJECT_MEMORY_NETWORK_FS"] == "project.memory_network_fs"
    assert codes["PROJECT_NETWORK_FS"] == "project.network_fs"
