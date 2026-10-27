"""X23 프로필 플러그인 로더(가짜 entry point)와 병합에서의 origin."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from agent_console_architecture import (
    ARCHITECTURE_PROFILES_GROUP,
    load_profile_plugins,
    merge_profiles,
    new_profile_registry,
    plugin_sources,
)

_PLUGIN = """
def profiles():
    return {"plug": {"title": "플러그인 프로필", "cells": {"c": {}}}}

WRAPPED = {"profiles": {"wrapped": {"title": "W"}}}

def broken():
    return {"bad": {"cells": 3}}

NOT_A_MAP = 3
"""


@pytest.fixture
def plugin_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    name = f"arch_plugin_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{name}.py").write_text(_PLUGIN, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return name


def _ep(name: str, value: str, group: str = ARCHITECTURE_PROFILES_GROUP) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=group)


def test_load_profile_plugins(plugin_module: str) -> None:
    registry = new_profile_registry()
    reports = load_profile_plugins(
        registry,
        entry_points=[
            _ep("one", f"{plugin_module}:profiles"),
            _ep("two", f"{plugin_module}:WRAPPED"),
            _ep("bad", f"{plugin_module}:broken"),
            _ep("odd", f"{plugin_module}:NOT_A_MAP"),
            _ep("missing", "no_such_module_xyz:thing"),
            _ep("other", f"{plugin_module}:profiles", group="something.else"),
        ],
    )
    assert [(r.key, r.status) for r in reports] == [
        ("bad", "failed"),
        ("missing", "failed"),
        ("odd", "failed"),
        ("one", "loaded"),
        ("two", "loaded"),
    ]
    sources = plugin_sources(registry)
    assert [(s.origin, list(s.profiles)) for s in sources] == [
        ("plugin:one", ["plug"]),
        ("plugin:two", ["wrapped"]),
    ]
    catalog = merge_profiles({}, sources, None)
    assert [(e.id, e.origin) for e in catalog.entries.values()] == [
        ("plug", "plugin:one"),
        ("wrapped", "plugin:two"),
    ]


def test_enabled_filter(plugin_module: str) -> None:
    registry = new_profile_registry()
    reports = load_profile_plugins(
        registry,
        enabled={"two"},
        entry_points=[
            _ep("one", f"{plugin_module}:profiles"),
            _ep("two", f"{plugin_module}:WRAPPED"),
        ],
    )
    assert [(r.key, r.status) for r in reports] == [("one", "skipped"), ("two", "loaded")]


def test_no_installed_plugins_is_fine() -> None:
    registry = new_profile_registry()
    load_profile_plugins(registry)  # 설치된 entry point(없을 수 있음)
    assert all(s.origin.startswith("plugin:") for s in plugin_sources(registry))
