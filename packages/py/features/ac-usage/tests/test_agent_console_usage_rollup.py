"""토큰 집계: 에이전트·팀 구성·모델·일, 명시 id로만 귀속, 없는 값은 0으로 채우지 않음."""

from __future__ import annotations

import builtins
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from agent_console_contracts import NodeRun, Run, RunEvent, Usage
from agent_console_usage import (
    DEFAULT_PRECISION_TEXT,
    UsageRecord,
    counts_toward_usage,
    load_usage_records,
    sum_usage,
    token_rollup,
    usage_records,
)

DAY1 = datetime(2026, 10, 14, 23, 30, tzinfo=UTC).timestamp()
DAY2 = datetime(2026, 10, 15, 1, 0, tzinfo=UTC).timestamp()


def _run(run_id: str = "r1", graph_id: str = "team", created: float = DAY1) -> Run:
    return Run(
        id=run_id,
        graph_id=graph_id,
        graph_version="v",
        status="completed",
        input={},
        origin="chat",
        created_at=created,
    )


def _ev(
    run_id: str,
    seq: int,
    type: str,
    payload: dict[str, Any],
    *,
    path: list[str],
    actor: str | None = None,
    attempt: int | None = 1,
    ts: float = DAY1,
) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=ts,
        node_path=path,
        attempt=attempt,
        actor=actor,
        type=type,
        payload=payload,
    )


def _node(
    run_id: str, node: str, usage: Usage | None, *, attempt: int = 1, at: float = DAY1
) -> NodeRun:
    return NodeRun(
        run_id=run_id, node_id=node, attempt=attempt, status="succeeded", usage=usage, started_at=at
    )


def _fixture() -> tuple[Run, list[NodeRun], list[RunEvent]]:
    run = _run()
    nodes = [
        _node("r1", "lead", Usage(input_tokens=100, output_tokens=10, cost_usd=0.5)),
        _node("r1", "lead", Usage(input_tokens=50, output_tokens=5), attempt=2, at=DAY2),
        _node("r1", "qa", Usage(input_tokens=7)),
        _node("r1", "user", None),  # 사용량 없는 노드는 기록 없음
    ]
    events = [
        _ev(
            "r1",
            1,
            "agent.session_started",
            {"session_id": "s", "backend": "b", "model": "m-big"},
            path=["lead"],
            actor="pl",
        ),
        _ev(
            "r1",
            2,
            "agent.session_started",
            {"session_id": "s2", "backend": "b", "model": "m-big"},
            path=["lead"],
            actor="pl",
            attempt=2,
            ts=DAY2,
        ),
        _ev(
            "r1",
            3,
            "agent.subagent_stopped",
            {"subagent_id": "t1", "usage": {"total_tokens": 900}},
            path=["lead", "dev"],
            actor="dev",
        ),
        _ev(
            "r1",
            4,
            "agent.subagent_stopped",
            {"subagent_id": "t2"},
            path=["lead", "dev"],
            actor="dev",
        ),  # usage 없음 → 기록 없음
        _ev("r1", 5, "agent.subagent_stopped", {"nope": 1}, path=["lead"]),  # 형식 틀림 → 건너뜀
        # 위임 대상의 session_started(경로 2)는 노드 귀속에 쓰지 않는다
        _ev(
            "r1",
            6,
            "agent.session_started",
            {"session_id": "x", "backend": "b", "model": "m-z"},
            path=["lead", "qa"],
            actor="wrong",
        ),
    ]
    return run, nodes, events


def test_usage_records_attribution_by_explicit_ids() -> None:
    run, nodes, events = _fixture()
    recs = usage_records(run, nodes, events)
    summary = [(r.origin, r.agent_id, r.model, r.usage.total_tokens) for r in recs]
    assert summary == [
        ("node", "pl", "m-big", None),
        ("node", "pl", "m-big", None),
        ("node", None, None, None),  # qa: session_started 없음 → 모름(추측 안 함)
        ("subagent", "dev", None, 900),
    ]
    assert all(r.graph_id == "team" and r.run_id == "r1" for r in recs)


def test_sum_usage_keeps_missing_fields_none() -> None:
    total = sum_usage([Usage(input_tokens=1), Usage(input_tokens=2, cost_usd=0.1)])
    assert total.input_tokens == 3
    assert total.cost_usd == pytest.approx(0.1)
    assert total.output_tokens is None  # 0으로 지어내지 않는다
    assert total.total_tokens is None
    assert sum_usage([]) == Usage()
    extra = sum_usage(
        [Usage.model_validate({"web_searches": 2}), Usage.model_validate({"web_searches": 3})]
    )
    assert extra.model_dump(exclude_none=True) == {"web_searches": 5}


def test_rollup_by_agent_model_day() -> None:
    run, nodes, events = _fixture()
    rows = token_rollup(usage_records(run, nodes, events))
    keyed = {(r.agent_id, r.graph_id, r.model, r.day): r for r in rows}
    pl1 = keyed[("pl", "team", "m-big", "2026-10-14")]
    assert (pl1.usage.input_tokens, pl1.usage.output_tokens, pl1.runs) == (100, 10, 1)
    pl2 = keyed[("pl", "team", "m-big", "2026-10-15")]
    assert pl2.usage.input_tokens == 50
    dev = keyed[("dev", "team", None, "2026-10-14")]
    assert dev.usage.total_tokens == 900
    assert dev.usage.input_tokens is None
    assert dev.precision == DEFAULT_PRECISION_TEXT["total_only"]
    assert pl1.precision is None
    assert rows[0].agent_id is None  # None 차원은 앞


def test_rollup_dimensions_timezone_and_mixed_precision() -> None:
    run, nodes, events = _fixture()
    recs = usage_records(run, nodes, events)
    (only,) = token_rollup(recs, by=())
    assert only.agent_id is None
    assert only.day is None
    assert only.usage.input_tokens == 157
    assert only.usage.total_tokens == 900
    assert only.precision == DEFAULT_PRECISION_TEXT["mixed"]
    assert only.runs == 1
    kst = timezone(timedelta(hours=9))
    days = {r.day for r in token_rollup(recs, by=("day",), tz=kst)}
    assert days == {"2026-10-15"}  # 23:30 UTC = 다음 날 08:30 KST
    custom = token_rollup(recs, by=("agent_id",), precision_text={"total_only": "T"})
    assert {r.agent_id: r.precision for r in custom}["dev"] == "T"
    with pytest.raises(ValueError, match="차원"):
        token_rollup(recs, by=("team",))  # type: ignore[arg-type]


def test_rollup_counts_distinct_runs() -> None:
    recs = [
        UsageRecord(run_id="a", usage=Usage(input_tokens=1), agent_id="x"),
        UsageRecord(run_id="a", usage=Usage(input_tokens=1), agent_id="x"),
        UsageRecord(run_id="b", usage=Usage(input_tokens=1), agent_id="x"),
    ]
    (row,) = token_rollup(recs, by=("agent_id",))
    assert (row.runs, row.usage.input_tokens) == (2, 3)
    (no_day,) = token_rollup([UsageRecord(run_id="a", usage=Usage())], by=("day",))
    assert no_day.day is None


class FakeRuns:
    def __init__(self, runs: list[Run], nodes: dict[str, list[NodeRun]]) -> None:
        self.runs = runs
        self.nodes = nodes

    def list(
        self, *, graph_id: str | None = None, root_only: bool = False, limit: int | None = None
    ) -> builtins.list[Run]:
        rows = [
            r
            for r in self.runs
            if (graph_id is None or r.graph_id == graph_id)
            and (not root_only or r.root_run_id is None)
        ]
        return rows[:limit]

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        return self.nodes.get(run_id, [])


class FakeEvents:
    def __init__(self, events: list[RunEvent]) -> None:
        self.events = events
        self.prefixes: list[str | None] = []

    def list(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int | None = None,
        actor: str | None = None,
        type_prefix: str | None = None,
    ) -> builtins.list[RunEvent]:
        self.prefixes.append(type_prefix)
        return [
            e
            for e in self.events
            if e.run_id == run_id and (type_prefix is None or e.type.startswith(type_prefix))
        ]


def test_load_usage_records_from_protocol_stores() -> None:
    run, nodes, events = _fixture()
    old = _run("r0", created=DAY1 - 86400 * 10)
    other = _run("r2", graph_id="solo", created=DAY2)
    runs = FakeRuns(
        [other, run, old],
        {
            "r1": nodes,
            "r0": [_node("r0", "a", Usage(input_tokens=1))],
            "r2": [_node("r2", "a", Usage(input_tokens=4))],
        },
    )
    evs = FakeEvents(events)
    recs = load_usage_records(runs, evs, since=DAY1 - 60)
    assert {r.run_id for r in recs} == {"r1", "r2"}
    assert None not in evs.prefixes  # 필요한 이벤트 종류만 읽는다
    only_team = load_usage_records(runs, evs, graph_id="team")
    assert {r.run_id for r in only_team} == {"r1", "r0"}


def test_child_runs_are_not_counted_twice() -> None:
    """자식 Run(중첩 팀)의 사용량은 부모 노드 usage에 이미 들어 있다 → 루트 Run만 센다(5R.13)."""
    root = _run("root")
    child = _run("child").model_copy(
        update={"parent_run_id": "root", "parent_node_id": "team", "root_run_id": "root"}
    )
    assert counts_toward_usage(root)
    assert not counts_toward_usage(child)
    runs = FakeRuns(
        [child, root],
        {
            # 부모의 중첩 노드 usage = 자식 totals
            "root": [_node("root", "team", Usage(input_tokens=30, output_tokens=3))],
            "child": [_node("child", "a", Usage(input_tokens=30, output_tokens=3))],
        },
    )
    recs = load_usage_records(runs, FakeEvents([]))
    assert [r.run_id for r in recs] == ["root"]
    assert sum_usage(r.usage for r in recs) == Usage(input_tokens=30, output_tokens=3)
