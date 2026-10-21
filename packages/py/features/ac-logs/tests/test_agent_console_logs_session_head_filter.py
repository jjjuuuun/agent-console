"""5.2R.38(B-2): 필터는 세션 포함 여부만 정한다. 제목·첫 cwd는 세션 id 조건만으로 고른다.

제목 행(`ai-title`·`custom-title`)에는 cwd·actor가 없어서, 필터 조건을 제목 선택에도 붙이면
프로젝트·에이전트·기간 필터를 걸 때 제목이 첫 입력으로 바뀌었다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_console_logs import TAG_SESSION_TITLE, LogFilter, query_context
from agent_console_logs._index import IndexBatch, LogIndex
from agent_console_logs.sqlite import SqliteLogIndex, create_log_engine, log_metadata
from agent_console_logs.testing import MemoryLogIndex, make_record

GENERATED = "session_title.generated"
RENAMED = "session_title.renamed"


def _records() -> list[object]:
    return [
        make_record(
            "input",
            session="S",
            time=1.0,
            cwd="/w/a",
            actor="main",
            thread="main",
            title="첫 입력",
            tags=(TAG_SESSION_TITLE,),
        ),
        # 제목 행: cwd·actor·thread가 없다(Claude Code ai-title·custom-title과 같다)
        make_record(
            "meta", session="S", time=2.0, title="자동 제목", tags=(TAG_SESSION_TITLE, GENERATED)
        ),
        make_record(
            "meta", session="S", time=2.5, title="고친 제목", tags=(TAG_SESSION_TITLE, RENAMED)
        ),
        make_record("tool_call", session="S", time=3.0, cwd="/w/a", actor="main", thread="main"),
        make_record("tool_call", session="S", time=4.0, cwd="/w/b", actor="main", thread="main"),
        make_record("input", session="T", time=5.0, cwd="/w/c", actor="other", title="다른 세션"),
    ]


@pytest.fixture(params=["memory", "sqlite"])
def index(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[LogIndex]:
    if request.param == "memory":
        idx: LogIndex = MemoryLogIndex()
    else:
        engine = create_log_engine(tmp_path / "head.sqlite3")
        log_metadata.create_all(engine)
        idx = SqliteLogIndex(engine, owns_engine=True)
    idx.write(IndexBatch(records=_records()))  # type: ignore[arg-type]
    yield idx
    close = getattr(idx, "close", None)
    if close is not None:
        close()


def _session(index: LogIndex, flt: LogFilter) -> tuple[str, str, int] | None:
    found = [s for s in index.list_sessions(flt, query_context(None)) if s.session == "S"]
    if not found:
        return None
    s = found[0]
    return s.title, s.cwd, s.events


def test_unfiltered_title_and_cwd(index: LogIndex) -> None:
    assert _session(index, LogFilter()) == ("고친 제목", "/w/a", 5)


def test_project_filter_keeps_title(index: LogIndex) -> None:
    ctx = query_context(None)
    [summary] = [s for s in index.list_sessions(LogFilter(), ctx) if s.session == "S"]
    assert summary.project is not None
    flt = LogFilter(project=(summary.project.id,))
    title, cwd, events = _session(index, flt) or ("", "", 0)
    assert (title, cwd) == ("고친 제목", "/w/a")
    assert events < 5  # 포함 여부·집계는 필터를 따른다


def test_agent_filter_keeps_title(index: LogIndex) -> None:
    assert _session(index, LogFilter(agent=("main",))) == ("고친 제목", "/w/a", 3)


def test_time_filter_keeps_title_and_first_cwd(index: LogIndex) -> None:
    # 기간 밖의 제목 행·첫 cwd 행도 세션 머리에 쓴다
    assert _session(index, LogFilter(since=3.5)) == ("고친 제목", "/w/a", 1)


def test_cwd_filter_keeps_first_cwd_of_session(index: LogIndex) -> None:
    assert _session(index, LogFilter(cwd=("/w/b",))) == ("고친 제목", "/w/a", 1)


def test_filter_still_decides_inclusion(index: LogIndex) -> None:
    assert _session(index, LogFilter(agent=("other",))) is None
    assert _session(index, LogFilter(since=10.0)) is None


def test_timeline_header_keeps_title(index: LogIndex) -> None:
    timeline = index.timeline("S", query_context(None), flt=LogFilter(agent=("main",)))
    assert timeline is not None
    assert timeline.session.title == "고친 제목"
