"""순수 투영(design §5.5R.10 "순수 투영" 행): 지표 5개·상태 3개·수집 범위·묶기·하위 구조도·
분류 안 됨·출처 우선순위·max_seq 경계, 그리고 R0 판정(칸·연결 id를 모두 바꿔도 같은 수,
빈 프로필)."""

from __future__ import annotations

import pytest

from agent_console_architecture import (
    DEFAULT_CELL_SIZE,
    project_architecture,
)
from agent_console_architecture.testing import make_events, rename_profile_ids
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureCellView,
    ArchitectureEdgeView,
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureView,
    KnownArchitectureNoteCodes,
)
from agent_console_contracts.logs import LogEvent, TokenSample

Ops = dict[str, ConditionOperator]


def _view(
    events: list[LogEvent],
    profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
    tokens: list[TokenSample] | None = None,
    **kwargs: object,
) -> ArchitectureView:
    return project_architecture(
        events,
        profile,
        profile_id="demo",
        operators=operators,
        source_kinds=source_kinds,
        tokens=tokens or [],
        **kwargs,  # type: ignore[arg-type]
    )


def _cell(view: ArchitectureView, cid: str) -> ArchitectureCellView:
    return next(c for c in view.cells if c.id == cid)


def _edge(view: ArchitectureView, eid: str) -> ArchitectureEdgeView:
    return next(e for e in view.edges if e.id == eid)


def _value(view: ArchitectureView, cid: str, metric: str) -> float | None:
    return _cell(view, cid).metrics[metric].value


@pytest.fixture
def view(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
    demo_tokens: list[TokenSample],
) -> ArchitectureView:
    return _view(demo_events, demo_profile, operators, source_kinds, demo_tokens)


# ---------------------------------------------------------------- 그리기 완결형


def test_view_carries_drawing_data(view: ArchitectureView) -> None:
    assert view.profile == "demo"
    assert view.title == "데모"
    assert view.canvas is not None
    assert (view.canvas.width, view.canvas.height) == (800, 400)
    assert [z.id for z in view.zones] == ["local", "remote"]
    assert [c.id for c in view.cells] == ["input", "model", "tools", "workers", "memo"]
    assert [e.id for e in view.edges] == ["ask", "call", "back"]
    model = _cell(view, "model")
    assert (model.label, model.description, model.x, model.y, model.zone) == (
        "모델",
        "원격 모델",
        700,
        50,
        "remote",
    )
    assert (model.w, model.h) == DEFAULT_CELL_SIZE
    assert _cell(view, "memo").w == 120
    assert _cell(view, "input").tone == "blue"
    assert _cell(view, "workers").view == "grouped"
    back = _edge(view, "back")
    assert back.points == [[300, 200], [700, 200], [700, 50]]
    assert back.label_at == [500, 200]
    assert back.label_max_w == 92
    assert (back.from_, back.to, back.style, back.label) == ("tools", "model", "return", "결과")
    assert view.event_total == 10
    assert view.max_seq == 10
    assert [(s.id, s.kind, s.events) for s in view.sources] == [
        ("a1", "kind-a", 9),
        ("b1", "kind-b", 1),
    ]


# ---------------------------------------------------------------- 지표 5개·상태 3개


def test_count_and_errors(view: ArchitectureView) -> None:
    assert _value(view, "input", "count") == 1
    assert _value(view, "model", "count") == 3
    assert _value(view, "model", "errors") == 1  # error_when: status error
    assert _value(view, "tools", "errors") == 1  # status failed
    # 기본 지표(비우면 횟수·오류)
    assert list(_cell(view, "input").metrics) == ["count", "errors"]
    assert _cell(view, "input").metrics["count"].status == "observed"


def test_errors_from_error_categories(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
) -> None:
    view = _view(
        demo_events, demo_profile, operators, source_kinds, error_categories=frozenset({"input"})
    )
    assert _value(view, "input", "errors") == 1


def test_zero_is_observed_not_null(
    demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    events = make_events([{"thread": "main", "source": "a1", "category": "input"}])
    view = _view(events, demo_profile, operators, source_kinds)
    tools = _cell(view, "tools")
    assert tools.status == "observed"
    assert tools.metrics["count"].status == "observed"
    assert tools.metrics["count"].value == 0
    # 소요 재료가 없으면 0이 아니라 수집 안 됨(null)
    assert tools.metrics["duration"].status == "not_collected"
    assert tools.metrics["duration"].value is None


def test_duration_uses_explicit_pair_values_only(view: ArchitectureView) -> None:
    duration = _cell(view, "tools").metrics["duration"]
    assert duration.status == "observed"
    assert duration.value == 120  # b1(kind-b)의 130은 우선순위로 빠진다
    assert duration.detail is not None
    assert (duration.detail.samples, duration.detail.total_ms, duration.detail.max_ms) == (
        1,
        120,
        120,
    )
    # 호출 연결에는 소요가 있는 이벤트가 없다
    assert _edge(view, "call").metrics["duration"].status == "not_collected"


def test_tokens_once_per_response(view: ArchitectureView) -> None:
    # (main, r1) 두 행이지만 한 번(10+5), 같은 응답의 작은 표본(3)은 버림, (sub1, r2) 7,
    # 무관한 zz는 빠짐
    tokens = _cell(view, "model").metrics["tokens"]
    assert tokens.status == "observed"
    assert tokens.value == 22
    assert _value(view, "workers", "tokens") == 7


def test_tokens_not_collected_without_samples(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
) -> None:
    view = _view(demo_events, demo_profile, operators, source_kinds, tokens=[])
    tokens = _cell(view, "model").metrics["tokens"]
    assert (tokens.status, tokens.value) == ("not_collected", None)


def test_inferred_duration_status_and_option(
    view: ArchitectureView,
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
) -> None:
    inferred = _cell(view, "model").metrics["inferred_duration"]
    # main 응답 r1 첫 행(10.0) - 바로 앞 이벤트(9.5) = 500ms. sub1의 r2는 앞 이벤트가 없다.
    assert inferred.status == "inferred"
    assert inferred.value == pytest.approx(500)
    assert inferred.detail is not None
    assert inferred.detail.samples == 1

    off = demo_profile.model_copy(update={"options": None})
    plain = _view(demo_events, off, operators, source_kinds)
    assert "inferred_duration" not in _cell(plain, "model").metrics


def test_unknown_metric_name_is_skipped(
    demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    cell = demo_profile.cells["input"].model_copy(update={"metrics": ["count", "nonsense"]})
    profile = demo_profile.model_copy(update={"cells": {**demo_profile.cells, "input": cell}})
    view = _view([], profile, operators, source_kinds)
    assert list(_cell(view, "input").metrics) == ["count"]


# ---------------------------------------------------------------- 수집 범위·부분·수집 불가


def test_coverage_and_partial(view: ArchitectureView) -> None:
    memo = _cell(view, "memo")  # 어느 출처도 채우지 않고 이벤트도 없다
    assert memo.status == "not_collected"
    assert memo.metrics["count"].status == "not_collected"
    assert memo.metrics["count"].value is None
    workers = _cell(view, "workers")
    assert (workers.status, workers.partial_reason) == ("partial", "일부만 보임")
    assert _cell(view, "tools").status == "observed"  # kind-a는 부분이 아님


def test_partial_needs_every_covering_kind(
    demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    events = make_events([{"thread": "x", "source": "a1", "category": "input"}])
    view = _view(events, demo_profile, operators, {"a1": "kind-a"})
    assert _cell(view, "workers").status == "partial"
    # 출처 종류가 kind-b뿐이면 workers를 채우는 종류가 없다. 하지만 맞은 이벤트가 있으면 관측이다.
    view_b = _view(events, demo_profile, operators, {"a1": "kind-b"})
    assert _cell(view_b, "workers").status == "observed"
    assert _cell(view_b, "model").status == "not_collected"


def test_no_events_means_not_collected_everywhere(
    demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    view = _view([], demo_profile, operators, source_kinds)
    assert {c.status for c in view.cells} == {"not_collected"}
    assert view.event_total == 0
    assert view.max_seq is None
    assert view.sources == []
    assert view.unassigned is not None
    assert view.unassigned.metrics["count"].value == 0


def test_profile_without_coverage_is_observed(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    profile = demo_profile.model_copy(update={"coverage": {}})
    view = _view(demo_events, profile, operators, {})
    assert {c.status for c in view.cells} == {"observed"}


def test_unavailable_items(view: ArchitectureView) -> None:
    model = _cell(view, "model")
    assert [(u.cell, u.item, u.reason) for u in model.unavailable] == [
        ("model", "요청 본문", "로그에 남지 않음")
    ]
    assert [(u.cell, u.item) for u in view.unavailable] == [("model", "요청 본문")]


# ---------------------------------------------------------------- 묶기·그 밖·하위 구조도


def test_groups_limit_and_rest(view: ArchitectureView) -> None:
    tools = _cell(view, "tools")
    assert tools.groups is not None
    # 횟수 내림차순, 같으면 값 순서. 표시 개수 2 → Read, Grep. 나머지 Write는 "그 밖 1"
    assert [(g.key, g.metrics["count"].value) for g in tools.groups] == [("Read", 2), ("Grep", 1)]
    assert tools.groups_rest is not None
    assert tools.groups_rest.groups == 1
    assert tools.groups_rest.metrics["count"].value == 1
    assert tools.groups[0].selector.arch_group == "Read"
    assert tools.groups[1].metrics["errors"].value == 1
    assert _cell(view, "input").groups is None


def test_group_without_value_is_unnamed(
    demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    events = make_events(
        [
            {"thread": "main", "source": "a1", "category": "tool"},
            {"thread": "main", "source": "a1", "category": "tool", "tool": ""},
        ]
    )
    tools = _cell(_view(events, demo_profile, operators, source_kinds), "tools")
    assert tools.groups is not None
    assert [(g.key, g.metrics["count"].value) for g in tools.groups] == [(None, 2)]
    assert tools.groups[0].selector.arch_group == ""
    assert tools.groups_rest is None


def test_drill_substitution(view: ArchitectureView) -> None:
    workers = _cell(view, "workers")
    assert workers.drillable is True
    assert workers.groups is not None
    drill = workers.groups[0].drill
    assert drill is not None
    assert (drill.filter, drill.value) == ("thread", "sub1")
    assert _cell(view, "tools").drillable is False
    assert _cell(view, "tools").groups[0].drill is None  # type: ignore[index]


def test_drill_template_prefix(
    demo_profile: ArchitectureProfile, operators: Ops, demo_events: list[LogEvent]
) -> None:
    cell = demo_profile.cells["workers"].model_copy(deep=True)
    assert cell.drill is not None
    cell.drill.filter, cell.drill.value = "scope", "run:{group}"
    profile = demo_profile.model_copy(update={"cells": {**demo_profile.cells, "workers": cell}})
    groups = _cell(_view(demo_events, profile, operators, {}), "workers").groups
    assert groups is not None
    assert groups[0].drill is not None
    assert (groups[0].drill.filter, groups[0].drill.value) == ("scope", "run:sub1")


def test_group_limit_zero_puts_all_in_rest(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    profile = demo_profile.model_copy(update={"group_limit": 0})
    tools = _cell(_view(demo_events, profile, operators, {}), "tools")
    assert tools.groups == []
    assert tools.groups_rest is not None
    assert tools.groups_rest.groups == 3


# ---------------------------------------------------------------- 분류 안 됨


def test_unassigned(
    view: ArchitectureView,
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
) -> None:
    assert view.unassigned is not None
    assert view.unassigned.metrics["count"].value == 1  # agent 행 하나(응답으로 몰지 않는다)
    assert view.unassigned.selector.arch == "demo:unassigned"
    off = demo_profile.model_copy(update={"unassigned": False})
    assert _view(demo_events, off, operators, {}).unassigned is None


# ---------------------------------------------------------------- 연결


def test_edges_observed_and_structural(view: ArchitectureView) -> None:
    call = _edge(view, "call")
    assert call.kind == "observed"
    assert call.metrics["count"].value == 3
    assert call.metrics["errors"].value == 1
    assert call.selector is not None
    assert call.selector.arch == "demo:edge:call"
    ask = _edge(view, "ask")
    assert (ask.kind, ask.metrics, ask.selector) == ("structural", {}, None)
    assert ask.status == "observed"


def test_edge_status_follows_ends_when_empty(
    demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    edge = {
        "id": "to-memo",
        "from": "input",
        "to": "memo",
        "when": {"all": [{"path": "/category", "op": "eq", "value": "memo"}]},
    }
    profile = ArchitectureProfile.model_validate(
        {**demo_profile.model_dump(by_alias=True), "edges": [edge]}
    )
    events = make_events([{"thread": "main", "source": "a1", "category": "input"}])
    to_memo = _edge(_view(events, profile, operators, source_kinds), "to-memo")
    assert to_memo.status == "not_collected"
    assert to_memo.metrics["count"].value is None


def test_unknown_kind_is_structural_and_bad_edges_are_dropped(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    data = demo_profile.model_dump(by_alias=True)
    data["edges"] = [
        {
            "id": "odd",
            "from": "input",
            "to": "model",
            "kind": "maybe",
            "when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]},
        },
        {"id": "ghost", "from": "input", "to": "nowhere"},
        {"id": "odd", "from": "model", "to": "tools"},
    ]
    view = _view(demo_events, ArchitectureProfile.model_validate(data), operators, {})
    assert [(e.id, e.kind, e.from_) for e in view.edges] == [("odd", "structural", "input")]
    assert [(n.code, n.details) for n in view.notes] == [
        (KnownArchitectureNoteCodes.PROFILE_ISSUES, {"issues": 2})
    ]


def test_notes_pass_through(demo_profile: ArchitectureProfile, operators: Ops) -> None:
    note = ArchitectureNote(code="x.y", message="안내")
    view = _view([], demo_profile, operators, {}, notes=[note])
    assert view.notes == [note]


# ---------------------------------------------------------------- 출처 우선순위·max_seq


def test_source_priority_counts_first_kind_only(view: ArchitectureView) -> None:
    tools = _cell(view, "tools")
    assert tools.metrics["count"].value == 4  # b1(kind-b) 결과 행 빠짐
    assert tools.selector.arch_sources == ["a1"]
    back = _edge(view, "back")
    assert back.metrics["count"].value == 1
    assert back.selector is not None
    assert back.selector.arch_sources == ["a1"]
    # 한 종류만 맞은 칸은 출처를 거르지 않는다
    assert _cell(view, "model").selector.arch_sources is None


def test_source_priority_unknown_kind_goes_last(
    demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    events = make_events(
        [
            {"thread": "main", "source": "x9", "category": "tool"},
            {"thread": "main", "source": "b1", "category": "tool"},
        ]
    )
    tools = _cell(_view(events, demo_profile, operators, {"b1": "kind-b"}), "tools")
    assert tools.metrics["count"].value == 1
    assert tools.selector.arch_sources == ["b1"]
    no_priority = demo_profile.model_copy(update={"source_priority": []})
    both = _cell(_view(events, no_priority, operators, {"b1": "kind-b"}), "tools")
    assert both.metrics["count"].value == 2
    assert both.selector.arch_sources is None


def test_max_seq_boundary(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
) -> None:
    view = _view(demo_events, demo_profile, operators, source_kinds, max_seq=5)
    assert view.event_total == 5
    assert view.max_seq == 5
    assert _value(view, "tools", "count") == 2
    assert _value(view, "model", "count") == 2


# ---------------------------------------------------------------- R0 판정


def _counts(view: ArchitectureView) -> list[tuple[float | None, ...]]:
    rows: list[tuple[float | None, ...]] = []
    for cell in view.cells:
        rows.append(tuple(m.value for m in cell.metrics.values()))
        for group in cell.groups or []:
            rows.append(tuple(m.value for m in group.metrics.values()))
    for edge in view.edges:
        rows.append(tuple(m.value for m in edge.metrics.values()))
    if view.unassigned is not None:
        rows.append(tuple(m.value for m in view.unassigned.metrics.values()))
    return rows


def test_renamed_ids_give_same_numbers(
    view: ArchitectureView,
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
    demo_tokens: list[TokenSample],
) -> None:
    renamed = rename_profile_ids(
        demo_profile, cell=lambda c: f"zz-{c[::-1]}", edge=lambda e: f"q{len(e)}-{e.upper()}"
    )
    assert set(renamed.cells).isdisjoint(demo_profile.cells)
    other = project_architecture(
        demo_events,
        renamed,
        profile_id="other-profile",
        operators=operators,
        source_kinds=source_kinds,
        tokens=demo_tokens,
    )
    assert _counts(other) == _counts(view)
    assert [c.status for c in other.cells] == [c.status for c in view.cells]
    assert {c.selector.arch.split(":", 1)[0] for c in other.cells} == {"other-profile"}


def test_empty_profile_and_empty_events_do_not_raise(
    demo_events: list[LogEvent], operators: Ops
) -> None:
    empty = ArchitectureProfile()
    view = project_architecture(demo_events, empty, profile_id="p", operators=operators)
    assert (view.cells, view.edges, view.canvas) == ([], [], None)
    assert view.unassigned is not None
    assert view.unassigned.metrics["count"].value == len(demo_events)
    assert view.title == "p"
    nothing = project_architecture([], empty, profile_id="p", operators={})
    assert nothing.event_total == 0
