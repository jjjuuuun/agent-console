"""규모 측정(5.5R.6): 큰 세션 50,000 이벤트에서 구조도 읽기·`arch` 첫 페이지.

기본 실행은 작업량(후처리 판정 횟수·읽은 쪽 수)을 단언한다. 벽시계는 `AGENT_CONSOLE_PERF=strict`일
때만 단언한다(기준: 구조도 1초, `arch` 첫 페이지 0.5초). 측정값은 `-s`로 본다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
import sqlalchemy as sa

from agent_console_contracts.logs import LogEvent
from agent_console_logs import LogFilter, LogScope, QueryContext
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import (
    CountingPredicate,
    ScaleLayout,
    build_scale_index,
    perf_strict,
    read_all_pages,
    time_best,
)

MAIN = 50_000
STRUCTURE_SECONDS = 1.0
FIRST_PAGE_SECONDS = 0.5
CTX = QueryContext(error_categories=frozenset({"error"}))


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[SqliteLogIndex, ScaleLayout]]:
    index = open_log_index(tmp_path_factory.mktemp("scale") / "i.sqlite3")
    layout = build_scale_index(index, main_events=MAIN, noise_events=MAIN)
    yield index, layout
    index.close()


def _report(name: str, seconds: float, **work: object) -> None:
    print(f"\n[scale] {name}: {seconds * 1000:.0f} ms {work}")


def _ctx(scope: LogScope, *predicates: Callable[[LogEvent], bool]) -> QueryContext:
    return replace(CTX, scope=scope, predicates=tuple(predicates))


def test_structure_read_by_session(big: tuple[SqliteLogIndex, ScaleLayout]) -> None:
    """큰 세션 전체를 쪽 넘김으로 읽는 경로(구조도): 쪽 수 = 이벤트 / 200, seq 오름차순."""
    index, layout = big
    ctx = _ctx(LogScope.of([layout.main_session]))
    flt = LogFilter(limit=200)
    events, pages = read_all_pages(index, flt, ctx)
    assert len(events) == layout.main_events
    assert pages == -(-layout.main_events // 200)
    seqs = [e.seq for e in events]
    assert seqs == sorted(set(seqs))
    assert {e.session for e in events} == {layout.main_session}
    sec = time_best(lambda: read_all_pages(index, flt, ctx), runs=2)
    _report("structure/scope", sec, events=len(events), pages=pages)
    if perf_strict():
        assert sec <= STRUCTURE_SECONDS


@pytest.mark.parametrize(
    ("name", "kind", "keep", "max_calls"),
    [
        # 맞는 행이 3개에 1개: 첫 쪽(50개 + 다음 쪽 확인 1개)만큼만 읽고 멈춘다.
        ("session/dense", "session", lambda e: e.tool == "Bash", 51 * 3 + 6),
        ("run/dense", "run", lambda e: e.tool == "Bash", 51 * 6 + 12),
        # 맞는 행이 100개에 1개.
        ("session/sparse", "session", lambda e: int(e.title.split()[1]) % 100 == 0, 51 * 100 + 200),
    ],
)
def test_first_page_stops_early(
    big: tuple[SqliteLogIndex, ScaleLayout],
    name: str,
    kind: str,
    keep: Callable[[LogEvent], bool],
    max_calls: int,
) -> None:
    """후처리 판정이 있어도 `LIMIT + 1`개를 채우면 읽기가 멈춘다(판정 횟수로 단언)."""
    index, layout = big
    scope = (
        LogScope.of([layout.main_session])
        if kind == "session"
        else LogScope.of((), [layout.run_id])
    )
    counter = CountingPredicate(keep)
    ctx = _ctx(scope, counter)
    flt = LogFilter(limit=50)
    page = index.query_events(flt, ctx)
    assert len(page.items) == 50
    assert page.next_cursor is not None
    assert counter.calls <= max_calls, counter.calls
    counter.calls = 0
    sec = time_best(lambda: index.query_events(flt, ctx), runs=2)
    _report(f"first page/{name}", sec, calls=counter.calls // 2 or counter.calls)
    if perf_strict():
        assert sec <= FIRST_PAGE_SECONDS


def test_first_page_rare_predicate_reads_whole_scope_once(
    big: tuple[SqliteLogIndex, ScaleLayout],
) -> None:
    """맞는 행이 드물면 범위 전체를 한 번 읽는다(상한 = 범위 크기). 시간은 기록만 한다."""
    index, layout = big
    counter = CountingPredicate(lambda e: "7777" in e.title)
    ctx = _ctx(LogScope.of([layout.main_session]), counter)
    flt = LogFilter(limit=50)
    page = index.query_events(flt, ctx)
    assert page.next_cursor is None
    assert 0 < len(page.items) < 50
    assert counter.calls == layout.main_events  # 범위 밖(잡음 세션)은 판정하지 않는다
    sec = time_best(lambda: index.query_events(flt, ctx), runs=2)
    _report("first page/rare", sec, calls=layout.main_events, matches=len(page.items))


def test_thread_filter_uses_seq_index_without_sort(big: tuple[SqliteLogIndex, ScaleLayout]) -> None:
    """`thread`·`session`·`run_id` 필터의 쪽 넘김 질의가 임시 정렬 없이 (값, seq) 색인을 탄다."""
    index, _ = big
    for column, index_name in (
        ("thread", "ix_log_events_thread_seq"),
        ("session", "ix_log_events_session_seq"),
        ("run_id", "ix_log_events_run_seq"),
    ):
        with index.engine.connect() as conn:
            plan = " ".join(
                str(r)
                for r in conn.execute(
                    sa.text(
                        f"EXPLAIN QUERY PLAN SELECT seq FROM log_events WHERE {column} = 'x' "
                        "AND seq > 10 ORDER BY seq LIMIT 51"
                    )
                )
            )
        assert index_name in plan, plan
        assert "TEMP B-TREE" not in plan, plan
    flt = LogFilter(thread=("sub1",), limit=50)
    sec = time_best(lambda: index.query_events(flt, CTX), runs=3)
    _report("first page/thread", sec)
    if perf_strict():
        assert sec <= FIRST_PAGE_SECONDS


def test_standalone_open_upgrades_old_file_without_loss(tmp_path: Path) -> None:
    """옛 모양(`run_id` 단독 색인) 파일을 `open_log_index`로 열면 색인만 바뀌고 행은 그대로다."""
    path = tmp_path / "old.sqlite3"
    first = open_log_index(path)
    build_scale_index(first, main_events=300, noise_events=100, noise_sessions=5)
    with first.engine.begin() as conn:  # 옛 모양으로 되돌린다
        for name in (
            "ix_log_events_run_seq",
            "ix_log_events_thread_seq",
            "ix_log_events_session_seq",
        ):
            conn.execute(sa.text(f"DROP INDEX {name}"))
        conn.execute(sa.text("CREATE INDEX ix_log_events_run ON log_events (run_id)"))
        rows = conn.execute(sa.text("SELECT seq, uid, run_id FROM log_events ORDER BY seq")).all()
    first.close()

    second = open_log_index(path)
    with second.engine.connect() as conn:
        names = {r[1] for r in conn.execute(sa.text("PRAGMA index_list(log_events)"))}
        again = conn.execute(sa.text("SELECT seq, uid, run_id FROM log_events ORDER BY seq")).all()
    assert again == rows
    assert {
        "ix_log_events_run_seq",
        "ix_log_events_thread_seq",
        "ix_log_events_session_seq",
    } <= names
    assert "ix_log_events_run" not in names
    assert second.query_events(LogFilter(thread=("sub1",), limit=5), CTX).items
    second.close()
