"""계약 v11(design §PI.10, 5.7R.33c2, 0.12.0): `projects` 3.0.0·`memory` 1.1.0·`common` 1.6.0.

- 프로젝트 구성 = 폴더 안 사본: `uses`·`import_mode` 계열 삭제. 0.11 형식 YAML은 읽히고 두 키는
  버린다(`ignored_project_keys`로 이슈를 낼 수 있음).
- 앱 등록부 `ProjectRegistration`·폴더 매니페스트 `ProjectManifest`(모르는 키 보존 왕복).
- `ProjectView.config_writable`·`manifest_id`·`kinds`·`issues`, 상태 `manifest_invalid`.
- 공간 `SpaceRef`(common), 복사 계획·적용, 폴더 선택, 메모리 복사.
- 오류·이슈 코드(+ HTTP 상태)와 문서 상수가 스키마 상수(→ TS)로 나간다.
- 종류 이름·동작·상태는 열린 문자열이다(코드에 고정 목록 없음, R0).
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
    IGNORED_PROJECT_KEYS,
    PROJECT_MANIFEST_FORMAT,
    CopyApplyItem,
    CopyApplyRequest,
    CopyApplyResult,
    CopyPlan,
    CopyPlanRequest,
    ErrorCodes,
    FolderCapabilities,
    FolderPickRequest,
    FolderPickResult,
    KnownIssueCodes,
    MemoryCopyRequest,
    MemoryCopyResult,
    Project,
    ProjectManifest,
    ProjectNotImportedDetails,
    ProjectRegistration,
    ProjectUpdate,
    ProjectView,
    SpaceRef,
    build_schema,
    ignored_project_keys,
)
from agent_console_contracts import memory as memory_module
from agent_console_contracts import projects as projects_module


def _load_yaml(text: str) -> Any:
    return YAML(typ="safe").load(StringIO(text))


# ---------------------------------------------------------------- 버전


def test_contracts_version_is_v11() -> None:
    assert CONTRACTS_VERSION == "0.12.0"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.12.0"
    assert CONTRACT_VERSIONS == {
        "common": "1.6.0",
        "resources": "1.1.0",
        "logs": "1.1.0",
        "definitions": "1.4.0",
        "runs": "1.4.0",
        "usage": "1.1.0",
        "projects": "3.0.0",
        "chat": "1.1.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "modules": "1.3.0",
    }


_REMOVED = (
    "ProjectUse",
    "ProjectUseMode",
    "ProjectImportMode",
    "ProjectUsesUpdate",
    "UseCopyRequest",
    "UseCopyResult",
    "DefinitionCopy",
    "LegacyUse",
    "LegacyUsesPlan",
    "LegacyUsesApplyRequest",
    "LegacyUseResult",
    "LegacyUsesApplyResult",
)


@pytest.mark.parametrize("name", _REMOVED)
def test_uses_models_are_gone(name: str) -> None:
    assert not hasattr(root, name)
    assert not hasattr(projects_module, name)
    assert name not in build_schema()["$defs"]


def test_removed_fields_are_not_in_schema() -> None:
    defs = build_schema()["$defs"]
    for model in ("Project", "ProjectCreate", "ProjectUpdate"):
        props = defs[model]["properties"]
        assert "uses" not in props, model
        assert "import_mode" not in props, model
    details = defs["ProjectNotImportedDetails"]["properties"]
    assert "reason" not in details
    assert "import_mode" not in details
    assert "in_library" in details


def test_new_models_live_in_their_submodules() -> None:
    grouped = build_schema()["x-modules"]
    assert {
        "ProjectRegistration",
        "ProjectManifest",
        "CopyPlanRequest",
        "CopyPlan",
        "CopyPlanItem",
        "CopyApplyRequest",
        "CopyApplyItem",
        "CopyApplyResult",
        "CopyApplyItemResult",
        "FolderCapabilities",
        "FolderPickRequest",
        "FolderPickResult",
        "DefinitionKey",
    } <= set(grouped["projects"])
    assert "SpaceRef" in grouped["common"]
    assert {
        "MemoryCopyRequest",
        "MemoryCopyResult",
        "MemoryCopyConflict",
        "MemoryCopyFilter",
        "MemoryScopeRemap",
    } <= set(grouped["memory"])
    for module in (projects_module, memory_module):
        for name in module.__all__:
            assert getattr(module, name) is getattr(root, name)


# ---------------------------------------------------------------- 0.11 형식 YAML 읽기(무시 + 이슈)

_V011_YAML = """\
kind: project
id: payments
name: 결제 서비스
folder: /home/me/work/payments
import_mode: all
uses:
  - {kind: graph, id: review-team}
  - {kind: graph, id: release-team, mode: pin, version: 3fa9c1b}
archived: false
zz_kept: 1
"""


@pytest.mark.parametrize("model", [Project, ProjectRegistration])
def test_v011_project_yaml_reads_and_drops_uses(model: type[Project | ProjectRegistration]) -> None:
    doc = _load_yaml(_V011_YAML)
    assert ignored_project_keys(doc) == ["uses", "import_mode"]
    loaded = model.model_validate(doc)
    dumped = loaded.model_dump(mode="json", exclude_unset=True)
    assert "uses" not in dumped  # 모르는 키 보존과 달리 저장 때 빠진다
    assert "import_mode" not in dumped
    assert dumped["zz_kept"] == 1
    assert loaded.folder == "/home/me/work/payments"


def test_ignored_project_keys_constant_and_non_mapping() -> None:
    assert IGNORED_PROJECT_KEYS == ("log_projects", "uses", "import_mode")
    assert ignored_project_keys(None) == []
    assert ignored_project_keys({"id": "p", "log_projects": []}) == ["log_projects"]


def test_project_update_ignores_old_keys() -> None:
    body = ProjectUpdate.model_validate({"uses": [], "import_mode": "all", "name": "N"})
    assert body.model_dump(exclude_unset=True) == {"name": "N"}


# ---------------------------------------------------------------- 등록부·매니페스트


def test_registration_holds_folder_and_state_only() -> None:
    reg = ProjectRegistration.model_validate(
        {"id": "payments", "working_directory": "/w/p", "labels": ["a"]}
    )
    assert reg.folder == "/w/p"
    assert reg.kind == "project"
    assert (reg.archived, reg.archived_at, reg.labels) == (False, None, ["a"])
    props = build_schema()["$defs"]["ProjectRegistration"]["properties"]
    assert {"id", "folder", "archived", "archived_at", "labels"} <= set(props)
    assert "name" not in props
    assert "settings" not in props
    with pytest.raises(ValidationError):
        ProjectRegistration.model_validate({"id": "bad id", "folder": "/w"})


_MANIFEST_YAML = """\
format: 1
id: payments
name: 결제 서비스
description: 결제 API
settings:
  model: zz-model
attributes: {team: zz}
zz_other_app_key: {nested: [1, 2]}
"""


def test_manifest_round_trips_unknown_keys() -> None:
    doc = _load_yaml(_MANIFEST_YAML)
    manifest = ProjectManifest.model_validate(doc)
    assert manifest.format == PROJECT_MANIFEST_FORMAT == 1
    assert manifest.id == "payments"
    assert manifest.model_dump(mode="json", exclude_unset=True) == doc


def test_manifest_requires_id_and_name_and_defaults_format() -> None:
    assert ProjectManifest.model_validate({"id": "p", "name": "P"}).format == 1
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"name": "P"})
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"id": "p"})
    with pytest.raises(ValidationError):
        ProjectManifest.model_validate({"id": "p", "name": "P", "format": 0})
    props = build_schema()["$defs"]["ProjectManifest"]["properties"]
    assert "folder" not in props
    assert "archived" not in props


def test_project_view_new_fields_and_defaults() -> None:
    base = {"project": {"id": "p", "name": "P", "folder": "/p"}, "status": "ready"}
    view = ProjectView.model_validate(base)
    assert view.config_writable is True  # 보내지 않은 옛 서버
    assert view.manifest_id is None
    assert view.kinds == []
    assert view.issues == []
    full = ProjectView.model_validate(
        {
            **base,
            "status": "manifest_invalid",
            "config_writable": False,
            "manifest_id": "payments",
            "kinds": ["zz-kind", "graph"],
            "issues": [{"severity": "info", "code": "project.memory_network_fs", "message": "m"}],
        }
    )
    assert full.kinds == ["zz-kind", "graph"]
    assert full.issues[0].code == KnownIssueCodes.PROJECT_MEMORY_NETWORK_FS
    statuses = build_schema()["x-constants"]["KNOWN_PROJECT_STATUSES"]
    assert statuses["MANIFEST_INVALID"] == "manifest_invalid"


def test_not_imported_details_in_library() -> None:
    details = ProjectNotImportedDetails.model_validate(
        {"project_id": "p", "kind": "zz-kind", "id": "t", "in_library": True}
    )
    assert details.in_library is True
    old = ProjectNotImportedDetails.model_validate(
        {"project_id": "p", "kind": "graph", "id": "t", "reason": "disabled"}
    )
    assert old.in_library is False
    assert "reason" not in old.model_dump()


# ---------------------------------------------------------------- 공간·복사(§PI.4.2)


def test_space_ref_null_is_library() -> None:
    assert SpaceRef().project_id is None
    assert SpaceRef.model_validate({"project_id": "p"}).project_id == "p"
    with pytest.raises(ValidationError):
        SpaceRef.model_validate({"project_id": "bad id"})


def test_copy_plan_request_defaults_and_open_kinds() -> None:
    req = CopyPlanRequest.model_validate(
        {"source": {}, "target": {"project_id": "p"}, "items": [{"kind": "zz-kind", "id": "a"}]}
    )
    assert req.include_references is True
    assert req.source.project_id is None
    plan = CopyPlan.model_validate(
        {
            "items": [
                {
                    "kind": "zz-kind",
                    "id": "a",
                    "reason": "requested",
                    "source_version": "h1",
                    "target_state": "zz-new-state",
                },
                {
                    "kind": "agent",
                    "id": "b",
                    "reason": "referenced",
                    "referenced_by": [{"kind": "zz-kind", "id": "a"}],
                    "source_version": "h2",
                    "target_state": "different",
                    "target_version": "h3",
                },
            ]
        }
    )
    assert plan.items[0].default_action is None
    assert plan.items[1].referenced_by[0].id == "a"


def test_copy_apply_rename_needs_new_id_and_actions_are_open() -> None:
    with pytest.raises(ValidationError):
        CopyApplyItem.model_validate(
            {"kind": "graph", "id": "a", "action": "rename", "source_version": "h"}
        )
    item = CopyApplyItem.model_validate(
        {"kind": "graph", "id": "a", "action": "rename", "new_id": "a-2", "source_version": "h"}
    )
    assert item.new_id == "a-2"
    assert (
        CopyApplyItem.model_validate(
            {"kind": "graph", "id": "a", "action": "zz-new-action", "source_version": "h"}
        ).action
        == "zz-new-action"
    )
    req = CopyApplyRequest.model_validate(
        {"source": {}, "target": {"project_id": "p"}, "items": [item.model_dump()]}
    )
    assert req.remove_source is False
    result = CopyApplyResult.model_validate(
        {
            "items": [
                {
                    "kind": "graph",
                    "id": "a",
                    "status": "conflict",
                    "issue": {"severity": "error", "code": "project.copy_conflict", "message": "m"},
                }
            ]
        }
    )
    assert result.items[0].issue is not None


def test_copy_and_pick_constants_exported() -> None:
    constants = build_schema()["x-constants"]
    assert set(constants["KNOWN_COPY_ACTIONS"].values()) == {
        "copy",
        "reuse",
        "overwrite",
        "rename",
        "skip",
    }
    assert set(constants["KNOWN_COPY_TARGET_STATES"].values()) == {
        "absent",
        "identical",
        "different",
    }
    assert set(constants["KNOWN_COPY_STATUSES"].values()) == {
        "copied",
        "reused",
        "overwritten",
        "renamed",
        "skipped",
        "conflict",
    }
    assert set(constants["KNOWN_FOLDER_PICK_STATUSES"].values()) == {
        "picked",
        "cancelled",
        "unavailable",
        "busy",
        "timeout",
        "failed",
    }
    assert constants["PROJECT_MANIFEST_FORMAT"] == 1


# ---------------------------------------------------------------- 폴더 선택(§PI.6, X35)


def test_folder_pick_models() -> None:
    caps = FolderCapabilities.model_validate({"browse": True})
    assert caps.native_dialog is False
    assert caps.reason is None
    assert FolderPickRequest.model_validate({}).initial is None
    picked = FolderPickResult.model_validate(
        {
            "status": "picked",
            "path": "/w/p",
            "provider": "zz-provider",
            "check": {"input": "/w/p", "path": "/w/p", "status": "ok"},
        }
    )
    assert picked.check is not None
    assert picked.check.status == "ok"
    assert FolderPickResult.model_validate({"status": "zz"}).path is None


# ---------------------------------------------------------------- 메모리 복사(§PI.4.3)


def test_memory_copy_request_defaults_and_remap_alias() -> None:
    req = MemoryCopyRequest.model_validate(
        {
            "source": {},
            "target": {"project_id": "p"},
            "remap": [{"from": "old", "to": "new", "kind": "zz-scope"}],
        }
    )
    assert req.on_conflict == "skip"
    assert req.filter.scope_kinds is None
    assert req.remap[0].from_ == "old"
    assert req.model_dump()["remap"][0]["from"] == "old"
    with pytest.raises(ValidationError):
        MemoryCopyRequest.model_validate({"source": {}, "target": {}, "on_conflict": "zz"})
    result = MemoryCopyResult.model_validate(
        {
            "copied": 2,
            "skipped": 1,
            "conflicts": [{"scope": {"kind": "zz", "id": "p"}, "key": "k", "resolution": "skip"}],
        }
    )
    assert result.conflicts[0].new_key is None


# ---------------------------------------------------------------- 오류·이슈 코드

_CODES = {
    "PROJECT_NOT_FOUND": ("project.not_found", 404),
    "PROJECT_MANIFEST_INVALID": ("project.manifest_invalid", 409),
    "PROJECT_CONFIG_READONLY": ("project.config_readonly", 409),
    "PROJECT_COPY_CONFLICT": ("project.copy_conflict", 409),
    "FOLDERS_DIALOG_UNAVAILABLE": ("folders.dialog_unavailable", 409),
    "FOLDERS_DIALOG_BUSY": ("folders.dialog_busy", 409),
    "FOLDERS_DIALOG_TIMEOUT": ("folders.dialog_timeout", 409),
}


@pytest.mark.parametrize(("name", "expected"), sorted(_CODES.items()))
def test_new_codes_exposed_with_http_status(name: str, expected: tuple[str, int]) -> None:
    code, status = expected
    assert getattr(ErrorCodes, name) == code
    assert getattr(KnownIssueCodes, name) == code
    assert HTTP_STATUS_BY_ERROR_CODE[code] == status
    constants = build_schema()["x-constants"]
    assert constants["ERROR_CODES"][name] == code
    assert constants["KNOWN_ISSUE_CODES"][name] == code


def test_memory_network_fs_is_issue_only() -> None:
    assert KnownIssueCodes.PROJECT_MEMORY_NETWORK_FS == "project.memory_network_fs"
    assert not hasattr(ErrorCodes, "PROJECT_MEMORY_NETWORK_FS")
    assert "project.memory_network_fs" not in HTTP_STATUS_BY_ERROR_CODE
    assert (
        build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]["PROJECT_MEMORY_NETWORK_FS"]
        == "project.memory_network_fs"
    )
