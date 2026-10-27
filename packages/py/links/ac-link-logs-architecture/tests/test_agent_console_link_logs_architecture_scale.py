"""규모 측정(5.5R.10, 5.5R.6 QA 조건, 5.5R.36): 큰 세션 구조도의 첫 호출·캐시 적중·증분,
`arch` 첫 쪽.

색인은 `agent_console_logs.testing.build_scale_index`(SQLite 파일)이고, 프로필은 이 테스트가 만든
칸 16개·
연결 21개 합성 프로필이다(기본 프로필 크기와 같은 판정 수).

기본 실행은 이벤트 5,000개로 작업량(읽은 이벤트·판정 수·투영 수)만 단언한다. 50,000개 측정은
`AGENT_CONSOLE_PERF=measure`(수치만 출력) 또는 `strict`(벽시계도 단언 — 첫 호출 1.5초, 증분 0.1초,
캐시 적중 0.1초, `arch` 첫 쪽 0.5초, 한가한 장비 전용)로 켠다. 수치는 `-s`로 본다.

5.5R.36에서 범위를 모델 없는 JSON 행으로 읽고(`ac-logs` `iter_event_rows`), 판정기가 최상위
키 값으로 칸·연결을 미리 거르며, 칸·연결별 누적 집계(`ArchitectureTally`)에 새 이벤트만 더하게
바꿨다. 같은 프로세스에서 데워진 첫 호출은 약 0.7초(같은 조건 5.5R.35 1.5초)지만 이 테스트처럼
색인을 막 만든 프로세스의 첫 호출은 1.35~1.55초라 strict 상한은 1.5초로 둔다(목표 1초, 남은
원인은 design 기록). 첫 호출은 다른 작업의 부하에 크게 흔들려(QA 부하 평균 3~4에서 벽시계
0.99~2.49초, 몇 초짜리 부하 구간이면 연달아 잰 세 번이 모두 느림) 측정 모드에서는 새 화면
묶음(빈 범위 캐시)으로 ``COLD_RUNS``번 재고, 이 프로세스의 CPU 시간(``time.process_time``) 최솟값을
상한과 비교한다(벽시계도 함께 출력). 작업량 단언은 첫 번째 묶음에만 건다.
맞는 행이 범위 끝에만 있는 `arch` 첫 쪽(범위를 거의 다 읽음)은 기록만 한다(design §5.5R.10
`[5.5R.6]` "기록만"). 수치는 design §5.5R.10 `[5.5R.36 구현·측정]`.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any

import pytest

from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_link_logs_architecture.scopes import MemoMatcher
from agent_console_link_logs_architecture.settings import DEFAULT_PAGE_SIZE
from agent_console_link_logs_architecture.testing import LogArchitectureHarness, selector_params
from agent_console_logs import IndexBatch, QueryContext
from agent_console_logs.sqlite import SqliteLogIndex, open_log_index
from agent_console_logs.testing import (
    ScaleLayout,
    build_scale_index,
    make_record,
    perf_strict,
)

MEASURE = os.environ.get("AGENT_CONSOLE_PERF", "") in ("measure", "strict")
MAIN = 50_000 if MEASURE else 5_000
NEW = 500
FIRST_SECONDS = 1.5
# 첫 호출 측정 횟수(최솟값을 쓴다). 한 번에 50,000건 약 1초라 3번이면 테스트가 2~3초 늘어난다.
COLD_RUNS = 3 if MEASURE else 1
INCREMENT_SECONDS = 0.1
HIT_SECONDS = 0.1
FIRST_PAGE_SECONDS = 0.5
CTX = QueryContext(error_categories=frozenset({"error"}))

# build_scale_index의 범주·스레드·도구 값에 맞춘 합성 프로필(측정 전용 데이터)
_CATEGORIES = ("input", "llm", "tool_call", "tool_result", "hook", "error")


def _profile() -> ArchitectureProfile:
    def item(path: str, value: Any) -> dict[str, Any]:
        return {"path": path, "op": "eq", "value": value}

    def eq(path: str, value: Any) -> dict[str, Any]:
        return {"all": [item(path, value)]}

    cells: dict[str, Any] = {}
    for i, cat in enumerate(_CATEGORIES):
        cells[f"c{i}"] = {"when": eq("/category", cat), "metrics": ["count", "errors", "duration"]}
    for i, thread in enumerate(("main", "sub1", "sub2", "sub3")):
        cells[f"t{i}"] = {"when": eq("/thread", thread), "group_by": "/tool"}
    cells["tools"] = {
        "when": {"all": [{"path": "/tool", "op": "eq", "value": "Bash"}]},
        "group_by": "/category",
    }
    cells["runs"] = {"when": {"all": [{"path": "/run_id", "op": "ne", "value": ""}]}}
    cells["calls"] = {
        "when": {"any": [{"path": "/category", "op": "in", "value": ["tool_call", "hook"]}]}
    }
    cells["llm_main"] = {"when": {"all": [item("/category", "llm"), item("/thread", "main")]}}
    cells["errs"] = {"when": {"all": [{"path": "/category", "op": "in", "value": ["error"]}]}}
    cells["late"] = {"when": {"all": [{"path": "/time", "op": "gt", "value": 1_700_040_000}]}}
    ids = list(cells)
    edges = []
    for i in range(21):
        a, b = ids[i % len(ids)], ids[(i + 3) % len(ids)]
        cat = _CATEGORIES[i % len(_CATEGORIES)]
        edges.append(
            {
                "id": f"e{i}",
                "from": a,
                "to": b,
                "kind": "observed",
                "when": {
                    "all": [item("/category", cat), item("/thread", "main" if i % 2 else "sub1")]
                },
            }
        )
    return ArchitectureProfile.model_validate(
        {"cells": cells, "edges": edges, "unassigned": True, "error_when": eq("/status", "failed")}
    )


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[SqliteLogIndex, ScaleLayout]]:
    index = open_log_index(tmp_path_factory.mktemp("scale") / "i.sqlite3")
    layout = build_scale_index(index, main_events=MAIN, noise_events=MAIN)
    yield index, layout
    index.close()


def _timed(fn: Any) -> tuple[Any, float]:
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def _timed_cpu(fn: Any) -> tuple[Any, float, float]:
    """(결과, 벽시계 초, 이 프로세스의 CPU 초). CPU 시간은 다른 프로세스의 부하에 덜 흔들린다."""
    c0, t0 = time.process_time(), time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0, time.process_time() - c0


def _report(name: str, seconds: float, **work: object) -> None:
    print(f"\n[scale {MAIN}] {name}: {seconds * 1000:.0f} ms {work}")


def test_first_call_cache_hit_and_increment(big: tuple[SqliteLogIndex, ScaleLayout]) -> None:
    index, layout = big
    params = {"session": layout.main_session}

    def harness() -> LogArchitectureHarness:
        return LogArchitectureHarness(
            index, profiles={"p": _profile()}, ctx=CTX, cache_events=MAIN * 2
        )

    h = harness()
    s = h.views.stats
    first, wall, cpu = _timed_cpu(lambda: h.project(**params))
    assert first.event_total == layout.main_events
    assert (s.events_read, s.judged, s.projections) == (MAIN, MAIN, 1)
    assert s.pages == -(-MAIN // DEFAULT_PAGE_SIZE)
    walls, cpus = [wall], [cpu]
    for _ in range(COLD_RUNS - 1):
        again = harness()  # 빈 범위 캐시 — 같은 첫 호출을 다시 잰다
        view, wall, cpu = _timed_cpu(lambda again=again: again.project(**params))
        assert view.event_total == layout.main_events
        assert again.views.stats.judged == MAIN
        walls.append(wall)
        cpus.append(cpu)
    cold = min(cpus)
    _report(
        "첫 호출(읽기 + 판정 + 투영, CPU 최솟값)",
        cold,
        pages=s.pages,
        judged=s.judged,
        wall_ms=[round(t * 1000) for t in walls],
        cpu_ms=[round(t * 1000) for t in cpus],
    )

    pages = s.pages
    second, hit = _timed(lambda: h.project(**params))
    assert second is first
    assert (s.events_read, s.judged, s.projections, s.view_hits) == (MAIN, MAIN, 1, 1)
    assert (s.pages - pages, s.total_checks) == (1, 1)
    _report("캐시 적중(빈 쪽 1 + 범위 수 확인 1)", hit, pages=s.pages - pages)

    # 수집이 이어짐: 새 이벤트만 읽고 새 이벤트만 판정한다
    records = [
        make_record(
            _CATEGORIES[i % len(_CATEGORIES)],
            source="platform-runs",
            origin="extra.jsonl",
            offset=i,
            session=layout.main_session,
            thread="main" if i % 2 else "sub1",
            time=1_800_000_000.0 + i,
        )
        for i in range(NEW)
    ]
    index.write(IndexBatch(records=records))
    third, inc = _timed(lambda: h.project(**params))
    assert third.event_total == layout.main_events + NEW
    assert (s.events_read, s.judged, s.projections) == (MAIN + NEW, MAIN + NEW, 2)
    _report(f"증분(+{NEW} 이벤트, 재투영)", inc, judged_new=NEW)

    # arch 첫 쪽: 구조도를 그린 범위라 다시 판정하지 않는다
    matchers: list[MemoMatcher] = []
    h.arch_filter._on_matcher = matchers.append
    # c0(첫 범주)는 큰 세션에 흔하다. c1은 큰 세션 앞부분에
    # 없고 증분 이벤트에만 있어(범주가 번갈아 쓰임) 범위를 거의 다 읽는 경우다.
    cell = next(c for c in third.cells if c.id == "c0")
    flt = h.query.parse_filter(
        {**params, **selector_params(cell.selector), "max_seq": third.max_seq, "limit": 50}
    )
    page, first_page = _timed(lambda: h.query.events(flt))
    assert len(page.items) == 50
    assert sum(m.misses for m in matchers) == 0
    _report("arch 첫 쪽 50개(판정 재사용)", first_page, hits=sum(m.hits for m in matchers))

    sparse = next(c for c in third.cells if c.id == "c1")
    flt = h.query.parse_filter(
        {**params, **selector_params(sparse.selector), "max_seq": third.max_seq, "limit": 50}
    )
    matchers.clear()
    rare, full_scan = _timed(lambda: h.query.events(flt))
    assert len(rare.items) == min(50, int(sparse.metrics["count"].value or 0))
    assert sum(m.misses for m in matchers) == 0
    _report(
        "arch 첫 쪽, 맞는 행이 끝에만(범위 거의 전체 읽음)",
        full_scan,
        hits=sum(m.hits for m in matchers),
    )

    if perf_strict():
        assert cold < FIRST_SECONDS, cold
        assert inc < INCREMENT_SECONDS, inc
        assert hit < HIT_SECONDS, hit
        assert first_page < FIRST_PAGE_SECONDS, first_page
