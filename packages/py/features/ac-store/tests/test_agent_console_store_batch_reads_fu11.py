"""FU.11: 여러 Run을 묶어 읽기(``list_node_runs_many``·``list_many``) — 집계 N+1 방지.

두 구현(SQLite·메모리)이 Run마다 부른 ``list_node_runs``·``list``와 같은 결과를 내고, SQLite는
Run ``RUN_BATCH_SIZE``개마다 질의 한 번이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sqlalchemy as sa

from agent_console_contracts import NodeRun, Run, RunEvent
from agent_console_store import RUN_BATCH_SIZE, open_sqlite


def make_run(run_id: str, *, created_at: float) -> Run:
    return Run(
        id=run_id,
        graph_id="g",
        graph_version="h",
        status="completed",
        input={},
        origin="api",
        created_at=created_at,
    )


def make_event(run_id: str, seq: int, *, type: str) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-e{seq}",
        run_id=run_id,
        seq=seq,
        ts=100.0 + seq,
        type=type,
        node_path=["n1"],
        payload={},
    )


def _fill(storage: Any) -> None:
    for i, run_id in enumerate(["a", "b", "c"]):
        storage.runs.save(make_run(run_id, created_at=float(i)))
    r = storage.runs
    r.save_node_run(NodeRun(run_id="a", node_id="y", status="succeeded", started_at=2.0))
    r.save_node_run(NodeRun(run_id="a", node_id="x", status="succeeded", started_at=1.0))
    r.save_node_run(NodeRun(run_id="a", node_id="z", status="pending"))
    r.save_node_run(NodeRun(run_id="b", node_id="x", status="succeeded", started_at=5.0))
    events = [
        make_event("a", 1, type="agent.session_started"),
        make_event("a", 2, type="node.started"),
        make_event("a", 3, type="agent.subagent_stopped"),
        make_event("a", 4, type="agent.session_started"),
        make_event("b", 1, type="agent.session_started"),
        make_event("c", 1, type="node.started"),
    ]
    storage.events.append_many(events)


def test_list_node_runs_many_matches_single_reads(storage: Any) -> None:
    _fill(storage)
    found = storage.runs.list_node_runs_many(["a", "b", "c", "a", "none"])
    assert set(found) == {"a", "b"}  # NodeRun이 없는 Run은 키가 없다
    for run_id in ("a", "b"):
        assert found[run_id] == storage.runs.list_node_runs(run_id)
    assert [n.node_id for n in found["a"]] == ["x", "y", "z"]  # 시작 전은 뒤
    assert storage.runs.list_node_runs_many([]) == {}


def test_list_many_since_and_type_prefixes(storage: Any) -> None:
    _fill(storage)
    events = storage.events
    types = ("agent.session_started", "agent.subagent_stopped")
    found = events.list_many({"a": 0, "b": 0, "c": 0, "none": 0}, type_prefixes=types)
    assert {k: [e.seq for e in v] for k, v in found.items()} == {"a": [1, 3, 4], "b": [1]}
    # Run마다 이어 읽기(seq > since)
    found = events.list_many({"a": 3, "b": 1}, type_prefixes=types)
    assert {k: [e.seq for e in v] for k, v in found.items()} == {"a": [4]}
    # 접두어가 비면 전부, 접두어는 Run마다 부른 list(type_prefix=)와 같다
    everything = events.list_many({"a": 1, "c": 0})
    assert [e.seq for e in everything["a"]] == [2, 3, 4]
    assert [e.seq for e in everything["c"]] == [1]
    one = events.list_many({"a": 0}, type_prefixes=["agent.sub"])
    assert one["a"] == events.list("a", type_prefix="agent.sub")
    assert events.list_many({}) == {}


def test_sqlite_batch_reads_use_one_query_per_chunk(tmp_path: Path) -> None:
    db = open_sqlite(tmp_path / "q.sqlite3")
    count = RUN_BATCH_SIZE + 5  # 묶음 두 개
    for i in range(count):
        run_id = f"r{i:04d}"
        db.runs.save(make_run(run_id, created_at=float(i)))
        db.runs.save_node_run(NodeRun(run_id=run_id, node_id="n", status="succeeded"))
        db.events.append(make_event(run_id, 1, type="agent.session_started"))
    selects: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    ids = [f"r{i:04d}" for i in range(count)]
    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        node_runs = db.runs.list_node_runs_many(ids)
        assert len(selects) == 2
        selects.clear()
        events = db.events.list_many(
            {run_id: (1 if i % 2 else 0) for i, run_id in enumerate(ids)},
            type_prefixes=["agent.session_started"],
        )
        assert len(selects) == 2
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)
    assert len(node_runs) == count
    assert sorted(events) == [run_id for i, run_id in enumerate(ids) if i % 2 == 0]
    db.close()
