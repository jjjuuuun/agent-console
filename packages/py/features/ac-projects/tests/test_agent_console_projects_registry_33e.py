"""5.7R.33e 등록 규칙: 경로 비교·겹침·상태·경로 → 프로젝트·등록 id·합치기(design §PI.2·§PI.8)."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import (
    ErrorCodes,
    KnownFolderCheckStatuses,
    Project,
    ProjectManifest,
    ProjectRegistration,
)
from agent_console_local_folders import MemoryFileSystem, normalize
from agent_console_projects import (
    MANIFEST_KEYS,
    REGISTRATION_KEYS,
    combined_version,
    conflict_details,
    conflict_error_code,
    conflict_status,
    folder_conflicts,
    folder_key,
    folder_slug,
    folder_within,
    ignored_key_issues,
    initial_manifest,
    legacy_manifest_values,
    load_path_rules,
    merge_project,
    path_relation,
    project_for_path,
    project_status,
    registration_id,
    registry_conflicts,
    resolve_folder,
    split_project,
    suggest_project_id,
)

# ---------------------------------------------------------------- 경로 비교(표)


@pytest.mark.parametrize(
    ("a", "b", "flavor", "relation"),
    [
        ("C:\\Work\\App", "c:\\work\\app\\", "windows", "same"),  # 드라이브 대소문자·끝 구분자
        ("C:\\Work\\App\\src", "c:\\WORK\\app", "windows", "parent"),
        ("C:\\Work", "C:\\work\\App", "windows", "child"),
        ("C:\\Work\\App", "D:\\Work\\App", "windows", None),
        ("/w/app/", "/w/app", "posix", "same"),  # 끝 슬래시
        ("/w/App", "/w/app", "posix", None),  # POSIX는 대소문자 구분(규칙 없으면)
        ("/w/app", "/w/apple", "posix", None),  # 앞부분만 같은 다른 폴더
        ("/w/app/x", "/w/app", "posix", "parent"),
        ("/", "/w", "posix", "child"),
    ],
)
def test_path_relation_table(a: str, b: str, flavor: str, relation: str | None) -> None:
    assert path_relation(a, b, flavor=flavor, rules=None) == relation  # type: ignore[arg-type]


def test_case_insensitive_rule_is_data() -> None:
    rules = load_path_rules({"case_insensitive": [{"pattern": "/mnt/?", "description": "drvfs"}]})
    assert path_relation("/mnt/c/Work", "/mnt/c/work/", flavor="posix", rules=rules) == "same"
    assert path_relation("/home/Me", "/home/me", flavor="posix", rules=rules) is None
    assert folder_key("/mnt/cd/X", flavor="posix", rules=rules) == "/mnt/cd/X"  # 한 글자만
    assert (
        folder_within("/MNT/C/x", "/mnt/c", flavor="posix", rules=rules) is False
    )  # 앞부분 맞아야
    with pytest.raises(ValueError, match="pattern"):
        load_path_rules({"case_insensitive": [{"nope": 1}]})
    assert load_path_rules(include_defaults=False).case_insensitive == ()


@pytest.mark.parametrize(
    ("value", "base", "flavor", "expected"),
    [
        ("/w/a/../b/", None, "posix", "/w/b"),
        ("sub", "/cfg", "posix", "/cfg/sub"),
        ("sub", None, "posix", None),
        ("", "/cfg", "posix", None),
        (None, "/cfg", "posix", None),
        ("c:/Work/App\\", None, "windows", "C:\\Work\\App"),
        ("C:\\x", None, "posix", None),  # 다른 OS 경로
    ],
)
def test_resolve_folder_table(
    value: object, base: str | None, flavor: str, expected: str | None
) -> None:
    assert resolve_folder(value, base_dir=base, flavor=flavor) == expected  # type: ignore[arg-type]


# ---------------------------------------------------------------- 겹침(양방향·보관·자기 제외)

REGS: list[dict[str, Any]] = [
    {"id": "app", "folder": "/w/app"},
    {"id": "mono", "folder": "/w/mono"},
    {"id": "gone", "folder": "/w/old", "archived": True},
    {"id": "inner", "folder": "/w/mono/pkg/x"},
]


def test_conflicts_both_directions() -> None:
    parent = folder_conflicts(REGS, "/w/app/sub", flavor="posix")
    assert [(c.project_id, c.relation) for c in parent] == [("app", "parent")]
    assert conflict_status(parent) == KnownFolderCheckStatuses.OVERLAP_PARENT
    child = folder_conflicts(REGS, "/w", flavor="posix")
    assert [(c.project_id, c.relation) for c in child] == [
        ("app", "child"),
        ("mono", "child"),
        ("inner", "child"),
    ]
    assert conflict_status(child) == KnownFolderCheckStatuses.OVERLAP_CHILD
    both = folder_conflicts(REGS, "/w/mono/pkg", flavor="posix")
    assert [(c.project_id, c.relation) for c in both] == [("mono", "parent"), ("inner", "child")]
    assert conflict_error_code(both[0]) == ErrorCodes.PROJECT_FOLDER_OVERLAPS
    assert conflict_details(both[0]).relation == "parent"


def test_same_folder_taken_and_archived() -> None:
    same = folder_conflicts(REGS, "/w/app/", flavor="posix")
    assert [(c.project_id, c.relation, c.archived) for c in same] == [("app", "same", False)]
    assert conflict_status(same) == KnownFolderCheckStatuses.TAKEN
    assert conflict_error_code(same[0]) == ErrorCodes.PROJECT_FOLDER_TAKEN
    assert conflict_details(same[0]).relation is None
    archived = folder_conflicts(REGS, "/w/old", flavor="posix")
    assert [(c.project_id, c.archived) for c in archived] == [("gone", True)]
    assert conflict_status(archived) == KnownFolderCheckStatuses.TAKEN_ARCHIVED
    # 보관된 프로젝트와의 겹침은 막지 않는다
    assert folder_conflicts(REGS, "/w/old/sub", flavor="posix") == []
    assert conflict_status([]) is None


def test_exclude_self_for_repath() -> None:
    assert folder_conflicts(REGS, "/w/app/moved", exclude_project_id="app", flavor="posix") == []
    assert folder_conflicts(REGS, "/w/app", exclude_project_id="nope", flavor="posix") != []


def test_link_is_compared_by_real_path() -> None:
    fs = MemoryFileSystem().add_dir("/w").add_dir("/w/real").add_link("/w/alias", "/w/real")
    stored = normalize("/w/alias", fs=fs)  # 등록할 때 실제 경로로 저장(ac-local-folders)
    assert stored == "/w/real"
    regs = [{"id": "r", "folder": "/w/real"}]
    assert [c.relation for c in folder_conflicts(regs, stored, flavor="posix")] == ["same"]


def test_windows_registry_conflicts_and_lookup() -> None:
    regs = [{"id": "a", "folder": "C:\\Work\\A"}, {"id": "b", "folder": "c:\\work\\a\\b"}]
    found = registry_conflicts(regs, flavor="windows")
    assert (found["a"].project_id, found["a"].relation) == ("b", "child")
    assert (found["b"].project_id, found["b"].relation) == ("a", "parent")
    # 옛 파일이 겹치면 가장 깊은 폴더가 이긴다
    assert project_for_path(regs, "C:\\WORK\\A\\B\\src", flavor="windows") == "b"
    assert project_for_path(regs, "C:\\Work\\A\\x", flavor="windows") == "a"
    assert project_for_path(regs, "relative", flavor="windows") is None


# ---------------------------------------------------------------- 상태


def test_project_status_table() -> None:
    fs = (
        MemoryFileSystem()
        .add_dir("/w")
        .add_dir("/w/ok")
        .add_file("/w/file")
        .add_dir("/w/locked", readable=False)
    )
    conflicts = registry_conflicts(
        [{"id": "x", "folder": "/w/ok"}, {"id": "y", "folder": "/w/ok/in"}], flavor="posix"
    )
    cases = {
        "ready": {"id": "p", "folder": "/w/ok"},
        "folder_unset": {"id": "p"},
        "folder_missing": {"id": "p", "folder": "/w/none"},
        "not_a_directory": {"id": "p", "folder": "/w/file"},
        "no_access": {"id": "p", "folder": "/w/locked"},
    }
    for status, project in cases.items():
        assert project_status(project, fs=fs).status == status
    result = project_status({"id": "x", "folder": "/w/ok"}, fs=fs, conflicts=conflicts)
    assert (result.status, result.detail) == ("folder_conflict", "y")
    assert (
        project_status({"id": "p", "folder": "/w/ok"}, fs=fs, manifest_invalid=True).status
        == "manifest_invalid"
    )
    relative = {"id": "p", "working_directory": "ok"}
    assert project_status(relative, fs=fs).status == "folder_unset"
    assert project_status(relative, fs=fs, base_dir="/w").status == "ready"


# ---------------------------------------------------------------- 등록 id(K33-25, U-23)


def test_folder_slug_and_fallback() -> None:
    assert folder_slug("/w/My Project!!", flavor="posix") == "my-project"
    assert folder_slug("/w/Café_2", flavor="posix") == "cafe_2"
    korean = folder_slug("/w/결제", flavor="posix")
    assert korean.startswith("proj-")
    assert len(korean) == len("proj-") + 4
    assert korean == folder_slug("/w/결제/", flavor="posix")  # 같은 폴더면 같은 값
    assert korean != folder_slug("/v/결제", flavor="posix")
    assert folder_slug("C:\\Work\\결제", flavor="windows") == folder_slug(
        "c:\\work\\결제", flavor="windows"
    )
    assert len(folder_slug("/w/" + "a" * 300, flavor="posix")) <= 128


def test_registration_id_suffix_for_worktrees() -> None:
    assert registration_id("payments", []) == "payments"
    assert registration_id("payments", ["payments"]) == "payments-2"
    assert registration_id("payments", ["PAYMENTS", "payments-2"]) == "payments-3"
    long_id = "a" * 128
    assert len(registration_id(long_id, [long_id])) == 128
    assert suggest_project_id("/w/wt2", manifest_id="payments", taken_ids=["payments"]) == (
        "payments-2"
    )


# ---------------------------------------------------------------- 합치기(K33-1·§PI.8)


def test_registration_and_manifest_keys_come_from_contracts() -> None:
    assert {"id", "folder", "archived"} <= REGISTRATION_KEYS
    assert {"name", "description", "settings", "attributes"} == MANIFEST_KEYS


def test_merge_registration_with_manifest() -> None:
    reg = ProjectRegistration(id="payments-2", folder="/w/wt2", labels=["x"])
    man = ProjectManifest.model_validate(
        {"id": "payments", "name": "결제", "description": "d", "settings": {"model": "m"}}
    )
    project = merge_project(reg, man)
    assert isinstance(project, Project)
    assert (project.id, project.folder, project.name, project.labels) == (
        "payments-2",
        "/w/wt2",
        "결제",
        ["x"],
    )
    assert project.settings is not None
    assert project.settings.model == "m"


def test_merge_legacy_registration_without_manifest() -> None:
    old = {
        "id": "app",
        "name": "App",
        "working_directory": "/w/app",
        "settings": {"model": "m"},
        "log_projects": ["g"],
        "uses": [],
    }
    project = merge_project(old)
    assert (project.name, project.folder) == ("App", "/w/app")
    assert legacy_manifest_values(old) == {"name": "App", "settings": {"model": "m"}}
    manifest = initial_manifest(old)
    assert (manifest.id, manifest.name, manifest.settings is not None) == ("app", "App", True)
    assert [i.details["key"] for i in ignored_key_issues(old)] == ["log_projects", "uses"]
    named = merge_project({"id": "x", "folder": "/w/folder-name"}, flavor="posix")
    assert named.name == "folder-name"


def test_split_project_round_trip() -> None:
    project = Project(id="a", name="A", folder="/w/a", description="d", labels=["l"])
    reg, man = split_project(project)
    assert set(reg) <= REGISTRATION_KEYS
    assert set(man) <= MANIFEST_KEYS
    back = merge_project(reg, {"id": "a", **man})
    assert back.model_dump() == project.model_dump()


def test_combined_version_changes_with_either_file() -> None:
    base = combined_version("r", "m")
    assert base != combined_version("r2", "m")
    assert base != combined_version("r", None)
    assert combined_version(None, None) == combined_version(None, None)
