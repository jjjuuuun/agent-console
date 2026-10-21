"""호스트 기본 서비스 확장 지점(3R.16): 레지스트리 묶음 공장·플러그인 로더·DB 공장·비밀 해석."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path

from agent_console_modkit import (
    HOST_DATABASE_GROUP,
    HOST_EXTENSIONS_REPORT_GROUP,
    HOST_PLUGIN_LOADERS_GROUP,
    HOST_REGISTRIES_GROUP,
    PLUGIN_MODULES_REPORT_GROUP,
    SECRET_PROVIDERS_REGISTRY,
    ExtensionRegistries,
    Paths,
    env_secret_lookup,
    load_host_plugins,
    open_host_database,
    secret_lookup,
    secret_providers_of,
)
from agent_console_modkit.testing import (
    EXAMPLE_EXTENSION,
    EXAMPLE_KEY,
    RecordingDatabase,
)

TESTING = "agent_console_modkit.testing"


def _ep(name: str, value: str, group: str) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=group)


def _paths(tmp_path: Path) -> Paths:
    return Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "ws" / ".state")


def test_no_extensions_gives_default_bundle(tmp_path: Path) -> None:
    plugins = load_host_plugins(entry_points=[], paths=_paths(tmp_path))
    assert isinstance(plugins.registries, ExtensionRegistries)
    assert plugins.reports == []
    assert plugins.secret_providers == []


def test_loader_registers_into_bundle_with_context(tmp_path: Path) -> None:
    eps = [_ep("ex", f"{TESTING}:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)]
    plugins = load_host_plugins(
        entry_points=eps, paths=_paths(tmp_path), options={EXAMPLE_KEY: {"a": 1}}
    )
    item = plugins.registries.extension(EXAMPLE_EXTENSION).get(EXAMPLE_KEY)
    assert item == {"workspace": str(tmp_path / "ws"), "options": {"a": 1}}
    assert [(g, r.status) for g, r in plugins.reports] == [(EXAMPLE_EXTENSION, "loaded")]


def test_enabled_is_passed_to_loaders() -> None:
    eps = [_ep("ex", f"{TESTING}:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)]
    plugins = load_host_plugins(entry_points=eps, enabled=[])
    assert [r.status for _, r in plugins.reports] == ["skipped"]
    assert EXAMPLE_KEY not in plugins.registries.extension(EXAMPLE_EXTENSION)


def test_registries_factory_first_by_name_and_failures_are_reports() -> None:
    eps = [
        _ep("b", "agent_console_modkit:ExtensionRegistries", HOST_REGISTRIES_GROUP),
        _ep("a", "agent_console_modkit:ExtensionRegistries", HOST_REGISTRIES_GROUP),
        _ep("broken", "no_such_module_xyz:load", HOST_PLUGIN_LOADERS_GROUP),
    ]
    plugins = load_host_plugins(entry_points=eps)
    assert isinstance(plugins.registries, ExtensionRegistries)
    statuses = {(g, r.key): r.status for g, r in plugins.reports}
    assert statuses[(HOST_EXTENSIONS_REPORT_GROUP, "b")] == "skipped"
    assert statuses[(HOST_EXTENSIONS_REPORT_GROUP, "broken")] == "failed"


def test_bad_bundle_falls_back_to_default() -> None:
    eps = [_ep("x", "builtins:dict", HOST_REGISTRIES_GROUP)]  # extension()·all()이 없다
    plugins = load_host_plugins(entry_points=eps)
    assert isinstance(plugins.registries, ExtensionRegistries)
    assert [r.status for _, r in plugins.reports] == ["failed"]


def test_register_plugins_run_after_loaders() -> None:
    eps = [_ep("ex", f"{TESTING}:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)]
    plugins = load_host_plugins(entry_points=eps, modules=["no_such_module_xyz:register"])
    groups = [g for g, _ in plugins.reports]
    assert groups == [EXAMPLE_EXTENSION, PLUGIN_MODULES_REPORT_GROUP]
    assert plugins.reports[-1][1].status == "failed"


def test_open_host_database(tmp_path: Path) -> None:
    eps = [_ep("rec", f"{TESTING}:open_recording_database", HOST_DATABASE_GROUP)]
    db = open_host_database(tmp_path / "x.db", entry_points=eps)
    assert isinstance(db, RecordingDatabase)
    assert db.path == tmp_path / "x.db"
    assert open_host_database(tmp_path / "x.db", entry_points=[]) is None


class _Provider:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get_secret(self, name: str) -> str | None:
        return self.values.get(name)


def test_secret_chain_env_first_then_providers() -> None:
    bundle = ExtensionRegistries()
    bundle.extension(SECRET_PROVIDERS_REGISTRY).register("p", _Provider({"a": "P", "b": "PB"}))
    providers = secret_providers_of(bundle)
    assert len(providers) == 1
    lookup = secret_lookup(env_secret_lookup({"X_A": "E", "X_c": "low"}, prefix="X_"), providers)
    assert lookup("a") == "E"  # 대문자 키
    assert lookup("c") == "low"
    assert lookup("b") == "PB"
    assert lookup("none") is None
