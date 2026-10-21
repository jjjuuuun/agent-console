"""mod-runs 마이그레이션 계보 `runs`(design §5R.10): 기준점·새 열·되돌리기·기존 DB·끄기·이식성."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_mod_runs import module
from agent_console_mod_runs.storage import BRANCH
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_runtime import Registries, load_registries
from agent_console_store import SqliteDatabase, SqliteStorage, create_sqlite_engine, upgrade
from agent_console_store.migrate import branch_version_table
from agent_console_store.schema import MODULE_OWNED_TABLES, runs_lineage_metadata

_OTHER_OWNERS = {"usage_observations", "conversations", "chat_queue"}
_RUN_TABLES = {"runs", "node_runs", "run_events", "interactions"}


def _cols(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _indexes(engine: sa.Engine, table: str) -> set[str]:
    return {str(i["name"]) for i in sa.inspect(engine).get_indexes(table)}


def _pk(engine: sa.Engine, table: str) -> list[str]:
    return list(sa.inspect(engine).get_pk_constraint(table)["constrained_columns"])


def test_branch_is_named_runs_and_owns_the_run_tables() -> None:
    assert BRANCH.name == "runs"
    assert _RUN_TABLES <= MODULE_OWNED_TABLES
    assert module.descriptor.migrations == (BRANCH,)
    assert [p.name.split("_")[0:2] for p in sorted(BRANCH.versions.glob("runs_*.py"))] == [
        ["runs", "0001"],
        ["runs", "0002"],
        ["runs", "0003"],
    ]


def test_empty_db_legacy_plus_runs_lineage_matches_metadata(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "e.sqlite3")
    db.upgrade([BRANCH])
    assert db.revision() == "0003"
    assert db.revision("runs") == "runs_0003"
    assert {"root_run_id", "parent_node_id"} <= _cols(db.engine, "runs")
    assert {"call", "invoked_by"} <= _cols(db.engine, "node_runs")
    assert "root_run_id" in _cols(db.engine, "interactions")
    assert _pk(db.engine, "node_runs") == ["run_id", "node_id", "attempt", "iteration", "call"]
    assert {"ix_runs_root", "ix_runs_parent", "ix_runs_project_created"} <= _indexes(
        db.engine, "runs"
    )
    assert "project_id" in _cols(db.engine, "runs")
    assert "ix_interactions_root" in _indexes(db.engine, "interactions")
    assert "ix_node_runs_type_status" in _indexes(db.engine, "node_runs")

    def only_run_tables(obj: object, name: str | None, type_: str, *_: object) -> bool:
        table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
        return table not in _OTHER_OWNERS and not str(table).startswith("alembic_version")

    with db.engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"include_object": only_run_tables, "compare_type": True}
        )
        assert compare_metadata(context, runs_lineage_metadata) == []
    db.close()


def test_branch_downgrade_touches_only_the_branch_and_reapply_restores(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "d.sqlite3")
    db.upgrade([BRANCH])
    storage = SqliteStorage(db.engine)
    from agent_console_contracts import NodeRun, Run

    run = Run(
        id="r", graph_id="g", graph_version="h", status="running", input={}, origin="api",
        created_at=1.0, parent_run_id="p", parent_node_id="team", root_run_id="root",
    )  # fmt: skip
    storage.runs.save(run)
    storage.runs.save_node_run(
        NodeRun(run_id="r", node_id="a", status="succeeded", invoked_by=["x"])
    )
    storage.runs.save_node_run(NodeRun(run_id="r", node_id="a", status="succeeded", call=1))
    db.downgrade_branch(BRANCH, "runs_0001")
    assert "project_id" not in _cols(db.engine, "runs")
    assert db.revision("runs") == "runs_0001"
    assert db.revision() == "0003"
    assert "root_run_id" not in _cols(db.engine, "runs")
    assert "call" not in _cols(db.engine, "node_runs")
    assert _pk(db.engine, "node_runs") == ["run_id", "node_id", "attempt", "iteration"]
    legacy = SqliteStorage(db.engine)  # 열이 없으면 doc만으로 읽는다
    got = legacy.runs.get("r")
    assert got is not None
    assert got.root_run_id == "root"
    assert [n.call for n in legacy.runs.list_node_runs("r")] == [
        0
    ]  # call>0 행은 되돌릴 때 사라진다
    db.downgrade_branch(BRANCH)
    assert db.revision("runs") is None
    assert set(sa.inspect(db.engine).get_table_names()) >= _RUN_TABLES  # legacy 표는 그대로
    db.upgrade([BRANCH])  # 다시 올리면 doc에서 열이 채워진다
    again = SqliteStorage(db.engine)
    assert [r.id for r in again.runs.list(root_run_id="root")] == ["r"]
    [first] = again.runs.list_node_runs("r")
    assert first.invoked_by == ["x"]
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT invoked_by, call FROM node_runs").one() == ('["x"]', 0)
    db.close()


def _seed_4r(engine: sa.Engine) -> None:
    """4R 시점의 기록(새 필드가 없는 doc)을 legacy 표에 직접 넣는다."""
    run_doc = {
        "id": "old", "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {"text": "안녕"}, "origin": "chat", "conversation_id": "c1", "created_at": 5.0,
    }  # fmt: skip
    node_doc = {
        "run_id": "old", "node_id": "pl", "attempt": 1, "iteration": 0, "status": "succeeded",
        "node_type": "agent", "started_at": 5.0, "ended_at": 6.0, "duration_ms": 1000,
        "inputs": {}, "outputs": {"out": "끝"},
    }  # fmt: skip
    event_body = {
        "event_id": "e1", "run_id": "old", "seq": 1, "ts": 5.5, "type": "node.started",
        "node_path": ["pl"], "attempt": 1, "payload": {}, "actor": "pl",
    }  # fmt: skip
    inter_doc = {
        "id": "i1", "run_id": "old", "node_id": "pl", "kind": "question", "status": "pending",
        "created_at": 5.7, "conversation_id": "c1",
    }  # fmt: skip
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO runs (id, graph_id, graph_version, status, origin, conversation_id, "
            "created_at, doc) VALUES ('old','g','h','completed','chat','c1',5.0,?)",
            (json.dumps(run_doc),),
        )
        conn.exec_driver_sql(
            "INSERT INTO node_runs (run_id, node_id, attempt, iteration, status, node_type, "
            "started_at, ended_at, duration_ms, doc) "
            "VALUES ('old','pl',1,0,'succeeded','agent',5.0,6.0,1000,?)",
            (json.dumps(node_doc),),
        )
        conn.exec_driver_sql(
            "INSERT INTO run_events (run_id, seq, event_id, ts, type, node_id, attempt, actor, "
            "body)"
            " VALUES ('old',1,'e1',5.5,'node.started','pl',1,'pl',?)",
            (json.dumps(event_body),),
        )
        conn.exec_driver_sql(
            "INSERT INTO interactions (id, run_id, conversation_id, node_id, kind, status, "
            "created_at, doc) VALUES ('i1','old','c1','pl','question','pending',5.7,?)",
            (json.dumps(inter_doc),),
        )


def test_4r_database_is_read_unchanged_after_upgrade(tmp_path: Path) -> None:
    path = tmp_path / "4r.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)  # 4R의 DB 모양 = legacy 0003
    _seed_4r(engine)
    engine.dispose()

    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    storage = SqliteStorage(db.engine)
    run = storage.runs.get("old")
    assert run is not None
    assert (run.input, run.conversation_id, run.root_run_id, run.parent_node_id) == (
        {"text": "안녕"}, "c1", None, None,
    )  # fmt: skip
    [node] = storage.runs.list_node_runs("old")
    assert (node.node_id, node.outputs, node.call, node.invoked_by) == (
        "pl",
        {"out": "끝"},
        0,
        None,
    )
    [event] = storage.events.list("old")
    assert (event.event_id, event.actor) == ("e1", "pl")
    [interaction] = storage.interactions.list(run_id="old")
    assert (interaction.id, interaction.root_run_id) == ("i1", None)
    assert [i.id for i in storage.interactions.list(root_run_id="old")] == ["i1"]
    assert storage.runs.list(root_run_id="old") == []
    db.close()


def test_disabled_module_does_not_upgrade_the_lineage(tmp_path: Path) -> None:
    def registries() -> Registries:
        found = Registries()
        load_registries(found)
        return found

    for disabled, expected in ((["mod-runs"], None), ([], "runs_0003")):
        db = SqliteDatabase.open(tmp_path / f"{len(disabled)}.sqlite3")
        assemble(
            [module, local_definitions_module()],
            ModulesConfig(disabled=disabled),
            base=BaseServices(
                paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st"),
                database=db,
                registries=registries(),
            ),
        )
        assert db.revision("runs") == expected
        has_table = "alembic_version_runs" in sa.inspect(db.engine).get_table_names()
        assert has_table == (expected is not None)
        db.close()


def test_migration_scripts_are_package_data_and_work_after_copy(tmp_path: Path) -> None:
    """폴더를 저장소 밖에 복사해도 빈 DB에서 upgrade 된다(P9)."""
    assert BRANCH.versions.is_dir()
    copied = tmp_path / "elsewhere" / "versions"
    shutil.copytree(BRANCH.versions, copied, ignore=shutil.ignore_patterns("__pycache__"))
    db = SqliteDatabase.open(tmp_path / "empty.sqlite3")
    db.upgrade([type("B", (), {"name": "runs", "versions": copied})()])
    assert db.revision("runs") == "runs_0003"
    db.close()


# ---- 프로젝트 id (5.2R.32, runs_0003) ---------------------------------------
def _run(id: str, created_at: float, **kw: object) -> object:
    from agent_console_contracts import Run

    fields: dict[str, object] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed", "input": {},
        "origin": "api", "created_at": created_at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)  # type: ignore[arg-type]


def _seed_projects(runs: object) -> None:
    for run in (
        _run("a", 1.0, project_id="p1"),
        _run("b", 2.0, project_id="p2"),
        _run("c", 3.0, project_id="p1", parent_run_id="a", root_run_id="a"),
        _run("d", 4.0),
        _run("e", 5.0, project_id="p1"),
        _run("f", 6.0, parent_run_id="e", root_run_id="e", project_id="p1"),
    ):
        runs.save(run)  # type: ignore[attr-defined]


def _query_cases(runs: object) -> None:

    def ids(**kw: Any) -> list[str]:
        return [r.id for r in runs.list(**kw)]  # type: ignore[attr-defined]

    assert ids(project_id="p1") == ["f", "e", "c", "a"]
    assert ids(project_id="p1", root_only=True) == ["e", "a"]
    assert ids(root_only=True) == ["e", "d", "b", "a"]
    assert ids(root_only=True, limit=2) == ["e", "d"]  # limit이 자식 Run에 먹히지 않는다
    assert ids(project_id="p1", root_only=True, limit=1) == ["e"]
    assert ids(project_id="none") == []
    assert ids() == ["f", "e", "d", "c", "b", "a"]


def test_project_and_root_only_filters_sqlite_and_memory(tmp_path: Path) -> None:
    from agent_console_store import InMemoryStorage

    db = SqliteDatabase.open(tmp_path / "p.sqlite3")
    db.upgrade([BRANCH])
    sqlite_runs = SqliteStorage(db.engine).runs
    _seed_projects(sqlite_runs)
    _query_cases(sqlite_runs)
    assert sqlite_runs.get("a").project_id == "p1"  # type: ignore[union-attr]
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT project_id FROM runs WHERE id = 'd'").scalar() is None
        assert conn.exec_driver_sql("SELECT project_id FROM runs WHERE id = 'a'").scalar() == "p1"
    memory_runs = InMemoryStorage().runs
    _seed_projects(memory_runs)
    _query_cases(memory_runs)
    db.close()


def test_project_filter_without_the_column_reads_doc(tmp_path: Path) -> None:
    """계보를 runs_0002까지만 올린(또는 되돌린) DB도 같은 결과를 낸다(doc을 훑는다)."""
    db = SqliteDatabase.open(tmp_path / "old.sqlite3")
    db.upgrade([BRANCH])
    storage = SqliteStorage(db.engine)
    _seed_projects(storage.runs)
    db.downgrade_branch(BRANCH, "runs_0002")
    assert "project_id" not in _cols(db.engine, "runs")
    older = SqliteStorage(db.engine)
    _query_cases(older.runs)
    db.downgrade_branch(BRANCH, "runs_0001")
    _query_cases(SqliteStorage(db.engine).runs)
    db.upgrade([BRANCH])  # 다시 올리면 doc에서 열을 채운다
    again = SqliteStorage(db.engine)
    with db.engine.connect() as conn:
        assert (
            conn.exec_driver_sql("SELECT count(*) FROM runs WHERE project_id = 'p1'").scalar() == 4
        )
    _query_cases(again.runs)
    db.close()


def test_5r_database_upgrades_with_null_project_and_old_rows_readable(tmp_path: Path) -> None:
    path = tmp_path / "5r.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)
    _seed_4r(engine)
    engine.dispose()
    upgrade(  # 5R 기준 DB = 계보 runs_0002까지
        create_sqlite_engine(path), "runs_0002", versions=BRANCH.versions,
        version_table=branch_version_table("runs"),
    )  # fmt: skip
    db = SqliteDatabase.open(path)
    assert db.revision("runs") == "runs_0002"
    db.upgrade([BRANCH])
    assert db.revision("runs") == "runs_0003"
    storage = SqliteStorage(db.engine)
    run = storage.runs.get("old")
    assert run is not None
    assert (run.project_id, run.conversation_id) == (None, "c1")
    assert [r.id for r in storage.runs.list(root_only=True)] == ["old"]
    assert storage.runs.list(project_id="p1") == []
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT project_id FROM runs").scalars().all() == [None]
    db.close()


def test_project_and_root_only_queries_use_indexes(tmp_path: Path) -> None:
    """색인 질의 계획(UX-D2): 정렬을 새로 하지 않고(임시 B-tree 없음) 색인을 쓴다."""
    db = SqliteDatabase.open(tmp_path / "plan.sqlite3")
    db.upgrade([BRANCH])

    def plan(where: str) -> str:
        sql = f"SELECT doc FROM runs WHERE {where} ORDER BY created_at DESC, id DESC LIMIT 20"
        with db.engine.connect() as conn:
            return " ".join(str(r[3]) for r in conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql))

    by_project = plan("project_id = 'p'")
    assert "ix_runs_project_created" in by_project
    roots = plan("root_run_id IS NULL")
    assert "ix_runs_created" in roots or "ix_runs_root" in roots
    both = plan("project_id = 'p' AND root_run_id IS NULL")
    assert "ix_runs_project_created" in both
    assert "SCAN runs" not in by_project.replace("USING INDEX", "")
    db.close()
