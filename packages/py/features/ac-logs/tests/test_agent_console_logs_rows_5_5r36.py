"""행 읽기(5.5R.36): `query_event_rows`·`iter_event_rows`가 `query_events` 결과를 덤프한 것과 같다.

메모리·SQLite 색인 둘 다, 무작위 데이터·여러 필터·쪽 넘김·순서·범위·확장 판정에서 확인한다.
능력이 없는 색인은 `query_events` + 덤프로 같은 결과를 낸다.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterator
from typing import Any

import pytest

from agent_console_contracts.logs import LogDocumentRef, LogEvent, LogEventPage
from agent_console_logs import (
    IndexBatch,
    LogEventRowReader,
    LogFilter,
    LogScope,
    QueryContext,
    complete_event_row,
    event_row,
    iter_event_rows,
    query_event_rows,
)
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

CTX = QueryContext(error_categories=frozenset({"error"}))


def _records(seed: int, n: int) -> list[Any]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append(
            make_record(
                rng.choice(["llm", "tool_call", "tool_result", "error"]),
                source=rng.choice(["s1", "s2"]),
                origin=f"f{i % 5}",
                offset=i,
                session=rng.choice(["S1", "S2", ""]),
                thread=rng.choice(["main", "sub1", ""]),
                tool=rng.choice(["", "Bash"]),
                call_id=rng.choice(["", "c1", "c2"]),
                stage=rng.choice(["info", "start", "complete"]),
                message_id=rng.choice(["", "m1", "m2"]),
                run_id=rng.choice(["", "r1"]),
                status=rng.choice(["", "ok", "failed"]),
                time=rng.choice([None, 1000.0 + rng.random() * 9000, 2000.0]),
                title=rng.choice(["a", "한글", ""]),
                tags=tuple(rng.sample(["x", "y"], rng.randint(0, 2))),
                from_=tuple(rng.sample(["main", "u"], rng.randint(0, 2))),
                correlation=rng.choice([{}, {"k": "a"}, {"k": ["a", "b"]}]),
                documents=rng.choice(
                    [
                        (),
                        (LogDocumentRef(path="SKILL.md"),),
                        (LogDocumentRef(path="a.md", kind="spec", action="read"),),
                    ]
                ),
                detail=rng.choice([None, {"cmd": "ls"}]),
            )
        )
    return out


@pytest.fixture(scope="module")
def indexes(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[MemoryLogIndex, SqliteLogIndex]]:
    mem = MemoryLogIndex()
    sql = open_log_index(tmp_path_factory.mktemp("rows") / "i.sqlite3")
    records = _records(11, 300)
    for i in range(0, len(records), 70):
        batch = IndexBatch(records=records[i : i + 70])
        mem.write(batch)
        sql.write(batch)
    yield mem, sql
    sql.close()


FILTERS: list[dict[str, Any]] = [
    {},
    {"session": ("S1",)},
    {"thread": ("main", "sub1")},
    {"category": ("error",), "order": "desc"},
    {"call_id": ("c1",), "stage": ("start", "complete")},
    {"max_seq": 150},
    {"q": "한글"},
]


def _pages(index: Any, flt: LogFilter, ctx: QueryContext) -> list[LogEventPage]:
    pages, cursor = [], flt.cursor
    while True:
        page = index.query_events(flt.with_(cursor=cursor), ctx)
        pages.append(page)
        if page.next_cursor is None:
            return pages
        cursor = page.next_cursor


@pytest.mark.parametrize("spec", FILTERS)
@pytest.mark.parametrize("which", [0, 1])
def test_rows_equal_dumped_events(indexes: Any, spec: dict[str, Any], which: int) -> None:
    assert isinstance(indexes[which], LogEventRowReader)
    index = indexes[which]
    flt = LogFilter(**spec, limit=23)
    cursor = None
    for page in _pages(index, flt, CTX):
        rows = index.query_event_rows(flt.with_(cursor=cursor), CTX)
        assert rows.rows == [e.model_dump(mode="json", by_alias=True) for e in page.items]
        assert rows.next_cursor == page.next_cursor
        cursor = page.next_cursor
    all_rows = list(iter_event_rows(index, flt, CTX))
    assert all_rows == [
        e.model_dump(mode="json", by_alias=True) for p in _pages(index, flt, CTX) for e in p.items
    ]


@pytest.mark.parametrize("spec", FILTERS)
def test_memory_and_sqlite_rows_match(indexes: Any, spec: dict[str, Any]) -> None:
    mem, sql = indexes
    flt = LogFilter(**spec, limit=40)
    assert list(iter_event_rows(mem, flt, CTX)) == list(iter_event_rows(sql, flt, CTX))


def test_rows_follow_scope_and_predicates(indexes: Any) -> None:
    mem, sql = indexes
    seen: list[int] = []

    def even(event: LogEvent) -> bool:
        seen.append(event.seq)
        return event.seq % 2 == 0

    ctx = QueryContext(
        error_categories=frozenset({"error"}),
        scope=LogScope(sessions=frozenset({"S2"}), run_ids=frozenset({"r1"})),
        predicates=(even,),
    )
    flt = LogFilter(scope="x:y", extra=(("even", ("1",)),), limit=9)
    for index in (mem, sql):
        rows = list(iter_event_rows(index, flt, ctx))
        events = [e for p in _pages(index, flt, ctx) for e in p.items]
        assert rows == [event_row(e) for e in events]
        assert rows
        assert all(r["seq"] % 2 == 0 for r in rows)
        assert all(r["session"] == "S2" or r["run_id"] == "r1" for r in rows)


class _ModelsOnly:
    """행 능력이 없는 색인(`query_events`만 쓴다)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def query_events(self, flt: LogFilter, ctx: QueryContext, **kw: Any) -> LogEventPage:
        page: LogEventPage = self._inner.query_events(flt, ctx, **kw)
        return page


def test_without_capability_falls_back_to_dump(indexes: Any) -> None:
    _mem, sql = indexes
    plain = _ModelsOnly(sql)
    assert not isinstance(plain, LogEventRowReader)
    flt = LogFilter(limit=50)
    page = query_event_rows(plain, flt, CTX)  # type: ignore[arg-type]
    assert page == sql.query_event_rows(flt, CTX)
    rows = list(iter_event_rows(plain, flt, CTX))  # type: ignore[arg-type]
    assert rows == list(iter_event_rows(sql, flt, CTX))
    assert len(rows) == 300


def test_rows_carry_pair_durations(indexes: Any) -> None:
    mem, sql = indexes
    flt = LogFilter(call_id=("c1",), limit=500)
    for index in (mem, sql):
        rows = list(iter_event_rows(index, flt, CTX))
        events = [e for p in _pages(index, flt, CTX) for e in p.items]
        assert [r["duration_ms"] for r in rows] == [e.duration_ms for e in events]
    assert any(r["duration_ms"] is not None for r in iter_event_rows(sql, flt, CTX))


def test_complete_event_row_fills_defaults_and_drops_unknown() -> None:
    event = make_record(
        "llm",
        session="S",
        documents=(LogDocumentRef(path="SKILL.md"), LogDocumentRef(path="b", kind="spec")),
        detail={"a": 1},
    ).event.model_copy(update={"seq": 4})
    compact = json.loads(
        event.model_dump_json(
            by_alias=True, exclude={"seq", "detail", "raw"}, exclude_defaults=True
        )
    )
    compact["future_field"] = 1
    compact["documents"][0]["future"] = "x"
    row = complete_event_row(compact, seq=4)
    assert row == event_row(event)
    assert "future_field" not in row
    assert "future_field" in compact  # 입력은 고치지 않는다
    # 기본 목록·객체는 행마다 새것이다
    other = complete_event_row(dict(compact), seq=5)
    assert row["to"] == []
    assert row["to"] is not other["to"]
    assert row["correlation"] is not other["correlation"]


def test_event_row_is_listing_shape() -> None:
    event = make_record("llm", detail={"a": 1}).event
    row = event_row(event)
    assert row["detail"] is None
    assert row["raw"] is None
    assert row["from"] == []
    assert "from_" not in row


@pytest.mark.parametrize("which", [0, 1])
def test_iter_rows_reports_pages(indexes: Any, which: int) -> None:
    index = indexes[which]
    sizes: list[int] = []
    rows = list(iter_event_rows(index, LogFilter(limit=70), CTX, on_page=sizes.append))
    assert sizes == [70, 70, 70, 70, 20]
    assert len(rows) == 300
    # 커서부터 이어 읽기
    rest = list(iter_event_rows(index, LogFilter(limit=70, cursor=str(rows[99]["seq"])), CTX))
    assert rest == rows[100:]
    plain: list[int] = []
    models_only: Any = _ModelsOnly(index)
    again = iter_event_rows(models_only, LogFilter(limit=70), CTX, on_page=plain.append)
    assert list(again) == rows
    assert plain == sizes
