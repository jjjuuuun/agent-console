"""SQLite 엔진 만들기와 단독 열기."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool

from ._index import SqliteLogIndex
from .schema import OBSOLETE_INDEXES, TABLE_NAMES, log_metadata

__all__ = ["create_log_engine", "open_existing_log_index", "open_log_index"]


def create_log_engine(target: str | Path, *, journal_mode: str = "WAL") -> Engine:
    """색인용 SQLite 엔진. `target`은 파일 경로 또는 `":memory:"`.

    파일이면 상위 폴더를 만든다. WAL(지원하지 않는 파일시스템이면 SQLite 기본값)과 잠금 대기 15초.
    """
    text = str(target)
    if text in (":memory:", "sqlite://"):
        engine = sa.create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        path = Path(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = sa.create_engine(
            f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 15}
        )

    @sa.event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA journal_mode={journal_mode}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        finally:
            cursor.close()

    return engine


def open_log_index(target: str | Path, *, journal_mode: str = "WAL") -> SqliteLogIndex:
    """색인 파일(또는 `":memory:"`)을 열고 없는 테이블을 만든다(단독 사용, `create_all`).

    이미 있는 파일이면 빠진 색인을 만들고 옛 색인을 지운다(행은 건드리지 않는다).
    서버 안에서는 이 함수 대신 모듈의 마이그레이션 계보 `logs`로 테이블을 만든다.
    반환한 색인의 `close()`가 엔진을 닫는다.
    """
    engine = create_log_engine(target, journal_mode=journal_mode)
    log_metadata.create_all(engine)
    _sync_indexes(engine)
    return SqliteLogIndex(engine, owns_engine=True)


def open_existing_log_index(path: str | Path) -> SqliteLogIndex:
    """이미 있는 색인 파일(별도 색인 파일 또는 서버 DB)을 연다. 파일·테이블을 만들지 않는다.

    도구(예: `agent-console logs purge`)가 서버 밖에서 색인을 고칠 때 쓴다. 반환한 색인의
    `close()`가 엔진을 닫는다.

    Raises:
        FileNotFoundError: 파일이 없다.
        LookupError: 로그 색인 테이블이 없다(모듈이 한 번도 켜지지 않은 DB 등).
    """
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"색인 파일이 없습니다: {target}")
    engine = create_log_engine(target)
    try:
        have = set(sa.inspect(engine).get_table_names())
    except Exception:
        engine.dispose()
        raise
    missing = [name for name in TABLE_NAMES if name not in have]
    if missing:
        engine.dispose()
        raise LookupError(f"로그 색인 테이블이 없습니다: {', '.join(missing)}")
    return SqliteLogIndex(engine, owns_engine=True)


def _sync_indexes(engine: Engine) -> None:
    """`create_all`이 건너뛴(테이블이 이미 있어서) 색인을 현재 정의대로 맞춘다."""
    for table in log_metadata.sorted_tables:
        for index in table.indexes:
            index.create(engine, checkfirst=True)
    with engine.begin() as conn:
        for name in OBSOLETE_INDEXES:
            conn.execute(sa.text(f'DROP INDEX IF EXISTS "{name}"'))
