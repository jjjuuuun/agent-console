# ruff: noqa: N818
"""프로젝트 공간 → 위키 공간(``wiki.spaces`` 구현, design §7R.3·§7R.4·§7R.13, §PI.5).

공간 이름(등록 id)을 ``projects.spaces``로 열고 ``mod-wiki``가 쓰는 모양(``ProjectWikiSpace``)으로
바꾼다. 위키·위키 규칙 정의는 그 폴더의 정의 저장소(``<folder>/<config_dir>/``), 페이지는
``<folder>/<config_dir>/<pages_dir>/<위키 id>/``에 들어가므로 폴더를 다른 앱(다른
workspace)에 등록해도 위키·페이지·규칙이 그대로다.

경로 지킴(§PI.5, ``ac-projects`` ``FolderGuard`` — ``link-projects-sdd``와 같은 규칙):

- 페이지 폴더는 구성 폴더 **안**이어야 하고, 구성 폴더의 예약 폴더(상태·세션 폴더, 정의 종류 폴더,
  설치자 ``reserved_dirs``)와 겹치면 안 된다(대소문자 무시). 겹치면 ``UnsafePagesRoot(reserved)``.
- 링크를 푼 페이지 폴더와 그 바로 아래 위키 폴더들이 프로젝트 폴더 안이어야 한다. 밖이면
  ``UnsafePagesRoot(link)``(422 ``folders.invalid_path``) — 위키 폴더 안 페이지 경로는 ``ac-wiki``
  ``LocalWikiPages``가 지킨다(링크 거부 + realpath가 위키 폴더 안).
- 열 때 폴더 매니페스트를 읽어 깨졌으면 ``ManifestInvalid``(409
  ``project.manifest_invalid``), 폴더가 없으면 제공자의 ``FolderMissing``(409
  ``project.folder_missing``), 모르는 프로젝트는 ``LookupError``.
- 쓸 수 없는 폴더(공간 ``config_writable`` 거짓, 또는 있는 페이지 폴더에 쓰기 권한이 없음)는
  ``config_writable=False``로 알린다. ``mod-wiki``가 쓰기를 409
  ``project.config_readonly``로 거부하고 보기·검색은 된다(검색 색인은 메모리).
- 아무것도 만들거나 쓰지 않는다. 캐시는 제공자(``mod-projects`` 공간 캐시)가 맡는다.
"""

from __future__ import annotations

import os
import posixpath
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_console_contracts import ErrorCodes
from agent_console_project_space import ProjectSpace, SpaceError, read_manifest
from agent_console_projects import FolderGuard, normalize_reserved, relative_inside
from agent_console_store import DefinitionStore

from .ports import ProjectSpaces, SpaceLike
from .settings import check_relative_dir, package_defaults

__all__ = [
    "ProjectWikiSpace",
    "ProjectWikiSpaces",
    "UnsafePagesRoot",
    "UnsafeSpaceRoot",
    "config_dir_of",
]


class UnsafeSpaceRoot(SpaceError):
    """공간의 구성 폴더가 프로젝트 폴더 안이 아니다(제공자 설정 오류) -> ``internal``.

    ``SpaceError``의 기본 ``code``(``internal``)를 그대로 쓴다. 폴더 밖 저장소에 위키를 두지 않는다.
    """


class UnsafePagesRoot(SpaceError):
    """페이지 폴더가 예약 폴더와 겹치거나 링크를 풀면 프로젝트 폴더 밖이다 -> 422
    ``folders.invalid_path``.

    Attributes:
        reason: ``reserved``(예약 폴더와 겹침)·``link``(실제 경로가 폴더 밖).
        path: 문제가 된 폴더(프로젝트 폴더 기준 상대 경로 — 절대 경로를 싣지 않는다).
    """

    code = ErrorCodes.FOLDERS_INVALID_PATH

    def __init__(self, path: str, reason: Literal["reserved", "link"]) -> None:
        super().__init__(f"wiki pages folder is not allowed ({reason}): {path}")
        self.path = path
        self.reason = reason
        self.details = {"path": path, "reason": reason}


@dataclass(frozen=True)
class ProjectWikiSpace:
    """열린 위키 공간 하나(``mod-wiki`` ``WikiSpace`` 모양).

    Attributes:
        store: 그 폴더의 정의 저장소(프로젝트 공간 것 그대로 — 읽기 전용·비밀 검사가 공간 규칙을
            따름).
        folder: 프로젝트 폴더(절대 경로 — ``mod-wiki``는 응답·로그에 싣지 않는다).
        config_writable: 쓸 수 있나(거짓이면 보기·검색만).
        config_dir: 저장소 폴더(폴더 기준 POSIX 상대 경로, 예: ``.agent-console``).
        pages_dir: 페이지 폴더(폴더 기준 POSIX 상대 경로 = ``<config_dir>/<설치자 pages_dir>``).
        pages_root: 페이지 폴더 절대 경로(위키 하나 = ``<pages_root>/<위키 id>/``).
        index_dir: 검색 색인 폴더(``<상태 폴더>/<설치자 index_dir>``, 다시 만들 수 있는 캐시). 상태
            폴더를 모르거나 쓸 수 없으면 None(메모리 색인).
    """

    store: DefinitionStore
    folder: Path
    config_writable: bool
    config_dir: str
    pages_dir: str
    pages_root: Path
    index_dir: Path | None


def config_dir_of(space: SpaceLike) -> str:
    """공간 구성 폴더의 폴더 기준 상대 경로(POSIX).

    >>> from types import SimpleNamespace
    >>> config_dir_of(SimpleNamespace(folder=Path("/w/app"), root=Path("/w/app/.cfg/x")))
    '.cfg/x'

    Raises:
        UnsafeSpaceRoot: 구성 폴더가 프로젝트 폴더와 같거나 밖이다.
    """
    try:
        return relative_inside(space.root, space.folder)
    except ValueError as exc:
        raise UnsafeSpaceRoot(f"project config folder: {exc}") from None


def _check_manifest(space: SpaceLike) -> None:
    if isinstance(space, ProjectSpace):
        read_manifest(space)  # 깨졌으면 ManifestInvalid(409)


def _optional_rel(space: SpaceLike, name: str) -> str | None:
    """공간의 선택 경로 속성(``state_dir`` 등)의 폴더 기준 상대 경로. 없거나 폴더 밖이면 None."""
    value = getattr(space, name, None)
    if value is None:
        return None
    try:
        return relative_inside(value, space.folder)
    except ValueError:
        return None


def _kind_dirs(store: DefinitionStore, config_dir: str) -> Iterator[str]:
    """정의 종류 폴더(``<config_dir>/<directory>``). 저장소가 종류 정보를 주지 않으면 없음."""
    info = getattr(store, "kind_info", None)
    if not callable(info):
        return
    for name in store.kinds():
        directory = str(getattr(info(name), "directory", "") or "").strip("/")
        if directory:
            yield posixpath.join(config_dir, directory)


def _overlaps(guard: FolderGuard, relative: str) -> bool:
    return guard.is_reserved(relative) or guard.contains_reserved(relative)


class ProjectWikiSpaces:
    """``wiki.spaces`` 구현: 공간 이름(등록 id) → ``ProjectWikiSpace``.

    Args:
        spaces: 지금 ``projects.spaces``(없으면 None — 모든 이름이 ``LookupError``).
        pages_dir: 구성 폴더 안 페이지 폴더(상대 경로, 기본 패키지 데이터).
        index_dir: 상태 폴더 안 검색 색인 폴더(상대 경로, 기본 패키지 데이터).
        reserved: 페이지 폴더와 겹치면 안 되는 폴더(프로젝트 폴더 기준 상대 경로). 구성 폴더의 상태·
            세션 폴더와 정의 종류 폴더는 늘 더한다.
        check_manifest: 공간 → 매니페스트 검사(주입, 기본 ``project.yaml`` 읽기).
        realpath: 링크 풀기(주입, 기본 ``os.path.realpath``).
        writable: 있는 폴더에 쓸 수 있나(주입, 기본 ``os.access(W_OK)``).

    >>> import tempfile
    >>> from agent_console_link_projects_wiki.testing import FolderSpaces
    >>> folder = Path(tempfile.mkdtemp())
    >>> space = ProjectWikiSpaces(lambda: FolderSpaces({"a": folder})).open("a")
    >>> space.pages_dir, space.config_writable, space.pages_root == folder / space.pages_dir
    ('.agent-console/wiki-pages', True, True)
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        *,
        pages_dir: str | None = None,
        index_dir: str | None = None,
        reserved: Iterable[str] = (),
        check_manifest: Callable[[SpaceLike], None] = _check_manifest,
        realpath: Callable[[str], str] = os.path.realpath,
        writable: Callable[[Path], bool] = lambda p: os.access(p, os.W_OK),
    ) -> None:
        defaults = package_defaults()
        self._spaces = spaces
        self._pages_dir = check_relative_dir(pages_dir or defaults["pages_dir"])
        self._index_dir = check_relative_dir(index_dir or defaults["index_dir"])
        self._reserved = normalize_reserved(reserved)
        self._check_manifest = check_manifest
        self._realpath = realpath
        self._writable = writable

    @property
    def pages_dir(self) -> str:
        """구성 폴더 안 페이지 폴더(설치자 값)."""
        return self._pages_dir

    def open(self, space: str) -> ProjectWikiSpace:
        """그 프로젝트의 위키 공간. 아무것도 만들거나 쓰지 않는다.

        Raises:
            LookupError: 모르는 프로젝트(또는 ``projects.spaces`` 없음).
            agent_console_project_space.FolderMissing: 폴더가 없다(409).
            agent_console_project_space.ManifestInvalid: 매니페스트가 깨졌다(409).
            UnsafePagesRoot: 페이지 폴더가 예약 폴더와 겹치거나 폴더 밖이다(422).
            agent_console_project_space.SpaceError: 그 밖에 열 수 없다(``code``).
        """
        provider = self._spaces()
        if provider is None:
            raise LookupError(space)
        found = provider.open(space)
        self._check_manifest(found)
        folder = Path(found.folder)
        config_dir = config_dir_of(found)
        state_rel = _optional_rel(found, "state_dir")
        sessions_rel = _optional_rel(found, "sessions_dir")
        reserved = [
            *self._reserved,
            *(r for r in (state_rel, sessions_rel) if r),
            *_kind_dirs(found.definitions, config_dir),
        ]
        guard = FolderGuard(folder, reserved=reserved, realpath=self._realpath)
        pages_rel = posixpath.join(config_dir, self._pages_dir)
        if _overlaps(guard, pages_rel):
            raise UnsafePagesRoot(pages_rel, "reserved")
        if not guard.resolves_inside(pages_rel):
            raise UnsafePagesRoot(pages_rel, "link")
        pages_root = folder / pages_rel
        for child in _child_dirs(pages_root):
            rel = posixpath.join(pages_rel, child)
            if not guard.resolves_inside(rel):
                raise UnsafePagesRoot(rel, "link")
        writable = bool(found.config_writable) and _can_write(pages_root, self._writable)
        index_dir: Path | None = None
        if writable and state_rel:
            index_rel = posixpath.join(state_rel, self._index_dir)
            if guard.resolves_inside(index_rel):
                index_dir = folder / index_rel
        return ProjectWikiSpace(
            store=found.definitions,
            folder=folder,
            config_writable=writable,
            config_dir=config_dir,
            pages_dir=pages_rel,
            pages_root=pages_root,
            index_dir=index_dir,
        )


def _child_dirs(root: Path) -> list[str]:
    """``root`` 바로 아래 폴더·링크 이름(없거나 못 읽으면 빈 목록, 숨김 포함)."""
    try:
        entries = list(os.scandir(root))
    except OSError:
        return []
    out: list[str] = []
    for entry in entries:
        try:
            if entry.is_symlink() or Path(entry.path).is_junction() or entry.is_dir():
                out.append(entry.name)
        except OSError:
            continue
    return sorted(out)


def _can_write(pages_root: Path, writable: Callable[[Path], bool]) -> bool:
    """있는 가장 가까운 폴더(페이지 폴더 → 구성 폴더 …)에 쓸 수 있나.

    공간 판정이 이미 참일 때만 본다.
    """
    probe = pages_root
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            return True
        probe = parent
    return writable(probe)
