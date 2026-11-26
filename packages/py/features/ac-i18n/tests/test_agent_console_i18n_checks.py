from collections.abc import Sequence

from agent_console_i18n import (
    Catalog,
    CatalogIssue,
    SchemaTextKeys,
    check_codes,
    check_details,
    check_texts,
    compare_catalogs,
    flatten_ns,
    is_complete,
    schema_texts,
)


def _codes(issues: Sequence[CatalogIssue]) -> list[tuple[str, str | None, str | None]]:
    return [(i.code, i.section, i.key) for i in issues]


def test_compare_reports_missing_extra_empty_and_placeholders() -> None:
    ko = Catalog(
        "ko",
        text={"저장": "저장", "삭제": "삭제"},
        codes={"run.failed": "{run_id} 실패", "run.done": "끝"},
        ns={"common": {"count": "{n}개", "only_ko": "가"}},
    )
    en = Catalog(
        "en",
        text={"저장": "Save", "삭제": ""},
        codes={"run.failed": "Run {id} failed", "run.extra": "x"},
        ns={"common": {"count": "{n} items"}},
    )
    issues = compare_catalogs(ko, en)
    assert _codes(issues) == [
        ("i18n.untranslated", "text", "삭제"),
        ("i18n.placeholder_mismatch", "codes", "run.failed"),
        ("i18n.missing_key", "codes", "run.done"),
        ("i18n.extra_key", "codes", "run.extra"),
        ("i18n.missing_key", "ns", "common.only_ko"),
    ]
    mismatch = issues[1]
    assert mismatch.language == "en"
    assert dict(mismatch.details) == {"expected": ["run_id"], "actual": ["id"]}
    assert not is_complete(ko, en)
    assert is_complete(ko, ko)


def test_plural_forms_compare_as_one_key() -> None:
    ko = Catalog("ko", ns={"runs": {"items_other": "{count}개"}})
    en = Catalog("en", ns={"runs": {"items_one": "One run", "items_other": "{count} runs"}})
    assert compare_catalogs(ko, en) == []
    assert compare_catalogs(en, ko) == []
    assert compare_catalogs(ko, en, plural_suffixes=()) != []


def test_sections_can_be_limited() -> None:
    base = Catalog("ko", text={"a": "가"}, codes={"c": "다"})
    assert _codes(compare_catalogs(base, Catalog("fr"), sections=["codes"])) == [
        ("i18n.missing_key", "codes", "c")
    ]
    assert is_complete(base, Catalog("fr", codes={"c": "C"}), sections=["codes"])


def test_check_codes_and_texts() -> None:
    en = Catalog("en", text={"저장": "Save", "빈": ""}, codes={"a.b": "AB", "a.empty": ""})
    assert _codes(check_codes(en, ["a.b", "a.c", "a.empty", "a.c"])) == [
        ("i18n.missing_code", "codes", "a.c"),
        ("i18n.missing_code", "codes", "a.empty"),
    ]
    assert _codes(check_texts(en, ["저장", "삭제", "빈"])) == [
        ("i18n.missing_text", "text", "삭제"),
        ("i18n.missing_text", "text", "빈"),
    ]


def test_check_details_finds_unknown_placeholders() -> None:
    en = Catalog("en", codes={"run.failed": "Run {run_id} failed: {reason}", "ok": "Fine"})
    issues = check_details(en, {"run.failed": {"run_id": "r1"}, "ok": [], "not.in.catalog": ["x"]})
    assert _codes(issues) == [("i18n.unknown_placeholder", "codes", "run.failed")]
    assert dict(issues[0].details) == {"unknown": ["reason"], "details": ["run_id"]}


def test_flatten_ns() -> None:
    assert flatten_ns({"a": {"b": {"c": "x"}, "d": "y"}}) == {"a.b.c": "x", "a.d": "y"}


SCHEMA = {
    "title": "공통 설정",
    "type": "object",
    "properties": {
        "default": {
            "type": "string",
            "title": "기본 백엔드",
            "description": "비우면 서버 설정",
            "default": {"title": "기본값 안은 보지 않음"},
            "examples": [{"description": "예시 안도 보지 않음"}],
            "x-ui": {
                "tier": "advanced",
                "when": "다른 백엔드를 쓸 때",
                "group_title": "실행",
                "unit": "초",
                "enum_labels": {"a": "가", "b": "나"},
                "variables": [{"name": "id", "description": "정의 id"}],
                "example": {"title": "x-ui 예시도 보지 않음"},
            },
        },
        "title": {"$ref": "#/$defs/Title"},
    },
    "$defs": {
        "Title": {"title": "제목", "description": "공통 설정", "anyOf": [{"title": "문자열"}]}
    },
}


def test_schema_texts_collects_screen_text_only() -> None:
    assert schema_texts(SCHEMA) == [
        "공통 설정",
        "기본 백엔드",
        "비우면 서버 설정",
        "다른 백엔드를 쓸 때",
        "실행",
        "초",
        "가",
        "나",
        "정의 id",
        "제목",
        "문자열",
    ]


def test_schema_text_keys_are_data() -> None:
    keys = SchemaTextKeys(keywords=("title",), ext_strings=(), ext_maps=(), ext_lists=())
    assert schema_texts(SCHEMA, keys=keys) == ["공통 설정", "기본 백엔드", "제목", "문자열"]
    assert schema_texts([{"title": " "}, "x", 3]) == []
