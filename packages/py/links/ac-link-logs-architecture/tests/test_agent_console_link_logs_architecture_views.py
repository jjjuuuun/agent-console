"""로그 범위 구조도(`LogArchitectureViews`)와 `arch` 필터(`ArchitectureFilter`) — 서버 없이
색인 위에서.

- 클릭 수 일치(design §5.5R.10): 모든 칸·묶음·관측 연결·분류 안 됨에서 (범위 + 선택 필터 + 결과
  `max_seq`)로 거른 표 수 = 지표 `count`. 메모리·SQLite 색인, 무작위 이벤트 묶음.
- 수집 중 `max_seq` 경계: 그린 뒤 이벤트가 더 들어와도 결과의 `max_seq`로 거르면 수가 같다.
- 결과 캐시·증분 읽기: 두 번째 호출은 새 이벤트만 읽고 새 이벤트만 판정한다. 새 이벤트가 없으면
  투영 결과를 그대로 준다. 범위 구성이 바뀌면 처음부터 다시 읽는다.
- 출처 종류 대응·출처 우선순위·오류 범주(질의 맥락)·상한·프로필 없음.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

import pytest

from agent_console_architecture.testing import rename_profile_ids
from agent_console_contracts.architecture import ArchitectureSelector, ArchitectureView
from agent_console_link_logs_architecture import (
    ArchitectureQueryError,
    EventNotFoundError,
    LogArchitectureViews,
    ProfileNotFoundError,
    ScopeTooLargeError,
)
from agent_console_link_logs_architecture.scopes import MemoMatcher
from agent_console_link_logs_architecture.testing import (
    DEMO_CONTEXT,
    IndexLogQuery,
    StaticCatalog,
    click_count_mismatches,
    demo_profiles,
    random_records,
    selector_params,
)
from agent_console_link_logs_architecture.testing import LogArchitectureHarness as Harness
from agent_console_logs import IndexBatch, IndexRecord, JsonValue, LogIndex, LogQueryError
from agent_console_logs.testing import MemoryLogIndex, TableScopeKind, make_record

CTX = DEMO_CONTEXT


def write(index: LogIndex, records: list[IndexRecord]) -> None:
    index.write(IndexBatch(records=records))


def assert_click_counts(h: Harness, view: ArchitectureView, base: Mapping[str, JsonValue]) -> int:
    wrong, checked = click_count_mismatches(view, h.count, base)
    assert wrong == []
    return checked


@pytest.mark.parametrize("seed", range(6))
def test_click_counts_match_random_events(index: LogIndex, seed: int) -> None:
    rng = random.Random(seed)
    write(index, random_records(rng, rng.randint(0, 160), sessions=("S1", "S2")))
    h = Harness(index)
    view = h.project(session="S1")
    checked = assert_click_counts(h, view, {"session": "S1"})
    if view.event_total:
        assert checked >= 5
    # 범위 밖 세션은 섞이지 않는다
    assert view.event_total == h.count({"session": "S1"})


def test_click_counts_with_scope_kind_and_thread(index: LogIndex) -> None:
    rng = random.Random(42)
    write(index, random_records(rng, 120, sessions=("S1", "S2", "S3")))
    kind = TableScopeKind("fake", {"both": (["S1", "S3"], [])})
    h = Harness(index, scope_kinds=[kind])
    view = h.project(scope="fake:both")
    assert view.event_total == h.count({"session": "S1,S3"})
    assert_click_counts(h, view, {"scope": "fake:both"})
    sub = h.project(scope="fake:both", thread="sub1")
    assert sub.event_total == h.count({"session": "S1,S3", "thread": "sub1"})
    assert_click_counts(h, sub, {"scope": "fake:both", "thread": "sub1"})


def test_max_seq_boundary_while_ingesting(index: LogIndex) -> None:
    """그린 뒤 수집이 이어져도 결과의 `max_seq`로 거르면 표 수 = 칸 수(R8.8)."""
    rng = random.Random(7)
    write(index, random_records(rng, 80))
    h = Harness(index)
    view = h.project(session="S1")
    write(index, random_records(rng, 40))
    assert_click_counts(h, view, {"session": "S1"})  # 옛 결과 + 옛 max_seq
    # 같은 max_seq로 다시 그리면 같은 수, 경계 없이 그리면 늘어난다
    again = h.project(session="S1", max_seq=view.max_seq)
    assert again.event_total == view.event_total
    assert [c.metrics for c in again.cells] == [c.metrics for c in view.cells]
    now = h.project(session="S1")
    assert now.event_total == view.event_total + 40
    assert_click_counts(h, now, {"session": "S1"})


def test_incremental_read_and_result_cache(index: LogIndex) -> None:
    rng = random.Random(3)
    write(index, random_records(rng, 300))
    h = Harness(index)
    first = h.project(session="S1")
    s = h.views.stats
    assert (s.events_read, s.judged, s.projections) == (300, 300, 1)

    # 새 이벤트 없음: 결과를 그대로 준다(읽기는 빈 쪽 하나 + 범위 수 확인)
    pages = s.pages
    second = h.project(session="S1")
    assert second is first
    assert (s.events_read, s.judged, s.view_hits, s.pages - pages) == (300, 300, 1, 1)

    # 새 이벤트 25개: 그것만 읽고 그것만 판정한다. 결과는 처음부터 그린 것과 같다
    write(index, random_records(rng, 25))
    third = h.project(session="S1")
    assert (s.events_read, s.judged, s.projections) == (325, 325, 2)
    fresh = Harness(index, cache_scopes=0).project(session="S1")
    assert third == fresh


def test_scope_change_rebuilds(index: LogIndex) -> None:
    """범위 구성이 바뀌어(예: 범위 종류가 세션을 더 품음) 기억한 수와 범위 수가 다르면 처음부터."""
    rng = random.Random(11)
    write(index, random_records(rng, 60, sessions=("S1", "S2")))
    table: dict[str, tuple[list[str], list[str]]] = {"r": (["S1"], [])}
    h = Harness(index, scope_kinds=[TableScopeKind("fake", table)])
    first = h.project(scope="fake:r")
    table["r"] = (["S1", "S2"], [])  # S2의 옛 이벤트(seq가 작다)가 범위에 들어온다
    second = h.project(scope="fake:r")
    assert h.views.stats.rebuilds == 1
    assert second.event_total == 60
    assert second.event_total > first.event_total
    assert_click_counts(h, second, {"scope": "fake:r"})


def test_arch_filter_reuses_judged_events(index: LogIndex) -> None:
    """구조도를 그린 범위의 이벤트는 `arch` 필터가 다시 판정하지 않는다(범위 단위 멤버십)."""
    rng = random.Random(5)
    write(index, random_records(rng, 90))
    h = Harness(index)
    view = h.project(session="S1")
    matchers: list[MemoMatcher] = []
    h.arch_filter._on_matcher = matchers.append
    tools = next(c for c in view.cells if c.id == "tools")
    h.count({"session": "S1", **selector_params(tools.selector), "max_seq": view.max_seq})
    assert matchers
    assert sum(m.misses for m in matchers) == 0
    assert sum(m.hits for m in matchers) > 0
    # 캐시가 없어도(다른 범위) 수는 같다
    cold = Harness(index, cache_scopes=0)
    params = {"session": "S1", **selector_params(tools.selector), "max_seq": view.max_seq}
    assert cold.count(params) == h.count(params)


def test_renamed_ids_give_same_counts(index: LogIndex) -> None:
    """R0: 칸·연결 id를 모두 바꾼 프로필로 같은 수."""
    rng = random.Random(9)
    write(index, random_records(rng, 100))
    base = demo_profiles()
    renamed = {
        "demo": rename_profile_ids(base["demo"], cell=lambda c: f"x-{c}", edge=lambda e: f"y-{e}")
    }
    a = Harness(index).project(session="S1")
    hb = Harness(index, profiles=renamed)
    b = hb.project(session="S1")
    assert [c.metrics for c in a.cells] == [c.metrics for c in b.cells]
    assert [e.metrics for e in a.edges] == [e.metrics for e in b.edges]
    assert_click_counts(hb, b, {"session": "S1"})


def test_source_kinds_and_priority(index: LogIndex) -> None:
    """출처 id → 종류는 설정 값(없으면 id 그대로). 같은 호출이 두 출처에 있으면 앞 종류만 센다."""
    rows = [
        make_record("tool", source=src, session="S1", thread="main", tool="Read", call_id="c1")
        for src in ("a1", "b1")
    ]
    write(index, rows)
    h = Harness(index)
    view = h.project(session="S1")
    assert {(s.id, s.kind) for s in view.sources} == {("a1", "kind-a"), ("b1", "kind-b")}
    tools = next(c for c in view.cells if c.id == "tools")
    assert tools.metrics["count"].value == 1  # kind-a가 앞
    assert tools.selector.arch_sources == ["a1"]
    assert_click_counts(h, view, {"session": "S1"})
    # 대응이 없으면 출처 id가 종류 → 프로필 종류와 맞지 않아 우선순위로 빼지 않는다
    plain = Harness(index, source_kinds={}).project(session="S1")
    assert {(s.id, s.kind) for s in plain.sources} == {("a1", "a1"), ("b1", "b1")}
    assert next(c for c in plain.cells if c.id == "tools").metrics["count"].value == 2


def test_error_categories_come_from_query_context(index: LogIndex) -> None:
    write(index, [make_record("error", source="a1", session="S1", thread="sub1")])
    view = Harness(index).project(session="S1")
    workers = next(c for c in view.cells if c.id == "workers")
    assert CTX.error_categories == {"error"}
    assert workers.metrics["errors"].value == 1


def test_scope_too_large(index: LogIndex) -> None:
    write(index, random_records(random.Random(1), 30))
    h = Harness(index, max_scope_events=20)
    with pytest.raises(ScopeTooLargeError) as err:
        h.project(session="S1")
    assert err.value.limit == 20
    assert err.value.events > 20
    assert len(h.views.cache) == 0
    assert h.project(session="S2").event_total == 0  # 다른 범위는 그대로


def test_profile_selection(index: LogIndex) -> None:
    write(index, random_records(random.Random(2), 10))
    h = Harness(index)
    fallback = h.project(session="S1", profile="nope")
    assert fallback.profile == "demo"
    assert [n.code for n in fallback.notes] == ["architecture.profile_fallback"]
    empty = Harness(index, profiles={})
    with pytest.raises(ProfileNotFoundError):
        empty.project(session="S1")


def test_bad_filters(index: LogIndex) -> None:
    h = Harness(index)
    with pytest.raises(ArchitectureQueryError) as err:
        h.project(nope="1")
    assert err.value.path == "nope"
    with pytest.raises(ArchitectureQueryError) as err:
        h.project(scope="fake:x")
    assert err.value.path == "scope"
    for bad in (
        {"arch": "demo:cell:missing"},
        {"arch": "other:cell:tools"},
        {"arch": "demo:cell:input", "arch_group": "x"},
        {"arch_group": "x"},
        {"arch": "broken"},
    ):
        with pytest.raises(LogQueryError):
            h.count(bad)


def test_membership(index: LogIndex) -> None:
    write(
        index,
        [
            make_record(
                "tool",
                source="a1",
                session="S1",
                thread="main",
                tool="Read",
                tags=("tool_call",),
                detail={"big": "x" * 100},
            )
        ],
    )
    h = Harness(index)
    uid = h.query.events(h.query.parse_filter({})).items[0].uid
    found = h.views.membership(uid)
    assert (found.profile, found.uid, found.cells, found.edges) == (
        "demo",
        uid,
        ["tools"],
        ["call"],
    )
    with pytest.raises(EventNotFoundError):
        h.views.membership("missing")


def test_empty_group_selector_selects_unnamed_group(index: LogIndex) -> None:
    """이름 없는 묶음(`arch_group=""`)은 묶을 값이 없는 이벤트만 고른다."""
    write(
        index,
        [
            make_record("tool", source="a1", session="S1", thread="main", tool="Read"),
            make_record("tool", source="a1", session="S1", thread="main"),
        ],
    )
    h = Harness(index)
    view = h.project(session="S1")
    tools = next(c for c in view.cells if c.id == "tools")
    keys = {g.key: g for g in tools.groups or []}
    assert set(keys) == {"Read", None}
    unnamed = keys[None].selector
    assert unnamed.arch_group == ""
    assert h.count({"session": "S1", **selector_params(unnamed)}) == 1


def test_views_accept_injected_cache_and_selector_shape() -> None:
    catalog = StaticCatalog(demo_profiles())
    views = LogArchitectureViews(IndexLogQuery(MemoryLogIndex(), CTX), catalog, cache_scopes=0)
    view = views.project(views.parse({"session": "none"})[0])
    assert view.event_total == 0
    assert ArchitectureSelector.model_validate(view.cells[0].selector.model_dump()).arch.startswith(
        "demo:"
    )
