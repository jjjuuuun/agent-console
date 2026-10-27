"""5.5R.36: 누적 집계(`ArchitectureTally`, 증분 투영)와 JSON 행 입력이 한 번에 그린 결과와 같다.

- 이벤트를 여러 번 나눠 더하고 중간중간 그려도, 끝의 `view`는 전체를 한 번에 투영한 것과 같다.
- 출처 종류(`source_kinds`)는 `view` 인자다 — 같은 누적에서 종류를 바꿔 그려도 새로 투영한 것과
  같다.
- JSON 행(`LogEvent`를 계약 별칭으로 덤프한 dict)을 넣어도 이벤트와 같은 결과다.
무작위 프로필(출처 우선순위·수집 범위·묶기·지표 5개·추정 소요 포함)과 기본 프로필·표본으로 본다.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from agent_console_architecture import (
    ArchitectureTally,
    ProfileMatcher,
    load_default_profiles,
    project_architecture,
)
from agent_console_architecture.testing import SAMPLES, load_sample
from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import ArchitectureProfile, ArchitectureView
from agent_console_contracts.logs import LogEvent, TokenSample

Ops = dict[str, ConditionOperator]
SOURCES = ["s1", "s2", "s3"]
KINDS = ["k1", "k2", "k3"]
CATEGORIES = ["input", "llm", "tool", "hook", "error"]
METRICS = ["count", "errors", "duration", "tokens", "inferred_duration", "nope"]


def _cond(rng: random.Random) -> dict[str, Any]:
    path, values = rng.choice(
        [
            ("/category", CATEGORIES),
            ("/thread", ["main", "sub"]),
            ("/tool", ["Bash", "Read", ""]),
            ("/source", SOURCES),
        ]
    )
    return {"all": [{"path": path, "op": rng.choice(["eq", "ne"]), "value": rng.choice(values)}]}


def _profile(rng: random.Random) -> ArchitectureProfile:
    cells: dict[str, Any] = {}
    for i in range(rng.randint(1, 6)):
        cell: dict[str, Any] = {"when": _cond(rng)}
        if rng.random() < 0.5:
            cell["group_by"] = rng.choice(["/tool", "/thread", "/message_id", "/nope"])
        if rng.random() < 0.7:
            cell["metrics"] = rng.sample(METRICS, rng.randint(0, 4))
        if rng.random() < 0.3:
            cell["drill"] = {"filter": "session", "value": "{group}"}
        cells[f"c{i}"] = cell
    ids = list(cells)
    edges = [
        {
            "id": f"e{i}",
            "from": rng.choice(ids),
            "to": rng.choice([*ids, "missing"]),
            "kind": rng.choice(["observed", "observed", "structural"]),
            "when": _cond(rng),
            "metrics": rng.sample(METRICS, rng.randint(0, 3)),
        }
        for i in range(rng.randint(0, 5))
    ]
    data: dict[str, Any] = {
        "cells": cells,
        "edges": edges,
        "unassigned": rng.random() < 0.7,
        "group_limit": rng.randint(1, 4),
        "options": {"inferred_llm_duration": rng.random() < 0.5},
    }
    if rng.random() < 0.7:
        data["source_priority"] = rng.sample(KINDS, rng.randint(1, 3))
    if rng.random() < 0.6:
        data["coverage"] = {
            kind: {
                "cells": rng.sample(ids, rng.randint(0, len(ids))),
                "partial": {cid: "일부" for cid in rng.sample(ids, rng.randint(0, 1))},
            }
            for kind in rng.sample(KINDS, rng.randint(1, 3))
        }
    if rng.random() < 0.5:
        data["error_when"] = {"all": [{"path": "/status", "op": "eq", "value": "failed"}]}
    return ArchitectureProfile.model_validate(data)


def _events(rng: random.Random, n: int) -> list[LogEvent]:
    out = []
    for seq in range(1, n + 1):
        out.append(
            LogEvent.model_validate(
                {
                    "uid": f"u{seq}",
                    "seq": seq,
                    "source": rng.choice(SOURCES),
                    "observed_at": 1.0,
                    "category": rng.choice(CATEGORIES),
                    "thread": rng.choice(["main", "sub", ""]),
                    "tool": rng.choice(["Bash", "Read", ""]),
                    "status": rng.choice(["ok", "failed", ""]),
                    "message_id": rng.choice(["", "m1", "m2", "m3"]),
                    "time": rng.choice([None, 1.0 + rng.random() * 50, 7.0]),
                    "duration_ms": rng.choice([None, 0.0, 12.5, 0.1, 1e-3, 3.3]),
                }
            )
        )
    return out


def _tokens(rng: random.Random) -> list[TokenSample]:
    return [
        TokenSample(
            thread=rng.choice(["main", "sub", ""]),
            message_id=rng.choice(["m1", "m2", "m3", ""]),
            input_tokens=rng.choice([None, 3, 10]),
            output_tokens=rng.choice([None, 1, 7]),
        )
        for _ in range(rng.randint(0, 8))
    ]


def _dump(view: ArchitectureView) -> dict[str, Any]:
    return view.model_dump(mode="json", by_alias=True)


def _kinds(rng: random.Random) -> dict[str, str]:
    return {s: rng.choice(KINDS) for s in rng.sample(SOURCES, rng.randint(0, len(SOURCES)))}


@pytest.mark.parametrize("seed", range(8))
def test_tally_in_chunks_equals_one_shot(seed: int, operators: Ops) -> None:
    rng = random.Random(seed)
    errors = frozenset({"error"}) if seed % 2 else frozenset()
    events = _events(rng, 120)
    for _ in range(25):
        profile = _profile(rng)
        kinds, tokens = _kinds(rng), _tokens(rng)
        matcher = ProfileMatcher(profile, operators, error_categories=errors)
        tally = ArchitectureTally(profile, profile_id="p")
        cut = sorted(rng.sample(range(1, len(events)), 3))
        for start, end in zip([0, *cut], [*cut, len(events)], strict=True):
            for event in events[start:end]:
                tally.add_event(event, matcher.match(event))
            partial = project_architecture(
                events[:end],
                profile,
                profile_id="p",
                operators=operators,
                source_kinds=kinds,
                tokens=tokens,
                error_categories=errors,
            )
            assert _dump(tally.view(source_kinds=kinds, tokens=tokens)) == _dump(partial)
        assert tally.events == len(events)
        assert tally.max_seq == events[-1].seq
        # 출처 종류만 바꿔 그려도 새로 투영한 것과 같다(다시 세지 않는다)
        other = _kinds(rng)
        fresh = project_architecture(
            events,
            profile,
            profile_id="p",
            operators=operators,
            source_kinds=other,
            tokens=tokens,
            error_categories=errors,
        )
        assert _dump(tally.view(source_kinds=other, tokens=tokens)) == _dump(fresh)


def test_small_cache_limits_give_same_views(
    operators: Ops, monkeypatch: pytest.MonkeyPatch
) -> None:
    """판정 결과 공유·누적 목록 기억의 상한을 넘어도(새 객체·id 재사용) 결과가 같다."""
    from agent_console_architecture import _match, _tally

    monkeypatch.setattr(_tally, "PLAN_LIMIT", 1)
    monkeypatch.setattr(_match, "MATCH_TABLE_LIMIT", 1)
    monkeypatch.setattr(_match, "GATE_TABLE_LIMIT", 1)
    test_tally_in_chunks_equals_one_shot(3, operators)


@pytest.mark.parametrize("seed", range(4))
def test_rows_equal_events(seed: int, operators: Ops) -> None:
    rng = random.Random(100 + seed)
    events = _events(rng, 80)
    rows = [e.model_dump(mode="json", by_alias=True) for e in events]
    mixed: list[Any] = [
        r if i % 2 else e for i, (e, r) in enumerate(zip(events, rows, strict=True))
    ]
    for _ in range(15):
        profile = _profile(rng)
        kinds, tokens = _kinds(rng), _tokens(rng)
        bound = rng.choice([None, 40])
        args: dict[str, Any] = {
            "profile_id": "p",
            "operators": operators,
            "source_kinds": kinds,
            "tokens": tokens,
            "error_categories": {"error"},
            "max_seq": bound,
        }
        want = _dump(project_architecture(events, profile, **args))
        assert _dump(project_architecture(rows, profile, **args)) == want
        assert _dump(project_architecture(mixed, profile, **args)) == want
        matcher = ProfileMatcher(profile, operators, error_categories={"error"})
        matches = [matcher.match_subject(r) for r in rows]
        assert matches == [matcher.match(e) for e in events]
        assert _dump(project_architecture(rows, profile, matches=matches, **args)) == want


@pytest.mark.parametrize("name", SAMPLES)
def test_default_profile_tally_matches_projection(name: str, operators: Ops) -> None:
    sample = load_sample(name)
    for pid, profile in load_default_profiles().items():
        matcher = ProfileMatcher(profile, operators, error_categories={"error"})
        tally = ArchitectureTally(profile, profile_id=pid)
        half = len(sample.events) // 2
        for event in sample.events[:half]:
            tally.add_event(event, matcher.match(event))
        tally.view(source_kinds=sample.source_kinds, tokens=sample.tokens)
        for event in sample.events[half:]:
            tally.add_row(event.model_dump(mode="json", by_alias=True), matcher.match(event))
        want = project_architecture(
            sample.events,
            profile,
            profile_id=pid,
            operators=operators,
            source_kinds=sample.source_kinds,
            tokens=sample.tokens,
            error_categories={"error"},
        )
        got = tally.view(source_kinds=sample.source_kinds, tokens=sample.tokens)
        assert _dump(got) == _dump(want)


def test_empty_tally_is_empty_view(operators: Ops) -> None:
    profile = ArchitectureProfile.model_validate({"cells": {}, "unassigned": True})
    view = ArchitectureTally(profile, profile_id="p").view()
    assert view.event_total == 0
    assert view.max_seq is None
    assert view.cells == []
    assert view.unassigned is not None
    assert view.unassigned.metrics["count"].value == 0


def test_duration_sum_does_not_depend_on_order(operators: Ops) -> None:
    profile = ArchitectureProfile.model_validate(
        {"cells": {"c": {"when": {"all": []}, "metrics": ["duration"]}}}
    )
    values = [0.1, 1e16, 0.2, -1e16, 0.3]
    events = [
        LogEvent.model_validate(
            {
                "uid": f"u{i}",
                "seq": i,
                "source": "s",
                "observed_at": 0,
                "category": "x",
                "duration_ms": v,
            }
        )
        for i, v in enumerate(values, start=1)
    ]
    one = project_architecture(events, profile, profile_id="p", operators=operators)
    two = project_architecture(events[::-1], profile, profile_id="p", operators=operators)
    first = one.cells[0].metrics["duration"].detail
    second = two.cells[0].metrics["duration"].detail
    assert first is not None
    assert second is not None
    assert first.total_ms == second.total_ms
