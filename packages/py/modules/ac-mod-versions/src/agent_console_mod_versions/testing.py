"""단독 실행·테스트용 모듈(공개). 다른 패키지의 테스트도 이것을 쓴다.

``local_definitions_module``: ``definitions.store``를 워크스페이스 폴더의 파일 저장소
(``FileDefinitionStore``, 버전 기록은 메모리)로 주고, 저장마다 ``definitions.saved``를 발행하는
작은 모듈. 단독 실행 ``python -m agent_console_mod_versions``가 ``--with`` 없이 실행되면 이것을
붙인다(design modularity §3.9.4). 통합 서버에서는 정의 모듈이 대신한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    DEFAULT_KINDS,
    FileDefinitionStore,
    InMemoryVersionRepository,
    ObservedVersionRepository,
)

from .ports import DEFINITIONS_SAVED, DEFINITIONS_STORE

LOCAL_DEFINITIONS_ID = "local-definitions"
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
    """``definitions.store`` 제공 + ``definitions.saved`` 발행 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)

        def publish(kind: str, item_id: str, version_hash: str) -> None:
            ctx.publish(DEFINITIONS_SAVED, Saved(kind, item_id, version_hash))

        versions = ObservedVersionRepository(InMemoryVersionRepository(), publish)
        ctx.provide(DEFINITIONS_STORE, FileDefinitionStore(root, DEFAULT_KINDS, versions=versions))
        return ModuleParts()

    return fake_module(module_id, kind="testing", provides=[DEFINITIONS_STORE], on_build=build)


__all__ = ["LOCAL_DEFINITIONS_ID", "Saved", "local_definitions_module"]
