"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, 3R.16): 가져오기 출처.

호스트 레지스트리 묶음의 ``import_sources`` 확장에 검사기를 붙이고 entry point 출처 공장을 로드한다.
"""

from __future__ import annotations

from agent_console_imports import (
    IMPORT_SOURCES_EXTENSION,
    as_import_source_factory,
    load_import_source_factories,
)
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport

REPORT_GROUP = "import_sources"
"""보고 그룹 이름."""


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """가져오기 출처 공장 entry point를 묶음의 ``import_sources`` 확장에 로드한다."""
    registry = ctx.registries.extension(
        IMPORT_SOURCES_EXTENSION, validator=as_import_source_factory
    )
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [(REPORT_GROUP, r) for r in load_import_source_factories(registry, enabled=enabled)]


__all__ = ["REPORT_GROUP", "load_plugins"]
