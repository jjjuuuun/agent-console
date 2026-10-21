"""단독 실행·테스트용 모듈(공개).

``local_sources_module``: ``definitions.lookup``(워크스페이스 파일 저장소)과 ``resources.types``
(entry point로 설치된 리소스 종류)를 주는 작은 모듈. 단독 실행이 ``--with`` 없이 실행되면 이것을
붙인다(통합 서버에서는 ``mod-definitions``·``mod-resources``가 대신한다).
"""

from __future__ import annotations

from pathlib import Path

from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_resources import load_resource_types, new_resource_types
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

from .ports import DEFINITIONS_LOOKUP, RESOURCE_TYPES

LOCAL_SOURCES_ID = "local-definitions-resources"
DEFAULT_WORKSPACE = Path(".agent-console")


def local_sources_module(
    module_id: str = LOCAL_SOURCES_ID, *, workspace: Path | None = None
) -> Module:
    """``definitions.lookup``·``resources.types`` 제공 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        root = workspace or (ctx.paths.workspace if ctx.paths is not None else DEFAULT_WORKSPACE)
        types = new_resource_types()
        load_resource_types(types)
        ctx.provide(DEFINITIONS_LOOKUP, FileDefinitionStore(root, DEFAULT_KINDS))
        ctx.provide(RESOURCE_TYPES, types)
        return ModuleParts()

    return fake_module(
        module_id, kind="testing", provides=[DEFINITIONS_LOOKUP, RESOURCE_TYPES], on_build=build
    )


__all__ = ["LOCAL_SOURCES_ID", "local_sources_module"]
