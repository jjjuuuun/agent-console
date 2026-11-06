"""단독 실행·테스트용 부품(공개). 실제 위키 모듈이 아니다.

- ``memory_repository``: 메모리 페이지·기록·검색 색인으로 만든 위키 저장소 하나(패키지 기본 문법).
- ``StaticWikiService``: ``wiki.service`` 모양의 작은 구현(공간 이름 → 위키 id → 대상 고정,
  ``notify`` 호출을 ``notices``에 모은다). 통합 서버에서는 ``mod-wiki``가 대신한다.
- ``wiki_service_module``: 위 서비스를 ``wiki.service``로 주는 모듈. 단독 실행
  ``python -m agent_console_link_wiki_runs``가 ``--with`` 없이 실행되면 이것을 붙인다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_wiki import (
    EffectiveWikiRules,
    InMemoryWikiHistory,
    ScanSearchIndex,
    WikiRepository,
    WikiToolTarget,
    compile_syntax,
    effective_syntax,
)
from agent_console_wiki.testing import MemoryWikiPages

from .ports import WIKI_SERVICE

WIKI_SERVICE_ID = "wiki-service"


def memory_repository(
    wiki_id: str,
    *,
    rules: EffectiveWikiRules | None = None,
    files: Mapping[str, str | bytes] | None = None,
) -> WikiRepository:
    """메모리 위키 저장소(파일·기록·검색 모두 메모리, 패키지 기본 문법).

    >>> repo = memory_repository("notes", files={"a.md": "# A"})
    >>> repo.current("a").text
    '# A'
    """
    return WikiRepository(
        MemoryWikiPages(files),
        wiki_id=wiki_id,
        syntax=compile_syntax(effective_syntax()),
        rules=rules,
        history=InMemoryWikiHistory(),
        search=ScanSearchIndex(),
    )


@dataclass(frozen=True)
class Notice:
    """``notify`` 호출 하나."""

    space: str | None
    wiki_id: str
    paths: tuple[str, ...]
    deleted: bool
    external: bool


class StaticWikiService:
    """``wiki.service`` 모양(이 연동이 쓰는 부분).

    Args:
        spaces: 공간 이름(None = 단독 공간) → 위키 id → 대상(``WikiToolTarget`` 또는
            ``WikiRepository``). 표에 없는 공간은 ``LookupError``.

    >>> service = StaticWikiService({None: {"notes": memory_repository("notes")}})
    >>> service.wiki_ids(None), list(service.tool_targets(None))
    (['notes'], ['notes'])
    """

    def __init__(
        self,
        spaces: Mapping[str | None, Mapping[str, WikiToolTarget | WikiRepository]] | None = None,
    ) -> None:
        self.spaces: dict[str | None, dict[str, WikiToolTarget]] = {
            space: {
                wiki: t if isinstance(t, WikiToolTarget) else WikiToolTarget(t)
                for wiki, t in table.items()
            }
            for space, table in (spaces or {}).items()
        }
        self.notices: list[Notice] = []

    def _space(self, space: str | None) -> dict[str, WikiToolTarget]:
        try:
            return self.spaces[space or None]
        except KeyError:
            raise LookupError(space) from None

    def wiki_ids(self, space: str | None) -> list[str]:
        """그 공간의 위키 id(정렬)."""
        return sorted(self._space(space))

    def tool_targets(self, space: str | None) -> dict[str, WikiToolTarget]:
        """그 공간의 위키 → 도구 대상."""
        return dict(self._space(space))

    def repository(self, space: str | None, wiki_id: str) -> WikiRepository:
        """그 공간 위키 하나의 저장소(없으면 ``LookupError``)."""
        try:
            return self._space(space)[wiki_id].repository
        except KeyError:
            raise LookupError(wiki_id) from None

    def notify(
        self,
        space: str | None,
        wiki_id: str,
        paths: Sequence[str] = (),
        *,
        deleted: bool = False,
        external: bool = False,
    ) -> None:
        """호출을 ``notices``에 남긴다."""
        self.notices.append(Notice(space, wiki_id, tuple(paths), deleted, external))


def wiki_service_module(service: Any = None, module_id: str = WIKI_SERVICE_ID) -> Module:
    """``wiki.service`` 제공 모듈(없으면 빈 단독 공간 하나인 ``StaticWikiService``)."""
    found = service if service is not None else StaticWikiService({None: {}})

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(WIKI_SERVICE, found)
        return ModuleParts()

    return fake_module(module_id, provides=(WIKI_SERVICE,), on_build=build)


def standalone_modules() -> list[Module]:
    """``--with`` 없는 단독 실행에 붙일 모듈(위키 서비스 대역)."""
    return [wiki_service_module()]


__all__ = [
    "WIKI_SERVICE_ID",
    "Notice",
    "StaticWikiService",
    "memory_repository",
    "standalone_modules",
    "wiki_service_module",
]
