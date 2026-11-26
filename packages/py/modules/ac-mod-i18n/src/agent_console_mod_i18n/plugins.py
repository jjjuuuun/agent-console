"""Host plugin loader (entry point ``agent_console.host_plugin_loaders``): message catalogs.

The loader registers the entry points of the group ``agent_console.message_catalogs`` in the host
registry bundle under the extension ``message_catalogs`` (key = entry point name, item = the
``EntryPoint`` itself). It does not import the catalog modules: ``agent_console_i18n`` does that
when the module builds, so a module that cannot be imported becomes an
``i18n.source_unavailable`` warning with the same shape in the integrated server and in a
standalone run.

Because the host passes the settings ``plugins.enabled``/``plugins.disabled`` to every loader
(``PluginLoadContext.enabled``), a catalog id written there is skipped like any other plugin name.
The module setting ``disabled_catalogs`` is applied on top of that.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from typing import Any, Final

from agent_console_i18n import MESSAGE_CATALOGS_GROUP
from agent_console_modkit import PluginLoadContext
from agent_console_registry import LoadReport, Registry, excluded_reason

MESSAGE_CATALOGS_EXTENSION: Final = "message_catalogs"
"""Name of the registry extension that holds catalog entry points."""

REPORT_GROUP: Final = MESSAGE_CATALOGS_EXTENSION
"""Report group name (server info plugin list)."""


def as_catalog_entry_point(obj: Any) -> importlib.metadata.EntryPoint:
    """Registry validator: an item must be an ``EntryPoint`` (its value names a module).

    A ``register(registries)`` plugin can add a catalog the same way, with
    ``EntryPoint(name, "my_package", MESSAGE_CATALOGS_GROUP)``.

    Raises:
        TypeError: for any other shape.
    """
    if isinstance(obj, importlib.metadata.EntryPoint):
        return obj
    raise TypeError(f"a message catalog item must be an EntryPoint, not {type(obj).__name__}")


def catalog_registry(registries: Any) -> Registry[importlib.metadata.EntryPoint] | None:
    """The ``message_catalogs`` registry of the host bundle, or None without a bundle."""
    extension = getattr(registries, "extension", None)
    if not callable(extension):
        return None
    found: Registry[importlib.metadata.EntryPoint] = extension(
        MESSAGE_CATALOGS_EXTENSION, validator=as_catalog_entry_point
    )
    return found


def catalog_entry_points(registries: Any) -> list[importlib.metadata.EntryPoint] | None:
    """Catalog entry points the host allowed (registry order), or None without a bundle.

    None means "no host bundle" (a standalone run): the caller reads the installed entry points.
    """
    registry = catalog_registry(registries)
    if registry is None:
        return None
    return [entry.item for entry in registry.list()]


def register_catalog_entry_points(
    registry: Registry[importlib.metadata.EntryPoint],
    *,
    enabled: Iterable[str] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
    group: str = MESSAGE_CATALOGS_GROUP,
) -> list[LoadReport]:
    """Register the installed catalog entry points without importing them.

    Args:
        registry: target registry.
        enabled: names to register (None = all). Others are reported as ``skipped``.
        entry_points: injected entry points for tests (only the matching group is used).
        group: entry point group.

    Returns:
        One report per entry point (name order). A duplicate name is ``failed``.
    """
    found = (
        [ep for ep in entry_points if ep.group == group]
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=group))
    )
    allowed = set(enabled) if enabled is not None else None
    reports: list[LoadReport] = []
    for ep in sorted(found, key=lambda item: (item.name, item.value)):
        source = f"entry_point {group}:{ep.name} ({ep.value})"
        dist = getattr(ep, "dist", None)
        if dist is not None:
            source += f" [{dist.name} {dist.version}]"
        reason = excluded_reason(ep.name, allowed)
        if reason is not None:
            reports.append(LoadReport(source=source, status="skipped", key=ep.name, reason=reason))
            continue
        try:
            registry.register(ep.name, ep, source=source)
        except Exception as exc:
            reports.append(
                LoadReport(
                    source=source,
                    status="failed",
                    key=ep.name,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        reports.append(LoadReport(source=source, status="loaded", key=ep.name, version=1))
    return reports


def load_plugins(ctx: PluginLoadContext) -> list[tuple[str, LoadReport]]:
    """Register the catalog entry points in the bundle's ``message_catalogs`` extension."""
    registry = catalog_registry(ctx.registries)
    if registry is None:  # pragma: no cover - the host always passes a bundle
        return []
    return [
        (REPORT_GROUP, report)
        for report in register_catalog_entry_points(registry, enabled=ctx.enabled)
    ]


__all__ = [
    "MESSAGE_CATALOGS_EXTENSION",
    "REPORT_GROUP",
    "as_catalog_entry_point",
    "catalog_entry_points",
    "catalog_registry",
    "load_plugins",
    "register_catalog_entry_points",
]
