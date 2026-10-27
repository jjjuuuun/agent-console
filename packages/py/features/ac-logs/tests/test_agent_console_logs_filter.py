import pytest

from agent_console_contracts.logs import LogSettings, LogTaxonomy
from agent_console_logs import (
    LogFilter,
    LogQueryError,
    parse_log_filter,
    parse_tz,
    query_context,
    query_schema,
)


def test_parse_values_and_lists() -> None:
    flt = parse_log_filter(
        {
            "category": "llm,tool",
            "from": ["a", "b"],
            "cwd": "/x,y",
            "since": "1970-01-01T00:00:10Z",
            "until": "20",
            "q": "z" * 600,
            "order": "desc",
            "limit": "999",
            "cursor": "12",
        }
    )
    assert flt.category == ("llm", "tool")
    assert flt.from_ == ("a", "b")
    assert flt.cwd == ("/x,y",)
    assert (flt.since, flt.until) == (10.0, 20.0)
    assert len(flt.q) == 500
    assert flt.order == "desc"
    assert flt.limit == 200
    assert flt.cursor == "12"


@pytest.mark.parametrize(
    ("params", "path"),
    [
        ({"nope": "1"}, "f.nope"),
        ({"order": "up"}, "f.order"),
        ({"limit": "x"}, "f.limit"),
        ({"cursor": "abc"}, "f.cursor"),
        ({"since": "yesterday"}, "f.since"),
        ({"tool": {"a": 1}}, "tool"),
    ],
)
def test_parse_errors_carry_path(params: dict[str, object], path: str) -> None:
    with pytest.raises(LogQueryError) as info:
        parse_log_filter(params, path="f")
    assert info.value.path == path


def test_tz() -> None:
    assert parse_tz(None) is None
    assert parse_tz("Asia/Seoul") is not None
    with pytest.raises(LogQueryError):
        parse_tz("Not/AZone")


def test_query_schema_lists_known_names() -> None:
    schema = query_schema()
    assert {d.id for d in schema.dimensions if d.kind == "time"} == {"day", "hour"}
    assert "tokens.total" in {m.id for m in schema.metrics}
    names = {f.id for f in schema.filters}
    assert {"from", "project", "q", "cursor"} <= names
    values = {n: "1" for n in names if n not in ("order",)}
    values["scope"] = "kind:1"  # 범위는 `<종류>:<값>` 형식
    parse_log_filter(values)  # 목록 이름은 모두 받는다


def test_query_context_from_settings() -> None:
    ctx = query_context(None)
    assert ctx.error_categories == frozenset({"error"})  # 기본 분류 체계의 tone: danger
    empty = query_context(None, base_taxonomy=LogTaxonomy())
    assert empty.error_categories == frozenset()
    custom = query_context(
        LogSettings.model_validate(
            {"taxonomy": {"categories": {"error": {"tone": "warning"}, "x": {"visible": False}}}}
        )
    )
    assert custom.error_categories == frozenset()
    assert custom.hidden_categories == frozenset({"x", "meta"})  # meta = 기본 숨김 범주(5R.19)
    assert LogFilter().with_(limit=3).limit == 3
