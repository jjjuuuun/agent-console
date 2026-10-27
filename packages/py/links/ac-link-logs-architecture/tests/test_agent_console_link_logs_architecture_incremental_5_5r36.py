"""5.5R.36: 행 읽기·증분 투영. 범위는 행 전체를 남기지 않고 누적 집계에 새 이벤트만 더한다.

- 수집이 이어질 때마다 그린 결과 = 캐시 없이 처음부터 그린 결과(메모리·SQLite 색인).
- `max_seq`가 범위 끝보다 앞이면 요약으로 그 앞까지 다시 그린다(처음부터 그린 것과 같다).
- 이미 읽은 범위에 새 프로필이 오면 같은 범위를 다시 읽어 그 프로필로만 판정한다. 다시 읽은 것이
  다르면(범위 구성이 바뀜) 처음부터 읽는다.
- 질의 포트에 행 읽기(`iter_event_rows`)가 없어도 같은 결과다(`events` 결과를 행으로 덤프).
"""

from __future__ import annotations

import random
from typing import Any

from agent_console_architecture.testing import rename_profile_ids
from agent_console_contracts.architecture import ArchitectureView
from agent_console_contracts.logs import LogEventPage
from agent_console_link_logs_architecture import LogArchitectureViews
from agent_console_link_logs_architecture.ports import LogRowReader
from agent_console_link_logs_architecture.testing import (
    DEMO_SOURCE_KINDS,
    LogArchitectureHarness,
    demo_profiles,
    random_records,
)
from agent_console_logs import IndexBatch, LogFilter, LogIndex
from agent_console_logs.testing import TableScopeKind


def _write(
    index: LogIndex, rng: random.Random, n: int, sessions: tuple[str, ...] = ("S1",)
) -> None:
    index.write(IndexBatch(records=random_records(rng, n, sessions=sessions)))


def _profiles() -> dict[str, Any]:
    demo = demo_profiles()["demo"]
    return {
        "demo": demo,
        "other": rename_profile_ids(demo, cell=lambda c: f"o-{c}", edge=lambda e: f"o-{e}"),
    }


def _fresh(index: LogIndex, **params: Any) -> ArchitectureView:
    return LogArchitectureHarness(index, profiles=_profiles(), cache_scopes=0).project(**params)


def test_incremental_views_equal_fresh(index: LogIndex) -> None:
    rng = random.Random(5)
    h = LogArchitectureHarness(index, profiles=_profiles())
    for n in (40, 1, 0, 33, 7):
        _write(index, rng, n)
        assert h.project(session="S1") == _fresh(index, session="S1")
    s = h.views.stats
    assert s.events_read == 81
    assert s.judged == 81  # 새 이벤트만 판정했다
    assert h.views.stats.slices == 0


def test_max_seq_before_end_uses_summaries(index: LogIndex) -> None:
    rng = random.Random(6)
    h = LogArchitectureHarness(index, profiles=_profiles())
    _write(index, rng, 50)
    old = h.project(session="S1")
    _write(index, rng, 20)
    h.project(session="S1")
    again = h.project(session="S1", max_seq=old.max_seq)
    assert h.views.stats.slices == 1
    assert again == _fresh(index, session="S1", max_seq=old.max_seq)
    assert again.event_total == old.event_total
    # 범위 끝 이상이면 누적 집계에서 그린다
    h.project(session="S1", max_seq=10**9)
    assert h.views.stats.slices == 1


def test_new_profile_on_read_scope_backfills(index: LogIndex) -> None:
    rng = random.Random(7)
    h = LogArchitectureHarness(index, profiles=_profiles())
    _write(index, rng, 60)
    h.project(session="S1", profile="demo")
    _write(index, rng, 15)
    read = h.views.stats.events_read
    other = h.project(session="S1", profile="other")
    assert other == _fresh(index, session="S1", profile="other")
    # 새 이벤트 15개 + 이미 읽은 60개를 다시 읽어 새 프로필로 판정했다
    assert h.views.stats.events_read - read == 15 + 60
    scope = next(iter(h.views.cache))
    assert len(scope.judged) == 2
    # 두 프로필 모두 새 이벤트를 읽을 때 함께 판정한다(다시 읽지 않음)
    _write(index, rng, 5)
    read = h.views.stats.events_read
    assert h.project(session="S1", profile="demo") == _fresh(index, session="S1", profile="demo")
    assert h.project(session="S1", profile="other") == _fresh(index, session="S1", profile="other")
    assert h.views.stats.events_read - read == 5


def test_backfill_mismatch_rebuilds(index: LogIndex) -> None:
    rng = random.Random(8)
    _write(index, rng, 50, sessions=("S1", "S2"))
    table: dict[str, tuple[list[str], list[str]]] = {"r": (["S1"], [])}
    kinds = [TableScopeKind("fake", table)]
    h = LogArchitectureHarness(index, profiles=_profiles(), scope_kinds=kinds)
    h.project(scope="fake:r", profile="demo")
    table["r"] = (["S1", "S2"], [])  # 옛 이벤트(seq가 작다)가 범위에 들어온다
    other = h.project(scope="fake:r", profile="other")
    assert h.views.stats.rebuilds == 1
    assert other.event_total == 50
    fresh = LogArchitectureHarness(
        index, profiles=_profiles(), scope_kinds=kinds, cache_scopes=0
    ).project(scope="fake:r", profile="other")
    assert other == fresh


class _EventsOnly:
    """행 읽기(``iter_event_rows``)가 없는 ``logs.query``."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def query_context(self, *, tz: str | None = None) -> Any:
        return self._inner.query_context(tz=tz)

    def parse_filter(self, params: Any, *, path: str = "") -> LogFilter:
        found: LogFilter = self._inner.parse_filter(params, path=path)
        return found

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage:
        found: LogEventPage = self._inner.events(flt, with_total=with_total)
        return found

    def event(self, uid: str) -> Any:
        return self._inner.event(uid)

    def token_samples(self, flt: LogFilter) -> Any:
        return self._inner.token_samples(flt)


def test_query_without_row_reader_gives_same_view(index: LogIndex) -> None:
    rng = random.Random(9)
    _write(index, rng, 70)
    h = LogArchitectureHarness(index, profiles=_profiles())
    assert isinstance(h.query, LogRowReader)
    plain = _EventsOnly(h.query)
    assert not isinstance(plain, LogRowReader)
    views = LogArchitectureViews(plain, h.catalog, source_kinds=DEMO_SOURCE_KINDS)
    flt = h.query.parse_filter({"session": "S1"})
    assert views.project(flt) == h.project(session="S1")
    _write(index, rng, 9)
    assert views.project(flt) == h.project(session="S1")
    assert views.stats.events_read == 79
