"""단독 실행·테스트용 모듈(공개). 다른 패키지의 테스트도 이것을 쓴다.

- ``local_definitions_module``: ``definitions.lookup``·``definitions.store``를 워크스페이스 폴더의
  파일 저장소(기본 정의 종류, 버전 기록은 메모리)로 주고 저장마다 ``definitions.saved``를 발행한다.
  단독 실행 ``python -m agent_console_mod_projects``가 ``--with`` 없이 실행되면 이것을 붙인다.
  통합 서버에서는 정의 모듈이 대신한다.
- ``references_module``: 주어진 함수를 ``definitions.references``로 주는 모듈(참조 추출 예제).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    DEFAULT_KINDS,
    FileDefinitionStore,
    InMemoryVersionRepository,
    ObservedVersionRepository,
)

from .ports import DEFINITIONS_LOOKUP, DEFINITIONS_REFERENCES, DEFINITIONS_SAVED, DEFINITIONS_STORE

LOCAL_DEFINITIONS_ID = "local-definitions"
REFERENCES_ID = "local-references"
DEFAULT_WORKSPACE = Path(".agent-console")


@dataclass(frozen=True)
class Saved:
    """``definitions.saved`` 항목(``SavedDefinition`` 모양)."""

    kind: str
    id: str
    version_hash: str


def local_definitions_module(
    module_id: str = LOCAL_DEFINITIONS_ID, *, workspace: Path | None = None
) -> Module:
    """``definitions.lookup``·``definitions.store`` 제공 + ``definitions.saved`` 발행 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)

        def publish(kind: str, item_id: str, version_hash: str) -> None:
            ctx.publish(DEFINITIONS_SAVED, Saved(kind, item_id, version_hash))

        versions = ObservedVersionRepository(InMemoryVersionRepository(), publish)
        store = FileDefinitionStore(root, DEFAULT_KINDS, versions=versions)
        ctx.provide(DEFINITIONS_STORE, store)
        ctx.provide(DEFINITIONS_LOOKUP, store)
        return ModuleParts()

    return fake_module(
        module_id,
        kind="testing",
        provides=[DEFINITIONS_STORE, DEFINITIONS_LOOKUP],
        on_build=build,
    )


def references_module(
    references: Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]],
    module_id: str = REFERENCES_ID,
) -> Module:
    """``references``를 ``definitions.references``로 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(DEFINITIONS_REFERENCES, references)
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_REFERENCES], on_build=build)


__all__ = [
    "LOCAL_DEFINITIONS_ID",
    "REFERENCES_ID",
    "Saved",
    "local_definitions_module",
    "references_module",
]
