import pytest

from agent_console_i18n import Catalog, is_language_tag, normalize_language, read_catalog


def test_read_catalog_reads_three_sections() -> None:
    catalog, issues = read_catalog(
        {
            "text": {"저장": "Save"},
            "codes": {"wiki.page_missing": "Page {page} is missing"},
            "ns": {"common": {"save": "Save", "menu": {"open": "Open"}}},
        },
        language="en",
        source="demo",
        origin="package",
    )
    assert issues == []
    assert catalog == Catalog(
        language="en",
        text={"저장": "Save"},
        codes={"wiki.page_missing": "Page {page} is missing"},
        ns={"common": {"save": "Save", "menu": {"open": "Open"}}},
        source="demo",
        origin="package",
        sources=("demo",),
    )
    assert catalog.to_dict()["ns"] == {"common": {"save": "Save", "menu": {"open": "Open"}}}


def test_bad_entries_are_skipped_and_reported() -> None:
    catalog, issues = read_catalog(
        {
            "text": {"a": "A", "b": 3},
            "codes": ["not", "an", "object"],
            "ns": {"common": {"ok": "OK", "bad": [1]}, "flat": "x"},
            "extra": {},
        },
        language="en",
        path="en.json",
    )
    assert catalog is not None
    assert catalog.text == {"a": "A"}
    assert catalog.codes == {}
    assert catalog.ns == {"common": {"ok": "OK"}}
    assert [(i.code, i.section, i.key) for i in issues] == [
        ("i18n.catalog_unknown_section", "extra", None),
        ("i18n.entry_invalid", "text", "b"),
        ("i18n.catalog_invalid", "codes", None),
        ("i18n.entry_invalid", "ns", "common.bad"),
        ("i18n.entry_invalid", "ns", "flat"),
    ]
    assert all(i.path == "en.json" and i.language == "en" for i in issues)


def test_top_level_must_be_object_and_language_valid() -> None:
    assert read_catalog([], language="en")[0] is None
    catalog, issues = read_catalog({}, language="not a tag")
    assert catalog is None
    assert issues[0].code == "i18n.language_invalid"


def test_language_is_normalized() -> None:
    catalog, _ = read_catalog({}, language="pt_br")
    assert catalog is not None
    assert catalog.language == "pt-BR"
    assert normalize_language("ZH-hant-tw") == "zh-Hant-TW"
    assert is_language_tag("x-klingon") is False
    assert is_language_tag("tlh")
    with pytest.raises(ValueError, match="language tag"):
        normalize_language("")
