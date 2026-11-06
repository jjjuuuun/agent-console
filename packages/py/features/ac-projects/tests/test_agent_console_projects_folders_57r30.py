"""등록된 프로젝트 → 폴더 묶음(5.7R.30 후속, 5.7R.33e: 서버 작업 폴더 대체 없음 + id)."""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts import Project
from agent_console_projects import ProjectFolder, ProjectFolderSet, project_folders


def test_no_projects_is_empty() -> None:
    sets = project_folders([], flavor="posix")
    assert sets.entries == ()
    assert sets.registered == ()
    assert sets.archived == ()


def test_entries_have_ids_and_skip_unset_archived_duplicates() -> None:
    projects = [
        Project(id="a", name="A", folder="/w/a"),
        Project(id="b", name="B", folder="sub"),  # 옛 상대 경로 → 설정 파일 폴더 기준
        Project(id="c", name="C", folder=None),  # folder_unset: 서버 작업 폴더로 대신하지 않는다
        Project(id="d", name="D", folder="/w/a/"),  # 같은 폴더: 처음 것만
        Project(id="e", name="E", folder="/w/e", archived=True),
    ]
    sets = project_folders(projects, base_dir="/w/app", flavor="posix")
    assert sets.entries == (
        ProjectFolder("a", Path("/w/a")),
        ProjectFolder("b", Path("/w/app/sub")),
    )
    assert sets.registered == (Path("/w/a"), Path("/w/app/sub"))
    assert sets.archived == (ProjectFolder("e", Path("/w/e")),)
    assert sets.archived_folders == (Path("/w/e"),)
    assert sets.project_for("/w/e/x") is None  # 보관 프로젝트에는 묶지 않는다


def test_relative_folder_without_base_is_skipped() -> None:
    assert project_folders([{"id": "b", "folder": "sub"}], flavor="posix").entries == ()


def test_current_compat_is_removed_33i() -> None:
    sets = project_folders([{"id": "a", "folder": "/w/a"}], flavor="posix")
    assert not hasattr(sets, "current")


def test_archived_same_folder_loses_to_registered() -> None:
    projects: list[dict[str, object]] = [
        {"id": "old", "folder": "/w/a", "archived": True},
        {"id": "new", "folder": "/w/a"},
    ]
    sets = project_folders(projects, flavor="posix")
    assert [e.id for e in sets.entries] == ["new"]
    assert sets.archived == ()


def test_project_for_subfolder_and_outside() -> None:
    sets = project_folders([{"id": "a", "folder": "/w/a"}], flavor="posix")
    assert isinstance(sets, ProjectFolderSet)
    assert sets.project_for("/w/a") == "a"
    assert sets.project_for("/w/a/deep/x") == "a"
    assert sets.project_for("/w/ab") is None
