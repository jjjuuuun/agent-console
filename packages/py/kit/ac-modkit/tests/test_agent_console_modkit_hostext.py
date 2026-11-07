"""호스트 기본 서비스 확장 지점(3R.16): 레지스트리 묶음 공장·플러그인 로더·DB 공장·비밀 해석."""

from __future__ import annotations

import sys
import textwrap
import uuid
from collections.abc import Iterator
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from agent_console_modkit import (
    HOST_DATABASE_GROUP,
    HOST_EXTENSIONS_REPORT_GROUP,
    HOST_PLUGIN_LOADERS_GROUP,
    HOST_REGISTRIES_GROUP,
    PLUGIN_MODULES_REPORT_GROUP,
    REASON_PLUGINS_DISABLED,
    REASON_PLUGINS_NOT_ENABLED,
    SECRET_PROVIDERS_REGISTRY,
    ExtensionRegistries,
    Paths,
    PluginLoadContext,
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


# ---------------------------------------------------------------- plugins.disabled

GROUPS = ("test.alpha", "test.beta")
"""두 그룹에 같은 이름(``base``·``extra``)의 플러그인을 둔다."""

LOADER_SOURCE = textwrap.dedent(
    """
    from importlib.metadata import EntryPoint
    from agent_console_registry import load_entry_points

    GROUPS = ("test.alpha", "test.beta")

    def _eps(group):
        return [EntryPoint(name=n, value="builtins:len", group=group) for n in ("base", "extra")]

    def loader(ctx):
        out = []
        for group in GROUPS:
            registry = ctx.registries.extension(group)
            out += [
                (group, r)
                for r in load_entry_points(
                    group, registry, enabled=ctx.enabled, entry_points=_eps(group)
                )
            ]
        return out

    def register(registries):
        registries.extension("test.alpha").register("mod-keep", 1)
        registries.extension("test.alpha").register("extra-mod", 2)
    """
)


@pytest.fixture
def loader_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """두 그룹을 ``ctx.enabled``로 읽는 로더 모듈(tmp_path)."""
    name = f"acmk_disabled_loader_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text(LOADER_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    sys.modules.pop(name, None)


def _eps_for(module: str) -> list[EntryPoint]:
    """로더 entry point + 두 그룹 플러그인 이름(설치된 이름 목록 계산용)."""
    plugins = [_ep(n, "builtins:len", g) for g in GROUPS for n in ("base", "extra")]
    return [_ep("two", f"{module}:loader", HOST_PLUGIN_LOADERS_GROUP), *plugins]


def _status(plugins: object, name: str) -> list[tuple[str, str, str | None]]:
    reports = plugins.reports  # type: ignore[attr-defined]
    return [(g, r.status, r.reason) for g, r in reports if r.key == name]


def test_disabled_skips_one_name_in_every_group(loader_module: str) -> None:
    plugins = load_host_plugins(entry_points=_eps_for(loader_module), disabled=["extra"])
    assert _status(plugins, "base") == [(g, "loaded", None) for g in GROUPS]
    assert _status(plugins, "extra") == [(g, "skipped", REASON_PLUGINS_DISABLED) for g in GROUPS]
    for group in GROUPS:
        registry = plugins.registries.extension(group)
        assert "base" in registry
        assert "extra" not in registry
    assert plugins.warnings == []


def test_disabled_is_removed_from_enabled(loader_module: str) -> None:
    plugins = load_host_plugins(
        entry_points=_eps_for(loader_module), enabled=["base", "extra"], disabled=["extra"]
    )
    assert _status(plugins, "base") == [(g, "loaded", None) for g in GROUPS]
    assert _status(plugins, "extra") == [(g, "skipped", REASON_PLUGINS_DISABLED) for g in GROUPS]


def test_enabled_only_reason_names_enabled(loader_module: str) -> None:
    plugins = load_host_plugins(entry_points=_eps_for(loader_module), enabled=["base"])
    assert _status(plugins, "extra") == [(g, "skipped", REASON_PLUGINS_NOT_ENABLED) for g in GROUPS]


def test_unknown_disabled_name_is_warning(
    loader_module: str, caplog: pytest.LogCaptureFixture
) -> None:
    plugins = load_host_plugins(entry_points=_eps_for(loader_module), disabled=["nope"])
    assert len(plugins.warnings) == 1
    assert "'nope'" in plugins.warnings[0]
    assert "nope" in caplog.text
    assert all(r.status == "loaded" for _, r in plugins.reports)


def test_disabled_applies_to_register_plugins(loader_module: str) -> None:
    plugins = load_host_plugins(
        entry_points=_eps_for(loader_module),
        modules=[f"{loader_module}:register"],
        disabled=["extra-mod"],
    )
    alpha = plugins.registries.extension("test.alpha")
    assert "mod-keep" in alpha
    assert "extra-mod" not in alpha
    assert _status(plugins, "extra-mod") == [
        (PLUGIN_MODULES_REPORT_GROUP, "disabled", REASON_PLUGINS_DISABLED)
    ]
    assert plugins.warnings == []


def test_example_loader_uses_allows_for_non_entry_point_key() -> None:
    eps = [_ep("ex", f"{TESTING}:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)]
    off = load_host_plugins(entry_points=eps, disabled=[EXAMPLE_KEY])
    assert [(r.status, r.reason) for _, r in off.reports] == [("skipped", REASON_PLUGINS_DISABLED)]
    other = load_host_plugins(entry_points=eps, disabled=["something-else"])
    assert [r.status for _, r in other.reports] == ["loaded"]


@pytest.mark.parametrize(
    ("ctx_kwargs", "expected"),
    [
        ({}, True),
        ({"enabled": frozenset({"a"})}, True),
        ({"enabled": frozenset({"b"})}, False),
        ({"enabled": frozenset({"a"}), "disabled": frozenset({"a"})}, False),
        ({"enabled": frozenset({"b"}), "allow_unlisted": True}, True),
        ({"disabled": frozenset({"a"}), "allow_unlisted": True}, False),
    ],
)
def test_context_allows(ctx_kwargs: dict[str, object], expected: bool) -> None:
    ctx = PluginLoadContext(registries=ExtensionRegistries(), **ctx_kwargs)  # type: ignore[arg-type]
    assert ctx.allows("a") is expected


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
