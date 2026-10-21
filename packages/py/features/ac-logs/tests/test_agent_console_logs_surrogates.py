"""외톨이 서로게이트 방어(4R.14 후속): 수집 레코드·SQLite 색인 쓰기·수집기·보관본·HTML.

깨진 UTF-16 원문(예: JSON `"\\ud800"`)은 Python에서 외톨이 서로게이트 문자열이 되고, UTF-8로
인코딩되지 않아 직렬화·색인 쓰기·응답이 실패한다. 수집 단계에서 U+FFFD로 바꾼다.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_console_contracts.logs import LogEvent, LogLane, LogSettings
from agent_console_logs import (
    AgentInfo,
    IndexBatch,
    IndexRecord,
    LogFilter,
    LogIngestor,
    LogRegistries,
    QueryContext,
    build_archive,
    render_archive,
    scrub_surrogates,
)
from agent_console_logs.sqlite import open_log_index
from agent_console_logs.testing import MemoryLogIndex, make_record

LONE_HIGH = chr(0xD800)
LONE_LOW = chr(0xDC00)
FFFD = chr(0xFFFD)
BAD = f"a{LONE_HIGH}b{LONE_LOW}c"
GOOD = f"a{FFFD}b{FFFD}c"


def test_scrub_surrogates_walks_values_and_keeps_identity() -> None:
    assert scrub_surrogates(BAD) == GOOD
    nested = {BAD: [BAD, (BAD, 1)], "k": {"x": BAD}}
    assert scrub_surrogates(nested) == {GOOD: [GOOD, (GOOD, 1)], "k": {"x": GOOD}}
    clean = {"a": ["b", ("c",)], "n": 1}
    assert scrub_surrogates(clean) is clean
    lane = LogLane.model_construct(id=BAD, label=BAD, parent_id=None)  # 검증을 거치지 않은 값
    assert scrub_surrogates(lane) == LogLane(id=GOOD, label=GOOD)
    ok_lane = LogLane(id="x")
    assert scrub_surrogates(ok_lane) is ok_lane
    assert scrub_surrogates("한글 😀") == "한글 😀"  # 짝이 맞는 문자는 그대로


def _hostile_record() -> IndexRecord:
    return make_record(
        BAD,
        title=BAD,
        session=BAD,
        thread=BAD,
        tool=BAD,
        call_id=BAD,
        tags=(BAD, "tool"),
        detail={BAD: [BAD]},
        raw=BAD,
        summary=BAD,
        correlation={BAD: [BAD]},
        time=1.0,
        agent=AgentInfo.model_construct(id=BAD, label=BAD, parent_id=None),
    )


def test_build_record_scrubs_every_string() -> None:
    record = _hostile_record()
    dumped = record.event.model_dump_json(by_alias=True)  # 직렬화가 실패하지 않는다
    assert LONE_HIGH not in dumped
    dumped.encode("utf-8")
    event = record.event
    assert (event.title, event.session, event.thread, event.category) == (GOOD,) * 4
    assert event.detail == {GOOD: [GOOD]}
    assert GOOD in event.tags
    assert record.agent == AgentInfo(id=GOOD, label=GOOD)


def test_sqlite_index_write_and_query_with_surrogates(tmp_path: Path) -> None:
    index = open_log_index(tmp_path / "logs.sqlite3")
    try:
        assert index.write(IndexBatch(records=[_hostile_record()])).inserted == 1
        ctx = QueryContext()
        items = index.query_events(LogFilter(session=(GOOD,)), ctx).items
        assert [e.title for e in items] == [GOOD]
        detail = index.get_event(items[0].uid, ctx)
        assert detail is not None
        assert detail.event.detail == {GOOD: [GOOD]}
        assert [s.session for s in index.list_sessions(LogFilter(), ctx)] == [GOOD]
        assert [lane.id for lane in index.lanes()] == [GOOD]
        archive = build_archive(index, LogFilter(), ctx, exported_at=0.0)
        archive.model_dump_json().encode("utf-8")
        render_archive(archive).encode("utf-8")
    finally:
        index.close()


def test_ingest_broken_utf16_escape_from_jsonl(tmp_path: Path) -> None:
    """jsonl의 `\\ud800`(짝 없는 이스케이프)를 읽어도 수집이 멈추지 않는다."""
    folder = tmp_path / "src"
    folder.mkdir()
    rows = [
        '{"schema_version": 1, "category": "input", "title": "x\\ud800y", "session": "S"}',
        '{"schema_version": 1, "category": "llm", "title": "ok", "session": "S"}',
    ]
    (folder / "a.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert json.loads(rows[0])["title"] == f"x{LONE_HIGH}y"
    registries = LogRegistries()
    registries.load()
    index = open_log_index(tmp_path / "logs.sqlite3")
    try:
        settings = LogSettings.model_validate(
            {
                "sources": [
                    {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}
                ]
            }
        )
        report = LogIngestor(index, registries).scan(settings)
        assert report.new_events == 2
        titles = [e.title for e in index.query_events(LogFilter(), QueryContext()).items]
        assert titles == [f"x{FFFD}y", "ok"]
    finally:
        index.close()


def test_archive_defends_events_from_other_index_implementations() -> None:
    """build_record를 거치지 않은 이벤트(다른 색인 구현)도 보관본·HTML이 실패하지 않는다."""
    base = make_record("t", title="t", session="S", time=1.0)
    raw_event = base.event.model_copy(update={"title": BAD, "detail": {BAD: BAD}})
    index = MemoryLogIndex()
    index.write(IndexBatch(records=[IndexRecord(event=raw_event, identity=base.identity)]))
    archive = build_archive(index, LogFilter(), QueryContext(), exported_at=0.0)
    assert archive.events[0].title == GOOD
    assert archive.events[0].detail == {GOOD: GOOD}
    archive.model_dump_json().encode("utf-8")
    page = render_archive(archive, title=BAD)
    page.encode("utf-8")
    assert isinstance(
        LogEvent.model_validate(archive.events[0].model_dump(by_alias=True)), LogEvent
    )


def test_fast_path_types_and_detection() -> None:
    """정확한 타입 빠른 경로와 일반 타입(str 하위 클래스·Mapping) 경로가 같은 결과를 낸다."""
    from collections import OrderedDict
    from types import MappingProxyType

    from agent_console_logs import dirty_surrogates

    class Text(str):
        pass

    assert not dirty_surrogates(["ascii", "한글 😀", 1, 2.5, True, None, {"k": ("v",)}])
    assert dirty_surrogates({"k": [1, {"x": BAD}]})
    assert dirty_surrogates(Text(BAD))
    assert scrub_surrogates(Text(BAD)) == GOOD
    proxy = MappingProxyType({"a": BAD})
    assert scrub_surrogates(proxy) == {"a": GOOD}
    ordered = OrderedDict(a="x")
    assert scrub_surrogates(ordered) is ordered
    lane = LogLane.model_construct(id="x", label=None, parent_id=BAD)
    assert dirty_surrogates(lane)
    assert scrub_surrogates(lane).parent_id == GOOD
