"""SQLite 엔진 만들기와 단독 열기."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool

from ._index import SqliteLogIndex
from .schema import log_metadata

__all__ = ["create_log_engine", "open_log_index"]


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

    서버 안에서는 이 함수 대신 모듈의 마이그레이션 계보 `logs`로 테이블을 만든다.
    반환한 색인의 `close()`가 엔진을 닫는다.
    """
    engine = create_log_engine(target, journal_mode=journal_mode)
    log_metadata.create_all(engine)
    return SqliteLogIndex(engine, owns_engine=True)
