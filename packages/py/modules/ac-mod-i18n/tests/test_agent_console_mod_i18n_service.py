"""I18nService: merge order, language list, catalog bodies, reload, warnings (no HTTP)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_i18n import Catalog, CatalogIssue, CatalogLoad
from agent_console_i18n.testing import write_catalog
from agent_console_mod_i18n import I18nService, UnknownLanguageError, issue_of

PACKAGE = CatalogLoad(
    catalogs=(
        Catalog(
            "en", text={"저장": "Save", "열기": "Open"}, codes={"x.y": "{n} failed"}, source="pkg"
        ),
        Catalog("ko", codes={"x.y": "{n} 실패"}, source="pkg"),
    )
)


def test_user_folder_overrides_package_text(tmp_path: Path) -> None:
    write_catalog(tmp_path / "mine", "en", text={"저장": "Store"})
    service = I18nService(packages=PACKAGE, folders=["mine"], base_dir=tmp_path)
    body = service.catalog("en").catalog
    assert body.text == {"저장": "Store", "열기": "Open"}
    assert body.codes == {"x.y": "{n} failed"}
    assert service.info().languages[0].sources == ["pkg", "mine"]


def test_info_lists_languages_with_completeness_against_fallback(tmp_path: Path) -> None:
    write_catalog(tmp_path, "de", text={"저장": "Speichern", "열기": ""})
    service = I18nService(
        packages=PACKAGE, folders=[tmp_path], default_language="ko", fallback_language="en"
    )
    info = service.info()
    assert (info.default_language, info.fallback_language) == ("ko", "en")
    rows = {row.code: (row.complete, row.missing) for row in info.languages}
    # de: "열기" is empty (untranslated) and the code is missing → 2. ko: both texts missing → 2.
    assert rows == {"de": (False, 2), "en": (True, 0), "ko": (False, 2)}
    assert [row.code for row in info.languages] == ["de", "en", "ko"]


def test_catalog_matches_region_and_reports_unknown_language() -> None:
    service = I18nService(packages=PACKAGE)
    assert service.catalog("en-US").catalog.language == "en"
    with pytest.raises(UnknownLanguageError) as caught:
        service.catalog("fr")
    assert (caught.value.language, caught.value.available) == ("fr", ("en", "ko"))
    with pytest.raises(UnknownLanguageError):
        service.catalog("not a language")


def test_version_is_stable_and_follows_content(tmp_path: Path) -> None:
    path = write_catalog(tmp_path, "en", text={"저장": "Store"})
    service = I18nService(packages=PACKAGE, folders=[tmp_path])
    first = service.catalog("en").version
    assert service.catalog("en").version == first
    write_catalog(tmp_path, "en", text={"저장": "Keep"})
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    again = service.catalog("en")
    assert again.catalog.text["저장"] == "Keep"
    assert again.version != first


def test_new_language_file_appears_without_restart(tmp_path: Path) -> None:
    service = I18nService(packages=PACKAGE, folders=[tmp_path])
    assert [row.code for row in service.info().languages] == ["en", "ko"]
    write_catalog(tmp_path, "ja", text={"저장": "保存"})
    assert [row.code for row in service.info().languages] == ["en", "ja", "ko"]


def test_loading_problems_become_warning_issues(tmp_path: Path) -> None:
    (tmp_path / "en.json").write_text("{", encoding="utf-8")
    (tmp_path / "bad name.json").write_text("{}", encoding="utf-8")
    write_catalog(tmp_path, "de", text={"저장": 3})  # type: ignore[dict-item]
    missing = tmp_path / "nowhere"
    service = I18nService(packages=PACKAGE, folders=[tmp_path, missing])
    issues = service.warnings()
    codes = sorted(issue.code for issue in issues)
    assert codes == [
        "i18n.catalog_unreadable",
        "i18n.entry_invalid",
        "i18n.language_invalid",
        "i18n.locales_missing",
    ]
    assert all(issue.severity == "warning" for issue in issues)
    entry = next(issue for issue in issues if issue.code == "i18n.entry_invalid")
    assert entry.details["key"] == "저장"
    assert entry.details["language"] == "de"
    assert "3" not in str(entry.details.values())  # catalog values are not sent
    # the remaining catalogs are still used
    assert service.catalog("en").catalog.text["저장"] == "Save"


def test_issue_of_keeps_location_only() -> None:
    issue = issue_of(
        CatalogIssue(
            code="i18n.source_unavailable",
            message="cannot import module 'x' (ImportError)",
            source="my-plugin",
        )
    )
    assert issue.code == "i18n.source_unavailable"
    assert issue.details == {"source": "my-plugin"}
    assert issue.message.endswith(": my-plugin")
    other = issue_of(CatalogIssue(code="i18n.something_new", message="English text"))
    assert other.message == "English text"
