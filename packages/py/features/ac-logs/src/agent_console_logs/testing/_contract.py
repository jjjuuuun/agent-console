"""`LogIndex` 계약 테스트 묶음. 구현마다 상속해 `make_index`만 채운다.

```python
class TestSqliteLogIndex(LogIndexContractTests):
    def make_index(self) -> LogIndex:
        return open_log_index(tmp_path / "logs.sqlite3")
```

pytest가 `test_` 메서드를 모은다(이 클래스 이름은 `Test`로 시작하지 않아 직접 모이지 않는다).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from typing import Any

from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogDocumentRef,
    LogLane,
    LogProjectGroup,
    LogProjectSettings,
    TokenSample,
)
from agent_console_logs._build import build_record
from agent_console_logs._draft import TAG_SESSION_TITLE, TAG_TOOL, LogEventDraft
from agent_console_logs._filter import LogFilter, LogQueryError, QueryContext
from agent_console_logs._index import IndexBatch, IndexRecord, LogIndex, StoredCursor
from agent_console_logs._projects import UNGROUPED_PROJECT

__all__ = ["LogIndexContractTests", "make_record"]

_counter = {"n": 0}


def make_record(
    category: str = "other",
    *,
    source: str = "test",
    origin: str = "f.jsonl",
    offset: int | None = None,
    observed_at: float = 1_000.0,
    repo_root: str = "",
    **fields: Any,
) -> IndexRecord:
    """테스트용 레코드(초안 필드를 키워드로). offset을 생략하면 매번 다른 위치."""
    if offset is None:
        _counter["n"] += 1
        offset = _counter["n"]
    draft = LogEventDraft(category=category, **fields)
    return build_record(
        draft,
        source_id=source,
        origin=origin,
        offset=offset,
        index=0,
        observed_at=observed_at,
        repo_root=repo_root,
    )


def _ctx(**kw: Any) -> QueryContext:
    base: dict[str, Any] = {"error_categories": frozenset({"error"}), "tz": UTC}
    base.update(kw)
    return QueryContext(**base)


class LogIndexContractTests:
    """`LogIndex` 구현이 지켜야 할 질의 의미(MemoryLogIndex와 같음)."""

    def make_index(self) -> LogIndex:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def _filled(self, records: list[IndexRecord]) -> LogIndex:
        index = self.make_index()
        index.write(IndexBatch(records=records))
        return index

    # ---------------------------------------------------------------- 쓰기

    def test_protocol(self) -> None:
        assert isinstance(self.make_index(), LogIndex)

    def test_insert_is_idempotent_by_identity(self) -> None:
        index = self.make_index()
        rec = make_record("llm", origin="a", offset=1, title="x")
        first = index.write(IndexBatch(records=[rec]))
        again = index.write(IndexBatch(records=[rec, rec]))
        assert first.inserted == 1
        assert again.inserted == 0
        assert index.max_seq() == first.max_seq

    def test_empty_index(self) -> None:
        index = self.make_index()
        assert index.max_seq() is None
        page = index.query_events(LogFilter(), _ctx())
        assert page.items == []
        assert page.next_cursor is None
        assert index.list_sessions(LogFilter(), _ctx()) == []
        assert index.timeline("nope", _ctx()) is None
        assert index.get_event("nope", _ctx()) is None
        assert index.aggregate(LogAggregateRequest(metric="events"), _ctx()) == []

    def test_cursor_written_with_batch(self) -> None:
        index = self.make_index()
        cur = StoredCursor(source="s", ref="a.jsonl", offset=42, size=50, mtime=1.5, state={"k": 1})
        index.write(IndexBatch(records=[make_record(source="s")], cursors=[cur]))
        got = index.get_cursor("s", "a.jsonl")
        assert got is not None
        assert (got.offset, got.size, got.mtime, dict(got.state)) == (42, 50, 1.5, {"k": 1})
        index.write(IndexBatch(cursors=[StoredCursor(source="s", ref="a.jsonl", offset=60)]))
        assert index.get_cursor("s", "a.jsonl").offset == 60  # type: ignore[union-attr]
        index.write(IndexBatch(cursors=[StoredCursor(source="s", ref="b.jsonl")]))
        assert [c.ref for c in index.list_cursors("s")] == ["a.jsonl", "b.jsonl"]
        assert index.list_cursors("other") == []
        assert index.get_cursor("s", "zzz") is None

    def test_tokens_counted_once_per_message(self) -> None:
        """R8.1: 같은 응답(message_id)이 여러 행이어도 최대 output 1회만 센다."""
        rows = [
            make_record(
                "llm",
                session="S",
                thread="T",
                model="m1",
                message_id="msg_1",
                time=10.0 + i,
                usage=TokenSample(input_tokens=100, output_tokens=out, cache_read_input_tokens=7),
            )
            for i, out in enumerate((5, 20, 12))
        ]
        index = self._filled(rows)
        ctx = _ctx()
        result = index.aggregate(
            LogAggregateRequest(group_by=["model"], metric="tokens.output"), ctx
        )
        assert [(r.keys, r.value) for r in result] == [({"model": "m1"}, 20.0)]
        total = index.aggregate(LogAggregateRequest(metric="tokens.total"), ctx)
        assert total[0].value == 127.0
        samples = index.token_samples(LogFilter(), ctx)
        assert len(samples) == 1
        assert samples[0].output_tokens == 20
        sessions = index.list_sessions(LogFilter(), ctx)
        assert sessions[0].tokens is not None
        assert sessions[0].tokens.input == 100
        assert sessions[0].tokens.output == 20

    def test_token_metric_without_values_is_null(self) -> None:
        index = self._filled(
            [make_record("llm", session="S", thread="T", message_id="m", usage=TokenSample())]
        )
        rows = index.aggregate(LogAggregateRequest(metric="tokens.total"), _ctx())
        assert [r.value for r in rows] == [None]
        assert index.list_sessions(LogFilter(), _ctx())[0].tokens is None

    # ---------------------------------------------------------------- 목록

    def _sample(self) -> LogIndex:
        return self._filled(
            [
                make_record(
                    "input",
                    source="a",
                    session="S1",
                    thread="main",
                    actor="user",
                    title="Hello World",
                    time=100.0,
                    cwd="/w/proj",
                    tags=(TAG_SESSION_TITLE,),
                ),
                make_record(
                    "tool_call",
                    source="a",
                    session="S1",
                    thread="main",
                    actor="main",
                    tool="Bash",
                    call_id="c1",
                    stage="start",
                    tags=(TAG_TOOL,),
                    time=101.0,
                    cwd="/w/proj",
                    detail={"cmd": "ls"},
                    raw={"cmd": "ls"},
                ),
                make_record(
                    "tool_result",
                    source="a",
                    session="S1",
                    thread="main",
                    actor="main",
                    tool="Bash",
                    call_id="c1",
                    stage="complete",
                    tags=(TAG_TOOL,),
                    time=101.5,
                    cwd="/w/proj",
                ),
                make_record(
                    "handoff",
                    source="a",
                    session="S1",
                    thread="main",
                    actor="main",
                    from_=("main",),
                    to=("sub",),
                    via="Task",
                    time=102.0,
                    cwd="/w/proj",
                ),
                make_record(
                    "error",
                    source="b",
                    session="S2",
                    thread="x",
                    actor="x",
                    status="failed",
                    time=200.0,
                    cwd="/other",
                ),
                make_record("other", source="b", session="", time=None, observed_at=150.0),
            ]
        )

    def test_filter_values_and_links(self) -> None:
        index = self._sample()
        ctx = _ctx()

        def titles(**kw: Any) -> list[str]:
            return [e.category for e in index.query_events(LogFilter(**kw), ctx).items]

        assert titles(source=("b",)) == ["error", "other"]
        assert titles(category=("tool",)) == ["tool_call", "tool_result"]
        assert titles(agent=("sub",)) == ["handoff"]
        assert titles(from_=("main",), to=("sub",)) == ["handoff"]
        assert titles(to=("main",)) == []
        assert titles(tool=("Bash",), stage=("complete",)) == ["tool_result"]
        assert titles(session=("S1", "S2"), status=("failed",)) == ["error"]
        assert titles(q="hello world") == ["input"]
        assert titles(since=101.0, until=102.0) == ["tool_call", "tool_result"]
        assert titles(since=150.0, until=151.0) == ["other"]  # 시각 없으면 색인 시각
        assert titles(cwd=("/other",)) == ["error"]

    def test_project_filter(self) -> None:
        index = self._sample()
        groups = LogProjectSettings(groups=[LogProjectGroup(id="p", match=["/w/**"])])
        ctx = _ctx(projects=groups)
        got = index.query_events(LogFilter(project=("p",)), ctx).items
        assert {e.session for e in got} == {"S1"}
        rest = index.query_events(LogFilter(project=(UNGROUPED_PROJECT,)), ctx).items
        assert {e.category for e in rest} == {"error", "other"}
        own = index.query_events(LogFilter(project=("/other",)), ctx).items
        assert [e.category for e in own] == ["error"]

    def test_keyset_pages_and_order(self) -> None:
        index = self._sample()
        ctx = _ctx()
        seen: list[int] = []
        flt = LogFilter(limit=2)
        while True:
            page = index.query_events(flt, ctx, with_total=True)
            assert page.total == 6
            seen += [e.seq for e in page.items]
            assert all(e.detail is None and e.raw is None for e in page.items)
            if page.next_cursor is None:
                break
            flt = flt.with_(cursor=page.next_cursor)
        assert seen == sorted(seen)
        assert len(seen) == 6
        desc = index.query_events(LogFilter(order="desc", limit=3), ctx)
        assert [e.seq for e in desc.items] == sorted(seen, reverse=True)[:3]
        nxt = index.query_events(LogFilter(order="desc", limit=3, cursor=desc.next_cursor), ctx)
        assert [e.seq for e in nxt.items] == sorted(seen, reverse=True)[3:]
        assert nxt.next_cursor is None

    # ---------------------------------------------------------------- 상세

    def test_detail_related_evidence_usage(self) -> None:
        index = self._filled(
            [
                make_record(
                    "tool_call",
                    thread="T",
                    call_id="c9",
                    stage="start",
                    tags=(TAG_TOOL,),
                    detail={"big": "x" * 500},
                    message_id="m1",
                    usage=TokenSample(output_tokens=3),
                ),
                make_record(
                    "tool_result", thread="T", call_id="c9", stage="complete", tags=(TAG_TOOL,)
                ),
                make_record("other", thread="U", correlation={"session": "S"}),
                make_record("other", thread="V", correlation={"session": "S"}),
            ]
        )
        ctx = _ctx()
        first = index.query_events(LogFilter(category=("tool_call",)), ctx).items[0]
        detail = index.get_event(first.uid, ctx, max_detail_bytes=100)
        assert detail is not None
        assert detail.event.detail is not None
        assert detail.detail_truncated is True
        assert [e.category for e in detail.related] == ["tool_result"]
        assert [link.basis for link in detail.evidence_links] == ["call_id"]
        assert detail.usage is not None
        assert detail.usage.output_tokens == 3
        assert detail.truncated is False
        full = index.get_event(first.uid, ctx)
        assert full is not None
        assert full.detail_truncated is False
        assert full.event.detail == {"big": "x" * 500}
        other = index.query_events(LogFilter(category=("other",)), ctx).items[0]
        few = index.get_event(other.uid, ctx, max_evidence=1)
        assert few is not None
        assert few.truncated is True

    # ---------------------------------------------------------------- 세션·타임라인

    def test_sessions(self) -> None:
        index = self._sample()
        ctx = _ctx()
        sessions = index.list_sessions(LogFilter(), ctx)
        assert [s.session for s in sessions] == ["S2", "S1"]  # 마지막 시각 내림차순
        s1 = sessions[1]
        assert s1.title == "Hello World"
        assert s1.events == 4
        assert s1.errors == 0
        assert s1.thread_count == 1
        assert (s1.first_time, s1.last_time) == (100.0, 102.0)
        assert s1.cwd == "/w/proj"
        assert s1.project is not None
        assert s1.project.id == "/w/proj"
        assert sessions[0].errors == 1
        assert sessions[0].title == ""
        assert index.list_sessions(LogFilter(limit=1), ctx)[0].session == "S2"
        assert [s.session for s in index.list_sessions(LogFilter(source=("a",)), ctx)] == ["S1"]

    def test_errors_follow_taxonomy_only(self) -> None:
        """F-25: 오류는 tone=danger 범주만. 범주 이름·status로 추측하지 않는다."""
        index = self._sample()
        none = index.list_sessions(LogFilter(), _ctx(error_categories=frozenset()))
        assert all(s.errors == 0 for s in none)
        custom = index.list_sessions(LogFilter(), _ctx(error_categories=frozenset({"input"})))
        assert {s.session: s.errors for s in custom} == {"S1": 1, "S2": 0}

    def test_timeline(self) -> None:
        index = self.make_index()
        index.write(
            IndexBatch(
                records=[
                    make_record("llm", session="S", thread="main", time=5.0, title="late"),
                    make_record(
                        "tool_call",
                        session="S",
                        thread="sub",
                        call_id="k",
                        stage="start",
                        time=1.0,
                        tags=(TAG_TOOL,),
                        agent=LogLane(id="sub", label="Explore", parent_id="main"),
                    ),
                    make_record(
                        "tool_result",
                        session="S",
                        thread="sub",
                        call_id="k",
                        stage="complete",
                        time=1.25,
                        tags=(TAG_TOOL,),
                    ),
                    make_record("secret", session="S", thread="main", time=2.0),
                    make_record("llm", session="S", thread="main", time=1.0, title="same-time"),
                ]
            )
        )
        ctx = _ctx(hidden_categories=frozenset({"secret"}))
        tl = index.timeline("S", ctx)
        assert tl is not None
        assert [e.category for e in tl.events] == ["tool_call", "llm", "tool_result", "llm"]
        assert [e.duration_ms for e in tl.events] == [250.0, None, 250.0, None]
        assert {lane.id: lane.parent_id for lane in tl.lanes} == {"sub": "main", "main": None}
        assert next(lane for lane in tl.lanes if lane.id == "sub").label == "Explore"
        assert tl.total == 4
        assert tl.truncated is False
        cut = index.timeline("S", ctx, limit=2)
        assert cut is not None
        assert len(cut.events) == 2
        assert cut.truncated is True
        assert index.lanes()[0].id == "sub"

    def test_list_fills_pair_durations(self) -> None:
        """4R.22: 목록 항목에도 타임라인과 같은 짝 소요 시간(필터와 상관없이 같은 세션의 짝)."""
        index = self.make_index()
        index.write(
            IndexBatch(
                records=[
                    make_record(
                        "hook", session="S", thread="m", call_id="h1", stage="start", time=1.0
                    ),
                    make_record(
                        "hook", session="S", thread="m", call_id="h1", stage="complete", time=1.5
                    ),
                    make_record(
                        "mcp", session="S", thread="m", call_id="c1", stage="start", time=2.0
                    ),
                    make_record(
                        "mcp", session="S", thread="m", call_id="c1", stage="complete", time=2.125
                    ),
                    make_record(
                        "mcp", session="T", thread="m", call_id="c1", stage="complete", time=9.0
                    ),
                    make_record("llm", session="S", thread="m", time=3.0),
                ]
            )
        )
        ctx = _ctx()
        page = index.query_events(LogFilter(session=("S",)), ctx)
        assert [e.duration_ms for e in page.items] == [500.0, 500.0, 125.0, 125.0, None]
        ends = index.query_events(LogFilter(stage=("complete",)), ctx)
        assert [(e.session, e.duration_ms) for e in ends.items] == [
            ("S", 500.0),
            ("S", 125.0),
            ("T", None),  # 다른 세션의 같은 thread·call_id와 짝짓지 않는다
        ]
        timeline = index.timeline("S", ctx)
        assert timeline is not None
        by_uid = {e.uid: e.duration_ms for e in timeline.events}
        assert all(by_uid[e.uid] == e.duration_ms for e in page.items)

    # ---------------------------------------------------------------- 집계

    def test_aggregate_counts(self) -> None:
        index = self._sample()
        ctx = _ctx()
        by_source = index.aggregate(LogAggregateRequest(group_by=["source"], metric="events"), ctx)
        assert [(r.keys["source"], r.value) for r in by_source] == [("a", 4.0), ("b", 2.0)]
        calls = index.aggregate(LogAggregateRequest(metric="tool_calls"), ctx)
        assert [r.value for r in calls] == [1.0]
        errors = index.aggregate(LogAggregateRequest(group_by=["session"], metric="errors"), ctx)
        assert [(r.keys["session"], r.value) for r in errors] == [("S2", 1.0)]
        dur = index.aggregate(LogAggregateRequest(group_by=["tool"], metric="duration_ms.sum"), ctx)
        assert [(r.keys["tool"], r.value) for r in dur] == [("Bash", 500.0)]
        days = index.aggregate(
            LogAggregateRequest(group_by=["day"], metric="events", filter={"source": "a"}), ctx
        )
        assert [(r.keys["day"], r.value) for r in days] == [("1970-01-01", 4.0)]
        tags = index.aggregate(
            LogAggregateRequest(group_by=["tag"], metric="events", filter={"category": "tool"}),
            ctx,
        )
        assert {r.keys["tag"]: r.value for r in tags} == {
            "tool": 2.0,
            "tool_call": 1.0,
            "tool_result": 1.0,
        }

    def test_aggregate_rejects_unknown_names(self) -> None:
        index = self._sample()
        for request, path in (
            (LogAggregateRequest(group_by=["nope"], metric="events"), "group_by.0"),
            (LogAggregateRequest(metric="nope"), "metric"),
            (LogAggregateRequest(metric="events", filter={"nope": "x"}), "filter.nope"),
            (LogAggregateRequest(metric="events", tz="No/Such_Zone"), "tz"),
        ):
            got: str | None = None
            try:
                index.aggregate(request, _ctx())
            except LogQueryError as exc:
                got = exc.path
            assert got == path, request

    def test_aggregate_tokens_with_event_filter(self) -> None:
        index = self._filled(
            [
                make_record(
                    "llm", thread="T", message_id="a", usage=TokenSample(output_tokens=1), tool=""
                ),
                make_record(
                    "tool_call",
                    thread="T",
                    message_id="b",
                    tool="Read",
                    usage=TokenSample(output_tokens=10),
                ),
            ]
        )
        ctx = _ctx()
        all_rows = index.aggregate(LogAggregateRequest(metric="tokens.output"), ctx)
        assert [r.value for r in all_rows] == [11.0]
        only = index.aggregate(
            LogAggregateRequest(metric="tokens.output", filter={"tool": "Read"}), ctx
        )
        assert [r.value for r in only] == [10.0]

    # ---------------------------------------------------------------- handoff·보존

    def test_handoffs(self) -> None:
        index = self._sample()
        matrix = index.handoffs(LogFilter(), _ctx())
        assert [(c.from_, c.to, c.via, c.count) for c in matrix.cells] == [
            ("main", "sub", "Task", 1)
        ]

    def test_prune(self) -> None:
        index = self._sample()
        removed = index.prune(150.5)
        assert removed == 5  # 시각 100~102 네 개 + 색인 시각 150 하나
        left = index.query_events(LogFilter(), _ctx()).items
        assert [e.category for e in left] == ["error"]

    def test_documents_roundtrip(self) -> None:
        doc = LogDocumentRef(path="SKILL.md", kind="skill", action="read")
        index = self._filled(
            [make_record("document", documents=(doc,), correlation={"x": ["1", "2"]})]
        )
        ev = index.query_events(LogFilter(), _ctx()).items[0]
        assert ev.documents == [doc]
        assert ev.correlation == {"x": ["1", "2"]}
        detail = index.get_event(ev.uid, _ctx())
        assert detail is not None
        assert isinstance(detail.event.correlation, Mapping)
