"""logs 계보: 적용·되돌리기, 스키마 일치, 기존 DB 호환, 색인 열기(design §3R.1.7·§4R.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_logs import LogFilter, QueryContext
from agent_console_logs._index import IndexBatch, StoredCursor
from agent_console_logs.sqlite import TABLE_NAMES, SqliteLogIndex, log_metadata
from agent_console_logs.testing import MemoryLogIndex, make_record
from agent_console_mod_logs.storage import BRANCH, open_log_storage
from agent_console_store import (
    SqliteDatabase,
    branch_version_table,
    create_sqlite_engine,
    current_revision,
    downgrade,
    upgrade,
)

CTX = QueryContext()
VERSION_TABLE = branch_version_table("logs")


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def test_branch_identity() -> None:
    assert BRANCH.name == "logs"
    assert VERSION_TABLE == "alembic_version_logs"
    assert (BRANCH.versions / "logs_0001_index.py").is_file()


def test_upgrade_creates_tables_and_downgrade_removes_them(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "a.sqlite3")
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    assert set(TABLE_NAMES) <= _tables(engine)
    assert current_revision(engine, version_table=VERSION_TABLE) == "logs_0002"
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)  # 멱등
    downgrade(engine, "base", versions=BRANCH.versions, version_table=VERSION_TABLE)
    assert not set(TABLE_NAMES) & _tables(engine)
    assert current_revision(engine, version_table=VERSION_TABLE) is None
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)  # 왕복 뒤 다시 올림
    assert set(TABLE_NAMES) <= _tables(engine)
    engine.dispose()


def test_migration_matches_log_metadata(tmp_path: Path) -> None:
    """마이그레이션이 만든 모양 = ac-logs의 테이블 정의(열·인덱스·유일 제약 차이 0)."""
    engine = create_sqlite_engine(tmp_path / "b.sqlite3")
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), log_metadata)
    # 버전 테이블은 메타데이터에 없으므로 제외한다.
    diff = [d for d in diff if not (d[0] == "remove_table" and d[1].name.startswith("alembic_"))]
    assert diff == []
    engine.dispose()


def test_existing_host_database_is_compatible(tmp_path: Path) -> None:
    """3R 시점 DB(legacy 0003)에 logs 계보를 올려도 기존 테이블·리비전은 그대로다."""
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    db.upgrade([])
    before = _tables(db.engine)
    legacy = db.revision()
    assert not set(TABLE_NAMES) & before
    db.upgrade([BRANCH])
    after = _tables(db.engine)
    assert before <= after
    assert set(TABLE_NAMES) <= after
    assert db.revision() == legacy
    assert db.revision("logs") == "logs_0002"
    db.upgrade([BRANCH])  # 멱등
    db.downgrade_branch(BRANCH)
    assert _tables(db.engine) == before | {VERSION_TABLE}
    assert db.revision() == legacy
    db.close()


def test_host_storage_roundtrip_and_reopen(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    db.upgrade([BRANCH])
    storage = open_log_storage(db)
    assert storage.kind == "host"
    rec = make_record("llm", session="S", title="안녕", time=5.0)
    storage.index.write(
        IndexBatch(records=[rec], cursors=[StoredCursor("src", "f", offset=7, state={"a": [1]})])
    )
    again = open_log_storage(db)  # 같은 DB를 다시 열어도 데이터 유지
    page = again.index.query_events(LogFilter(), CTX)
    assert [e.title for e in page.items] == ["안녕"]
    cursor = again.index.get_cursor("src", "f")
    assert cursor is not None
    assert (cursor.offset, dict(cursor.state)) == (7, {"a": [1]})
    storage.close()  # 호스트 엔진은 닫지 않는다
    assert again.index.max_seq() == 1
    db.close()


def test_index_path_uses_own_file_and_leaves_host_alone(tmp_path: Path) -> None:
    host = SqliteDatabase.open(tmp_path / "host.sqlite3")
    host.upgrade([])
    storage = open_log_storage(host, index_path=tmp_path / "sub" / "idx.sqlite3")
    assert storage.kind == "file"
    storage.index.write(IndexBatch(records=[make_record("llm", session="S")]))
    assert not set(TABLE_NAMES) & _tables(host.engine)
    assert isinstance(storage.index, SqliteLogIndex)
    assert set(TABLE_NAMES) <= _tables(storage.index.engine)
    # 별도 파일에는 logs 계보만 있다(legacy 계보 테이블이 없다).
    assert "alembic_version" not in _tables(storage.index.engine)
    assert current_revision(storage.index.engine, version_table=VERSION_TABLE) == "logs_0002"
    storage.close()
    again = open_log_storage(None, index_path=tmp_path / "sub" / "idx.sqlite3")  # 다시 열기
    assert again.index.max_seq() == 1
    again.close()
    host.close()


def test_memory_when_no_database() -> None:
    storage = open_log_storage(None)
    assert storage.kind == "memory"
    assert isinstance(storage.index, MemoryLogIndex)


def test_rerunning_ingest_does_not_duplicate(tmp_path: Path) -> None:
    """같은 묶음을 다시 써도(재시작 뒤 재수집) 이벤트·토큰이 늘지 않는다."""
    storage = open_log_storage(None, index_path=tmp_path / "i.sqlite3")
    batch = IndexBatch(records=[make_record("llm", origin="a", offset=1, session="S")])
    first = storage.index.write(batch)
    second = storage.index.write(batch)
    assert (first.inserted, second.inserted) == (1, 0)
    assert storage.index.query_events(LogFilter(), CTX, with_total=True).total == 1
    storage.close()


@pytest.mark.parametrize("name", ["log_events", "log_usage"])
def test_dashboard_columns_are_indexed(tmp_path: Path, name: str) -> None:
    engine = create_sqlite_engine(tmp_path / "c.sqlite3")
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    indexed = {tuple(i["column_names"]) for i in sa.inspect(engine).get_indexes(name)}
    if name == "log_events":
        assert {
            ("session", "etime"),
            ("etime",),
            ("cwd", "repo_root"),
            ("run_id", "seq"),
        } <= indexed
        assert {("session", "seq"), ("thread", "seq")} <= indexed
        assert ("run_id",) not in indexed  # 0002가 (run_id, seq)로 바꿨다
    else:
        assert {("session",), ("time",)} <= indexed
    engine.dispose()


def _fill(index: SqliteLogIndex, n: int) -> None:
    index.write(
        IndexBatch(
            records=[
                make_record(
                    "llm",
                    origin="a",
                    offset=i,
                    session=f"S{i % 3}",
                    thread="main" if i % 2 else "sub",
                    run_id="r1" if i % 5 == 0 else "",
                    time=100.0 + i,
                )
                for i in range(n)
            ]
        )
    )


def test_index_file_upgrades_from_0001_without_loss(tmp_path: Path) -> None:
    """0001로 만든 `index_path` 파일에 데이터를 쓴 뒤 열면 0002로 올라가고 행이 그대로다."""
    path = tmp_path / "old.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine, "logs_0001", versions=BRANCH.versions, version_table=VERSION_TABLE)
    assert ("run_id",) in {
        tuple(i["column_names"]) for i in sa.inspect(engine).get_indexes("log_events")
    }
    _fill(SqliteLogIndex(engine), 60)
    with engine.connect() as conn:
        before = conn.execute(
            sa.text("SELECT seq, uid, session, thread, run_id FROM log_events ORDER BY seq")
        ).all()
        bodies = conn.execute(sa.text("SELECT count(*) FROM log_bodies")).scalar()
    engine.dispose()

    storage = open_log_storage(None, index_path=path)  # 열면서 계보를 올린다
    assert isinstance(storage.index, SqliteLogIndex)
    engine = storage.index.engine
    assert current_revision(engine, version_table=VERSION_TABLE) == "logs_0002"
    with engine.connect() as conn:
        after = conn.execute(
            sa.text("SELECT seq, uid, session, thread, run_id FROM log_events ORDER BY seq")
        ).all()
        assert conn.execute(sa.text("SELECT count(*) FROM log_bodies")).scalar() == bodies
        plan = conn.execute(
            sa.text(
                "EXPLAIN QUERY PLAN SELECT seq FROM log_events "
                "WHERE thread = 'main' ORDER BY seq LIMIT 5"
            )
        ).all()
    assert after == before
    assert any("ix_log_events_thread_seq" in str(r) for r in plan)
    assert not any("TEMP B-TREE" in str(r) for r in plan)
    page = storage.index.query_events(LogFilter(run_id=("r1",), limit=100), CTX)
    assert len(page.items) == 12
    storage.close()


def test_downgrade_0002_restores_old_indexes_and_keeps_rows(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "d.sqlite3")
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    _fill(SqliteLogIndex(engine), 20)
    downgrade(engine, "logs_0001", versions=BRANCH.versions, version_table=VERSION_TABLE)
    names = {i["name"] for i in sa.inspect(engine).get_indexes("log_events")}
    assert "ix_log_events_run" in names
    assert (
        not {"ix_log_events_run_seq", "ix_log_events_thread_seq", "ix_log_events_session_seq"}
        & names
    )
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM log_events")).scalar() == 20
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)  # 다시 올림
    assert current_revision(engine, version_table=VERSION_TABLE) == "logs_0002"
    engine.dispose()
