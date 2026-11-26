from pathlib import Path

import pytest

from agent_console_i18n import (
    Catalog,
    CatalogSet,
    folder_catalogs,
    match_language,
    package_catalogs,
    placeholders,
    render,
)
from agent_console_i18n.testing import catalog_entry_point, make_catalog_package, write_catalog


def test_user_folder_overrides_package_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = tmp_path / "site"
    monkeypatch.syspath_prepend(str(site))
    make_catalog_package(
        site, "i18n_lookup_pkg", {"en": {"text": {"저장": "Save", "취소": "Cancel"}}}
    )
    write_catalog(tmp_path / "mine", "en", text={"저장": "Store", "취소": ""})
    write_catalog(tmp_path / "mine", "fr", text={"저장": "Enregistrer"})
    catalogs = CatalogSet.from_load(
        package_catalogs(entry_points=[catalog_entry_point("pkg", "i18n_lookup_pkg")]),
        folder_catalogs([tmp_path / "mine"]),
    )
    assert catalogs.languages() == ("en", "fr")
    en = catalogs.translator("en")
    assert en.text("저장") == "Store"
    # 빈 값은 앞 출처를 지우지 않는다(아직 번역 안 함)
    assert en.text("취소") == "Cancel"
    assert catalogs.sources("en") == ("pkg", str(tmp_path / "mine"))
    assert [c.source for c in catalogs.parts("en")] == ["pkg", str(tmp_path / "mine")]
    # 사용자가 더한 새 언어는 일부만 있어도 되고 빠진 것은 대체 언어로 간다
    fr = catalogs.translator("fr-CA", fallback="en")
    assert fr.languages == ("fr", "en")
    assert (fr.text("저장"), fr.text("취소"), fr.text("모름")) == ("Enregistrer", "Cancel", "모름")


def test_ns_merges_leaf_by_leaf() -> None:
    catalogs = CatalogSet(
        [
            Catalog(
                "ko", ns={"common": {"save": "저장", "menu": {"open": "열기", "close": "닫기"}}}
            ),
            Catalog("ko", ns={"common": {"menu": {"open": "펼치기"}}, "wiki": {"t": "위키"}}),
        ]
    )
    merged = catalogs.catalog("ko")
    assert merged is not None
    assert merged.ns == {
        "common": {"save": "저장", "menu": {"open": "펼치기", "close": "닫기"}},
        "wiki": {"t": "위키"},
    }


def test_translator_namespace_overlays_fallback() -> None:
    catalogs = CatalogSet(
        [
            Catalog("en", ns={"common": {"save": "Save", "close": "Close"}}),
            Catalog("de", ns={"common": {"save": "Speichern"}}),
        ]
    )
    assert catalogs.translator("de", fallback="en").namespace("common") == {
        "save": "Speichern",
        "close": "Close",
    }
    assert catalogs.translator("xx").namespace("common") == {}


def test_code_lookup_fills_details_and_falls_back() -> None:
    catalogs = CatalogSet(
        [
            Catalog("en", codes={"run.failed": "Run {run_id} failed", "only.en": "Only {n}"}),
            Catalog("ko", codes={"run.failed": "{run_id} 실행이 실패했습니다"}),
        ]
    )
    ko = catalogs.translator("ko", fallback="en")
    assert ko.code("run.failed", {"run_id": "r1"}) == "r1 실행이 실패했습니다"
    assert ko.code("only.en", {"n": 2}) == "Only 2"
    assert ko.code("unknown.code", default="서버 원문") == "서버 원문"
    assert ko.code("unknown.code") is None
    # 값이 빠지면 서버 원문을 쓴다(웹이 메시지를 쪼개지 않는다)
    assert ko.code("run.failed", {}, default="원문") == "원문"
    assert ko.code("run.failed") == "{run_id} 실행이 실패했습니다"
    assert ko.template("only.en") == "Only {n}"


def test_match_language_lookup_order() -> None:
    available = ["en", "zh-Hant", "pt-BR"]
    assert match_language("en-US", available) == "en"
    assert match_language("zh-hant-tw", available) == "zh-Hant"
    assert match_language("pt", available) is None
    assert match_language("PT_br", available) == "pt-BR"
    assert match_language("not a tag", available) is None
    assert match_language("en", ["bad tag", "en"]) == "en"


def test_empty_set_returns_original_text() -> None:
    translator = CatalogSet().translator("en", fallback="en")
    assert translator.languages == ()
    assert translator.text("원문") == "원문"


def test_cache_is_reset_when_catalog_added() -> None:
    catalogs = CatalogSet([Catalog("en", text={"a": "A"})])
    assert catalogs.translator("en").text("a") == "A"
    catalogs.add(Catalog("en", text={"a": "B"}))
    assert catalogs.translator("en").text("a") == "B"


def test_placeholders_and_render() -> None:
    assert placeholders("{a} and { b } and {c, particle.object} and {{x}}") == {"a", "b", "c", "x"}
    assert placeholders("no {1} or {} here") == frozenset()
    assert render("{label, particle.object} 지움", {"label": "팀"}) == ("팀 지움", frozenset())
