"""mod-i18n assembled alone: REST shape, ETag/304, 404 code, user folders, turning catalogs off.

The module needs no other feature (design §I18N.8). Package catalogs come from the host bundle
(filled by the plugin loader, so ``plugins.disabled`` applies) or, without a bundle, from the
installed entry points.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ErrorCodes
from agent_console_contracts.i18n import I18nInfo, MessageCatalog
from agent_console_i18n import schema_texts
from agent_console_i18n.testing import catalog_entry_point, make_catalog_package, write_catalog
from agent_console_mod_i18n import (
    MESSAGE_CATALOGS_EXTENSION,
    I18nModuleSettings,
    load_plugins,
    module,
    register_catalog_entry_points,
)
from agent_console_mod_i18n.plugins import catalog_registry
from agent_console_modkit import (
    BaseServices,
    ExtensionRegistries,
    ModuleParts,
    ModulesConfig,
    Paths,
    PluginLoadContext,
    PortKey,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

TOKEN = "t" * 32
API = "/api/v1"
WARNINGS: PortKey[Any] = PortKey("server.warnings", multi=True)


def _other_module() -> Any:
    def build(ctx: Any) -> ModuleParts:
        router = APIRouter()

        @router.get("/other")
        def other() -> dict[str, bool]:
            return {"ok": True}

        return ModuleParts(routers=[router])

    return fake_module("other-feature", on_build=build)


@contextmanager
def _client(
    *modules: Any,
    options: dict[str, Any] | None = None,
    registries: Any = None,
    base_dir: Path | None = None,
    disabled: list[str] | None = None,
) -> Iterator[TestClient]:
    paths = Paths(base_dir, base_dir / "ws", base_dir / "state") if base_dir is not None else None
    base = BaseServices(registries=registries, paths=paths)
    config = ModulesConfig(
        options={"mod-i18n": options} if options is not None else {},
        disabled=disabled or [],
    )
    assembly = assemble([module, *modules], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


@pytest.fixture
def plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two importable catalog packages: ``alpha`` (en + ko) and ``beta`` (en only)."""
    root = tmp_path / "site"
    make_catalog_package(
        root,
        "modi18n_demo_alpha",
        {
            "en": {"text": {"저장": "Save", "열기": "Open"}, "codes": {"x.failed": "{n} failed"}},
            "ko": {"codes": {"x.failed": "{n} 실패"}},
        },
    )
    make_catalog_package(root, "modi18n_demo_beta", {"en": {"text": {"열기": "Open it"}}})
    monkeypatch.syspath_prepend(str(root))
    return root


def _entry_points() -> list[importlib.metadata.EntryPoint]:
    return [
        catalog_entry_point("alpha", "modi18n_demo_alpha"),
        catalog_entry_point("beta", "modi18n_demo_beta"),
    ]


def _bundle(*, enabled: frozenset[str] | None = None) -> ExtensionRegistries:
    bundle = ExtensionRegistries()
    registry = catalog_registry(bundle)
    assert registry is not None
    register_catalog_entry_points(registry, enabled=enabled, entry_points=_entry_points())
    return bundle


def test_alone_serves_info_and_catalog(plugin_root: Path) -> None:
    with _client(registries=_bundle()) as client:
        info = I18nInfo.model_validate(client.get(f"{API}/i18n").json())
        assert (info.default_language, info.fallback_language) == ("en", "en")
        rows = {row.code: row for row in info.languages}
        assert rows["en"].sources == ["alpha", "beta"]
        # ko is the default source language: its texts are the keys, so only codes count (R10.9).
        assert (rows["en"].complete, rows["ko"].complete, rows["ko"].missing) == (True, True, 0)
        reply = client.get(f"{API}/i18n/en-US")
        assert reply.status_code == 200
        body = MessageCatalog.model_validate(reply.json())
        assert body.language == "en"
        assert body.text == {"저장": "Save", "열기": "Open it"}  # beta comes later and wins
        assert body.codes == {"x.failed": "{n} failed"}
        assert reply.headers["ETag"].startswith('"')
        assert reply.headers["Cache-Control"] == "no-cache"


def test_etag_answers_if_none_match_with_304(plugin_root: Path) -> None:
    with _client(registries=_bundle()) as client:
        tag = client.get(f"{API}/i18n/en").headers["ETag"]
        assert client.get(f"{API}/i18n/en", headers={"If-None-Match": tag}).status_code == 304
        weak = client.get(f"{API}/i18n/en", headers={"If-None-Match": f'"other", W/{tag}'})
        assert weak.status_code == 304
        assert client.get(f"{API}/i18n/en", headers={"If-None-Match": '"x"'}).status_code == 200
        assert client.get(f"{API}/i18n/ko").headers["ETag"] != tag


def test_unknown_language_is_404_with_code(plugin_root: Path) -> None:
    with _client(registries=_bundle()) as client:
        reply = client.get(f"{API}/i18n/fr")
        assert reply.status_code == 404
        body = reply.json()["error"]
        assert body["code"] == ErrorCodes.I18N_UNKNOWN_LANGUAGE
        assert body["details"] == {"language": "fr", "available": ["en", "ko"]}


def test_user_folder_overrides_package_text_relative_to_settings_folder(
    plugin_root: Path, tmp_path: Path
) -> None:
    write_catalog(tmp_path / "my-locales", "en", text={"저장": "Store"})
    write_catalog(tmp_path / "my-locales", "de", text={"저장": "Speichern"})
    with _client(
        registries=_bundle(), base_dir=tmp_path, options={"catalog_dirs": ["my-locales"]}
    ) as client:
        en = client.get(f"{API}/i18n/en").json()
        assert en["text"]["저장"] == "Store"
        assert en["text"]["열기"] == "Open it"
        info = client.get(f"{API}/i18n").json()
        rows = {row["code"]: row for row in info["languages"]}
        assert rows["en"]["sources"] == ["alpha", "beta", "my-locales"]
        assert rows["de"]["sources"] == ["my-locales"]
        assert rows["de"]["complete"] is False


def test_disabled_catalogs_setting_leaves_package_out(plugin_root: Path) -> None:
    with _client(registries=_bundle(), options={"disabled_catalogs": ["beta"]}) as client:
        en = client.get(f"{API}/i18n/en").json()
        assert en["text"]["열기"] == "Open"
        rows = {row["code"]: row for row in client.get(f"{API}/i18n").json()["languages"]}
        assert rows["en"]["sources"] == ["alpha"]


def test_plugins_disabled_leaves_package_out_through_the_loader(plugin_root: Path) -> None:
    bundle = ExtensionRegistries()
    installed = frozenset(ep.name for ep in _entry_points())
    ctx = PluginLoadContext(
        registries=bundle, enabled=installed - {"alpha"}, disabled=frozenset({"alpha"})
    )
    registry = catalog_registry(bundle)
    assert registry is not None
    reports = register_catalog_entry_points(
        registry, enabled=ctx.enabled, entry_points=_entry_points()
    )
    assert [(r.key, r.status) for r in reports] == [("alpha", "skipped"), ("beta", "loaded")]
    with _client(registries=bundle) as client:
        rows = {row["code"]: row for row in client.get(f"{API}/i18n").json()["languages"]}
        assert rows["en"]["sources"] == ["beta"]
        assert "ko" not in rows  # only alpha had ko


def test_loader_registers_installed_entry_points_without_importing() -> None:
    bundle = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=bundle))
    groups = {group for group, _ in reports}
    assert groups <= {MESSAGE_CATALOGS_EXTENSION}
    names = {r.key for _, r in reports if r.status == "loaded"}
    assert "ac-mod-i18n" in names  # this package's own catalog
    registry = catalog_registry(bundle)
    assert registry is not None
    with pytest.raises(TypeError):
        registry.register("bad", "not an entry point")  # type: ignore[arg-type]


def test_import_failure_is_a_server_warning(plugin_root: Path) -> None:
    bundle = ExtensionRegistries()
    registry = catalog_registry(bundle)
    assert registry is not None
    register_catalog_entry_points(
        registry,
        entry_points=[*_entry_points(), catalog_entry_point("gone", "modi18n_demo_missing")],
    )
    assembly = assemble([module], ModulesConfig(), base=BaseServices(registries=bundle))
    issues = [issue for source in assembly.ports(WARNINGS) for issue in source()]
    assert [(i.code, i.details.get("source")) for i in issues] == [
        ("i18n.source_unavailable", "gone")
    ]
    with _client(registries=bundle) as client:
        assert client.get(f"{API}/i18n/en").status_code == 200


def test_turning_the_module_off_removes_only_its_routes(plugin_root: Path) -> None:
    with _client(_other_module(), registries=_bundle(), disabled=["mod-i18n"]) as client:
        assert client.get(f"{API}/i18n").status_code == 404
        assert client.get(f"{API}/other").status_code == 200
        modules = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert modules["mod-i18n"]["state"] == "disabled"


def test_no_catalogs_is_an_empty_list() -> None:
    with _client(registries=ExtensionRegistries()) as client:
        assert client.get(f"{API}/i18n").json() == {
            "languages": [],
            "default_language": "en",
            "fallback_language": "en",
            "source_language": "ko",
        }
        assert client.get(f"{API}/i18n/en").status_code == 404


def test_source_language_setting_reaches_info() -> None:
    """I-18: the server source language (default ``ko``) is in ``GET /i18n``; null = unknown."""
    assert I18nModuleSettings().source_language == "ko"
    for given, expected in (("EN", "en"), (None, None), ("", None)):
        options = {"source_language": given}
        with _client(registries=ExtensionRegistries(), options=options) as client:
            info = I18nInfo.model_validate(client.get(f"{API}/i18n").json())
            assert info.source_language == expected
    with pytest.raises(ValueError, match="language tag"):
        I18nModuleSettings.model_validate({"source_language": "not a language"})


def test_source_language_null_counts_texts_again() -> None:
    with _client(registries=_bundle(), options={"source_language": None}) as client:
        info = I18nInfo.model_validate(client.get(f"{API}/i18n").json())
        ko = next(row for row in info.languages if row.code == "ko")
        assert (ko.complete, ko.missing) == (False, 2)


def test_without_a_bundle_reads_installed_entry_points() -> None:
    with _client(registries=None) as client:
        rows = {row["code"]: row for row in client.get(f"{API}/i18n").json()["languages"]}
        assert "ac-mod-i18n" in rows["en"]["sources"]
        en = client.get(f"{API}/i18n/en").json()
        assert en["text"][module.descriptor.title] == "Language"


def test_settings_normalize_and_reject_language_codes() -> None:
    cfg = I18nModuleSettings.model_validate(
        {"default_language": "EN_us", "fallback_language": "ko"}
    )
    assert (cfg.default_language, cfg.fallback_language) == ("en-US", "ko")
    with pytest.raises(ValueError, match="language tag"):
        I18nModuleSettings.model_validate({"default_language": "not a language"})
    with pytest.raises(ValueError, match="Extra inputs"):
        I18nModuleSettings.model_validate({"languages": ["en"]})


def test_own_english_catalog_covers_module_text() -> None:
    """This package's ``locales/en.json`` translates every Korean string it shows."""
    path = Path(__file__).parents[1] / "src" / "agent_console_mod_i18n" / "locales" / "en.json"
    text = json.loads(path.read_text(encoding="utf-8"))["text"]
    shown = [
        module.descriptor.title,
        module.descriptor.description,
        *schema_texts(I18nModuleSettings.model_json_schema()),
    ]
    korean = [s for s in shown if any("가" <= ch <= "힣" for ch in s)]
    assert korean
    assert [s for s in korean if s not in text] == []
    assert [k for k in text if k not in korean] == []
