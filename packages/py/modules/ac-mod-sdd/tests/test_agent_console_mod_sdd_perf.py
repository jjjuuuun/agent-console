"""파싱 캐시 성능(design §6R.14·§6R.16 위험 7): 400KB·작업 3,000개 스펙을 다시 읽을 때 파싱하지
않는다. 기본 실행은 작업량(캐시 맞음·빗나감 수)만, ``AGENT_CONSOLE_PERF=strict``일 때 벽시계(캐시
맞은 읽기 100ms 이하)를 단언한다."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from agent_console_contracts.sdd import SpecDocument
from agent_console_mod_sdd import SDD_SERVICE, SddService

TASKS = 3000


def _build() -> dict[str, bytes]:
    reqs = ["# 요구\n"] + [f"\n**R{i // 10}.{i % 10}** 요구 {i}\n" for i in range(1000)]
    tasks = ["# 작업\n"]
    for i in range(TASKS):
        if i % 100 == 0:
            tasks.append(f"\n## 단계 {i // 100}\n\n")
        deps = f"T{i - 1}" if i else "—"
        tasks.append(
            f"- [ ] T{i} 작업 {i} [owner: team-{i % 7}] [req: R{i % 100}.{i % 10}] "
            f"[depends: {deps}]\n  - 하는 일: 작업 {i}의 설명 줄이다.\n"
        )
    design = ["# 설계\n"]
    while sum(len(s.encode()) for s in [*reqs, *tasks, *design]) < 400 * 1024:
        design.append("\n설계 문단은 작업 문법으로 읽지 않는다. " * 8)
    return {
        "req.md": "".join(reqs).encode(),
        "design.md": "".join(design).encode(),
        "tasks.md": "".join(tasks).encode(),
    }


def test_cached_load_skips_parse(tmp_path: Path, kit: Any) -> None:
    service = kit.make_assembly(tmp_path).port(SDD_SERVICE)
    assert isinstance(service, SddService)
    repo = service.scope(None).repository
    docs = [
        SpecDocument(id="req", title="요구", file="req.md", roles=["requirements"]),
        SpecDocument(id="design", title="설계", file="design.md"),
        SpecDocument(id="tasks", title="작업", file="tasks.md", roles=["tasks"]),
    ]
    repo.create(name="Big", documents=docs, contents=_build())
    service.cache.clear()
    start = time.perf_counter()
    first = repo.load("big")
    cold = time.perf_counter() - start
    assert len(first.index.tasks) == TASKS
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        again = repo.load("big")
        best = min(best, time.perf_counter() - start)
    assert again.index is first.index
    stats = service.cache.stats()
    assert (stats["misses"], stats["hits"]) == (1, 3)
    print(f"cold {cold * 1000:.0f}ms, cached best {best * 1000:.0f}ms")
    if os.environ.get("AGENT_CONSOLE_PERF", "") == "strict":
        assert best <= 0.1, f"cached load {best * 1000:.0f}ms > 100ms"
