"""프로젝트 폴더 안 경로 지킴(design §PI.5): 예약 경로·링크를 푼 실제 경로가 폴더 안인지.

폴더 안 파일을 읽고 쓰는 연동(``link-projects-sdd`` 스펙 파일, ``link-projects-wiki`` 페이지 폴더)이
같은 규칙을 쓰도록 한 곳에 둔다. 경로 **문자열** 검사(``..``·절대·드라이브·금지 문자)는
호출자 몫이다(각자 오류 형식이 다르다). 여기서는 이미 정규화한 폴더 기준 POSIX 상대 경로만
받는다.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import Literal

from ._paths import PathRules, folder_within

__all__ = ["FolderGuard", "GuardViolation", "normalize_reserved", "relative_inside"]

type GuardViolation = Literal["reserved", "link"]
"""``FolderGuard.violation`` 결과: 예약 경로(``reserved``)·실제 경로가 폴더 밖(``link``)."""


def normalize_reserved(paths: Iterable[str]) -> tuple[str, ...]:
    """예약 경로 목록 정리: 앞뒤 ``/`` 빼기, 빈 값·중복(대소문자 무시) 빼기.

    >>> normalize_reserved(["/.agent-console/", "", ".AGENT-console", "build/out"])
    ('.agent-console', 'build/out')
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        norm = raw.strip().strip("/")
        if not norm or norm.casefold() in seen:
            continue
        seen.add(norm.casefold())
        out.append(norm)
    return tuple(out)


def relative_inside(path: str | os.PathLike[str], folder: str | os.PathLike[str]) -> str:
    """``folder`` 아래 ``path``의 폴더 기준 POSIX 상대 경로(문자열 비교, 링크는 풀지 않는다).

    >>> relative_inside("/w/app/.cfg/x", "/w/app")
    '.cfg/x'

    Raises:
        ValueError: ``path``가 ``folder``와 같거나 밖이다.
    """
    try:
        rel = Path(path).relative_to(Path(folder))
    except ValueError:
        raise ValueError("path is outside the folder") from None
    if not rel.parts or ".." in rel.parts:
        raise ValueError("path must be a folder inside the folder")
    return PurePosixPath(*rel.parts).as_posix()


class FolderGuard:
    """폴더 하나의 경로 지킴.

    Args:
        folder: 프로젝트 폴더.
        reserved: 손대지 않을 폴더(폴더 기준 상대 경로, 그 아래 전부). 비교는 대소문자를 무시한다
            (대소문자를 무시하는 파일 시스템에서 우회되지 않게).
        realpath: 링크 풀기(주입, 기본 ``os.path.realpath``).
        rules: 경로 비교 규칙(``folder_within``에 그대로, 기본 데이터).

    >>> guard = FolderGuard("/w/app", reserved=[".agent-console"], realpath=lambda p: p)
    >>> guard.violation(".Agent-Console/x.md"), guard.violation("docs/a.md")
    ('reserved', None)
    """

    def __init__(
        self,
        folder: str | os.PathLike[str],
        *,
        reserved: Iterable[str] = (),
        realpath: Callable[[str], str] = os.path.realpath,
        rules: PathRules | None = None,
    ) -> None:
        self._folder = Path(folder)
        self._reserved = normalize_reserved(reserved)
        self._folded = tuple(r.casefold() for r in self._reserved)
        self._realpath = realpath
        self._rules = rules

    @property
    def folder(self) -> Path:
        """프로젝트 폴더."""
        return self._folder

    @property
    def reserved(self) -> tuple[str, ...]:
        """예약 경로(정리한 값)."""
        return self._reserved

    def is_reserved(self, relative: str) -> bool:
        """``relative``가 예약 경로이거나 그 아래인가(빈 값 = 폴더 루트 = 아님)."""
        key = relative.strip("/").casefold()
        return bool(key) and any(key == r or key.startswith(r + "/") for r in self._folded)

    def contains_reserved(self, relative: str) -> bool:
        """``relative`` 아래에 예약 경로가 있는가(빈 값 = 폴더 루트 = 예약이 하나라도 있으면 참)."""
        key = relative.strip("/").casefold()
        return any(not key or r.startswith(key + "/") for r in self._folded)

    def resolves_inside(self, relative: str) -> bool:
        """링크를 푼 ``<folder>/<relative>``가 링크를 푼 폴더와 같거나 그 아래인가.

        없는 경로도 본다(있는 앞부분까지 링크를 푼다).
        """
        root = self._realpath(str(self._folder))
        norm = relative.strip("/")
        target = self._realpath(str(self._folder / norm)) if norm else root
        return folder_within(target, root, rules=self._rules)

    def violation(self, relative: str) -> GuardViolation | None:
        """예약(``reserved``)·폴더 밖(``link``)이면 그 이유, 괜찮으면 None."""
        if self.is_reserved(relative):
            return "reserved"
        if not self.resolves_inside(relative):
            return "link"
        return None
