"""단독 실행·테스트용 모듈(공개).

``memory_projects_module``: ``projects.lookup``을 메모리 목록으로 주는 작은 모듈. 단독 실행
``python -m agent_console_link_projects_runs``가 ``--with`` 없이 실행되면 이것을 붙인다(통합
서버에서는 ``mod-projects``가 대신한다).
"""

from __future__ import annotations

from collections.abc import Iterable

from agent_console_contracts import Project
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import PROJECTS_LOOKUP

MEMORY_PROJECTS_ID = "memory-projects"


class MemoryProjects:
    """``projects.lookup`` 메모리 구현.

    >>> MemoryProjects([Project(id="app", name="App")]).get_project("app").name
    'App'
    """

    def __init__(self, projects: Iterable[Project] = ()) -> None:
        self._items = {p.id: p for p in projects}

    def get_project(self, project_id: str) -> Project | None:
        return self._items.get(project_id)

    def list_projects(self) -> list[Project]:
        return [self._items[k] for k in sorted(self._items)]


def memory_projects_module(
    projects: Iterable[Project] = (), module_id: str = MEMORY_PROJECTS_ID
) -> Module:
    """``projects.lookup``(메모리) 제공 모듈."""
    lookup = MemoryProjects(projects)

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(PROJECTS_LOOKUP, lookup)
        return ModuleParts()

    return fake_module(module_id, provides=(PROJECTS_LOOKUP,), on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(빈 메모리 프로젝트)."""
    return [memory_projects_module()]


__all__ = ["MEMORY_PROJECTS_ID", "MemoryProjects", "memory_projects_module", "standalone_modules"]
