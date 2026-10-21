"""프로젝트 묶기(design §4R.6, 질의 때 적용)와 git worktree 본 저장소 찾기(수집 때)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import BinaryIO

from agent_console_contracts.logs import LogProjectRef, LogProjectSettings

from ._glob import glob_match, normalize_path
from ._source import read_only_open

__all__ = [
    "DEFAULT_UNGROUPED_LABEL",
    "UNGROUPED_PROJECT",
    "RepoRootResolver",
    "git_worktree_root",
    "group_projects",
    "project_base",
    "resolve_project",
]

UNGROUPED_PROJECT = "~ungrouped"
""""묶이지 않음" 예약 값(필터 `project`, 정책 `none`의 묶음 id).
`~` 접두로 그룹 id와 겹치지 않는다."""

DEFAULT_UNGROUPED_LABEL = "기타"
"""정책 `none`일 때 묶음 표시 이름 기본값(호출자가 바꿀 수 있다)."""


def project_base(cwd: str, repo_root: str, settings: LogProjectSettings | None) -> str:
    """묶기 기준 경로: worktree 묶기가 켜져 있고(기본) 본 저장소 경로가 있으면 그것, 아니면 cwd."""
    worktrees = (
        True if settings is None or settings.git_worktrees is None else settings.git_worktrees
    )
    return (
        normalize_path(repo_root if worktrees and repo_root else cwd) if (repo_root or cwd) else ""
    )


def resolve_project(
    cwd: str,
    repo_root: str,
    settings: LogProjectSettings | None,
    *,
    ungrouped_label: str = DEFAULT_UNGROUPED_LABEL,
) -> tuple[LogProjectRef | None, bool]:
    """경로 하나의 프로젝트 묶음.

    1. `settings.groups`를 순서대로 보고 처음 맞는 묶음(기준 = `project_base`).
    2. 없으면 `ungrouped` 정책: `cwd`(기본) = 자기 경로, `repo_root` = 기준 경로,
       `none` = `UNGROUPED_PROJECT` 한 묶음.

    Returns:
        (묶음 또는 None(경로가 전혀 없음), 묶기 규칙에 맞았는지).
    """
    base = project_base(cwd, repo_root, settings)
    if not base:
        return None, False
    for group in (settings.groups if settings and settings.groups else []) or []:
        if any(glob_match(pattern, base) for pattern in group.match):
            return LogProjectRef(id=group.id, label=group.label or group.id), True
    policy = (settings.ungrouped if settings else None) or "cwd"
    if policy == "none":
        return LogProjectRef(id=UNGROUPED_PROJECT, label=ungrouped_label), False
    path = base if policy == "repo_root" else normalize_path(cwd or base)
    return LogProjectRef(id=path, label=path), False


def group_projects(
    paths: Iterable[tuple[str, str]],
    settings: LogProjectSettings | None,
    *,
    ungrouped_label: str = DEFAULT_UNGROUPED_LABEL,
) -> dict[tuple[str, str], LogProjectRef | None]:
    """(cwd, repo_root) 여러 개를 한 번에 묶는다(순수 함수, 규칙을 바꿔도 다시 색인할 필요 없음).

    Returns:
        입력 쌍 → 묶음(경로가 없으면 None).
    """
    return {
        pair: resolve_project(pair[0], pair[1], settings, ungrouped_label=ungrouped_label)[0]
        for pair in dict.fromkeys(paths)
    }


def git_worktree_root(cwd: str, *, open_read: Callable[[Path], BinaryIO] = read_only_open) -> str:
    """cwd가 git worktree면 본 저장소 경로, 아니면 빈 문자열.

    `<cwd>/.git`이 **파일**이고 `gitdir: <본 저장소>/.git/worktrees/<이름>`이면
    본 저장소 경로를 낸다.
    읽기 전용으로만 열고, 실패하면 빈 문자열이다(묶기 기준은 cwd로 돌아간다).
    """
    if not cwd:
        return ""
    try:
        with open_read(Path(cwd) / ".git") as stream:
            head = stream.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return ""
    for line in head.splitlines():
        if line.startswith("gitdir:"):
            gitdir = normalize_path(line[len("gitdir:") :].strip())
            marker = "/.git/worktrees/"
            if marker in gitdir:
                return gitdir.split(marker, 1)[0]
    return ""


class RepoRootResolver:
    """cwd별로 캐시하는 `git_worktree_root`(수집 한 번 동안 같은 cwd를 다시 읽지 않는다)."""

    def __init__(self, open_read: Callable[[Path], BinaryIO] = read_only_open) -> None:
        self._open_read = open_read
        self._cache: dict[str, str] = {}

    def __call__(self, cwd: str) -> str:
        if cwd not in self._cache:
            self._cache[cwd] = git_worktree_root(cwd, open_read=self._open_read)
        return self._cache[cwd]
