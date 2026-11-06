"""세션 프로젝트 예약 값과 git worktree 본 저장소 찾기(수집 때).

5.7R.33i(design §PI.5, K33-15): 옛 묶기 규칙(`logs.projects`의 `groups`·`ungrouped`·
`git_worktrees`) 해석을 지웠다. 세션의 프로젝트는 질의 맥락 `QueryContext.project_for`(작업 폴더 →
등록 프로젝트 id) 하나로 정한다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from ._glob import normalize_path
from ._source import read_only_open

__all__ = [
    "UNGROUPED_PROJECT",
    "RepoRootResolver",
    "git_worktree_root",
]

UNGROUPED_PROJECT = "~ungrouped"
""""어느 등록 프로젝트에도 들지 않음" 예약 값(필터 `project`).
`~` 접두로 등록 id와 겹치지 않는다."""


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
