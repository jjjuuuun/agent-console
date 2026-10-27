"""5.5R.10 QA: 결과 캐시 무효화·상한. 프로필 변경 무효화, 출처 종류 변경, 범위·이벤트 상한."""

from __future__ import annotations

import random
from collections.abc import Callable

from agent_console_architecture.testing import rename_profile_ids
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_link_logs_architecture.testing import (
    LogArchitectureHarness as Harness,
)
from agent_console_link_logs_architecture.testing import demo_profiles, random_records
from agent_console_logs import IndexBatch, LogIndex


def cell_namer(suffix: str) -> Callable[[str], str]:
    return lambda name: f"{name}{suffix}"


def _write(index: LogIndex, n: int, seed: int = 1) -> None:
    index.write(IndexBatch(records=random_records(random.Random(seed), n, sessions=("S1",))))


def test_profile_change_and_source_kinds_change_invalidate(index: LogIndex) -> None:
    _write(index, 80)
    box: dict[str, ArchitectureProfile] = dict(demo_profiles())
    kinds = {"a1": "kind-a"}
    h = Harness(index, profiles=lambda: box)  # type: ignore[arg-type]
    h.catalog._profiles = lambda: box  # 부를 때마다 읽는다
    first = h.project(session="S1")
    assert h.project(session="S1") is first
    # 프로필 변경: 같은 객체를 돌려주면 안 된다
    box["demo"] = rename_profile_ids(box["demo"], cell=lambda c: f"z-{c}", edge=lambda e: f"w-{e}")
    second = h.project(session="S1")
    assert second is not first
    assert {c.id for c in second.cells}.isdisjoint({c.id for c in first.cells})
    # 출처 종류 변경
    h.views._kinds = kinds
    third = h.project(session="S1")
    assert third is not second


def test_caches_respect_limits(index: LogIndex) -> None:
    _write(index, 60)
    h = Harness(index, cache_scopes=2, cache_events=100)
    for s in ("S1", "S1,S2", "S1,S3", "S1,S4"):
        h.project(session=s)
    assert len(h.views.cache) <= 2
    h2 = Harness(index, cache_scopes=8, cache_events=50)
    h2.project(session="S1")
    assert sum(len(s) for s in h2.views.cache) <= 50


def test_judged_does_not_grow_with_profile_edits(index: LogIndex) -> None:
    """프로필을 고칠 때마다 옛 판정 결과가 범위에 남으면 메모리가 무한히 는다."""
    _write(index, 60)
    box = dict(demo_profiles())
    h = Harness(index)
    h.catalog._profiles = lambda: box
    for i in range(12):
        suffix = str(i)
        box["demo"] = rename_profile_ids(
            demo_profiles()["demo"],
            cell=cell_namer(suffix),
            edge=cell_namer(suffix),
        )
        h.project(session="S1")
    scope = next(iter(h.views.cache))
    assert len(scope.judged) <= 4, len(scope.judged)
