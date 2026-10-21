"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, 3R.16): 사용량 출처.

호스트 레지스트리 묶음의 ``usage_sources`` 확장에 검사기를 붙이고 entry point 출처를 로드한다.
"""

from __future__ import annotations

from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport
from agent_console_usage import USAGE_SOURCES_EXTENSION, as_usage_source, load_usage_sources

REPORT_GROUP = "usage_sources"
"""보고 그룹 이름."""


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """사용량 출처 entry point를 묶음의 ``usage_sources`` 확장에 로드한다."""
    registry = ctx.registries.extension(USAGE_SOURCES_EXTENSION, validator=as_usage_source)
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    return [(REPORT_GROUP, r) for r in load_usage_sources(registry, enabled=enabled)]


__all__ = ["REPORT_GROUP", "load_plugins"]
