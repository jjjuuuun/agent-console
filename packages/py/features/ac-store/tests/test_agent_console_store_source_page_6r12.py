"""6R.12: 출처를 잇는 커서(``page_across_sources``)와 이벤트 ``node`` 거르기."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts import Run, RunEvent
from agent_console_store import (
    InvalidCursor,
    decode_source_cursor,
    encode_source_cursor,
    page_across_sources,
)

ORDER = ("project", "app")


def _source(rows: dict[str, list[int]], size: int) -> Any:
    """출처마다 정수 목록을 ``size``씩 자르는 가짜 저장소(저장소 커서 = 다음 시작 위치)."""

    def read(src: str, inner: str | None) -> tuple[list[int], str | None]:
        start = int(inner or 0)
        chunk = rows[src][start : start + size]
        end = start + len(chunk)
        return chunk, (str(end) if end < len(rows[src]) else None)

    return read


def _collect(rows: dict[str, list[int]], size: int, source: str = "project") -> list[Any]:
    read = _source(rows, size)
    seen: list[Any] = []
    cursor: str | None = None
    while True:
        page = page_across_sources(
            cursor, source, order=ORDER, read=read, has_any=lambda s: bool(rows[s])
        )
        seen.append((page.source, page.items))
        cursor = page.next_cursor
        if cursor is None:
            return seen


def test_cursor_round_trip_and_bad_cursors() -> None:
    assert decode_source_cursor(encode_source_cursor("app", "abc"), ORDER) == ("app", "abc")
    assert decode_source_cursor(encode_source_cursor("project", None), ORDER) == ("project", None)
    for bad in ("", "app", "nope.x", ".x"):
        with pytest.raises(InvalidCursor):
            decode_source_cursor(bad, ORDER)
    with pytest.raises(ValueError, match="출처"):
        encode_source_cursor("a.b", None)


def test_reads_first_source_to_end_then_next_without_mixing() -> None:
    rows = {"project": [1, 2, 3, 4, 5], "app": [6, 7, 8]}
    pages = _collect(rows, 2)
    assert pages == [
        ("project", [1, 2]),
        ("project", [3, 4]),
        ("project", [5]),
        ("app", [6, 7]),
        ("app", [8]),
    ]


def test_skips_empty_later_source_and_starts_from_cursor_source() -> None:
    assert _collect({"project": [1], "app": []}, 5) == [("project", [1])]
    assert _collect({"project": [], "app": [1]}, 5) == [("project", []), ("app", [1])]
    assert _collect({"project": [1], "app": [2, 3]}, 5, source="app") == [("app", [2, 3])]
    read = _source({"project": [1], "app": [2, 3]}, 1)
    page = page_across_sources("app.1", "project", order=ORDER, read=read, has_any=bool)
    assert (page.source, page.items, page.next_cursor) == ("app", [3], None)


def test_single_source_order_does_not_chain() -> None:
    read = _source({"project": [1], "app": [2]}, 5)
    page = page_across_sources(
        None, "project", order=("project",), read=read, has_any=lambda _s: True
    )
    assert page.next_cursor is None


def _run() -> Run:
    return Run.model_validate(
        {
            "id": "r1", "graph_id": "g", "graph_version": "h", "status": "completed",
            "input": {}, "origin": "api", "created_at": 1.0,
        }
    )  # fmt: skip


def _event(i: int, path: list[str]) -> RunEvent:
    return RunEvent.model_validate(
        {
            "event_id": f"e{i}", "run_id": "r1", "seq": i + 1, "ts": float(i),
            "type": "log.info", "node_path": path, "payload": {},
        }
    )  # fmt: skip


def test_event_node_filter_matches_node_path(storage: Any) -> None:
    storage.runs.save(_run())
    paths = [[], ["A"], ["B"], ["A", "x"], ["B", "A"], ["x"], ["AA"]]
    storage.events.append_many([_event(i, p) for i, p in enumerate(paths)])
    every = storage.events.list("r1")
    for node in ("A", "B", "x", "AA", "zz"):
        got = storage.events.list("r1", node=node)
        assert [e.seq for e in got] == [e.seq for e in every if node in e.node_path], node
    assert [e.seq for e in storage.events.list("r1", node="A", since_seq=2, limit=1)] == [4]
