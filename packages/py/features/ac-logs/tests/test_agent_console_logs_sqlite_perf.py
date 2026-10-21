"""대용량 성능(4R.5): 이벤트 10만 건에서 필터 1페이지·세션 목록이 각각 500ms 이하.

시간 단언은 `AGENT_CONSOLE_SKIP_PERF=1`이면 건너뛴다(정확성 단언은 유지). 기준 500ms에
허용 계수 `PERF_FACTOR`(기본 3)를 곱한 값이 한도다: 개발 장비(WSL의 /mnt/c 포함)와 CI의 편차,
다른 테스트와 동시에 도는 부하를 흡수하려는 값이다. 측정값은 `-s`로 보면 출력된다.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from agent_console_contracts.logs import LogAggregateRequest, TokenSample
from agent_console_logs import LogFilter, QueryContext
from agent_console_logs._draft import TAG_SESSION_TITLE, TAG_TOOL
from agent_console_logs._index import IndexBatch
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import make_record

EVENTS = 100_000
SESSIONS = 2_000
BUDGET_SECONDS = 0.5
PERF_FACTOR = float(os.environ.get("AGENT_CONSOLE_PERF_FACTOR", "3"))
SKIP_TIME = bool(os.environ.get("AGENT_CONSOLE_SKIP_PERF"))
CTX = QueryContext(error_categories=frozenset({"error"}))


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SqliteLogIndex]:
    index = open_log_index(tmp_path_factory.mktemp("perf") / "big.sqlite3")
    rng = random.Random(1)
    base = 1_700_000_000.0
    pending = []
    for i in range(EVENTS):
        s = i % SESSIONS
        cat = rng.choice(["input", "llm", "tool_call", "tool_result", "error", "hook"])
        msg = f"m{i}" if cat == "llm" else ""
        pending.append(
            make_record(
                cat,
                source=("claude-code-jsonl", "platform-runs")[s % 2],
                origin=f"s{s}.jsonl",
                offset=i,
                session=f"S{s}",
                thread="main" if i % 5 else f"sub{i % 3}",
                cwd=f"/work/proj{s % 40}",
                title=f"event {i} {cat}",
                call_id=f"c{i // 2}" if cat.startswith("tool") else "",
                stage="start"
                if cat == "tool_call"
                else "complete"
                if cat == "tool_result"
                else "info",
                tags=(TAG_TOOL,)
                if cat.startswith("tool")
                else (TAG_SESSION_TITLE,)
                if i < SESSIONS
                else (),
                model="m1",
                message_id=msg,
                time=base + i * 7.0,
                usage=TokenSample(message_id=msg, input_tokens=10, output_tokens=5)
                if msg
                else None,
                detail={"text": "x" * 200},
            )
        )
        if len(pending) == 2000:
            index.write(IndexBatch(records=pending))
            pending = []
    if pending:
        index.write(IndexBatch(records=pending))
    yield index
    index.close()


def _best(fn: Callable[[], object], runs: int = 3) -> float:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def _check(name: str, seconds: float) -> None:
    print(f"\n[perf] {name}: {seconds * 1000:.0f} ms")
    if not SKIP_TIME:
        assert seconds <= BUDGET_SECONDS * PERF_FACTOR, f"{name}: {seconds * 1000:.0f} ms"


def test_fixture_size(big: SqliteLogIndex) -> None:
    page = big.query_events(LogFilter(limit=1), CTX, with_total=True)
    assert page.total is not None
    assert page.total >= EVENTS * 0.9  # 같은 도구 호출의 짝 이벤트는 하나로 합쳐질 수 있다


@pytest.mark.parametrize(
    ("name", "flt"),
    [
        ("page: no filter", LogFilter(limit=50)),
        ("page: category", LogFilter(category=("error",), limit=50)),
        ("page: session", LogFilter(session=("S17",), limit=50)),
        ("page: time range desc", LogFilter(since=1_700_100_000.0, order="desc", limit=50)),
        ("page: q (substring)", LogFilter(q="event 77777", limit=50)),
        ("page: project/cwd", LogFilter(cwd=("/work/proj3",), limit=50)),
        ("page: keyset 2nd page", LogFilter(cursor="60000", limit=50)),
    ],
)
def test_filter_page_is_fast(big: SqliteLogIndex, name: str, flt: LogFilter) -> None:
    result = big.query_events(flt, CTX)
    assert result.items
    _check(name, _best(lambda: big.query_events(flt, CTX)))


def test_session_list_is_fast(big: SqliteLogIndex) -> None:
    flt = LogFilter(limit=50)
    sessions = big.list_sessions(flt, CTX)
    assert len(sessions) == 50
    assert sessions[0].tokens is not None
    _check("session list", _best(lambda: big.list_sessions(flt, CTX)))


def test_timeline_and_aggregate_are_reasonable(big: SqliteLogIndex) -> None:
    timeline = big.timeline("S5", CTX)
    assert timeline is not None
    _check("timeline (one session)", _best(lambda: big.timeline("S5", CTX)))
    req = LogAggregateRequest(group_by=["day"], metric="tokens.total")
    assert big.aggregate(req, CTX)
    _check("aggregate tokens by day", _best(lambda: big.aggregate(req, CTX)))
    req2 = LogAggregateRequest(group_by=["project", "category"], metric="events")
    assert big.aggregate(req2, CTX)
    _check("aggregate events by project/category", _best(lambda: big.aggregate(req2, CTX)))


def test_file_stays_small_enough(big: SqliteLogIndex, tmp_path: Path) -> None:
    path = Path(str(big.engine.url.database))
    print(f"\n[perf] db size: {path.stat().st_size / 1e6:.1f} MB")
    assert path.stat().st_size < 600e6
