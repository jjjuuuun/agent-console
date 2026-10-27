"""규모 측정 도구(5.5R.6): 큰 세션 하나를 가진 색인을 만들고, 질의의 작업량과 시간을 잰다.

- `build_scale_index`: 큰 세션 하나(`main_session`)와 잡음 세션들을 색인에 쓴다. 이벤트는 결정적이다
  (같은 인자 = 같은 데이터). 스레드는 `main`과 `sub<n>`, 일부 이벤트에만 `run_id`가 있다.
- `CountingPredicate`: 확장 판정 함수를 감싸 불린 횟수(= 후처리가 읽은 행 수)를 센다.
- `read_all_pages`: 필터 결과를 끝까지 쪽 넘김으로 읽는다(구조도가 범위 이벤트를 모으는 경로).
- `time_best`: 가장 빠른 실행 시간.

시간은 환경 영향이 커서 기본 테스트는 작업량(불린 횟수·읽은 쪽 수)을 단언하고,
`perf_strict()`가 참일 때(`AGENT_CONSOLE_PERF=strict`)만 벽시계를 단언한다.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from agent_console_contracts.logs import LogEvent
from agent_console_logs._filter import EventPredicate, LogFilter, QueryContext
from agent_console_logs._index import IndexBatch, LogIndex

from ._contract import make_record

__all__ = [
    "CountingPredicate",
    "ScaleLayout",
    "build_scale_index",
    "perf_strict",
    "read_all_pages",
    "time_best",
]

_BASE_TIME = 1_700_000_000.0
_CATEGORIES = ("input", "llm", "tool_call", "tool_result", "hook", "error")


def perf_strict() -> bool:
    """`AGENT_CONSOLE_PERF=strict`이면 참(벽시계 단언을 켠다)."""
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


@dataclass(frozen=True, slots=True)
class ScaleLayout:
    """`build_scale_index`가 만든 데이터의 모양.

    Attributes:
        main_session: 큰 세션 id.
        main_events: 큰 세션의 이벤트 수.
        noise_events: 잡음 세션들의 이벤트 수 합.
        run_id: 큰 세션 이벤트 중 일부에 붙은 run_id(나머지는 빈 값).
        run_events: 그 run_id를 가진 이벤트 수.
    """

    main_session: str
    main_events: int
    noise_events: int
    run_id: str
    run_events: int


def build_scale_index(
    index: LogIndex,
    *,
    main_events: int = 50_000,
    noise_events: int = 50_000,
    noise_sessions: int = 500,
    threads: int = 4,
    run_every: int = 10,
    batch: int = 2000,
    main_session: str = "BIG",
    run_id: str = "run-big",
) -> ScaleLayout:
    """큰 세션 하나와 잡음 세션들을 `index`에 쓴다(이벤트마다 위치가 달라 중복되지 않는다).

    Args:
        index: 쓸 색인(어떤 구현이든).
        main_events: 큰 세션 이벤트 수.
        noise_events: 잡음 세션 이벤트 수 합(큰 세션만 있을 때보다 색인 선택이 어렵다).
        noise_sessions: 잡음 세션 수.
        threads: 스레드 종류 수(`main`, `sub1`...).
        run_every: 큰 세션 이벤트 중 n번째마다 `run_id`를 붙인다(0이면 없음).
        batch: 한 번에 쓰는 레코드 수.
    """
    pending: list[object] = []
    run_events = 0
    total = main_events + noise_events

    def flush() -> None:
        nonlocal pending
        if pending:
            index.write(IndexBatch(records=pending))  # type: ignore[arg-type]
            pending = []

    main_left, noise_left = main_events, noise_events
    for i in range(total):
        # 큰 세션과 잡음을 번갈아 쓴다(한쪽이 먼저 떨어지면 남은 쪽으로 채운다).
        big = main_left > 0 and (noise_left == 0 or i % 2 == 0 or main_left > noise_left)
        if big:
            main_left -= 1
        else:
            noise_left -= 1
        session = main_session if big else f"N{i % max(1, noise_sessions)}"
        thread = "main" if i % threads == 0 else f"sub{i % threads}"
        rid = ""
        if big and run_every and i % run_every == 0:
            rid = run_id
            run_events += 1
        cat = _CATEGORIES[i % len(_CATEGORIES)]
        pending.append(
            make_record(
                cat,
                source="platform-runs" if big else "claude-code-jsonl",
                origin=f"{session}.jsonl",
                offset=i,
                session=session,
                thread=thread,
                run_id=rid,
                cwd=f"/work/p{i % 20}",
                title=f"event {i} {cat}",
                tool="Bash" if cat.startswith("tool") else "",
                time=_BASE_TIME + i,
                detail={"text": "x" * 80},
            )
        )
        if len(pending) >= batch:
            flush()
    flush()
    return ScaleLayout(main_session, main_events, noise_events, run_id, run_events)


class CountingPredicate:
    """판정 함수를 감싸 부른 횟수를 센다(후처리가 읽은 행 수).

    Args:
        inner: 실제 판정. 이벤트 → 참/거짓.
    """

    def __init__(self, inner: Callable[[LogEvent], bool]) -> None:
        self._inner = inner
        self.calls = 0

    def __call__(self, event: LogEvent) -> bool:
        self.calls += 1
        return self._inner(event)

    def as_predicate(self) -> EventPredicate:
        """`QueryContext.predicates`에 넣을 수 있는 함수."""
        return self


def read_all_pages(
    index: LogIndex, flt: LogFilter, ctx: QueryContext
) -> tuple[list[LogEvent], int]:
    """필터 결과를 끝까지 읽는다. (이벤트들, 읽은 쪽 수)."""
    events: list[LogEvent] = []
    pages = 0
    cursor: str | None = flt.cursor
    while True:
        page = index.query_events(flt.with_(cursor=cursor), ctx)
        pages += 1
        events.extend(page.items)
        if page.next_cursor is None:
            return events, pages
        cursor = page.next_cursor


def time_best(fn: Callable[[], object], runs: int = 3) -> float:
    """`fn`을 `runs`번 돌려 가장 빠른 시간(초)."""
    best = float("inf")
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best
