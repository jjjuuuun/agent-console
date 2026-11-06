"""6R.9: 값 IN 나누기(M-15)와 확장 판정 행 기준 미리 거르기(M-1).

- 값 40,000개 IN: 배포판 기본 SQLite 변수 한도(32,766)로 낮춘 연결에서도 질의가 된다.
- 미리 거르기: 열 값으로 답이 나는 행은 판정 함수(본문 → `LogEvent`)를 부르지 않고, 결과는 옛
  경로(미리 거르기 없음)·메모리 색인과 같다(차등 0).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts.logs import LogAggregateRequest, LogEvent
from agent_console_logs import (
    EVENT_ROW_FIELDS,
    IndexBatch,
    LogFilter,
    LogFilterContext,
    LogScope,
    QueryContext,
    RowCheckedPredicate,
    RowPredicate,
    row_check_of,
)
from agent_console_logs.sqlite import SqliteLogIndex, create_log_engine, log_events, log_metadata
from agent_console_logs.testing import CountingPredicate, FieldFilter, MemoryLogIndex, make_record

DEFAULT_VARIABLE_LIMIT = 32_766
"""Windows·macOS 배포판 Python의 SQLite 기본 변수 한도(일부 리눅스 배포판은 더 크다)."""
CTX = QueryContext(error_categories=frozenset({"error"}))


def _records() -> list[Any]:
    out = []
    for i in range(240):
        cat = ("input", "tool_call", "tool_result", "error")[i % 4]
        out.append(
            make_record(
                cat,
                source=("a", "b", "c")[i % 3],
                offset=i,
                session=f"s{i % 6}",
                thread=("main", "sub1")[i % 2],
                tool="Bash" if cat.startswith("tool") else "",
                title=f"event {i}",
                time=1_000.0 + i,
                detail={"n": i} if i % 5 == 0 else None,
            )
        )
    return out


@pytest.fixture
def limited(tmp_path: Path) -> Iterator[SqliteLogIndex]:
    """연결마다 변수 한도를 기본값으로 낮춘 색인."""
    engine = create_log_engine(tmp_path / "i.sqlite3")

    @sa.event.listens_for(engine, "connect")
    def _limit(dbapi: sqlite3.Connection, _record: object) -> None:
        dbapi.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, DEFAULT_VARIABLE_LIMIT)

    log_metadata.create_all(engine)
    index = SqliteLogIndex(engine, owns_engine=True)
    index.write(IndexBatch(records=_records()))
    yield index
    index.close()


@pytest.fixture
def pair() -> Iterator[tuple[SqliteLogIndex, MemoryLogIndex]]:
    from agent_console_logs.sqlite import open_log_index

    sqlite_index = open_log_index(":memory:")
    memory = MemoryLogIndex()
    records = _records()
    sqlite_index.write(IndexBatch(records=records))
    memory.write(IndexBatch(records=records))
    yield sqlite_index, memory
    sqlite_index.close()


def _many(prefix: str, n: int, *real: str) -> tuple[str, ...]:
    return (*real, *(f"{prefix}{i}" for i in range(n - len(real))))


# ------------------------------------------------------------------ M-15 `_in`


def test_limit_is_active_for_plain_in(limited: SqliteLogIndex) -> None:
    """이 고정 장치가 한도를 실제로 건다(나누지 않은 IN은 실패한다)."""
    values = list(_many("x", 40_000))
    with limited.engine.connect() as conn, pytest.raises(sa.exc.OperationalError):
        conn.execute(sa.select(log_events.c.seq).where(log_events.c.session.in_(values))).all()


@pytest.mark.parametrize("column", ["session", "source", "thread", "tool", "run_id", "cwd"])
def test_value_filter_with_40000_values(limited: SqliteLogIndex, column: str) -> None:
    real = {"session": "s1", "source": "b", "thread": "sub1", "tool": "Bash"}.get(column, "")
    values = _many("missing-", 40_000, *([real] if real else []))
    page = limited.query_events(
        LogFilter(limit=500).with_(**{column: values}), CTX, with_total=True
    )
    expected = limited.query_events(
        LogFilter(limit=500).with_(**{column: (real,) if real else ()}), CTX, with_total=True
    )
    if real:
        assert [e.uid for e in page.items] == [e.uid for e in expected.items]
        assert page.total == expected.total
        assert page.total
    else:
        assert page.items == []


def test_scope_and_agent_and_category_with_40000_values(limited: SqliteLogIndex) -> None:
    ctx = replace(CTX, scope=LogScope.of(_many("nope-", 40_000, "s2"), _many("run-", 40_000)))
    page = limited.query_events(LogFilter(limit=500), ctx, with_total=True)
    assert page.total == 40
    assert {e.session for e in page.items} == {"s2"}
    cats = limited.query_events(
        LogFilter(limit=500, category=_many("cat-", 40_000, "error")), CTX, with_total=True
    )
    assert cats.total == 60
    agents = limited.query_events(LogFilter(limit=5, agent=_many("ag-", 40_000)), CTX)
    assert agents.items == []


def test_usage_and_aggregate_with_40000_values(limited: SqliteLogIndex) -> None:
    flt = LogFilter(session=_many("missing-", 40_000, "s3"))
    many = limited.aggregate(
        LogAggregateRequest(
            group_by=["source"], metric="events", filter={"session": list(flt.session)}
        ),
        CTX,
    )
    one = limited.aggregate(
        LogAggregateRequest(group_by=["source"], metric="events", filter={"session": ["s3"]}), CTX
    )
    assert many == one
    assert one
    assert limited.token_samples(flt, CTX) == limited.token_samples(LogFilter(session=("s3",)), CTX)
    sessions = limited.list_sessions(flt, CTX)
    assert [s.session for s in sessions] == ["s3"]


# ------------------------------------------------------------------ M-1 행 기준


def _only_source(value: str) -> tuple[CountingPredicate, RowCheckedPredicate]:
    counter = CountingPredicate(lambda e: e.source == value)
    return counter, RowCheckedPredicate(
        counter, lambda row: row.get("source") == value, frozenset({"source"})
    )


def test_row_check_capability_detection() -> None:
    _counter, pred = _only_source("a")
    assert isinstance(pred, RowPredicate)
    assert not isinstance(lambda e: True, RowPredicate)
    found = row_check_of(pred)
    assert found is not None
    assert found[0] == frozenset({"seq", "source"})
    weird = RowCheckedPredicate(lambda e: True, lambda row: None, frozenset({"nope", "uid"}))
    found = row_check_of(weird)
    assert found is not None
    assert found[0] == frozenset({"seq", "uid"})
    assert frozenset({"seq", "uid", "source"}) <= EVENT_ROW_FIELDS
    assert row_check_of(lambda e: True) is None


def _uids(page: Any) -> list[str]:
    return [e.uid for e in page.items]


def test_decided_rows_do_not_build_events(pair: tuple[SqliteLogIndex, MemoryLogIndex]) -> None:
    index, memory = pair
    counter, pred = _only_source("b")
    flt = LogFilter(limit=500)
    page = index.query_events(flt, replace(CTX, predicates=(pred,)), with_total=True)
    assert counter.calls == 0  # 열 값으로 모두 답했다
    old = index.query_events(
        flt, replace(CTX, predicates=(counter.as_predicate(),)), with_total=True
    )
    assert counter.calls > 0
    mem = memory.query_events(flt, replace(CTX, predicates=(pred,)), with_total=True)
    assert _uids(page) == _uids(old) == _uids(mem)
    assert page.total == old.total == mem.total == 80


def test_undecided_rows_fall_back_to_event(pair: tuple[SqliteLogIndex, MemoryLogIndex]) -> None:
    """미리 거르기가 None이면 본문 판정으로(같은 결과), 본문을 쓰는 판정만 이벤트를 만든다."""
    index, memory = pair
    calls = CountingPredicate(lambda e: e.source == "a" and isinstance(e.detail, dict))

    def maybe(row: Any) -> bool | None:
        return False if row["source"] != "a" else None

    pred = RowCheckedPredicate(calls, maybe, frozenset({"source"}))
    flt = LogFilter(limit=500)
    page = index.query_events(flt, replace(CTX, predicates=(pred,)), with_total=True)
    assert calls.calls == 80  # source == a 인 행만(전체 수·쪽 질의가 seq별 캐시를 함께 쓴다)
    mem = memory.query_events(flt, replace(CTX, predicates=(pred,)), with_total=True)
    assert _uids(page) == _uids(mem)
    assert page.total == mem.total == 16


def test_mixed_predicates_keep_and_semantics(pair: tuple[SqliteLogIndex, MemoryLogIndex]) -> None:
    """미리 거르기가 없는 판정이 섞이면 '모두 맞음'을 확정하지 않는다(그 판정은 본문으로)."""
    index, memory = pair
    _counter, by_row = _only_source("c")
    plain = CountingPredicate(lambda e: e.thread == "main")
    ctx = replace(CTX, predicates=(by_row, plain))
    flt = LogFilter(limit=500)
    page = index.query_events(flt, ctx, with_total=True)
    assert plain.calls == 80  # source == c 인 행만 본문 판정
    assert _uids(page) == _uids(memory.query_events(flt, ctx))
    assert page.total == 40


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_paging_aggregate_and_sessions_match_old_path(
    pair: tuple[SqliteLogIndex, MemoryLogIndex], order: str
) -> None:
    index, _memory = pair
    ext = FieldFilter("t", "thread", row_check=True)
    old_ext = FieldFilter("t", "thread")
    context = LogFilterContext(filter=LogFilter(), query=CTX)
    new = replace(CTX, predicates=(ext.build({"t": ("!main",)}, context),))
    old = replace(CTX, predicates=(old_ext.build({"t": ("!main",)}, context),))
    assert row_check_of(new.predicates[0]) is not None
    assert row_check_of(old.predicates[0]) is None

    def pages(ctx: QueryContext) -> list[str]:
        out: list[str] = []
        cursor: str | None = None
        while True:
            page = index.query_events(LogFilter(limit=7, order=order, cursor=cursor), ctx)  # type: ignore[arg-type]
            out += _uids(page)
            cursor = page.next_cursor
            if cursor is None:
                return out

    assert pages(new) == pages(old)
    assert len(pages(new)) == 120
    request = LogAggregateRequest(group_by=["source", "category"], metric="events")
    assert index.aggregate(request, new) == index.aggregate(request, old)
    flt = LogFilter()
    assert index.list_sessions(flt, new) == index.list_sessions(flt, old)
    assert index.token_samples(flt, new) == index.token_samples(flt, old)
    assert index.timeline("s1", new) == index.timeline("s1", old)


def test_field_filter_row_check_only_without_body_rule() -> None:
    context = LogFilterContext(filter=LogFilter(), query=CTX)
    body = FieldFilter("t", "thread", detail_key="n", row_check=True)
    assert row_check_of(body.build({"t": ("main",), "t_has": ("1",)}, context)) is None
    not_column = FieldFilter("t", "title", row_check=True)
    assert row_check_of(not_column.build({"t": ("x",)}, context)) is None
    pred = FieldFilter("t", "thread", row_check=True).build({"t": ("main",)}, context)
    found = row_check_of(pred)
    assert found is not None
    event = LogEvent.model_validate(
        {"uid": "u", "seq": 1, "source": "a", "observed_at": 1.0, "category": "x", "thread": "main"}
    )
    assert found[1]({"seq": 1, "thread": "main"}) is True
    assert pred(event) is True
