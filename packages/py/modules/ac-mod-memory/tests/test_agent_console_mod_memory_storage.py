"""계보 ``memory``(memory_0001)와 저장소 열기(design §5.7R.6).

- 마이그레이션이 만든 모양 = ``ac-memory`` 표 정의(``compare_metadata`` 차이 0, 전문 검색 가상 표와
  그림자 표·버전 표는 비교 밖).
- 기존 호스트 DB에 올려도 다른 계보는 그대로이고, 내려도 메모리 표만 사라진다.
- 열기 순서: ``store_path`` > 호스트 DB 파일 > 메모리(경고).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import MemoryAuthor, MemoryScopeRef
from agent_console_memory import InMemoryMemoryStore
from agent_console_memory.sqlite import SqliteMemoryStore, fts5_trigram_available, schema
from agent_console_mod_memory.storage import BRANCH, host_database_file, open_memory_storage
from agent_console_store import (
    SqliteDatabase,
    branch_version_table,
    create_sqlite_engine,
    upgrade,
)

VERSION_TABLE = branch_version_table("memory")
SCOPE = MemoryScopeRef(kind="notes", id="p1")
USER = MemoryAuthor(kind="user")


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _outside_comparison(name: str) -> bool:
    return name.startswith("alembic_") or name.startswith(schema.SEARCH_TABLE)


def test_branch_identity() -> None:
    assert BRANCH.name == "memory"
    assert VERSION_TABLE == "alembic_version_memory"
    assert (BRANCH.versions / "memory_0001_tables.py").is_file()


def test_migration_matches_memory_metadata(tmp_path: Path) -> None:
    """마이그레이션이 만든 모양 = ac-memory 표 정의(열·색인·부분 색인·유일 제약 차이 0)."""
    engine = create_sqlite_engine(tmp_path / "m.sqlite3")
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), schema.metadata)
    diff = [d for d in diff if not (d[0] == "remove_table" and _outside_comparison(d[1].name))]
    assert diff == []
    engine.dispose()


def test_migration_then_store_adds_search_table(tmp_path: Path) -> None:
    """계보가 만든 표에 저장소를 열면 전문 검색 가상 표만 더한다(쓸 수 있을 때)."""
    path = tmp_path / "m.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine, versions=BRANCH.versions, version_table=VERSION_TABLE)
    before = _tables(engine)
    store = open_memory_storage(None, store_path=path).store
    assert isinstance(store, SqliteMemoryStore)
    store.write(SCOPE, "결정/api", "본문 하나", author=USER)
    after = _tables(engine)
    added = {t for t in after - before if not t.startswith(schema.SEARCH_TABLE)}
    assert added == set()
    assert (schema.SEARCH_TABLE in after) == fts5_trigram_available()
    store.close()
    engine.dispose()


def test_existing_host_database_is_compatible(tmp_path: Path) -> None:
    """기존 DB(legacy)에 memory 계보를 올려도 기존 테이블·리비전은 그대로다.

    내리면 메모리 표만 빠진다.
    """
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    db.upgrade([])
    before = _tables(db.engine)
    legacy = db.revision()
    assert not {t for t in before if t.startswith("memory_")}
    db.upgrade([BRANCH])
    after = _tables(db.engine)
    assert before <= after
    assert {schema.ENTRIES_TABLE, schema.VERSIONS_TABLE, schema.TAGS_TABLE} <= after
    assert db.revision() == legacy
    assert db.revision("memory") == "memory_0001"
    db.upgrade([BRANCH])  # 멱등
    db.downgrade_branch(BRANCH)
    assert _tables(db.engine) == before | {VERSION_TABLE}
    db.close()


def test_open_host_database_file(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    db.upgrade([BRANCH])
    storage = open_memory_storage(db)
    assert storage.kind == "host"
    assert storage.path == tmp_path / "host.sqlite3"
    entry = storage.store.write(SCOPE, "k", "값", author=USER).entry
    storage.close()
    again = open_memory_storage(db)
    assert again.store.get(entry.id) is not None  # 다시 열어도 남는다
    assert KnownIssueCodes.MEMORY_STORAGE_MEMORY not in [i.code for i in again.warnings()]
    again.close()
    db.close()


def test_store_path_wins_and_gets_its_own_lineage(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "host.sqlite3")
    own = tmp_path / "sub" / "memory.db"
    storage = open_memory_storage(db, store_path=own)
    assert storage.kind == "file"
    assert own.is_file()
    engine = create_sqlite_engine(own)
    assert VERSION_TABLE in _tables(engine)
    engine.dispose()
    assert not {t for t in _tables(db.engine) if t.startswith("memory_")}
    storage.close()
    db.close()


def test_no_database_means_memory_store_with_warning() -> None:
    storage = open_memory_storage(None)
    assert storage.kind == "memory"
    assert isinstance(storage.store, InMemoryMemoryStore)
    assert [i.code for i in storage.warnings()] == [KnownIssueCodes.MEMORY_STORAGE_MEMORY]


def test_in_memory_host_database_is_not_shared() -> None:
    """호스트 DB가 프로세스 메모리 DB면 다른 엔진이 붙을 수 없어 메모리 저장소다."""
    db = SqliteDatabase.open(":memory:")
    assert host_database_file(db) is None
    assert open_memory_storage(db).kind == "memory"
    db.close()


def test_full_text_search_off_warns_fallback(tmp_path: Path) -> None:
    storage = open_memory_storage(None, store_path=tmp_path / "m.db", use_fts=False)
    codes = [i.code for i in storage.warnings()]
    assert codes == [KnownIssueCodes.MEMORY_SEARCH_FALLBACK]
    storage.close()
