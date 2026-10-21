"""계보 `runs`의 열(root_run_id·parent_node_id·call·invoked_by)을 읽고 쓰는 저장소 스위트.

세 가지 저장소에 같은 기대를 건다: 인메모리, 계보를 안 올린 SQLite(값은 `doc`에만, 단독 사용),
열이 있는 SQLite. 열을 더하는 마이그레이션은 `agent_console_mod_runs`에 있으므로(이 패키지는 그
모듈을 모른다) 여기서는 같은 모양을 `schema.node_runs_v2` 등으로 직접 만든다.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import Interaction, NodeRun, Run
from agent_console_store import InMemoryStorage, SqliteStorage, open_sqlite
from agent_console_store.schema import node_runs_v2, runs_lineage_active


def _add_lineage(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN parent_node_id TEXT")
        conn.exec_driver_sql("ALTER TABLE runs ADD COLUMN root_run_id TEXT")
        conn.exec_driver_sql("CREATE INDEX ix_runs_root ON runs (root_run_id)")
        conn.exec_driver_sql("ALTER TABLE interactions ADD COLUMN root_run_id TEXT")
        conn.exec_driver_sql("DROP TABLE node_runs")
        node_runs_v2.create(conn)


@pytest.fixture(params=["memory", "sqlite-doc-only", "sqlite-columns"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    if request.param == "memory":
        impl: Any = InMemoryStorage()
    else:
        db = open_sqlite(tmp_path / "c.sqlite3")
        if request.param == "sqlite-columns":
            _add_lineage(db.engine)
        impl = SqliteStorage(db.engine)
        assert runs_lineage_active(db.engine) == (request.param == "sqlite-columns")
    yield impl
    impl.close()


def _run(id: str, created_at: float, **kw: Any) -> Run:
    return Run(
        id=id, graph_id="g", graph_version="h", status="running", input={}, origin="api",
        created_at=created_at, **kw,
    )  # fmt: skip


def _interaction(id: str, run_id: str, created_at: float, **kw: Any) -> Interaction:
    return Interaction(
        id=id, run_id=run_id, node_id="n", kind="question", status="pending",
        created_at=created_at, **kw,
    )  # fmt: skip


def test_runs_round_trip_lineage_fields_and_list_by_root(store: Any) -> None:
    runs = store.runs
    runs.save(_run("root", 1.0))
    runs.save(_run("child", 2.0, parent_run_id="root", parent_node_id="team", root_run_id="root"))
    runs.save(_run("grand", 3.0, parent_run_id="child", parent_node_id="x", root_run_id="root"))
    runs.save(_run("other", 4.0))
    got = runs.get("child")
    assert (got.parent_node_id, got.root_run_id) == ("team", "root")
    # 루트 아래 모든 자손(루트 자신 제외), 최신순. 직접 자식은 parent_run_id로 따로 묻는다.
    assert [r.id for r in runs.list(root_run_id="root")] == ["grand", "child"]
    assert [r.id for r in runs.list(parent_run_id="root")] == ["child"]
    assert runs.list(root_run_id="nobody") == []
    assert [r.id for r in runs.list(root_run_id="root", limit=1)] == ["grand"]


def test_node_run_call_and_invoked_by(store: Any) -> None:
    runs = store.runs
    runs.save(_run("r", 1.0))
    scheduled = NodeRun(run_id="r", node_id="lead", status="succeeded", started_at=1.0)
    first = NodeRun(
        run_id="r", node_id="dev", status="succeeded", started_at=2.0, call=0, invoked_by=["lead"]
    )
    second = first.model_copy(update={"call": 1, "started_at": 3.0})
    for node_run in (scheduled, first, second):
        runs.save_node_run(node_run)
    runs.save_node_run(second.model_copy(update={"status": "failed"}))  # 같은 키는 교체
    got = runs.list_node_runs("r")
    if getattr(
        runs, "_lineage", True
    ):  # 열이 없는 SQLite는 call이 키에 못 들어가 한 행으로 합쳐진다
        assert [(n.node_id, n.call, n.status) for n in got] == [
            ("lead", 0, "succeeded"),
            ("dev", 0, "succeeded"),
            ("dev", 1, "failed"),
        ]
    else:
        assert [(n.node_id, n.status) for n in got] == [("lead", "succeeded"), ("dev", "failed")]
    assert got[0].invoked_by is None
    assert got[1].invoked_by == ["lead"]


def test_interactions_round_trip_and_list_by_root(store: Any) -> None:
    items = store.interactions
    items.save(_interaction("i1", "root", 1.0))
    items.save(_interaction("i2", "child", 2.0, root_run_id="root"))
    items.save(_interaction("i3", "other", 3.0))
    assert items.get("i2").root_run_id == "root"
    assert [i.id for i in items.list(root_run_id="root")] == ["i1", "i2"]
    assert [i.id for i in items.list(root_run_id="root", status="pending", limit=1)] == ["i1"]
    assert [i.id for i in items.list(run_id="child")] == ["i2"]
    assert items.list(root_run_id="nobody") == []


def test_delete_run_removes_its_node_runs_and_interactions(store: Any) -> None:
    store.runs.save(_run("r", 1.0))
    store.runs.save_node_run(NodeRun(run_id="r", node_id="a", status="succeeded", call=2))
    store.interactions.save(_interaction("i", "r", 1.0))
    assert store.runs.delete("r") is True
    assert store.runs.list_node_runs("r") == []
    assert store.interactions.get("i") is None
