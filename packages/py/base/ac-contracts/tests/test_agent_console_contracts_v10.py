"""계약 v10(design §PI.10, 5.7R.33c, 0.11.0): `projects` 2.0.0 — 프로젝트 = 로컬 폴더.

- 옛 프로젝트 YAML(`working_directory`·`log_projects`)이 읽힌다: 폴더는 `folder`로, 묶음은 버림.
- 옛 로그 묶기 `logs.projects`·새 정의 범위 `projects`가 든 설정도 읽힌다(deprecated 표시).
- 이슈·오류 코드 7개가 스키마 상수(→ TS)로 나가고 HTTP 상태가 정해져 있다.
- 폴더 확인 요청 `exclude_project_id`·응답 `nearest_existing`(K33-13), `x-path` 경로 주석(X33).
- 정의 종류·상태 이름은 열린 문자열이다(코드에 고정 목록 없음).

0.12.0(5.7R.33c2)에서 `uses`·`import_mode`·`ProjectUse`·`ProjectUsesUpdate`·`UseCopy*`·
`LegacyUse*`가 없어져 그 테스트는 v11 테스트로 옮겼다(옛 키는 읽고 버림).
"""

from io import StringIO
from typing import Any

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

import agent_console_contracts as root
from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    HTTP_STATUS_BY_ERROR_CODE,
    X_PATH,
    AssignProjectRequest,
    AssignProjectResult,
    ErrorCodes,
    FolderCheck,
    FolderCheckRequest,
    FolderListing,
    KnownIssueCodes,
    LogSessionSummary,
    Project,
    ProjectCounts,
    ProjectCreate,
    ProjectUpdate,
    ProjectView,
    WorkspaceSettings,
    build_schema,
    x_path,
)
from agent_console_contracts import projects as projects_module


def _load_yaml(text: str) -> Any:
    return YAML(typ="safe").load(StringIO(text))


# ---------------------------------------------------------------- 버전


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_v10() -> None:
    """0.11.0에서 정한 버전 이상이다(정확한 지금 값은 v11 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 11, 0)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v10 = {
        "common": "1.5.0",
        "resources": "1.1.0",
        "logs": "1.1.0",
        "definitions": "1.4.0",
        "runs": "1.4.0",
        "usage": "1.1.0",
        "projects": "2.0.0",
        "chat": "1.1.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.0.0",
        "modules": "1.3.0",
    }
    for sub, version in v10.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_new_project_models_live_in_projects_submodule() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        "ProjectView",
        "FolderCheckRequest",
        "FolderCheck",
        "FolderConflict",
        "FolderListing",
        "FolderEntry",
        "FolderRoot",
        "AssignProjectRequest",
        "AssignProjectResult",
        "ProjectCounts",
        "ProjectNotImportedDetails",
        "ProjectFolderConflictDetails",
        "ProjectFolderUnavailableDetails",
        "ProjectOutsideFolderDetails",
    } <= set(grouped["projects"])
    for name in projects_module.__all__:
        assert getattr(projects_module, name) is getattr(root, name)


# ---------------------------------------------------------------- 옛 프로젝트 파일 읽기(§PI.8)

_LEGACY_YAML = """\
kind: project
id: payments
name: 결제 서비스
description: 옛 형식
working_directory: /home/me/work/payments
log_projects: [grp-a, ~ungrouped]
settings:
  model: zz-model
zz_kept: true
"""


def test_legacy_project_yaml_reads_working_directory_as_folder() -> None:
    project = Project.model_validate(_load_yaml(_LEGACY_YAML))
    assert project.folder == "/home/me/work/payments"
    dumped = project.model_dump(mode="json", exclude_unset=True)
    assert "working_directory" not in dumped
    assert "log_projects" not in dumped  # 읽고 버린다(저장할 때 키가 빠짐)
    assert dumped["folder"] == "/home/me/work/payments"
    assert dumped["zz_kept"] is True  # 모르는 키는 그대로
    assert project.archived is False
    # 1.x 파이썬 소비자 호환 읽기(스키마에는 없음)
    assert project.working_directory == project.folder
    assert project.log_projects == []
    assert "working_directory" not in Project.model_json_schema()["properties"]


def test_legacy_project_without_folder_is_folder_unset() -> None:
    project = Project.model_validate({"id": "old", "name": "Old", "working_directory": None})
    assert project.folder is None
    assert Project.model_validate({"id": "old", "name": "Old"}).folder is None


def test_folder_wins_over_legacy_working_directory() -> None:
    doc = {"id": "p", "name": "P", "folder": "/new", "working_directory": "/old"}
    assert Project.model_validate(doc).folder == "/new"


def test_folder_is_required_key_in_schema() -> None:
    defs = build_schema()["$defs"]
    assert "folder" in defs["Project"]["required"]
    assert "folder" in defs["ProjectCreate"]["required"]
    assert "id" not in defs["ProjectCreate"].get("required", [])
    assert "name" not in defs["ProjectCreate"].get("required", [])
    assert "log_projects" not in defs["Project"]["properties"]


def test_project_create_requires_folder_and_fills_nothing() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate({"id": "p", "name": "P"})
    created = ProjectCreate.model_validate({"folder": "/w/p"})
    assert created.id is None
    assert created.name is None


def test_project_update_repath_and_restore() -> None:
    body = ProjectUpdate.model_validate({"folder": "/w/q", "archived": False})
    assert body.model_dump(exclude_unset=True) == {"folder": "/w/q", "archived": False}
    # 옛 키는 요청에서 무시된다(전방 호환 ContractModel)
    assert (
        ProjectUpdate.model_validate({"working_directory": "/x"}).model_dump(exclude_unset=True)
        == {}
    )


def test_project_view_status_is_open_string() -> None:
    view = ProjectView.model_validate(
        {"project": {"id": "p", "name": "P", "folder": "/p"}, "status": "zz-new-status"}
    )
    assert view.status == "zz-new-status"
    statuses = build_schema()["x-constants"]["KNOWN_PROJECT_STATUSES"]
    assert {
        "ready",
        "folder_missing",
        "not_a_directory",
        "no_access",
        "folder_unset",
        "folder_conflict",
    } <= set(statuses.values())


# ---------------------------------------------------------------- 폴더 확인·탐색(§PI.6, K33-13)


def test_folder_check_request_exclude_project_id() -> None:
    assert FolderCheckRequest.model_validate({"path": "~/w"}).exclude_project_id is None
    body = FolderCheckRequest.model_validate({"path": "/w/x", "exclude_project_id": "p"})
    assert body.exclude_project_id == "p"
    assert body.create is False
    with pytest.raises(ValidationError):
        FolderCheckRequest.model_validate({"path": "/w", "exclude_project_id": "bad id"})


def test_folder_check_carries_nearest_existing_and_conflict() -> None:
    check = FolderCheck.model_validate(
        {
            "input": "/w/gone/deeper",
            "path": "/w/gone/deeper",
            "nearest_existing": "/w",
            "can_create": False,
            "status": "missing_parent",
        }
    )
    assert check.nearest_existing == "/w"
    assert check.conflict is None
    taken = FolderCheck.model_validate(
        {
            "input": "/w/a",
            "path": "/w/a",
            "exists": True,
            "is_dir": True,
            "status": "overlap_parent",
            "conflict": {"project_id": "a", "relation": "parent", "folder": "/w"},
        }
    )
    assert taken.conflict is not None
    assert taken.conflict.relation == "parent"
    known = build_schema()["x-constants"]["KNOWN_FOLDER_CHECK_STATUSES"]
    for status in ("ok", "missing", "taken", "taken_archived", "overlap_child", "same_path"):
        assert status in known.values()


def test_folder_listing_entries() -> None:
    listing = FolderListing.model_validate(
        {
            "path": "/w",
            "parent": "/",
            "entries": [
                {"name": "a", "path": "/w/a", "project_id": "a"},
                {"name": "b", "path": "/w/b", "locked": True},
            ],
            "roots": [{"kind": "home", "path": "/home/me", "label": "홈"}],
            "truncated": True,
        }
    )
    assert listing.entries[0].project_id == "a"
    assert listing.entries[1].locked is True
    assert listing.hidden_count == 0


# ---------------------------------------------------------------- 이전 기록 넣기·개수(§PI.8)


def test_assign_project_request_needs_exactly_one_selector() -> None:
    assert AssignProjectRequest.model_validate({"to": "p", "ids": ["r1"]}).ids == ["r1"]
    assert AssignProjectRequest.model_validate({"to": "p", "from_null": True}).from_null
    with pytest.raises(ValidationError):
        AssignProjectRequest.model_validate({"to": "p"})
    with pytest.raises(ValidationError):
        AssignProjectRequest.model_validate({"to": "p", "ids": ["r"], "from_null": True})
    result = AssignProjectResult.model_validate(
        {"assigned": 3, "skipped": [{"id": "r9", "reason": "other_project", "project_id": "q"}]}
    )
    assert result.skipped[0].project_id == "q"


def test_project_counts_keeps_unknown_project_ids() -> None:
    counts = ProjectCounts.model_validate(
        {"total": 5, "no_project": 2, "by_project": {"a": 2, "gone": 1}}
    )
    assert counts.by_project["gone"] == 1


# ---------------------------------------------------------------- 오류·이슈 코드


_PROJECT_CODES = {
    "PROJECT_REQUIRED": ("project.required", 422),
    "PROJECT_NOT_IMPORTED": ("project.not_imported", 422),
    "PROJECT_FOLDER_MISSING": ("project.folder_missing", 409),
    "PROJECT_FOLDER_TAKEN": ("project.folder_taken", 409),
    "PROJECT_FOLDER_OVERLAPS": ("project.folder_overlaps", 409),
    "PROJECT_OUTSIDE_FOLDER": ("project.outside_folder", 422),
    "FOLDERS_REMOTE_DISABLED": ("folders.remote_disabled", 403),
}


@pytest.mark.parametrize(("name", "expected"), sorted(_PROJECT_CODES.items()))
def test_project_codes_exposed_to_ts_with_http_status(name: str, expected: tuple[str, int]) -> None:
    code, status = expected
    assert getattr(KnownIssueCodes, name) == code
    assert getattr(ErrorCodes, name) == code
    assert HTTP_STATUS_BY_ERROR_CODE[code] == status
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_ISSUE_CODES"][name] == code
    assert constants["ERROR_CODES"][name] == code
    assert constants["HTTP_STATUS_BY_ERROR_CODE"][code] == status


def test_folder_error_codes_follow_local_folders_codes() -> None:
    """`ac-local-folders` `FolderError.code`에 `folders.` 접두. 없음 404, 범위 밖 403, 입력 422."""
    package_codes = (
        "empty",
        "invalid_path",
        "relative",
        "foreign_path",
        "no_home",
        "outside_roots",
        "not_found",
        "not_directory",
        "no_access",
        "invalid_name",
        "exists",
        "missing_parent",
        "io_error",
    )
    for code in package_codes:
        value = getattr(ErrorCodes, f"FOLDERS_{code.upper()}")
        assert value == f"folders.{code}"
        assert value in HTTP_STATUS_BY_ERROR_CODE
    assert HTTP_STATUS_BY_ERROR_CODE["folders.not_found"] == 404
    assert HTTP_STATUS_BY_ERROR_CODE["folders.outside_roots"] == 403
    assert HTTP_STATUS_BY_ERROR_CODE["folders.relative"] == 422


def test_settings_ignored_key_issue_code() -> None:
    assert KnownIssueCodes.SETTINGS_IGNORED_KEY == "settings.ignored_key"
    assert KnownIssueCodes.LOGS_NO_PROJECTS == "logs.no_projects"


# ---------------------------------------------------------------- deprecated 설정(K33-15, §PI.8)

_LEGACY_SETTINGS_YAML = """\
logs:
  projects:
    groups:
      - {id: my-app, label: 내 앱, match: ["/home/me/app/**"]}
    ungrouped: repo_root
    git_worktrees: false
projects:
  new_definition_scope: {agent: shared}
  fallback: project
"""


def test_legacy_logs_projects_and_scope_settings_still_read() -> None:
    doc = _load_yaml(_LEGACY_SETTINGS_YAML)
    settings = WorkspaceSettings.model_validate(doc)
    assert settings.logs is not None
    assert settings.logs.projects is not None
    assert settings.model_dump(mode="json", exclude_unset=True) == doc


def test_deprecated_fields_are_marked_in_schema() -> None:
    defs = build_schema()["$defs"]
    assert defs["LogSettings"]["properties"]["projects"]["deprecated"] is True
    assert defs["WorkspaceSettings"]["properties"]["projects"]["deprecated"] is True
    assert defs["LogSessionSummary"]["properties"]["project"]["deprecated"] is True
    assert "project_id" in defs["LogSessionSummary"]["properties"]


def test_log_session_summary_project_id() -> None:
    assert LogSessionSummary.model_validate({"session": "s"}).project_id is None
    assert LogSessionSummary.model_validate({"session": "s", "project_id": "p"}).project_id == "p"


# ---------------------------------------------------------------- x-path(X33)


def test_x_path_annotations_on_path_fields() -> None:
    defs = build_schema()["$defs"]
    assert defs["AgentSettings"]["properties"]["working_directory"][X_PATH] == "directory"
    assert defs["Limits"]["properties"]["directories"][X_PATH] == "directory"
    constants = build_schema()["x-constants"]
    assert constants["X_PATH"] == "x-path"
    assert constants["X_PATH_KINDS"] == ["directory", "file"]
    assert x_path("file") == {"x-path": "file"}
    with pytest.raises(ValueError, match="x-path"):
        x_path("zz")  # type: ignore[arg-type]
