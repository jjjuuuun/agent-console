"""호스트 플러그인 로더(3R.16): 리소스 종류(entry point + 워크스페이스 선언형)."""

from __future__ import annotations

from pathlib import Path

from agent_console_mod_resources.plugins import REPORT_GROUP, load_plugins
from agent_console_modkit import ExtensionRegistries, Paths, PluginLoadContext

TYPE_YAML = "id: memo\ntitle: 메모\ncontributes:\n  - slot: notes\n    template: '{name}'\n"


def _paths(tmp_path: Path) -> Paths:
    return Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")


def test_declarative_types_from_workspace(tmp_path: Path) -> None:
    folder = tmp_path / "ws" / "resource-types"
    folder.mkdir(parents=True)
    (folder / "memo.yaml").write_text(TYPE_YAML, encoding="utf-8")
    bundle = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=bundle, paths=_paths(tmp_path)))
    assert {g for g, _ in reports} <= {REPORT_GROUP, f"{REPORT_GROUP}.declarative"}
    assert all(r.ok for _, r in reports), reports
    assert "memo" in bundle.extension("resource_types")


def test_module_options_choose_extension_name(tmp_path: Path) -> None:
    bundle = ExtensionRegistries()
    options = {"mod-resources": {"types_extension": "my_types", "declarative_dir": "kinds"}}
    folder = tmp_path / "ws" / "kinds"
    folder.mkdir(parents=True)
    (folder / "memo.yaml").write_text(TYPE_YAML, encoding="utf-8")
    load_plugins(PluginLoadContext(registries=bundle, paths=_paths(tmp_path), options=options))
    assert "memo" in bundle.extension("my_types")
    assert "memo" not in bundle.extension("resource_types")


def test_bad_options_fall_back_to_defaults() -> None:
    bundle = ExtensionRegistries()
    options = {"mod-resources": {"types_extension": ""}}
    reports = load_plugins(PluginLoadContext(registries=bundle, options=options))
    assert all(g == REPORT_GROUP for g, _ in reports)
