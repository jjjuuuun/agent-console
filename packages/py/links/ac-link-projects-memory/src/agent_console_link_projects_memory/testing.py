"""단독 실행·테스트용 모듈(공개).

``folder_spaces_module``: ``projects.spaces``를 폴더 목록(등록 id → 폴더)으로 주는 작은 모듈. 통합
서버에서는 ``mod-projects``가 대신한다. 실제 ``agent_console_project_space.open_space``로 공간을
연다(메모리 DB 경로는 파일을 만들지 않는다).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_project_space import open_space

from .ports import PROJECTS_SPACES, SpaceLike

FOLDER_SPACES_ID = "folder-spaces"


class FolderSpaces:
    """``projects.spaces`` 폴더 목록 구현.

    >>> import tempfile
    >>> folder = Path(tempfile.mkdtemp())
    >>> FolderSpaces({"a": folder}).open("a").memory_db_path.name
    'memory.sqlite3'
    """

    def __init__(self, folders: Mapping[str, Path]) -> None:
        self.folders = dict(folders)

    def open(self, project_id: str) -> SpaceLike:
        try:
            folder = self.folders[project_id]
        except KeyError:
            raise LookupError(project_id) from None
        return open_space(folder)


def folder_spaces_module(
    folders: Mapping[str, Path] | None = None, module_id: str = FOLDER_SPACES_ID
) -> Module:
    """``projects.spaces``(폴더 목록) 제공 모듈."""
    spaces = FolderSpaces(folders or {})

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECTS_SPACES, spaces)
        return ModuleParts()

    return fake_module(module_id, provides=(PROJECTS_SPACES,), on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(빈 폴더 목록)."""
    return [folder_spaces_module()]


__all__ = ["FOLDER_SPACES_ID", "FolderSpaces", "folder_spaces_module", "standalone_modules"]
