"""선택 필터 `arch`와 이벤트 판정: 투영 결과의 모든 칸·연결·묶음·분류 안 됨에서 판정 함수로
거른 수가 지표 `count`와 같다(R8.8 수 일치, 무작위 이벤트 포함). 멤버십."""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from agent_console_architecture import (
    ArchitectureSelectorError,
    ArchTarget,
    event_membership,
    format_arch,
    parse_arch,
    project_architecture,
    selector_predicate,
)
from agent_console_architecture.testing import make_events
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureMetric,
    ArchitectureProfile,
    ArchitectureSelector,
    ArchitectureView,
)
from agent_console_contracts.logs import LogEvent

Ops = dict[str, ConditionOperator]


def test_format_and_parse_arch() -> None:
    assert format_arch("p", "cell", "a") == "p:cell:a"
    assert format_arch("p", "unassigned") == "p:unassigned"
    assert parse_arch("p:cell:a") == ArchTarget("p", "cell", "a")
    assert parse_arch("p:edge:x:y") == ArchTarget("p", "edge", "x:y")
    assert parse_arch("p:unassigned") == ArchTarget("p", "unassigned")


@pytest.mark.parametrize(
    "value", ["", "p", ":cell:a", "p:cell", "p:cell:", "p:zone:a", "p:unassigned:x"]
)
def test_parse_arch_rejects(value: str) -> None:
    with pytest.raises(ArchitectureSelectorError):
        parse_arch(value)


@pytest.mark.parametrize(
    ("arch", "group"),
    [
        ("other:cell:input", None),
        ("demo:cell:nope", None),
        ("demo:edge:nope", None),
        ("demo:cell:input", "x"),  # 묶을 값이 없는 칸
        ("demo:edge:call", "x"),
        ("demo:unassigned", "x"),
    ],
)
def test_selector_predicate_rejects(
    demo_profile: ArchitectureProfile, operators: Ops, arch: str, group: str | None
) -> None:
    with pytest.raises(ArchitectureSelectorError):
        selector_predicate(
            demo_profile,
            ArchitectureSelector(arch=arch, arch_group=group),
            profile_id="demo",
            operators=operators,
        )


Target = tuple[str, ArchitectureSelector, ArchitectureMetric]


def _targets(view: ArchitectureView) -> Iterator[Target]:
    for cell in view.cells:
        yield f"cell {cell.id}", cell.selector, cell.metrics["count"]
        for group in cell.groups or []:
            yield f"group {cell.id}/{group.key}", group.selector, group.metrics["count"]
    for edge in view.edges:
        if edge.selector is not None:
            yield f"edge {edge.id}", edge.selector, edge.metrics["count"]
    if view.unassigned is not None:
        yield "unassigned", view.unassigned.selector, view.unassigned.metrics["count"]


def _assert_click_counts(
    view: ArchitectureView,
    events: list[LogEvent],
    profile: ArchitectureProfile,
    operators: Ops,
) -> int:
    checked = 0
    bound = view.max_seq
    scoped = [e for e in events if bound is not None and e.seq <= bound]
    for name, selector, count in _targets(view):
        if count.status == "not_collected":
            continue
        keep = selector_predicate(profile, selector, profile_id=view.profile, operators=operators)
        assert sum(1 for e in scoped if keep(e)) == count.value, name
        checked += 1
    return checked


def test_click_counts_match_demo(
    demo_events: list[LogEvent],
    demo_profile: ArchitectureProfile,
    operators: Ops,
    source_kinds: dict[str, str],
) -> None:
    view = project_architecture(
        demo_events,
        demo_profile,
        profile_id="demo",
        operators=operators,
        source_kinds=source_kinds,
    )
    assert _assert_click_counts(view, demo_events, demo_profile, operators) >= 10


@pytest.mark.parametrize("seed", range(8))
def test_click_counts_match_random_events(
    seed: int, demo_profile: ArchitectureProfile, operators: Ops, source_kinds: dict[str, str]
) -> None:
    rng = random.Random(seed)
    rows = []
    for _ in range(rng.randint(0, 120)):
        row: dict[str, object] = {
            "source": rng.choice(["a1", "b1", "c1"]),
            "thread": rng.choice(["main", "main", "sub1", "sub2", ""]),
            "category": rng.choice(["input", "llm", "tool", "agent", "other"]),
            "status": rng.choice(["", "ok", "failed", "error"]),
            "tags": rng.sample(["tool_call", "tool_result", "x"], rng.randint(0, 2)),
        }
        if rng.random() < 0.7:
            row["tool"] = rng.choice(["Read", "Grep", "Write", "mcp__s__t", ""])
        if rng.random() < 0.5:
            row["model"] = rng.choice(["m1", "m2", "m3"])
        if rng.random() < 0.3:
            row["duration_ms"] = rng.uniform(1, 500)
        rows.append(row)
    events = make_events(rows)
    rng.shuffle(events)
    max_seq = rng.choice([None, len(rows) // 2])
    view = project_architecture(
        events,
        demo_profile,
        profile_id="demo",
        operators=operators,
        source_kinds=source_kinds,
        max_seq=max_seq,
    )
    _assert_click_counts(view, events, demo_profile, operators)
    # 칸 안 묶음의 합(표시 + 그 밖) = 칸 횟수
    for cell in view.cells:
        if cell.groups is None or cell.metrics["count"].value is None:
            continue
        total = sum(g.metrics["count"].value or 0 for g in cell.groups)
        if cell.groups_rest is not None:
            total += cell.groups_rest.metrics["count"].value or 0
        assert total == cell.metrics["count"].value


def test_structural_edge_and_disabled_unassigned_select_nothing(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    keep = selector_predicate(
        demo_profile,
        ArchitectureSelector(arch="demo:edge:ask"),
        profile_id="demo",
        operators=operators,
    )
    assert not any(keep(e) for e in demo_events)
    off = demo_profile.model_copy(update={"unassigned": False})
    keep = selector_predicate(
        off, ArchitectureSelector(arch="demo:unassigned"), profile_id="demo", operators=operators
    )
    assert not any(keep(e) for e in demo_events)


def test_membership(
    demo_events: list[LogEvent], demo_profile: ArchitectureProfile, operators: Ops
) -> None:
    sub = next(e for e in demo_events if e.thread == "sub1")
    found = event_membership(sub, demo_profile, profile_id="demo", operators=operators)
    assert found.profile == "demo"
    assert found.uid == sub.uid
    assert found.cells == ["model", "workers"]
    assert found.edges == []
    assert [(g.cell, g.key) for g in found.groups] == [("model", "m2"), ("workers", "sub1")]
    assert found.unassigned is False

    call = next(e for e in demo_events if "tool_call" in e.tags)
    assert event_membership(call, demo_profile, profile_id="demo", operators=operators).edges == [
        "call"
    ]
    agent = next(e for e in demo_events if e.category == "agent")
    assert event_membership(agent, demo_profile, profile_id="demo", operators=operators).unassigned
