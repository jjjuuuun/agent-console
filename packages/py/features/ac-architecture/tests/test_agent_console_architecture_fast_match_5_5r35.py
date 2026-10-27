"""5.5R.35: 컴파일한 조건(참·거짓만)으로 판정해도 결과가 같다(차등 테스트).

기준은 5.5R.10까지의 판정(이벤트 전체 덤프 + `evaluate_conditions` 근거 API)이다. 무작위 프로필·
이벤트와 기본 프로필로 칸·연결·묶음·오류를 비교한다.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

import pytest

from agent_console_architecture import (
    EventMatch,
    ProfileMatcher,
    event_subject,
    load_default_profiles,
)
from agent_console_conditions import (
    MISSING,
    ConditionOperator,
    evaluate_conditions,
    resolve_pointer,
)
from agent_console_contracts import ConditionSpec
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_contracts.logs import LogEvent

Ops = dict[str, ConditionOperator]


def _reference(
    profile: ArchitectureProfile, operators: Ops, errors: frozenset[str], event: LogEvent
) -> EventMatch:
    """5.5R.10까지의 판정(근거 API + 전체 덤프)."""
    subject = event_subject(event)

    def holds(spec: ConditionSpec) -> bool:
        return evaluate_conditions(spec, subject, operators).result

    def group(pointer: str) -> str | None:
        value = resolve_pointer(subject, pointer)
        if value is MISSING or value is None or value == "":
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    cells: list[str] = []
    groups: dict[str, str | None] = {}
    for cid, cell in profile.cells.items():
        if cell.when is not None and holds(cell.when):
            cells.append(cid)
            if cell.group_by is not None:
                groups[cid] = group(cell.group_by)
    first: dict[str, Any] = {}
    for edge in profile.edges:
        first.setdefault(edge.id, edge)
    edges = [
        eid
        for eid, edge in first.items()
        if edge.when is not None and edge.kind == "observed" and holds(edge.when)
    ]
    error = subject.get("category") in errors
    if not error and profile.error_when is not None:
        error = holds(profile.error_when)
    return EventMatch(cells=tuple(cells), edges=tuple(edges), groups=groups, error=error)


CATEGORIES = ["input", "llm", "tool", "hook", "error", ""]
PATHS = [
    "/category",
    "/thread",
    "/tool",
    "/status",
    "/from",
    "/from/0",
    "/to/1",
    "/tags",
    "/tags/0",
    "/correlation",
    "/correlation/k",
    "/correlation/k/0",
    "/documents",
    "/documents/0/kind",
    "/time",
    "/duration_ms",
    "/seq",
    "/nope",
    "",
]
VALUES: list[Any] = [
    *CATEGORIES,
    "main",
    "Bash",
    "ok",
    "failed",
    "skill",
    None,
    0,
    1,
    1.5,
    10.0,
    True,
    ["tool", "hook"],
    ["main", "sub"],
    [],
    {"k": "v"},
]
OPS = ["eq", "ne", "in", "contains", "matches", "exists", "gt", "gte", "lt", "lte", "nope"]


def _item(rng: random.Random) -> dict[str, Any]:
    op = rng.choice(OPS)
    value: Any = rng.choice(VALUES)
    if op == "matches":
        value = rng.choice(["^t", "o+", "a|b", "["])
    elif op == "in":
        value = rng.sample(VALUES, rng.randint(0, 4))
    return {"path": rng.choice(PATHS), "op": op, "value": value}


def _spec(rng: random.Random) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    if rng.random() < 0.8:
        spec["all"] = [_item(rng) for _ in range(rng.randint(1, 3))]
    if rng.random() < 0.4:
        spec["any"] = [_item(rng) for _ in range(rng.randint(1, 3))]
    if rng.random() < 0.2:
        spec["negate"] = True
    return spec


def _profile(rng: random.Random) -> ArchitectureProfile:
    cells: dict[str, Any] = {}
    for i in range(rng.randint(1, 8)):
        cell: dict[str, Any] = {"when": _spec(rng)}
        if rng.random() < 0.4:
            cell["group_by"] = rng.choice(PATHS)
        cells[f"c{i}"] = cell
    ids = list(cells)
    edges = [
        {
            "id": f"e{i % 5}",  # 중복 id도 섞는다(처음 것만 쓴다)
            "from": rng.choice(ids),
            "to": rng.choice(ids),
            "kind": rng.choice(["observed", "structural"]),
            "when": _spec(rng),
        }
        for i in range(rng.randint(0, 7))
    ]
    data: dict[str, Any] = {"cells": cells, "edges": edges}
    if rng.random() < 0.5:
        data["error_when"] = _spec(rng)
    return ArchitectureProfile.model_validate(data)


def _event(rng: random.Random, seq: int) -> LogEvent:
    row: dict[str, Any] = {
        "uid": f"u{seq}",
        "seq": seq,
        "source": "s",
        "observed_at": 1.0,
        "category": rng.choice([c for c in CATEGORIES if c]),
        "thread": rng.choice(["main", "sub", ""]),
        "tool": rng.choice(["Bash", "Read", ""]),
        "status": rng.choice(["ok", "failed", ""]),
        "from": rng.choice([[], ["main"], ["main", "sub"]]),
        "to": rng.choice([[], ["a", "b"]]),
        "tags": rng.choice([[], ["tool"], ["tool", "hook"]]),
        "correlation": rng.choice([{}, {"k": "v"}, {"k": ["a", "b"]}]),
        "documents": rng.choice([[], [{"path": "a.md", "kind": "skill"}]]),
        "time": rng.choice([None, 1.5, 10.0, math.inf]),
        "duration_ms": rng.choice([None, 0.0, 12.5]),
    }
    return LogEvent.model_validate(row)


@pytest.mark.parametrize("seed", range(6))
def test_fast_matcher_equals_reference(seed: int, operators: Ops) -> None:
    rng = random.Random(seed)
    errors = frozenset({"error"}) if seed % 2 else frozenset()
    events = [_event(rng, i) for i in range(60)]
    for _ in range(30):
        profile = _profile(rng)
        matcher = ProfileMatcher(profile, operators, error_categories=errors)
        for event in events:
            want = _reference(profile, operators, errors, event)
            assert matcher.match(event) == want, (profile, event)


def test_default_profile_equals_reference(operators: Ops) -> None:
    rng = random.Random(99)
    profiles = load_default_profiles()
    events = [_event(rng, i) for i in range(400)]
    for profile in profiles.values():
        matcher = ProfileMatcher(profile, operators, error_categories={"error"})
        for event in events:
            assert matcher.match(event) == _reference(
                profile, operators, frozenset({"error"}), event
            )
