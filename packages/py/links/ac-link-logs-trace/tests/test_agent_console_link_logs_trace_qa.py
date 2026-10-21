"""QA 추가: 2단계 위임·병렬 위임·3줄 순환·같은 호출 id 소유자 둘."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.logs import LogEvent
from agent_console_link_logs_trace import build_log_trace


def _ev(seq: int, thread: str, **f: Any) -> LogEvent:
    return LogEvent.model_validate(
        {
            "uid": f"u{seq}",
            "seq": seq,
            "source": "t",
            "observed_at": 1000.0 + seq,
            "category": "other",
            "thread": thread,
            "session": "s",
            "time": float(seq),
            **f,
        }
    )


def _parents(events: list[LogEvent]) -> dict[str, str | None]:
    return {s.id: s.parent_id for s in build_log_trace(events).spans}


def test_two_level_delegation() -> None:
    events = [
        _ev(1, "main", call_id="c1"),
        _ev(2, "mid", correlation={"tool_use_id": "c1"}),
        _ev(3, "mid", call_id="c2"),
        _ev(4, "leaf", correlation={"tool_use_id": "c2"}),
        _ev(5, "mid", call_id="c2", stage="complete", status="completed", summary="끝"),
    ]
    trace = build_log_trace(events)
    assert _parents(events) == {
        "thread:main": None,
        "thread:mid": "thread:main",
        "thread:leaf": "thread:mid",
    }
    leaf = next(s for s in trace.spans if s.id == "thread:leaf")
    assert (leaf.tool_use_id, leaf.result_preview, leaf.status) == ("c2", "끝", "completed")


def test_parallel_delegation_siblings() -> None:
    events = [
        _ev(1, "main", call_id="c1"),
        _ev(2, "main", call_id="c2"),
        _ev(3, "a", correlation={"tool_use_id": "c1"}),
        _ev(4, "b", correlation={"tool_use_id": "c2"}),
        _ev(5, "a", summary="x"),
    ]
    assert _parents(events) == {
        "thread:main": None,
        "thread:a": "thread:main",
        "thread:b": "thread:main",
    }


def test_three_cycle_all_unlinked() -> None:
    events = [
        _ev(1, "a", call_id="x", correlation={"tool_use_id": "z"}),
        _ev(2, "b", call_id="y", correlation={"tool_use_id": "x"}),
        _ev(3, "c", call_id="z", correlation={"tool_use_id": "y"}),
    ]
    assert set(_parents(events).values()) == {None}


def test_call_id_owned_by_two_threads_is_ambiguous() -> None:
    events = [
        _ev(1, "a", call_id="x"),
        _ev(2, "b", call_id="x"),
        _ev(3, "sub", correlation={"tool_use_id": "x"}),
    ]
    assert _parents(events)["thread:sub"] is None
