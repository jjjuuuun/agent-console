"""성능(design §6R.14): 문서 3개·400KB·작업 3,000개 파싱 300ms 이하(strict만 벽시계).

기본 실행은 작업량(작업 수·의존 수)만 단언하고, `AGENT_CONSOLE_PERF=strict`일 때 가장 빠른 실행
시간을 단언한다(부하가 큰 장비에서 벽시계가 흔들리므로). 정규식 매치 시간 상한(기본 0.1초)을 넘으면
그 문서의 작업을 버리므로(`sdd.parse_timeout`) 기본 실행은 시간 상한을 넉넉히 준다(느린 CI 러너).
"""

from __future__ import annotations

import os
import time

from agent_console_safe_regex import DEFAULT_TIMEOUT_SECONDS
from agent_console_sdd import compile_syntax, effective_syntax, find_task, parse_spec, patch_task
from agent_console_sdd.testing import sample_spec

TASKS = 3000
LOOSE_REGEX_TIMEOUT = 600.0  # 기본 실행: 벽시계에 기대지 않는다


def _strict() -> bool:
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


def _regex_timeout() -> float:
    return DEFAULT_TIMEOUT_SECONDS if _strict() else LOOSE_REGEX_TIMEOUT


def _build() -> dict[str, str]:
    reqs = ["# 요구\n"]
    for i in range(1000):
        reqs.append(f"\n**R{i // 10}.{i % 10}** 요구 {i} 설명 문장이 이어진다.\n")
    tasks = ["# 작업\n"]
    for i in range(TASKS):
        if i % 100 == 0:
            tasks.append(f"\n## 단계 {i // 100}\n\n")
        deps = f"T{i - 1}, T{max(0, i - 5)}~T{max(0, i - 3)}" if i else "—"
        mark = "x" if i < TASKS // 3 else " "
        tasks.append(
            f"- [{mark}] T{i} 작업 {i} 제목 `code` [owner: team-{i % 7}] "
            f"[req: R{i % 100}.{i % 10}] [depends: {deps}]\n"
            f"  - 하는 일: 작업 {i}의 설명. 여러 낱말이 들어간 본문 줄이다.\n"
        )
    design = ["# 설계\n"]
    filler = "설계 문단은 작업 문법으로 읽지 않는다. " * 4
    while sum(len(s.encode()) for s in [*reqs, *tasks, *design]) < 400 * 1024:
        design.append(f"\n{filler}\n")
    return {
        "requirements.md": "".join(reqs),
        "design.md": "".join(design),
        "tasks.md": "".join(tasks),
    }


def test_parse_400kb_3000_tasks() -> None:
    files = _build()
    total = sum(len(v.encode()) for v in files.values())
    assert total >= 400 * 1024
    syntax = compile_syntax(effective_syntax(), regex_timeout=_regex_timeout())
    spec = sample_spec()
    best = float("inf")
    index = None
    for _ in range(3 if _strict() else 1):
        start = time.perf_counter()
        index = parse_spec(spec, files, syntax)
        best = min(best, time.perf_counter() - start)
    assert index is not None
    assert len(index.tasks) == TASKS
    assert len(index.requirements) == 1000
    expected_deps = sum(
        len({i - 1, *range(max(0, i - 5), max(0, i - 3) + 1)}) for i in range(1, TASKS)
    )
    assert sum(len(t.dependencies) for t in index.tasks) == expected_deps
    assert index.issues == []
    if _strict():
        assert best <= 0.3, f"parse_spec {best * 1000:.0f}ms > 300ms"

    task = find_task(index, "T2500")
    assert task is not None
    start = time.perf_counter()
    out = patch_task(files["tasks.md"], task, syntax=syntax, status="done")
    took = time.perf_counter() - start
    assert out != files["tasks.md"]
    if _strict():
        assert took <= 0.1, f"patch_task {took * 1000:.0f}ms > 100ms"
