"""build_log_trace: span = 줄, 부모 = 명시 연결 키, 링크 = from→to, 명시 id 없으면 부모 없음."""

from __future__ import annotations

from typing import Any

import pytest

from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_trace import (
    SPAN_KIND_THREAD,
    build_log_trace,
    thread_span_id,
)
from agent_console_trace import SPAN_KIND_DELEGATED

SESSION = "s1"


def _ev(seq: int, thread: str, **fields: Any) -> LogEvent:
    data: dict[str, Any] = {
        "uid": f"u{seq}",
        "seq": seq,
        "source": "test",
        "observed_at": 1000.0 + seq,
        "category": fields.pop("category", "other"),
        "thread": thread,
        "session": fields.pop("session", SESSION),
        "time": fields.pop("time", float(seq)),
        **fields,
    }
    return LogEvent.model_validate(data)


def _delegation(call: str = "c1", *, sub: str = "sub", corr: Any = None) -> list[LogEvent]:
    """메인이 sub에게 위임하고(호출·수신·결과) 돌아오는 이벤트."""
    return [
        _ev(1, "main", summary="시작"),
        _ev(2, "main", call_id=call, stage="start", via="Task", **{"from": ["main"]}, to=[sub]),
        _ev(
            3,
            sub,
            role="reviewer",
            summary="문서를 검토해 줘",
            correlation={"tool_use_id": corr if corr is not None else call},
            **{"from": ["main"]},
            to=[sub],
        ),
        _ev(4, sub, summary="검토 중"),
        _ev(
            5,
            "main",
            call_id=call,
            stage="complete",
            status="completed",
            summary="검토 완료",
            via="Task",
            **{"from": [sub]},
            to=["main"],
        ),
    ]


def test_threads_become_spans_and_call_id_links_parent() -> None:
    trace = build_log_trace(_delegation())
    assert trace.run_id == SESSION
    spans = {s.id: s for s in trace.spans}
    assert list(spans) == [thread_span_id("main"), thread_span_id("sub")]
    main, sub = spans["thread:main"], spans["thread:sub"]
    assert main.kind == SPAN_KIND_THREAD
    assert main.parent_id is None
    assert (main.started_at, main.ended_at) == (1.0, 5.0)
    assert sub.kind == SPAN_KIND_DELEGATED
    assert sub.parent_id == "thread:main"
    assert sub.tool_use_id == "c1"
    assert sub.actor == "reviewer"
    assert sub.session_id == SESSION
    assert (sub.started_at, sub.ended_at) == (3.0, 4.0)
    assert sub.task_preview == "문서를 검토해 줘"
    assert sub.result_preview == "검토 완료"
    assert sub.status == "completed"


def test_from_to_become_links_deduplicated_by_call() -> None:
    trace = build_log_trace(_delegation())
    assert [(lk.source, lk.target, lk.edge_id, lk.kind) for lk in trace.links] == [
        ("thread:main", "thread:sub", "c1", "Task"),  # 호출 + 수신 = 하나
        ("thread:sub", "thread:main", "c1", "Task"),
    ]


def test_without_explicit_id_span_stays_parentless() -> None:
    """시간상 바로 뒤에 시작한 줄이라도 연결 키가 없으면 부모 없이 남긴다."""
    events = [
        _ev(1, "main", call_id="c1", stage="start", **{"from": ["main"]}, to=["sub"]),
        _ev(2, "sub", summary="수신"),  # correlation 없음
    ]
    trace = build_log_trace(events)
    sub = next(s for s in trace.spans if s.id == "thread:sub")
    assert sub.parent_id is None
    assert sub.kind == SPAN_KIND_THREAD
    assert sub.tool_use_id is None
    # from/to는 명시 값이므로 링크는 남는다
    assert [(lk.source, lk.target) for lk in trace.links] == [("thread:main", "thread:sub")]


def test_correlation_to_own_call_is_not_a_parent() -> None:
    """같은 줄의 hook 이벤트가 자기 도구 호출 id를 실어도 부모가 되지 않는다."""
    events = [
        _ev(1, "main", call_id="t1", stage="start", tool="Read"),
        _ev(2, "main", category="hook", correlation={"tool_use_id": "t1"}),
    ]
    [span] = build_log_trace(events).spans
    assert span.parent_id is None


def test_ambiguous_parent_left_unlinked() -> None:
    events = [
        _ev(1, "a", call_id="x"),
        _ev(2, "b", call_id="y"),
        _ev(3, "sub", correlation={"tool_use_id": ["x", "y"]}),
    ]
    sub = next(s for s in build_log_trace(events).spans if s.id == "thread:sub")
    assert sub.parent_id is None


def test_list_correlation_and_unique_owner() -> None:
    events = [_ev(1, "a", call_id="x"), _ev(2, "sub", correlation={"tool_use_id": ["x", "z"]})]
    sub = next(s for s in build_log_trace(events).spans if s.id == "thread:sub")
    assert sub.parent_id == "thread:a"
    assert sub.task_preview is None  # 수신 이벤트에 본문 없음


def test_cycle_is_left_unlinked() -> None:
    """서로를 부모로 가리키면(순환) 어느 쪽도 고르지 않는다. 순환으로 들어가는 줄은 유지한다."""
    events = [
        _ev(1, "a", call_id="x"),
        _ev(2, "b", call_id="y"),
        _ev(3, "b", correlation={"tool_use_id": "x"}),
        _ev(4, "a", correlation={"tool_use_id": "y"}),
        _ev(5, "c", correlation={"tool_use_id": "y"}),
    ]
    parents = {s.id: s.parent_id for s in build_log_trace(events).spans}
    assert parents == {"thread:a": None, "thread:b": None, "thread:c": "thread:b"}


def test_link_keys_are_data() -> None:
    events = _delegation(corr="c1")
    renamed = [
        e.model_copy(update={"correlation": {"delegation": "c1"}}) if e.correlation else e
        for e in events
    ]
    default = {s.id: s.parent_id for s in build_log_trace(renamed).spans}
    assert default["thread:sub"] is None
    custom = {s.id: s.parent_id for s in build_log_trace(renamed, link_keys=["delegation"]).spans}
    assert custom["thread:sub"] == "thread:main"


def test_unknown_endpoints_and_threadless_events_are_skipped() -> None:
    events = [
        _ev(1, "main", call_id="c1", **{"from": ["main"]}, to=["reviewer"]),  # 줄이 아닌 이름
        _ev(2, "", summary="줄 없음"),
    ]
    trace = build_log_trace(events)
    assert [s.id for s in trace.spans] == ["thread:main"]
    assert trace.links == []


def test_order_is_time_then_seq_and_missing_time_uses_observed() -> None:
    events = [_ev(2, "late", time=50.0), _ev(1, "early", time=None)]  # observed_at 1001
    spans = build_log_trace(events).spans
    assert [s.id for s in spans] == ["thread:late", "thread:early"]
    assert spans[1].started_at is None  # 원본 시각이 없으면 지어내지 않는다


def test_session_required() -> None:
    with pytest.raises(ValueError, match="세션"):
        build_log_trace([_ev(1, "main", session="")])
    assert build_log_trace([], session="s").model_dump(exclude_none=True) == {
        "run_id": "s",
        "spans": [],
        "links": [],
    }
