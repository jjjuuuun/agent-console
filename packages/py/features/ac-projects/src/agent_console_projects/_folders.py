"""등록된 프로젝트 → 로컬 폴더(5.7R.30 후속). 기능은 앱에 등록된 프로젝트 폴더에 대해서만 동작한다.

로그 수집 범위(현재 프로젝트 / 등록된 프로젝트 전체)처럼 "어느 폴더가 앱의 프로젝트인가"를 묻는
곳이 이 함수 하나를 쓴다. 프로젝트 모델이 바뀌어도 이 함수와 결과 모양(`ProjectFolderSet`)만 맞추면
쓰는 쪽은 그대로다.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_contracts import Project

from ._logs import normalize_path

__all__ = ["ProjectFolderSet", "project_folders"]


@dataclass(frozen=True)
class ProjectFolderSet:
    """프로젝트 폴더 묶음.

    Attributes:
        current: 현재 프로젝트 폴더(0개 또는 1개) — 앱 작업 폴더와 같은 폴더의 등록된 프로젝트.
        registered: 등록된 프로젝트 폴더 전체(겹침 없음, 등록 순).
    """

    current: tuple[Path, ...] = ()
    registered: tuple[Path, ...] = ()


def _folder(value: Any, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    return Path(os.path.normpath(path if path.is_absolute() else base / path))


def project_folders(
    projects: Iterable[Project | Mapping[str, Any]],
    *,
    working_directory: Path,
) -> ProjectFolderSet:
    """등록된 프로젝트의 작업 폴더 → 폴더 묶음.

    - 프로젝트 `working_directory`가 없으면 앱 작업 폴더(`working_directory`)를 쓴다.
    - 상대 경로는 앱 작업 폴더 기준.
    - 현재 프로젝트 = 앱 작업 폴더와 같은 폴더의 프로젝트. 등록된 프로젝트가 없으면 둘 다 비어 있다.

    >>> sets = project_folders(
    ...     [{"id": "a", "working_directory": "/w/a"}, {"id": "here"}],
    ...     working_directory=Path("/w/app"),
    ... )
    >>> [p.as_posix() for p in sets.registered], [p.as_posix() for p in sets.current]
    (['/w/a', '/w/app'], ['/w/app'])
    >>> project_folders([], working_directory=Path("/w/app"))
    ProjectFolderSet(current=(), registered=())
    """
    base = Path(os.path.normpath(working_directory))
    registered: list[Path] = []
    seen: set[str] = set()
    for project in projects:
        raw = (
            project.working_directory
            if isinstance(project, Project)
            else project.get("working_directory")
        )
        folder = _folder(raw, base) or base
        key = normalize_path(str(folder))
        if key not in seen:
            seen.add(key)
            registered.append(folder)
    here = normalize_path(str(base))
    current = tuple(f for f in registered if normalize_path(str(f)) == here)
    return ProjectFolderSet(current=current[:1], registered=tuple(registered))
