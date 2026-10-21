"""호스트 플러그인 로더(entry point ``agent_console.host_plugin_loaders``, 3R.16): 로그 출처·분류기.

호스트 레지스트리 묶음의 ``log_sources``·``log_classifiers`` 확장에 검사기를 붙이고 X5·X6 entry
point를 로드한다. 보고 그룹은 확장 이름과 같다(``log_sources``·``log_classifiers``).
"""

from __future__ import annotations

from typing import Any

from agent_console_logs import (
    LOG_CLASSIFIERS_EXTENSION,
    LOG_SOURCES_EXTENSION,
    LoadReport,
    LogRegistries,
    as_log_classifier,
    as_log_source,
)
from agent_console_modkit import PluginLoadContext

REPORT_GROUPS = (LOG_SOURCES_EXTENSION, LOG_CLASSIFIERS_EXTENSION)
"""보고 그룹 이름."""


def bundle_registries(registries: Any) -> LogRegistries | None:
    """호스트 묶음의 확장으로 만든 ``LogRegistries``(묶음에 ``extension``이 없으면 None)."""
    extension = getattr(registries, "extension", None)
    if not callable(extension):
        return None
    return LogRegistries(
        sources=extension(LOG_SOURCES_EXTENSION, validator=as_log_source),
        classifiers=extension(LOG_CLASSIFIERS_EXTENSION, validator=as_log_classifier),
    )


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """출처·분류기 entry point를 묶음에 로드한다(설정 ``plugins.enabled``로 거른다)."""
    registries = bundle_registries(ctx.registries)
    if registries is None:  # pragma: no cover - 호스트 묶음은 항상 extension이 있다
        return []
    enabled = set(ctx.enabled) if ctx.enabled is not None else None
    reports = registries.load(enabled_sources=enabled, enabled_classifiers=enabled)
    return [(group, r) for group in REPORT_GROUPS for r in reports.get(group, [])]


__all__ = ["REPORT_GROUPS", "bundle_registries", "load_plugins"]
