"""4R.5 QA: SQL 주입·LIKE 특수문자·대소문자 q, 토큰 1회(배치·재시작·두 엔진), prune 원문 삭제."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.logs import LogAggregateRequest, TokenSample
from agent_console_logs import LogFilter, QueryContext
from agent_console_logs._index import IndexBatch
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

CTX = QueryContext()
NASTY = ["'", '"; DROP TABLE log_events; --', "%", "_", "\\", "' OR '1'='1", "a%b_c\\d", "\x00x"]


def _fill(idx: Any) -> None:
    idx.write(
        IndexBatch(
            records=[
                make_record("llm", session="S1", title="Hello World", cwd="/w/a", model="m1"),
                make_record("input", session="S2", title="100% sure_thing", cwd="/w/b"),
                make_record("tool_call", session="it's", title="O'Brien \\ x", tool="Bash"),
            ]
        )
    )


@pytest.mark.parametrize("value", NASTY)
@pytest.mark.parametrize("field", ["session", "cwd", "tool", "model", "source", "agent", "project"])
def test_filter_values_are_data_not_sql(tmp_path: Path, field: str, value: str) -> None:
    sql, mem = open_log_index(tmp_path / "i.sqlite3"), MemoryLogIndex()
    _fill(sql)
    _fill(mem)
    kw: dict[str, Any] = {field: [value]}
    flt = LogFilter(**kw)
    a = [e.title for e in sql.query_events(flt, CTX).items]
    b = [e.title for e in mem.query_events(flt, CTX).items]
    assert a == b
    # 테이블이 살아 있다.
    assert len(sql.query_events(LogFilter(), CTX).items) == 3
    sql.close()


@pytest.mark.parametrize(
    "q", ["HELLO", "Hello", "hello", "%", "_", "100%", "sure_", "o'brien", "\\", "' or", "ß"]
)
def test_q_matches_memory_including_case_and_like_chars(tmp_path: Path, q: str) -> None:
    sql, mem = open_log_index(tmp_path / "i.sqlite3"), MemoryLogIndex()
    _fill(sql)
    _fill(mem)
    flt = LogFilter(q=q)
    assert [e.title for e in sql.query_events(flt, CTX).items] == [
        e.title for e in mem.query_events(flt, CTX).items
    ]
    sql.close()


def _row(out: int, offset: int, msg: str = "m") -> Any:
    return make_record(
        "llm",
        origin="a",
        offset=offset,
        session="S",
        thread="T",
        message_id=msg,
        usage=TokenSample(input_tokens=10, output_tokens=out),
    )


def _total(idx: Any, metric: str) -> float | None:
    rows = idx.aggregate(LogAggregateRequest(metric=metric), CTX)
    return rows[0].value if rows else None


def test_tokens_once_in_batch_across_batches_restart_and_two_engines(tmp_path: Path) -> None:
    path = tmp_path / "i.sqlite3"
    a, b = open_log_index(path), open_log_index(path)
    a.write(IndexBatch(records=[_row(5, 1), _row(30, 2), _row(12, 3), _row(7, 4, "m2")]))
    b.write(IndexBatch(records=[_row(30, 5), _row(9, 6, "m2")]))
    a.close()
    a = open_log_index(path)
    a.write(IndexBatch(records=[_row(30, 7), _row(30, 2)]))
    for idx in (a, b):
        assert _total(idx, "tokens.output") == 39.0  # m=30, m2=9
        assert _total(idx, "tokens.input") == 20.0
    a.close()
    b.close()


def test_two_engines_concurrent_token_batches(tmp_path: Path) -> None:
    path = tmp_path / "i.sqlite3"
    engines = [open_log_index(path), open_log_index(path)]
    errs: list[BaseException] = []

    def run(idx: Any) -> None:
        try:
            for i in range(40):
                idx.write(IndexBatch(records=[_row(i + 1, 1000 + i, f"m{i % 10}")]))
        except BaseException as exc:
            errs.append(exc)

    ts = [threading.Thread(target=run, args=(e,)) for e in engines]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errs == []
    # m0..m9 각 최대 output = 31..40
    assert _total(engines[0], "tokens.output") == float(sum(range(31, 41)))
    for e in engines:
        e.close()


def test_prune_removes_raw_and_detail_everywhere(tmp_path: Path) -> None:
    path = tmp_path / "i.sqlite3"
    idx = open_log_index(path)
    idx.write(
        IndexBatch(
            records=[
                make_record(
                    "llm",
                    session="S",
                    time=10.0,
                    title="old",
                    detail={"d": "DETAILSECRET"},
                    raw={"r": "RAWSECRET"},
                ),
                make_record("llm", session="S", time=9_999_999.0, title="new"),
            ]
        )
    )
    idx.close()
    con = sqlite3.connect(path)
    dump = repr(
        [
            r
            for (n,) in con.execute("select name from sqlite_master where type='table'").fetchall()
            for r in con.execute(f'select * from "{n}"').fetchall()
        ]
    )
    con.close()
    assert "RAWSECRET" in dump
    assert "DETAILSECRET" in dump
    idx = open_log_index(path)
    assert idx.prune(5_000_000.0) == 1
    idx.close()
    con = sqlite3.connect(path)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for (name,) in con.execute("select name from sqlite_master where type='table'").fetchall():
        for row in con.execute(f'select * from "{name}"').fetchall():
            assert "SECRET" not in repr(row), name
    con.close()
