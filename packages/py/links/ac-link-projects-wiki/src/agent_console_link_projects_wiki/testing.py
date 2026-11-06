"""단독 실행·테스트용 모듈(공개).

``folder_spaces_module``: ``projects.spaces``를 폴더 목록(등록 id → 폴더)으로 주는 작은 모듈. 통합
서버에서는 ``mod-projects``가 대신한다. 공간은 ``agent_console_project_space.testing.FolderSpaces``
(실제 ``open_space``, 아무것도 만들지 않는다)로 연다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_project_space.testing import FolderSpaces

from .ports import PROJECTS_SPACES

FOLDER_SPACES_ID = "folder-spaces"


def folder_spaces_module(
    folders: Mapping[str, Path] | None = None,
    module_id: str = FOLDER_SPACES_ID,
    **options: Any,
) -> Module:
    """``projects.spaces``(폴더 목록) 제공 모듈. ``options``는 ``open_space``에 그대로."""
    spaces = FolderSpaces(folders or {}, **options)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECTS_SPACES, spaces)
        return ModuleParts()

    return fake_module(module_id, provides=(PROJECTS_SPACES,), on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(빈 폴더 목록)."""
    return [folder_spaces_module()]


__all__ = ["FOLDER_SPACES_ID", "FolderSpaces", "folder_spaces_module", "standalone_modules"]
