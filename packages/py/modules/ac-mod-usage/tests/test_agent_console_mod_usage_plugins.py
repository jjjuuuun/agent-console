"""호스트 플러그인 로더(3R.16): 묶음의 확장에 entry point를 로드한다."""

from __future__ import annotations

from agent_console_mod_usage.plugins import REPORT_GROUP, load_plugins
from agent_console_modkit import ExtensionRegistries, PluginLoadContext
from agent_console_usage import USAGE_SOURCES_EXTENSION


def test_loads_into_named_extension() -> None:
    bundle = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=bundle))
    assert all(group == REPORT_GROUP for group, _ in reports)
    assert all(r.ok for _, r in reports)
    registry = bundle.extension(USAGE_SOURCES_EXTENSION)
    assert {r.key for _, r in reports if r.status == "loaded"} == {e.key for e in registry.list()}


def test_enabled_empty_skips_everything() -> None:
    bundle = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=bundle, enabled=frozenset()))
    assert all(r.status == "skipped" for _, r in reports)
    assert len(bundle.extension(USAGE_SOURCES_EXTENSION)) == 0
