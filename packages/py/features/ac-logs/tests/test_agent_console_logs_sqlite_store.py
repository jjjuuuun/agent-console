"""SqliteLogIndex: 재시작·재수집·동시 쓰기·요약/원문 분리·실제 수집기 연동."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_console_contracts.logs import LogSettings, TokenSample
from agent_console_logs import (
    LogFilter,
    LogIndex,
    LogIngestor,
    LogRegistries,
    QueryContext,
    query_context,
)
from agent_console_logs._index import IndexBatch
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

CTX = QueryContext()


def test_reopen_keeps_data_and_ids(tmp_path: Path) -> None:
    path = tmp_path / "i.sqlite3"
    first = open_log_index(path)
    first.write(IndexBatch(records=[make_record("llm", origin="a", offset=1, title="하나")]))
    first.close()
    second = open_log_index(path)
    result = second.write(
        IndexBatch(
            records=[
                make_record("llm", origin="a", offset=1, title="하나"),
                make_record("llm", origin="a", offset=2, title="둘"),
            ]
        )
    )
    assert (result.inserted, result.max_seq) == (1, 2)  # seq는 이어서 매긴다
    assert [e.title for e in second.query_events(LogFilter(), CTX).items] == ["하나", "둘"]
    second.close()


def test_seq_not_reused_after_prune(tmp_path: Path) -> None:
    index = open_log_index(tmp_path / "i.sqlite3")
    index.write(IndexBatch(records=[make_record("llm", time=1.0), make_record("llm", time=2.0)]))
    assert index.prune(1.5) == 1
    index.write(IndexBatch(records=[make_record("llm", time=3.0)]))
    seqs = [e.seq for e in index.query_events(LogFilter(), CTX).items]
    assert seqs == [2, 3]  # 지운 seq(1)를 다시 쓰지 않는다 — 키셋 커서가 어긋나지 않게
    index.close()


def test_list_items_do_not_carry_bodies_but_detail_does(tmp_path: Path) -> None:
    index = open_log_index(tmp_path / "i.sqlite3")
    rec = make_record("llm", title="t", detail={"big": "x" * 50}, raw={"marker": "RAWONLY"})
    index.write(IndexBatch(records=[rec]))
    item = index.query_events(LogFilter(), CTX).items[0]
    assert item.detail is None
    assert item.raw is None
    assert item.summary
    with sqlite3.connect(tmp_path / "i.sqlite3") as db:
        (body,) = db.execute("select body from log_bodies").fetchone()
        (heavy,) = db.execute("select heavy from log_bodies").fetchone()
    assert "RAWONLY" not in body
    assert "RAWONLY" in heavy
    detail = index.get_event(item.uid, CTX)
    assert detail is not None
    assert detail.event.detail == {"big": "x" * 50}
    assert detail.event.raw == {"marker": "RAWONLY"}
    index.close()


def test_two_writers_on_one_file_never_duplicate(tmp_path: Path) -> None:
    """두 색인 객체(두 엔진)가 같은 이벤트를 동시에 써도 한 번만 들어간다."""
    path = tmp_path / "i.sqlite3"
    first, second = open_log_index(path), open_log_index(path)
    records = [make_record("llm", origin="a", offset=i, session="S") for i in range(60)]
    errors: list[BaseException] = []

    def run(index: SqliteLogIndex) -> None:
        try:
            for i in range(0, 60, 10):
                index.write(IndexBatch(records=records[i : i + 10]))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    page = first.query_events(LogFilter(limit=200), CTX, with_total=True)
    assert page.total == 60
    assert len({e.uid for e in page.items}) == 60
    first.close()
    second.close()


def test_usage_keeps_largest_output_across_batches_and_restarts(tmp_path: Path) -> None:
    path = tmp_path / "i.sqlite3"

    def row(out: int, offset: int) -> IndexBatch:
        return IndexBatch(
            records=[
                make_record(
                    "llm",
                    origin="a",
                    offset=offset,
                    session="S",
                    thread="T",
                    message_id="m",
                    usage=TokenSample(input_tokens=1, output_tokens=out),
                )
            ]
        )

    index = open_log_index(path)
    index.write(row(20, 1))
    index.close()
    index = open_log_index(path)
    index.write(row(5, 2))  # 더 작은 output은 덮지 못한다
    index.write(row(30, 3))
    samples = index.token_samples(LogFilter(), CTX)
    assert [(s.message_id, s.output_tokens) for s in samples] == [("m", 30)]
    index.close()


@pytest.mark.parametrize(
    "make", [lambda p: open_log_index(p / "x.sqlite3"), lambda _p: MemoryLogIndex()]
)
def test_ingestor_end_to_end_is_incremental_and_restart_safe(
    tmp_path: Path, make: Callable[[Path], LogIndex]
) -> None:
    """실제 수집기(normalized-v1)로 두 번·재시작 뒤 다시 수집해도 중복이 없다."""
    folder = tmp_path / "logs"
    folder.mkdir()
    rows = [
        {
            "schema_version": 1,
            "category": "llm",
            "title": "a",
            "session": "S",
            "thread": "m",
            "message_id": "m1",
            "usage": {"input_tokens": 10, "output_tokens": 3},
        },
        {
            "schema_version": 1,
            "category": "llm",
            "title": "b",
            "session": "S",
            "thread": "m",
            "message_id": "m1",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        },
        {"schema_version": 1, "category": "error", "title": "c", "session": "S"},
    ]
    (folder / "e.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    settings = LogSettings.model_validate(
        {"sources": [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}]}
    )
    registries = LogRegistries()
    registries.load()
    index = make(tmp_path)
    assert LogIngestor(index, registries).scan(settings).new_events == 3
    assert LogIngestor(index, registries).scan(settings).new_events == 0  # 새 수집기 = 재시작
    (folder / "e.jsonl").write_text(
        (folder / "e.jsonl").read_text(encoding="utf-8") + json.dumps(rows[2]) + "\n",
        encoding="utf-8",
    )
    assert LogIngestor(index, registries).scan(settings).new_events == 1
    ctx = query_context(settings)
    summary = index.list_sessions(LogFilter(), ctx)[0]
    assert summary.tokens is not None
    assert (summary.events, summary.errors, summary.tokens.output) == (4, 2, 8)
