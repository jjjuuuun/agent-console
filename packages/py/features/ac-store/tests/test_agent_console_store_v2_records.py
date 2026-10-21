"""1R.4 런타임 기록: 대화, 상호작용, 사용량 관측, 이벤트 조회(actor·type_prefix), Run 필터.

`storage` 픽스처가 SQLite와 인메모리에 같은 스위트를 돌린다.
"""

import threading
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    Interaction,
    Run,
    RunEvent,
)
from agent_console_store import (
    InteractionClosed,
    NotFound,
    open_sqlite,
)


def make_run(id: str = "r1", graph_id: str = "g1", created_at: float = 10.0, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id,
        "graph_id": graph_id,
        "graph_version": "h1",
        "status": "queued",
        "input": {},
        "origin": "chat",
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
    }
    fields.update(kw)
    return RunEvent(**fields)


def make_inter(id: str = "i1", run_id: str = "r1", created_at: float = 10.0, **kw: Any) -> Any:
    fields: dict[str, Any] = {
        "id": id,
        "run_id": run_id,
        "node_id": "n1",
        "kind": "question",
        "status": "pending",
        "created_at": created_at,
        "payload": {"question": "어느 쪽?"},
        "response_schema": {"type": "object"},
    }
    fields.update(kw)
    return Interaction(**fields)


# ---- Run 필터 -------------------------------------------------------------
def test_run_list_filters_conversation_agent_status_graph(storage: Any) -> None:
    storage.runs.save(make_run("r1", "g1", 10.0, conversation_id="c1", status="completed"))
    storage.runs.save(make_run("r2", "g1", 20.0, conversation_id="c1", status="running"))
    storage.runs.save(make_run("r3", "g2", 30.0, conversation_id="c2", status="running"))
    storage.events.append(make_event("r1", 1, actor="pl"))
    storage.events.append(make_event("r2", 1, actor="qa"))
    storage.events.append(make_event("r2", 2, actor="pl"))
    storage.events.append(make_event("r3", 1))

    def ids(**kw: Any) -> list[str]:
        return [r.id for r in storage.runs.list(**kw)]

    assert ids(conversation_id="c1") == ["r2", "r1"]
    assert ids(agent="pl") == ["r2", "r1"]
    assert ids(agent="qa") == ["r2"]
    assert ids(agent="nobody") == []
    assert ids(conversation_id="c1", status=["running"]) == ["r2"]
    assert ids(graph_id="g2", agent="pl") == []
    assert ids(conversation_id="c1", agent="pl", status=["completed"], graph_id="g1") == ["r1"]
    assert storage.runs.get("r1").conversation_id == "c1"


# ---- 이벤트 조회 ----------------------------------------------------------
def _seed_events(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    storage.runs.save(make_run("r2"))
    rows = [
        ("r1", 1, "node.started", "pl", 1.0),
        ("r1", 2, "agent.subagent_started", "be", 2.0),
        ("r1", 3, "agent.subagent_stopped", "be", 3.0),
        ("r1", 4, "usage.rate_limit", None, 4.0),
        ("r2", 1, "usage.rate_limit", None, 9.0),
        ("r2", 2, "Agent.Upper", "pl", 10.0),
        ("r2", 3, "node.finished", "pl", 11.0),
    ]
    for run_id, seq, typ, actor, ts in rows:
        storage.events.append(make_event(run_id, seq, type=typ, actor=actor, ts=ts))


def test_events_actor_is_stored_and_filterable(storage: Any) -> None:
    _seed_events(storage)
    assert [e.seq for e in storage.events.list("r1", actor="be")] == [2, 3]
    assert [e.seq for e in storage.events.list("r1", actor="pl")] == [1]
    assert storage.events.list("r1", actor="none") == []
    assert storage.events.list("r1")[0].actor == "pl"


def test_events_type_prefix_is_exact_and_case_sensitive(storage: Any) -> None:
    _seed_events(storage)
    assert [e.seq for e in storage.events.list("r1", type_prefix="agent.")] == [2, 3]
    assert [e.seq for e in storage.events.list("r2", type_prefix="agent.")] == []  # 대문자 구분
    assert [e.seq for e in storage.events.list("r2", type_prefix="Agent.")] == [2]
    assert [
        e.seq for e in storage.events.list("r1", type_prefix="agent.", actor="be", since_seq=2)
    ] == [3]
    assert len(storage.events.list("r1", type_prefix="")) == 4  # 빈 접두 = 필터 없음
    assert [e.seq for e in storage.events.list("r2", type_prefix="node.")] == [3]
    assert storage.events.list("r1", type_prefix="agent_") == []  # LIKE 와일드카드 아님


def test_events_type_prefix_with_like_wildcards_is_literal(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    storage.events.append(make_event("r1", 1, type="a%b.x"))
    storage.events.append(make_event("r1", 2, type="axb.x"))
    assert [e.seq for e in storage.events.list("r1", type_prefix="a%")] == [1]


def test_events_latest_by_type(storage: Any) -> None:
    _seed_events(storage)
    latest = storage.events.latest_by_type("usage.rate_limit")
    assert [(e.run_id, e.seq) for e in latest] == [("r2", 1)]
    both = storage.events.latest_by_type("usage.rate_limit", limit=5)
    assert [(e.run_id, e.seq) for e in both] == [("r2", 1), ("r1", 4)]
    one_run = storage.events.latest_by_type("usage.rate_limit", run_id="r1")
    assert [(e.run_id, e.seq) for e in one_run] == [("r1", 4)]
    assert [e.seq for e in storage.events.latest_by_type("node.started", actor="pl")] == [1]
    assert storage.events.latest_by_type("nothing") == []


def test_events_list_by_actor_across_runs_newest_first(storage: Any) -> None:
    _seed_events(storage)
    got = storage.events.list_by_actor("pl")
    assert [(e.run_id, e.seq) for e in got] == [("r2", 3), ("r2", 2), ("r1", 1)]
    assert [(e.run_id, e.seq) for e in storage.events.list_by_actor("pl", limit=2)] == [
        ("r2", 3),
        ("r2", 2),
    ]
    assert [e.seq for e in storage.events.list_by_actor("pl", since=10.0)] == [3, 2]
    assert [e.seq for e in storage.events.list_by_actor("pl", type_prefix="node.")] == [3, 1]


def test_events_actor_append_is_still_idempotent(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    assert storage.events.append(make_event("r1", 1, actor="pl")) is True
    assert storage.events.append(make_event("r1", 1, actor="pl")) is False
    assert len(storage.events.list_by_actor("pl")) == 1


# ---- 상호작용 -------------------------------------------------------------
def test_interaction_save_get_and_list_filters(storage: Any) -> None:
    storage.interactions.save(make_inter("i1", "r1", 10.0, conversation_id="c1"))
    storage.interactions.save(make_inter("i2", "r1", 20.0, conversation_id="c1", kind="review"))
    storage.interactions.save(make_inter("i3", "r2", 5.0, conversation_id="c2"))
    assert storage.interactions.get("i1").payload == {"question": "어느 쪽?"}
    assert storage.interactions.get("zzz") is None

    def ids(**kw: Any) -> list[str]:
        return [i.id for i in storage.interactions.list(**kw)]

    assert ids() == ["i3", "i1", "i2"]  # created_at 오름차순
    assert ids(run_id="r1") == ["i1", "i2"]
    assert ids(conversation_id="c2") == ["i3"]
    assert ids(status="pending") == ["i3", "i1", "i2"]
    assert ids(status=["answered", "expired"]) == []
    assert ids(run_id="r1", limit=1) == ["i1"]


def test_interaction_close_answered_records_response(storage: Any) -> None:
    storage.interactions.save(make_inter())
    closed = storage.interactions.close(
        "i1", status="answered", closed_at=50.0, response={"answer": "A"}, answered_by="user"
    )
    assert closed.status == "answered"
    assert closed.response == {"answer": "A"}
    assert closed.answered_by == "user"
    assert closed.closed_at == 50.0
    assert storage.interactions.get("i1") == closed
    assert storage.interactions.list(status="pending") == []


def test_interaction_close_twice_second_gets_interaction_closed(storage: Any) -> None:
    storage.interactions.save(make_inter())
    storage.interactions.close("i1", status="answered", closed_at=50.0, response={"a": 1})
    with pytest.raises(InteractionClosed) as exc:
        storage.interactions.close("i1", status="answered", closed_at=60.0, response={"a": 2})
    assert exc.value.interaction.response == {"a": 1}  # 먼저 닫은 쪽이 이긴다
    assert exc.value.code == "interaction_closed"
    with pytest.raises(InteractionClosed):
        storage.interactions.close("i1", status="cancelled", closed_at=70.0)
    assert storage.interactions.get("i1").closed_at == 50.0


def test_interaction_close_unknown_and_bad_status(storage: Any) -> None:
    with pytest.raises(NotFound):
        storage.interactions.close("nope", status="answered", closed_at=1.0)
    storage.interactions.save(make_inter())
    with pytest.raises(ValueError, match="status"):
        storage.interactions.close("i1", status="pending", closed_at=1.0)
    assert storage.interactions.get("i1").status == "pending"


def test_interaction_save_never_reopens_a_closed_one(storage: Any) -> None:
    assert storage.interactions.save(make_inter()) is True
    assert storage.interactions.save(make_inter(title="갱신")) is True  # pending은 갱신 가능
    assert storage.interactions.get("i1").title == "갱신"
    storage.interactions.close("i1", status="answered", closed_at=5.0, response={"a": 1})
    assert storage.interactions.save(make_inter(title="늦은 저장")) is False
    got = storage.interactions.get("i1")
    assert got.status == "answered"
    assert got.title == "갱신"


def test_interaction_close_pending_by_run_or_all(storage: Any) -> None:
    storage.interactions.save(make_inter("i1", "r1", 1.0, conversation_id="c1"))
    storage.interactions.save(make_inter("i2", "r1", 2.0))
    storage.interactions.save(make_inter("i3", "r2", 3.0))
    storage.interactions.close("i2", status="answered", closed_at=4.0, response={})
    closed = storage.interactions.close_pending(
        status="cancelled", closed_at=9.0, run_id="r1", close_reason="cancelled"
    )
    assert [i.id for i in closed] == ["i1"]
    assert closed[0].close_reason == "cancelled"
    assert closed[0].answered_by == "system"
    assert storage.interactions.get("i2").status == "answered"  # 이미 닫힌 건 그대로
    assert storage.interactions.get("i3").status == "pending"
    rest = storage.interactions.close_pending(
        status="expired", closed_at=10.0, close_reason="interrupted", answered_by=None
    )
    assert [i.id for i in rest] == ["i3"]
    assert rest[0].status == "expired"
    assert rest[0].answered_by is None
    assert storage.interactions.close_pending(status="expired", closed_at=11.0) == []
    with pytest.raises(ValueError, match="status"):
        storage.interactions.close_pending(status="answered", closed_at=1.0)


def test_interaction_pending_counts_by_conversation(storage: Any) -> None:
    storage.interactions.save(make_inter("i1", conversation_id="c1", created_at=1.0))
    storage.interactions.save(make_inter("i2", conversation_id="c1", created_at=2.0))
    storage.interactions.save(make_inter("i3", conversation_id="c2", created_at=3.0))
    storage.interactions.save(make_inter("i4", created_at=4.0))  # 대화 없음
    storage.interactions.close("i2", status="answered", closed_at=5.0, response={})
    assert storage.interactions.pending_counts() == {"c1": 1, "c2": 1}
    assert storage.interactions.pending_counts(["c2", "c9"]) == {"c2": 1}


def test_interaction_concurrent_responses_only_one_wins(storage: Any) -> None:
    storage.interactions.save(make_inter())
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    lock = threading.Lock()

    def respond(n: int) -> None:
        barrier.wait()
        try:
            storage.interactions.close(
                "i1", status="answered", closed_at=float(n), response={"n": n}, answered_by="user"
            )
            result = f"won:{n}"
        except InteractionClosed:
            result = "lost"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=respond, args=(n,)) for n in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    winners = [o for o in outcomes if o.startswith("won")]
    assert len(winners) == 1
    assert outcomes.count("lost") == 7
    final = storage.interactions.get("i1")
    assert final.status == "answered"
    assert final.response == {"n": int(winners[0].split(":")[1])}


def test_delete_run_removes_its_interactions(storage: Any) -> None:
    storage.runs.save(make_run("r1"))
    storage.interactions.save(make_inter("i1", "r1"))
    storage.interactions.save(make_inter("i2", "r2"))
    storage.runs.delete("r1")
    assert [i.id for i in storage.interactions.list()] == ["i2"]


# ---- 영속 -----------------------------------------------------------------
def test_v2_records_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "c.sqlite3"
    db = open_sqlite(path)
    db.interactions.save(make_inter(conversation_id="c1"))
    db.close()
    again = open_sqlite(path)
    assert again.interactions.pending_counts() == {"c1": 1}
    again.close()
