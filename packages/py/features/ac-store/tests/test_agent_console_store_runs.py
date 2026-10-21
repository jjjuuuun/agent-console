"""RunRepository / EventRepository 공통 스위트(SQLite, 인메모리 모두)."""

from typing import Any

import pytest

from agent_console_contracts import (
    ErrorInfo,
    NodeRun,
    Run,
    RunEvent,
)
from agent_console_store import EventConflict, NotFound, get_run_snapshot


def make_run(id: str = "r1", graph_id: str = "g1", created_at: float = 10.0, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id,
        "graph_id": graph_id,
        "graph_version": "h1",
        "status": "queued",
        "input": {"text": "안녕"},
        "origin": "api",
        "created_at": created_at,
    }
    fields.update(kw)
    return Run(**fields)


def make_event(run_id: str = "r1", seq: int = 1, **kw: Any) -> RunEvent:
    fields: dict[str, Any] = {
        "event_id": f"{run_id}-e{seq}",
        "run_id": run_id,
        "seq": seq,
        "ts": 100.0 + seq,
        "type": "node.started",
        "node_path": ["n1"],
        "attempt": 1,
        "payload": {"status": "running"},
    }
    fields.update(kw)
    return RunEvent(**fields)


# ---------------------------------------------------------------- runs
def test_run_save_get_list_filters(storage: Any) -> None:
    runs = storage.runs
    runs.save(make_run("a", "g1", 1.0))
    runs.save(make_run("b", "g2", 2.0, status="running"))
    runs.save(make_run("c", "g1", 3.0, parent_run_id="a"))
    assert runs.get("a").input == {"text": "안녕"}
    assert runs.get("zzz") is None
    assert [r.id for r in runs.list()] == ["c", "b", "a"]  # 최신순
    assert [r.id for r in runs.list(graph_id="g1")] == ["c", "a"]
    assert [r.id for r in runs.list(status=["running"])] == ["b"]
    assert [r.id for r in runs.list(parent_run_id="a")] == ["c"]
    assert [r.id for r in runs.list(limit=1)] == ["c"]


def test_run_save_is_upsert(storage: Any) -> None:
    storage.runs.save(make_run("a"))
    storage.runs.save(make_run("a", status="completed", ended_at=20.0))
    assert len(storage.runs.list()) == 1
    assert storage.runs.get("a").status == "completed"


def test_node_runs_upsert_and_order(storage: Any) -> None:
    r = storage.runs
    r.save_node_run(NodeRun(run_id="r1", node_id="b", status="running", started_at=2.0))
    r.save_node_run(NodeRun(run_id="r1", node_id="a", status="succeeded", started_at=1.0))
    r.save_node_run(NodeRun(run_id="r1", node_id="c", status="pending"))
    r.save_node_run(NodeRun(run_id="r1", node_id="b", status="succeeded", started_at=2.0))
    r.save_node_run(NodeRun(run_id="r1", node_id="b", attempt=2, status="running", started_at=3.0))
    nodes = r.list_node_runs("r1")
    assert [(n.node_id, n.attempt, n.status) for n in nodes] == [
        ("a", 1, "succeeded"),
        ("b", 1, "succeeded"),
        ("b", 2, "running"),
        ("c", 1, "pending"),
    ]
    assert r.list_node_runs("other") == []


def test_interrupt_unfinished_marks_only_open_runs(storage: Any) -> None:
    runs = storage.runs
    runs.save(make_run("q", status="queued"))
    runs.save(make_run("r", status="running"))
    runs.save(make_run("done", status="completed", ended_at=5.0))
    err = ErrorInfo(code="interrupted", message="server restarted")
    assert runs.interrupt_unfinished(ended_at=99.0, error=err) == ["q", "r"]
    assert runs.get("q").status == "interrupted"
    assert runs.get("q").ended_at == 99.0
    assert runs.get("q").error == err
    assert runs.get("done").status == "completed"
    assert runs.interrupt_unfinished(ended_at=100.0) == []


# ---------------------------------------------------------------- events
def test_events_append_and_since_seq(storage: Any) -> None:
    ev = storage.events
    assert ev.append_many([make_event(seq=i) for i in (1, 2, 3, 4)]) == 4
    assert ev.last_seq("r1") == 4
    assert ev.last_seq("none") == 0
    assert [e.seq for e in ev.list("r1")] == [1, 2, 3, 4]
    assert [e.seq for e in ev.list("r1", since_seq=2)] == [3, 4]  # 재접속 증분
    assert [e.seq for e in ev.list("r1", since_seq=1, limit=2)] == [2, 3]
    assert ev.list("r1", since_seq=4) == []
    assert ev.list("other-run") == []


def test_events_are_stored_in_generic_form_and_keep_unknown_types(storage: Any) -> None:
    ev = storage.events
    ev.append(
        make_event(seq=1, type="plugin.custom", payload={"x": [1, {"y": "한글"}]}, raw={"a": 1})
    )
    (got,) = ev.list("r1")
    assert got.type == "plugin.custom"
    assert got.payload == {"x": [1, {"y": "한글"}]}
    assert got.raw == {"a": 1}
    assert got.ts == 101.0
    assert got.node_path == ["n1"]


def test_events_append_is_idempotent(storage: Any) -> None:
    ev = storage.events
    assert ev.append(make_event(seq=1)) is True
    assert ev.append(make_event(seq=1)) is False  # 같은 이벤트 재적재
    assert ev.append_many([make_event(seq=1), make_event(seq=2)]) == 1
    assert len(ev.list("r1")) == 2


def test_events_same_seq_different_id_conflicts(storage: Any) -> None:
    storage.events.append(make_event(seq=1))
    with pytest.raises(EventConflict):
        storage.events.append(make_event(seq=1, event_id="other"))


def test_events_accept_known_typed_events(storage: Any) -> None:
    from agent_console_contracts import NodeStatusEvent, NodeStatusPayload

    known = NodeStatusEvent(
        event_id="k1",
        run_id="r1",
        seq=1,
        ts=1.0,
        node_path=["n1"],
        type="node.completed",
        payload=NodeStatusPayload(status="succeeded", duration_ms=5),
    )
    storage.events.append(known)
    (got,) = storage.events.list("r1")
    assert type(got) is RunEvent
    assert got.payload["status"] == "succeeded"


def test_delete_run_cascades(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    storage.runs.save_node_run(NodeRun(run_id="r1", node_id="n", status="running"))
    storage.events.append(make_event("r1", 1))
    storage.runs.save(make_run("r2"))
    storage.events.append(make_event("r2", 1))
    assert storage.runs.delete("r1") is True
    assert storage.runs.delete("r1") is False
    assert storage.runs.get("r1") is None
    assert storage.runs.list_node_runs("r1") == []
    assert storage.events.list("r1") == []
    assert len(storage.events.list("r2")) == 1


def test_run_snapshot(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    storage.runs.save_node_run(NodeRun(run_id="r1", node_id="n", status="running"))
    storage.events.append_many([make_event("r1", 1), make_event("r1", 2)])
    snap = get_run_snapshot(storage.runs, storage.events, "r1")
    assert (snap.run.id, len(snap.node_runs), snap.last_seq) == ("r1", 1, 2)
    with pytest.raises(NotFound):
        get_run_snapshot(storage.runs, storage.events, "nope")


# ---------------------------------------------------------------- legacy routing_decisions
def test_delete_run_clears_legacy_routing_rows(tmp_path: Any) -> None:
    """2R.20: 라우팅 저장소 코드는 지웠지만 SQLite 테이블은 남는다. Run 삭제는 남은 행도 지운다."""
    import sqlalchemy as sa

    from agent_console_store import open_sqlite, schema

    db = open_sqlite(tmp_path / "console.sqlite3")
    try:
        assert not hasattr(db, "routing")
        db.runs.save(make_run("r1"))
        table = schema.routing_decisions
        row = {"run_id": "r1", "node_id": "n", "attempt": 1, "manual": 0, "decided_at": 1.0}
        with db.engine.begin() as conn:
            conn.execute(sa.insert(table).values(**row, doc="{}"))
        assert db.runs.delete("r1") is True
        with db.engine.connect() as conn:
            assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar() == 0
    finally:
        db.close()
