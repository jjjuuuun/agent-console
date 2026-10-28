"""정리 계획 규모(design §5.7R.10: 100,000개·규칙 5개 → 2 s).

저장소 비용과 떼어 계획 자체(판단 대상 만들기 + 컴파일한 조건)를 잰다. 저장소는 미리 만든 요약을
쪽으로 내주는 표본(`SearchableStore`)이다. 평소에는 작업량(읽은 쪽 수·판정 수)을 단언하고,
`AGENT_CONSOLE_PERF=strict`일 때만 100,000개로 벽시계를 단언한다.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest

from agent_console_conditions import ConditionOperator, builtin_operators
from agent_console_contracts.memory import (
    MemoryAuthor,
    MemoryEntryPage,
    MemoryEntrySummary,
    MemoryScopeRef,
)
from agent_console_memory import (
    MemoryQuery,
    SearchableStore,
    compile_retention_rules,
    decode_cursor,
    encode_cursor,
    retention_plan,
)

DAY = 86_400.0
NOW = 1_800_000_000.0
OPS: dict[str, ConditionOperator] = {op.descriptor.id: op for op in builtin_operators()}
STRICT = os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


def _cond(*items: tuple[str, str, Any]) -> dict[str, Any]:
    return {"all": [{"path": p, "op": o, "value": v} for p, o, v in items]}


RULES: list[dict[str, Any]] = [
    {
        "id": "r1",
        "action": "archive",
        "when": _cond(("/tags", "contains", "tmp"), ("/idle_days", "gte", 30)),
    },
    {
        "id": "r2",
        "action": "delete",
        "when": _cond(("/archived", "eq", True), ("/idle_days", "gte", 60)),
    },
    {
        "id": "r3",
        "action": "archive",
        "when": _cond(("/scope/kind", "eq", "journal"), ("/age_days", "gte", 365)),
    },
    {
        "id": "r4",
        "action": "archive",
        "when": _cond(("/bytes", "gt", 4096), ("/last_read_days", "gte", 90)),
    },
    {
        "id": "r5",
        "action": "delete",
        "when": _cond(("/author_kind", "eq", "agent"), ("/key", "matches", "^draft/")),
    },
]


class SnapshotStore:
    """미리 만든 요약을 `updated_at` 오름차순 쪽으로 내준다(`search`만, 다른 조건은 무시)."""

    def __init__(self, entries: list[MemoryEntrySummary]) -> None:
        self.entries = sorted(entries, key=lambda e: e.updated_at)
        self.pages = 0

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        self.pages += 1
        start = decode_cursor(query.cursor)
        page = self.entries[start : start + query.limit]
        end = start + len(page)
        nxt = encode_cursor(end) if end < len(self.entries) else None
        return MemoryEntryPage(items=page, next_cursor=nxt, total=len(self.entries))


def _entries(count: int) -> list[MemoryEntrySummary]:
    kinds = ("notes", "journal", "board", "team-x")
    agent = MemoryAuthor(kind="agent", agent_id="a", run_id="r")
    user = MemoryAuthor(kind="user")
    out: list[MemoryEntrySummary] = []
    for i in range(count):
        scope = MemoryScopeRef.model_construct(kind=kinds[i % 4], id=f"s{i % 200}")
        author = agent if i % 3 == 0 else user
        out.append(
            MemoryEntrySummary.model_construct(
                id=f"e{i}",
                scope=scope,
                key=f"draft/{i}" if i % 7 == 0 else f"k/{i}",
                content_type="text/markdown",
                tags=["tmp"] if i % 5 == 0 else ["keep", "x"],
                pinned=i % 50 == 0,
                archived=i % 11 == 0,
                version=1 + i % 4,
                bytes=1024 + (i % 8) * 1024,
                sha256="",
                created_at=NOW - (i % 800) * DAY,
                created_by=author,
                updated_at=NOW - (i % 120) * DAY,
                updated_by=author,
                last_read_at=None if i % 2 else NOW - (i % 150) * DAY,
                deleted_at=None,
                preview="",
            )
        )
    return out


def _expected(entries: list[MemoryEntrySummary]) -> int:
    """규칙을 손으로 옮긴 기대 계획 수(첫 규칙만, 보관 항목 보관은 계획 아님, 고정 제외)."""
    count = 0
    for e in entries:
        if e.pinned:
            continue
        idle = (NOW - e.updated_at) / DAY
        age = (NOW - e.created_at) / DAY
        read = None if e.last_read_at is None else (NOW - e.last_read_at) / DAY
        rules = [
            ("archive", "tmp" in e.tags and idle >= 30),
            ("delete", e.archived and idle >= 60),
            ("archive", e.scope.kind == "journal" and age >= 365),
            ("archive", e.bytes > 4096 and read is not None and read >= 90),
            ("delete", e.updated_by.kind == "agent" and e.key.startswith("draft/")),
        ]
        for action, hit in rules:
            if hit:
                if not (action == "archive" and e.archived):
                    count += 1
                break
    return count


def _run(count: int, runs: int = 1) -> tuple[list[float], list[float], int, SnapshotStore, int]:
    """(벽시계 초들, CPU 초들, 계획 수, 마지막 저장소, 기대 수). 매번 새 표본 저장소로 잰다."""
    entries = _entries(count)
    compiled = compile_retention_rules(RULES, OPS)
    assert compiled.issues == ()
    walls: list[float] = []
    cpus: list[float] = []
    counts: set[int] = set()
    store = SnapshotStore(entries)
    for _ in range(runs):
        store = SnapshotStore(entries)
        assert isinstance(store, SearchableStore)
        c0, t0 = time.process_time(), time.perf_counter()
        plan = retention_plan(store, compiled, now=NOW, limit=1_000)
        walls.append(time.perf_counter() - t0)
        cpus.append(time.process_time() - c0)
        assert plan.truncated
        assert len(plan.items) == 1_000
        counts.add(plan.count)
    assert len(counts) == 1
    return walls, cpus, counts.pop(), store, _expected(entries)


def test_plan_work_matches_rules_and_reads_each_page_once() -> None:
    _walls, _cpus, count, store, expected = _run(10_000)
    assert count == expected
    assert count > 0
    assert store.pages == 2  # 기본 쪽 크기 5,000 → 10,000개는 두 쪽


@pytest.mark.skipif(not STRICT, reason="AGENT_CONSOLE_PERF=strict에서만 시간 단언")
def test_plan_100k_entries_five_rules_under_two_seconds() -> None:
    # 단언은 이 프로세스의 CPU 시간 3회 최솟값(부하에 덜 흔들림, 5.5R.36 선례), 벽시계는 출력만
    walls, cpus, count, store, expected = _run(100_000, runs=3)
    print(
        f"retention_plan 100,000 entries / 5 rules: CPU min {min(cpus):.3f}s "
        f"cpu={[round(c, 3) for c in cpus]} wall={[round(w, 3) for w in walls]}, planned {count}"
    )
    assert count == expected
    assert store.pages == 20
    assert min(cpus) < 2.0
