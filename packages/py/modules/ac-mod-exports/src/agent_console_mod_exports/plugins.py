"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, 3R.16): 내보내기 형식.

호스트 레지스트리 묶음의 ``exporters`` 확장에 검사기를 붙이고 entry point 형식 공장을 로드한다.
"""

from __future__ import annotations

from agent_console_exports import (
    EXPORTERS_EXTENSION,
    as_exporter_factory,
    load_exporter_factories,
)
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport

REPORT_GROUP = "exporters"
"""보고 그룹 이름."""


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """내보내기 형식 공장 entry point를 묶음의 ``exporters`` 확장에 로드한다."""
    registry = ctx.registries.extension(EXPORTERS_EXTENSION, validator=as_exporter_factory)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [(REPORT_GROUP, r) for r in load_exporter_factories(registry, enabled=enabled)]


__all__ = ["REPORT_GROUP", "load_plugins"]
