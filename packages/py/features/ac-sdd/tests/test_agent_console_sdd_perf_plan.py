"""성능(design §6R.14): 계획 5,000작업·의존 15,000개 100ms, 추적 요구 1,000·작업 5,000·연결 20,000개
1초(strict만 벽시계, 기본 실행은 작업량만 단언 — 6R.10 방식)."""

from __future__ import annotations

import os
import time

from agent_console_contracts import Usage
from agent_console_contracts.sdd import SpecIndex, TaskLink, VerificationResult
from agent_console_sdd import compile_syntax, effective_syntax, parse_spec, plan, trace
from agent_console_sdd.testing import sample_spec

TASKS = 5000
REQS = 1000
LINKS = 20000
SYNTAX = compile_syntax(effective_syntax())


def _strict() -> bool:
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


def _index() -> SpecIndex:
    reqs = "".join(f"\n**R{i}** 요구 {i}\n" for i in range(REQS))
    lines = []
    for i in range(TASKS):
        deps = ", ".join(f"T{j}" for j in (i - 1, i - 7, i - 13) if j >= 0) or "—"
        mark = "x" if i < TASKS // 5 else " "
        lines.append(f"- [{mark}] T{i} 작업 {i} [req: R{i % REQS}] [depends: {deps}]\n")
    spec = sample_spec(
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    )
    return parse_spec(spec, {"req.md": reqs, "tasks.md": "".join(lines)}, SYNTAX)


def _best(fn: object, repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()  # type: ignore[operator]
        best = min(best, time.perf_counter() - start)
    return best


def test_plan_and_trace_workload() -> None:
    index = _index()
    assert len(index.tasks) == TASKS
    deps = sum(len(t.dependencies) for t in index.tasks)
    assert deps >= 14_900  # 거의 15,000(앞쪽 몇 작업만 덜 가짐)

    result = plan(index, SYNTAX)
    open_count = TASKS - TASKS // 5
    assert sum(len(layer) for layer in result.layers) == open_count
    assert result.ready == ["T1000"]
    assert len(result.layers) == open_count  # 사슬(i-1 의존)이라 층마다 하나
    assert result.critical_path[0] == "T1000"
    assert result.critical_path[-1] == f"T{TASKS - 1}"

    links = [
        TaskLink(
            integration="runs",
            kind="run",
            ref=f"r{n}",
            task_key=f"T{n % TASKS}",
            status="succeeded",
            at=float(n),
            totals=Usage(input_tokens=1),
        )
        for n in range(LINKS)
    ]
    results = [
        VerificationResult(source="runs", status="pass", requirement_ids=[f"R{n}"], at=1.0)
        for n in range(0, REQS, 2)
    ]
    matrix = trace(index, links, results, syntax=SYNTAX)
    assert len(matrix.rows) == REQS
    assert sum(len(r.tasks) for r in matrix.rows) == TASKS
    assert matrix.rows[0].totals is not None
    assert matrix.rows[0].totals.input_tokens == 20

    if _strict():
        plan_s = _best(lambda: plan(index, SYNTAX), 5)
        trace_s = _best(lambda: trace(index, links, results, syntax=SYNTAX), 3)
        assert plan_s <= 0.1, f"plan {plan_s * 1000:.0f}ms > 100ms"
        assert trace_s <= 1.0, f"trace {trace_s * 1000:.0f}ms > 1000ms"
