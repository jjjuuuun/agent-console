"""단독 실행·테스트용 부품(공개).

- ``StaticMemoryService``: ``memory.service`` 모양의 작은 구현(저장소 + 범위 종류 목록 고정).
  통합 서버에서는 ``mod-memory``가 대신한다.
- ``memory_service_module``: 위 서비스를 ``memory.service``로 주는 모듈. 단독 실행
  ``python -m agent_console_link_memory_runs``가 ``--with`` 없이 실행되면 이것을 붙인다.
"""

from __future__ import annotations

from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
)
from agent_console_memory import (
    EventSink,
    InMemoryMemoryStore,
    MemoryStore,
    MemoryToolkit,
    ScopeKindCatalog,
    ToolText,
    WriteBudget,
    merge_scope_kinds,
)
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import MEMORY_SERVICE

MEMORY_SERVICE_ID = "memory-service"


class StaticMemoryService:
    """``memory.service`` 모양(이 연동이 쓰는 부분 + ``store``).

    Args:
        store: 저장소(없으면 새 ``InMemoryMemoryStore``).
        catalog: 범위 종류(없으면 ``ac-memory`` 패키지 기본 데이터).
        max_search_results: 에이전트 검색 결과 상한.

    >>> from agent_console_memory import load_default_scope_kinds
    >>> service = StaticMemoryService()
    >>> service.catalog().ids() == list(load_default_scope_kinds())
    True
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        catalog: ScopeKindCatalog | None = None,
        max_search_results: int = 20,
    ) -> None:
        self.store: MemoryStore = store if store is not None else InMemoryMemoryStore()
        self._catalog = catalog if catalog is not None else merge_scope_kinds()
        self.max_search_results = max_search_results

    def catalog(self) -> ScopeKindCatalog:
        """범위 종류 목록."""
        return self._catalog

    def toolkit(
        self,
        access: MemoryAccessConfig,
        context: MemoryAccessContext,
        *,
        on_event: EventSink | None = None,
        author: MemoryAuthor | None = None,
        write_budget: WriteBudget | None = None,
        text: ToolText | None = None,
    ) -> MemoryToolkit:
        """에이전트 도구 묶음."""
        return MemoryToolkit(
            self.store,
            access=access,
            context=context,
            catalog=self._catalog,
            author=author,
            text=text,
            on_event=on_event,
            write_budget=write_budget,
            max_search_results=self.max_search_results,
        )


def memory_service_module(
    service: StaticMemoryService | None = None, module_id: str = MEMORY_SERVICE_ID
) -> Module:
    """``memory.service``(``StaticMemoryService``) 제공 모듈."""
    found = service if service is not None else StaticMemoryService()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(MEMORY_SERVICE, found)
        return ModuleParts()

    return fake_module(module_id, provides=(MEMORY_SERVICE,), on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(메모리 저장소 서비스)."""
    return [memory_service_module()]


__all__ = [
    "MEMORY_SERVICE_ID",
    "StaticMemoryService",
    "memory_service_module",
    "standalone_modules",
]
