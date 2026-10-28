"""5.7R.30 후속: 등록된 프로젝트 → 폴더(현재·전체)."""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts import Project
from agent_console_projects import ProjectFolderSet, project_folders


def test_no_projects_is_empty() -> None:
    assert project_folders([], working_directory=Path("/w")) == ProjectFolderSet()


def test_current_is_registered_project_at_app_folder() -> None:
    projects = [
        Project(id="a", name="A", working_directory="/w/a"),
        Project(id="b", name="B", working_directory="sub"),
        Project(id="c", name="C"),
        Project(id="d", name="D", working_directory="/w/a/"),
    ]
    sets = project_folders(projects, working_directory=Path("/w/app"))
    assert sets.registered == (Path("/w/a"), Path("/w/app/sub"), Path("/w/app"))
    assert sets.current == (Path("/w/app"),)


def test_no_current_when_app_folder_not_registered() -> None:
    sets = project_folders(
        [{"id": "a", "working_directory": "/w/a"}], working_directory=Path("/w/app")
    )
    assert sets.current == ()
    assert sets.registered == (Path("/w/a"),)
