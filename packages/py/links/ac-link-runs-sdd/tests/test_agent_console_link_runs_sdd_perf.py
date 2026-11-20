"""성능(design §6R.14 `trace`): 요구 1,000·작업 5,000·연결 Run 20,000개 추적 표 1초 이하.

연동 경로 전체를 잰다: 작업 연결(`RunsTaskIntegration.links` — 스펙 라벨 질의 한 번을 상한까지
페이지로) + 검증 결과(`RunsVerificationSource.collect` — 검증 목적 라벨 질의 한 번) + `trace`.
스펙 파싱은 재지 않는다(기준이 따로 있고 서버는 파싱을 캐시한다, `ac-sdd` 성능 테스트).
`runs.reader`는 미리 거른 목록을 쪽으로 자르는 가벼운 대역이라 실행 기록 DB 시간은 들지 않는다
(`GET /runs/page` 기준은 `mod-runs`가 잰다).

기본 실행은 작은 규모로 작업량(질의 수·연결 수·행 수)만 단언하고, `AGENT_CONSOLE_PERF=strict`일 때
기준 규모에서 가장 빠른 실행 시간을 단언한다(부하가 큰 장비에서 벽시계가 흔들리므로).
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

from agent_console_contracts import Run, Usage
from agent_console_link_runs_sdd import (
    RunsSddSettings,
    RunsTaskIntegration,
    RunsVerificationSource,
    StatusReflector,
    package_defaults,
)
from agent_console_link_runs_sdd.testing import FakeRuns, LocalSddService
from agent_console_sdd import VerificationContext, trace
from agent_console_sdd.testing import TEST_TEMPLATE_KIND


def _strict() -> bool:
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


REQS, TASKS, LINKS = (1000, 5000, 20000) if _strict() else (100, 500, 2000)
VERIFY_EVERY = 4  # 연결 넷 중 하나는 검증 목적 실행
PAGE_SIZE = 1000


class _Reader:
    """`runs.reader` 대역: 라벨로 미리 거른 목록(최근 순)을 쪽으로 자르고 질의를 센다."""

    def __init__(self, runs: list[Run]) -> None:
        self._runs = sorted(runs, key=lambda r: (r.created_at, r.id), reverse=True)
        self._hits: dict[tuple[tuple[str, str], ...], list[Run]] = {}
        self.calls: list[dict[str, Any]] = []

    def page(self, **filters: Any) -> tuple[list[Run], str | None]:
        self.calls.append(filters)
        labels = tuple(sorted(dict(filters.get("labels") or {}).items()))
        hit = self._hits.get(labels)
        if hit is None:
            hit = [r for r in self._runs if all(r.labels.get(k) == v for k, v in labels)]
            self._hits[labels] = hit
        offset = int(filters.get("cursor") or 0)
        limit = int(filters["limit"])
        more = offset + limit < len(hit)
        return hit[offset : offset + limit], (str(offset + limit) if more else None)

    def get(self, run_id: str) -> Run | None:
        return None


def _setup() -> tuple[Any, LocalSddService, str]:
    sdd = LocalSddService()
    repo = sdd.repository
    template = {
        "kind": TEST_TEMPLATE_KIND,
        "id": "t",
        "name": "틀",
        "documents": [
            {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
            {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
        ],
        "rules": {
            "run_profiles": [
                {"id": "impl", "title": "구현", "graph": "g", "purpose": "implement"},
                {"id": "verify", "title": "검증", "graph": "qa", "purpose": "verify"},
            ],
            "verification": {
                "purposes": ["verify"],
                "result_map": {"succeeded": "pass", "failed": "fail"},
            },
        },
    }
    reqs = "".join(f"\n**R{i}** 요구 {i}\n" for i in range(REQS))
    tasks = "".join(
        f"- [{'x' if i % 3 == 0 else ' '}] T{i} 작업 {i} [req: R{i % REQS}]"
        f" [depends: {f'T{i - 1}' if i else '—'}]\n"
        for i in range(TASKS)
    )
    created = repo.store.create(TEST_TEMPLATE_KIND, template)
    repo.store.write_files(
        TEST_TEMPLATE_KIND,
        "t",
        {"req.md": reqs.encode(), "tasks.md": tasks.encode()},
        expected_version=created.version_hash,
    )
    spec_id = repo.create(name="big", template="t").id
    return repo.load(spec_id), sdd, spec_id


def _runs(sdd: LocalSddService, spec_id: str) -> list[Run]:
    out: list[Run] = []
    for n in range(LINKS):
        verify = n % VERIFY_EVERY == 0
        labels = {
            sdd.label_key("spec"): spec_id,
            sdd.label_key("task"): f"T{n % TASKS}",
            sdd.label_key("profile"): "verify" if verify else "impl",
            sdd.label_key("purpose"): "verify" if verify else "implement",
        }
        out.append(
            Run(
                id=f"r{n}",
                graph_id="qa" if verify else "g",
                graph_version="v",
                status="failed" if n % 10 == 0 else "completed",
                input={},
                origin="sdd",
                created_at=float(n),
                ended_at=float(n) + 0.5,
                labels=labels,
                totals=Usage(input_tokens=1),
            )
        )
    return out


async def test_trace_through_runs_integration_workload() -> None:
    loaded, sdd, spec_id = _setup()
    assert len(loaded.index.tasks) == TASKS
    assert len(loaded.index.requirements) == REQS
    reader = _Reader(_runs(sdd, spec_id))
    d = package_defaults()
    reflector = StatusReflector(
        sdd,
        run_outcomes=d["run_outcomes"],
        status_events=d["status_events"],
        finished_statuses=d["finished_statuses"],
        max_issues=10,
    )
    settings = RunsSddSettings(max_link_runs=LINKS, page_size=PAGE_SIZE)
    integration = RunsTaskIntegration(
        sdd=sdd, starter=FakeRuns(), reader=reader, reflector=reflector, settings=settings
    )
    source = RunsVerificationSource(integration)
    ctx = sdd.context(sdd.scope(None), loaded)

    async def once() -> Any:
        links = await integration.links(ctx, ctx.index.tasks)
        results = await source.collect(VerificationContext(spec=ctx, options={}))
        return links, results, trace(ctx.index, links, results, syntax=loaded.compiled)

    reader.calls.clear()
    links, results, matrix = await once()
    # 라벨 질의: 스펙 라벨 한 번 + 검증 목적 라벨 한 번(작업 수만큼 질의하지 않는다)
    verify_runs = math.ceil(LINKS / VERIFY_EVERY)
    pages = math.ceil(LINKS / PAGE_SIZE) + math.ceil(verify_runs / PAGE_SIZE)
    assert len(reader.calls) == pages
    assert {tuple(sorted(c["labels"])) for c in reader.calls} == {
        (sdd.label_key("spec"),),
        (sdd.label_key("purpose"), sdd.label_key("spec")),
    }
    assert len(links) == LINKS
    assert len(results) == verify_runs
    assert len(matrix.rows) == REQS
    assert sum(len(r.tasks) for r in matrix.rows) == TASKS
    assert sum(len(r.results) for r in matrix.rows) == verify_runs
    first = matrix.rows[0]
    assert first.totals is not None
    assert first.totals.input_tokens == LINKS // REQS
    assert first.verification is not None
    # R0의 가장 최근 검증 실행은 r{LINKS - REQS}(열 번째마다 실패) → result_map으로 fail
    assert first.verification.status == "fail"

    if _strict():
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            await once()
            best = min(best, time.perf_counter() - start)
        print(f"trace via runs integration best {best * 1000:.0f}ms")
        assert best <= 1.0, f"trace {best * 1000:.0f}ms > 1000ms"
