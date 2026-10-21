"""Alembic: 적용, 롤백, 재적용, 모델-마이그레이션 일치, 파일 DB 영속."""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_contracts import RunEvent
from agent_console_store import (
    create_sqlite_engine,
    current_revision,
    downgrade,
    open_sqlite,
    upgrade,
)
from agent_console_store.schema import MODULE_OWNED_TABLES, include_object, metadata


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_creates_all_tables_and_downgrade_removes_them(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    assert current_revision(engine) is None
    upgrade(engine)
    assert current_revision(engine) == "0003"
    assert _tables(engine) == set(metadata.tables) | MODULE_OWNED_TABLES
    downgrade(engine)
    assert _tables(engine) == set()
    assert current_revision(engine) is None
    upgrade(engine)  # 다시 적용 가능
    upgrade(engine)  # 멱등
    assert _tables(engine) == set(metadata.tables) | MODULE_OWNED_TABLES
    engine.dispose()


def test_migrated_schema_matches_sqlalchemy_metadata(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine)
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"include_object": include_object}), metadata
        )
    assert diff == []
    engine.dispose()


def test_open_sqlite_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "c.sqlite3"  # 상위 폴더는 만들어 준다
    db = open_sqlite(path)
    db.events.append(RunEvent(event_id="e", run_id="r", seq=1, ts=1.0, type="t", node_path=[]))
    db.close()
    again = open_sqlite(path)
    assert again.events.last_seq("r") == 1
    again.close()


def test_open_sqlite_memory_and_url() -> None:
    db = open_sqlite(":memory:")
    assert db.events.last_seq("r") == 0
    db.close()


def test_indexes_exist_for_listed_columns(tmp_path: Path) -> None:
    db = open_sqlite(tmp_path / "i.sqlite3")
    inspector = sa.inspect(db.engine)
    names = {i["name"] for t in metadata.tables for i in inspector.get_indexes(t)}
    assert {"ix_runs_graph_created", "ix_runs_status", "ix_run_events_type"} <= names
    db.close()


def _cols(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _index_names(engine: sa.Engine, table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(engine).get_indexes(table) if i["name"]}


def test_0002_adds_columns_tables_and_indexes(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine, "0001")
    assert "conversation_id" not in _cols(engine, "runs")
    assert "conversations" not in _tables(engine)
    upgrade(engine)
    assert "conversation_id" in _cols(engine, "runs")
    assert "actor" in _cols(engine, "run_events")
    assert {"conversations", "usage_observations", "interactions"} <= _tables(engine)
    assert "ix_run_events_actor_ts" in _index_names(engine, "run_events")
    assert "ix_runs_conversation" in _index_names(engine, "runs")
    assert {
        "ix_interactions_status_created",
        "ix_interactions_run",
        "ix_interactions_conversation_status",
    } <= _index_names(engine, "interactions")
    engine.dispose()


def test_0002_downgrade_and_reapply_keep_data_and_restore_projection(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine, "0001")
    run_doc = json.dumps({"id": "r1", "conversation_id": "c1"})
    event_body = json.dumps({"event_id": "e1", "run_id": "r1", "seq": 1, "actor": "pl"})
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO runs (id, graph_id, graph_version, status, origin, created_at, doc) "
            "VALUES ('r1', 'g', 'h', 'completed', 'chat', 1.0, ?)",
            (run_doc,),
        )
        conn.exec_driver_sql(
            "INSERT INTO run_events (run_id, seq, event_id, ts, type, body) "
            "VALUES ('r1', 1, 'e1', 1.0, 'node.started', ?)",
            (event_body,),
        )
    upgrade(engine)
    with engine.connect() as conn:  # 적용할 때 doc/body에서 새 컬럼을 채운다
        assert conn.exec_driver_sql("SELECT conversation_id FROM runs").scalar() == "c1"
        assert conn.exec_driver_sql("SELECT actor FROM run_events").scalar() == "pl"
    downgrade(engine, "0001")
    assert current_revision(engine) == "0001"
    assert "conversation_id" not in _cols(engine, "runs")
    assert "actor" not in _cols(engine, "run_events")
    assert "interactions" not in _tables(engine)
    assert "ix_runs_status" in _index_names(engine, "runs")  # 0001의 인덱스는 그대로
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM runs").scalar() == 1
        assert conn.exec_driver_sql("SELECT count(*) FROM run_events").scalar() == 1
    upgrade(engine)  # 다시 적용하면 같은 값이 복구된다
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT conversation_id FROM runs").scalar() == "c1"
        assert conn.exec_driver_sql("SELECT actor FROM run_events").scalar() == "pl"
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"include_object": include_object})
        assert compare_metadata(context, metadata) == []
    engine.dispose()
