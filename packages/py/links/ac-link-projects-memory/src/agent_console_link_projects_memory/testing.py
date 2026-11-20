"""단독 실행·테스트용 모듈(공개).

``folder_spaces_module``: ``projects.spaces``·``projects.lookup``(등록 목록)을 폴더 목록(등록 id →
폴더)으로 주는 작은 모듈. 통합 서버에서는 ``mod-projects``가 대신한다. 실제
``agent_console_project_space.open_space``로 공간을 연다(메모리 DB 경로는 파일을 만들지 않는다).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_project_space import open_space

from .ports import PROJECTS_LOOKUP, PROJECTS_SPACES, SpaceLike

FOLDER_SPACES_ID = "folder-spaces"


@dataclass(frozen=True)
class ListedProject:
    """``projects.lookup`` 목록 항목(이 연동이 보는 칸만)."""

    id: str
    archived: bool = False


class FolderSpaces:
    """``projects.spaces``·``projects.lookup``(목록만) 폴더 목록 구현.

    >>> import tempfile
    >>> folder = Path(tempfile.mkdtemp())
    >>> FolderSpaces({"a": folder}).open("a").memory_db_path.name
    'memory.sqlite3'
    >>> [p.id for p in FolderSpaces({"a": folder}).list_projects()]
    ['a']

    Args:
        folders: 등록 id → 폴더.
        archived: 보관된(켜지지 않은) 등록 id.
    """

    def __init__(self, folders: Mapping[str, Path], archived: Collection[str] = ()) -> None:
        self.folders = dict(folders)
        self.archived = set(archived)

    def list_projects(self) -> list[ListedProject]:
        """등록 목록(id 순, 보관 포함)."""
        return [ListedProject(pid, pid in self.archived) for pid in sorted(self.folders)]

    def open(self, project_id: str) -> SpaceLike:
        try:
            folder = self.folders[project_id]
        except KeyError:
            raise LookupError(project_id) from None
        return open_space(folder)


def folder_spaces_module(
    folders: Mapping[str, Path] | None = None,
    module_id: str = FOLDER_SPACES_ID,
    *,
    archived: Collection[str] = (),
    listing: bool = True,
) -> Module:
    """``projects.spaces``(폴더 목록) 제공 모듈.

    Args:
        folders: 등록 id → 폴더.
        module_id: 모듈 id.
        archived: 보관된 등록 id(``projects.lookup`` 목록의 ``archived``).
        listing: 거짓이면 ``projects.lookup``을 주지 않는다(등록 목록 없는 조립).
    """
    spaces = FolderSpaces(folders or {}, archived)
    provides = (PROJECTS_SPACES, PROJECTS_LOOKUP) if listing else (PROJECTS_SPACES,)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECTS_SPACES, spaces)
        if listing:
            ctx.provide(PROJECTS_LOOKUP, spaces)
        return ModuleParts()

    return fake_module(module_id, provides=provides, on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(빈 폴더 목록)."""
    return [folder_spaces_module()]


__all__ = [
    "FOLDER_SPACES_ID",
    "FolderSpaces",
    "ListedProject",
    "folder_spaces_module",
    "standalone_modules",
]
