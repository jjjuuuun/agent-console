import sys
from pathlib import Path

import pytest

from agent_console_i18n import (
    MESSAGE_CATALOGS_GROUP,
    folder_catalogs,
    load_catalog_folder,
    package_catalogs,
)
from agent_console_i18n.testing import (
    catalog_entry_point,
    make_catalog_package,
    make_distribution,
    write_catalog,
)


def test_folder_reads_json_files_in_name_order(tmp_path: Path) -> None:
    write_catalog(tmp_path, "ko", text={"a": "가"})
    write_catalog(tmp_path, "en", text={"a": "A"})
    (tmp_path / "README.md").write_text("not a catalog", encoding="utf-8")
    (tmp_path / ".hidden.json").write_text("{", encoding="utf-8")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    load = load_catalog_folder(tmp_path, source="mine", origin="folder")
    assert [c.language for c in load.catalogs] == ["en", "ko"]
    assert all(c.origin == "folder" and c.source == "mine" for c in load.catalogs)
    assert [(i.code, i.language) for i in load.issues] == [("i18n.catalog_unreadable", "broken")]


def test_missing_folder_is_an_issue(tmp_path: Path) -> None:
    load = load_catalog_folder(tmp_path / "nope", source="mine")
    assert load.catalogs == ()
    assert [i.code for i in load.issues] == ["i18n.locales_missing"]


def test_folder_catalogs_resolves_relative_to_base_dir(tmp_path: Path) -> None:
    write_catalog(tmp_path / "conf" / "lang", "fr", text={"저장": "Enregistrer"})
    load = folder_catalogs(["lang"], base_dir=tmp_path / "conf")
    assert [(c.language, c.source) for c in load.catalogs] == [("fr", "lang")]


def test_package_catalogs_with_injected_entry_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    make_catalog_package(tmp_path, "i18n_demo_b", {"en": {"text": {"x": "B"}}})
    make_catalog_package(tmp_path, "i18n_demo_a.sub", {"en": {"text": {"x": "A"}}})
    make_catalog_package(tmp_path, "i18n_demo_off", {"en": {"text": {"x": "OFF"}}})
    (tmp_path / "i18n_demo_empty").mkdir()
    (tmp_path / "i18n_demo_empty" / "__init__.py").touch()
    eps = [
        catalog_entry_point("zeta", "i18n_demo_b"),
        catalog_entry_point("alpha", "i18n_demo_a.sub:ignored_attr"),
        catalog_entry_point("off", "i18n_demo_off"),
        catalog_entry_point("gone", "i18n_demo_does_not_exist"),
        catalog_entry_point("empty", "i18n_demo_empty"),
        catalog_entry_point("other-group", "i18n_demo_b", group="something.else"),
    ]
    load = package_catalogs(entry_points=eps, disabled=["off"])
    assert [(c.source, c.text["x"]) for c in load.catalogs] == [("alpha", "A"), ("zeta", "B")]
    assert all(c.origin == "package" for c in load.catalogs)
    assert load.skipped_sources == ("off",)
    assert [(i.code, i.source) for i in load.issues] == [
        ("i18n.locales_missing", "empty"),
        ("i18n.source_unavailable", "gone"),
    ]


def test_package_catalogs_finds_installed_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_catalog_package(tmp_path, "i18n_demo_dist", {"de": {"codes": {"x.y": "Fehler {n}"}}})
    make_distribution(tmp_path, "i18n-demo-dist", {"i18n-demo": "i18n_demo_dist"})
    monkeypatch.syspath_prepend(str(tmp_path))
    load = package_catalogs()
    mine = [c for c in load.catalogs if c.source == "i18n-demo"]
    assert [(c.language, dict(c.codes)) for c in mine] == [("de", {"x.y": "Fehler {n}"})]
    assert MESSAGE_CATALOGS_GROUP == "agent_console.message_catalogs"
    assert "i18n_demo_dist" in sys.modules
