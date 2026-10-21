"""5R.19: 목록 `duration_ms` 짝 질의의 색인 사용, 세션 제목 순위 규칙(데이터), 기본 숨김 범주."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts.logs import LogTaxonomy
from agent_console_logs import (
    DEFAULT_SESSION_TITLE_RULES,
    TAG_SESSION_TITLE,
    LogFilter,
    QueryContext,
    SessionTitleRule,
    load_default_session_title_rules,
    load_default_taxonomy,
    parse_session_title_rules,
    pick_session_title,
    query_context,
)
from agent_console_logs._index import IndexBatch
from agent_console_logs.sqlite import SqliteLogIndex, create_log_engine, log_metadata
from agent_console_logs.testing import MemoryLogIndex, make_record

PAIR_MARK = "(log_events.thread, log_events.call_id) IN"


# ---------------------------------------------------------------- 짝 질의 실행 계획


@pytest.fixture
def traced(tmp_path: Path) -> Iterator[tuple[SqliteLogIndex, Path, list[tuple[str, Any]]]]:
    path = tmp_path / "plan.sqlite3"
    engine = create_log_engine(path)
    log_metadata.create_all(engine)
    seen: list[tuple[str, Any]] = []

    def capture(_conn: Any, _cursor: Any, statement: str, params: Any, *_: Any) -> None:
        if PAIR_MARK in statement:
            seen.append((statement, params))

    sa.event.listen(engine, "before_cursor_execute", capture)
    index = SqliteLogIndex(engine, owns_engine=True)
    records = []
    for i in range(400):
        call = f"c{i // 2}"
        records.append(
            make_record(
                "tool_call" if i % 2 == 0 else "tool_result",
                session=f"S{(i // 2) % 4}",
                thread="main" if (i // 2) % 3 else "sub",
                call_id=call,
                stage="start" if i % 2 == 0 else "complete",
                time=1000.0 + i,
                title=f"e{i}",
            )
        )
    index.write(IndexBatch(records=records))
    with engine.connect() as conn:
        conn.exec_driver_sql("ANALYZE")
    yield index, path, seen
    index.close()


def _plan(path: Path, statement: str, params: Any) -> list[str]:
    with sqlite3.connect(path) as raw:
        rows = raw.execute("EXPLAIN QUERY PLAN " + statement, params).fetchall()
    return [str(r[-1]) for r in rows]


def test_list_duration_pair_query_uses_thread_call_index(traced: Any) -> None:
    index, path, seen = traced
    page = index.query_events(LogFilter(limit=50), QueryContext())
    assert any(e.duration_ms is not None for e in page.items)  # 짝 질의가 실제로 돌았다
    assert seen, "짝 질의가 실행되지 않았다"
    for statement, params in seen:
        plan = _plan(path, statement, params)
        assert any("ix_log_events_thread_call" in step for step in plan), plan
        assert not any(step.startswith("SCAN log_events") for step in plan), plan


def test_timeline_duration_pair_query_uses_thread_call_index(traced: Any) -> None:
    index, path, seen = traced
    timeline = index.timeline("S1", QueryContext())
    assert timeline is not None
    for statement, params in seen:
        plan = _plan(path, statement, params)
        assert any("ix_log_events_thread_call" in step for step in plan), plan


# ---------------------------------------------------------------- 세션 제목 순위


class _E:
    def __init__(self, title: str, *tags: str) -> None:
        self.title = title
        self.tags = tags


def test_pick_session_title_follows_rules_in_order() -> None:
    events = [
        _E("첫 입력", TAG_SESSION_TITLE),
        _E("자동1", TAG_SESSION_TITLE, "session_title.generated"),
        _E("이름1", TAG_SESSION_TITLE, "session_title.renamed"),
        _E("자동2", TAG_SESSION_TITLE, "session_title.generated"),
        _E("", "session_title.renamed"),  # 빈 제목은 후보가 아니다
    ]
    rules = load_default_session_title_rules()
    assert pick_session_title(events, rules) == "이름1"
    assert pick_session_title(events[:2] + events[3:], rules) == "자동2"
    assert pick_session_title(events[:1], rules) == "첫 입력"
    assert pick_session_title(events, DEFAULT_SESSION_TITLE_RULES) == "첫 입력"  # 4R 동작
    assert pick_session_title(events, ()) == ""


def test_session_title_rules_file_is_data(tmp_path: Path) -> None:
    assert load_default_session_title_rules() == (
        SessionTitleRule("session_title.renamed", "last"),
        SessionTitleRule("session_title.generated", "last"),
        SessionTitleRule(TAG_SESSION_TITLE, "first"),
    )
    # 지우거나 비우면 코어 기본(태그 session_title의 첫 후보)
    assert load_default_session_title_rules(tmp_path / "none.yaml") == DEFAULT_SESSION_TITLE_RULES
    (tmp_path / "e.yaml").write_text("", encoding="utf-8")
    assert load_default_session_title_rules(tmp_path / "e.yaml") == DEFAULT_SESSION_TITLE_RULES
    (tmp_path / "c.yaml").write_text("rules: [{tag: mine}]\n", encoding="utf-8")
    assert load_default_session_title_rules(tmp_path / "c.yaml") == (SessionTitleRule("mine"),)


@pytest.mark.parametrize(
    "data",
    [{"rules": "x"}, [{"tag": ""}], [{"tag": "a", "pick": "middle"}], ["a"]],
)
def test_bad_session_title_rules_are_rejected(data: Any) -> None:
    with pytest.raises(ValueError, match="세션 제목 규칙"):
        parse_session_title_rules(data)


def test_query_context_takes_rules_and_memory_index_uses_them() -> None:
    index = MemoryLogIndex()
    index.write(
        IndexBatch(
            records=[
                make_record(
                    "input", session="S", time=1.0, title="입력", tags=(TAG_SESSION_TITLE,)
                ),
                make_record(
                    "meta",
                    session="S",
                    time=2.0,
                    title="자동",
                    tags=(TAG_SESSION_TITLE, "session_title.generated"),
                ),
            ]
        )
    )
    [default] = index.list_sessions(LogFilter(), query_context(None))
    assert default.title == "자동"
    old = query_context(None, session_title_rules=DEFAULT_SESSION_TITLE_RULES)
    [first] = index.list_sessions(LogFilter(), old)
    assert first.title == "입력"


# ---------------------------------------------------------------- 기본 숨김 범주


def test_default_taxonomy_has_hidden_meta_category() -> None:
    tax = load_default_taxonomy()
    assert tax.categories["meta"].visible is False
    assert "meta" in query_context(None).hidden_categories


def test_meta_events_hidden_from_timeline_but_listed() -> None:
    index = MemoryLogIndex()
    index.write(
        IndexBatch(
            records=[
                make_record("input", session="S", time=1.0, title="입력"),
                make_record("meta", session="S", time=2.0, title="대기열"),
            ]
        )
    )
    ctx = query_context(None)
    timeline = index.timeline("S", ctx)
    assert timeline is not None
    assert [e.title for e in timeline.events] == ["입력"]
    assert {e.title for e in index.query_events(LogFilter(), ctx).items} == {"입력", "대기열"}
    # 분류 체계를 비워도 동작한다(숨김 없음)
    empty = query_context(None, base_taxonomy=LogTaxonomy())
    assert empty.hidden_categories == frozenset()
    full = index.timeline("S", empty)
    assert full is not None
    assert [e.title for e in full.events] == ["입력", "대기열"]
