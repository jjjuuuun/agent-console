"""SQLite 페이지 기록 저장소 `SqliteWikiHistory`(X49 구현, design §7R.6).

- `record(entries)` 한 번 = `BEGIN IMMEDIATE` 트랜잭션 하나(옮기기 두 행·링크 고친 페이지 행 포함).
- 본문은 `wiki_blobs`에 해시로 한 번만 둔다. `HistoryEntry.content=None`이면 블롭을 넣지 않는다.
- `changes`는 `seq`(삽입 순서) 내림차순 + 불투명 커서(마지막 `seq`).
- `prune`은 첫 버전을 남기고 오래된 것부터 지우며, 가리키는 버전이 없어진 블롭을 같은 트랜잭션에서
  지운다.

표는 `create=True`면 열 때 `schema.metadata.create_all`로 만든다(단독 사용). 계보 `wiki`가 이미 만든
파일에서는 아무 일도 하지 않는다.
"""

from __future__ import annotations

import contextlib
import random
import sqlite3
import threading
import time
from collections.abc import Callable, Collection, Iterator, Sequence
from pathlib import Path
from typing import TypeVar

from sqlalchemy import (
    Connection,
    Engine,
    and_,
    create_engine,
    delete,
    event,
    func,
    literal_column,
    or_,
    select,
)
from sqlalchemy import exc as sa_exc
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool

from agent_console_contracts.wiki import (
    WikiAuthor,
    WikiChange,
    WikiChangePage,
    WikiHistoryPage,
    WikiPageVersion,
)
from agent_console_wiki._history import HistoryEntry, HistorySummary

from . import schema

__all__ = ["SqliteWikiHistory"]

_T = TypeVar("_T")
_V = schema.versions
_B = schema.blobs
_BEGIN_KEY = "ac_wiki_begin"
_COLUMNS = (
    _V.c.version,
    _V.c.op,
    _V.c.sha256,
    _V.c.bytes,
    _V.c.at,
    _V.c.from_path,
    _V.c.to_path,
    _V.c.message,
    _V.c.author_json,
)


def _is_busy(error: sa_exc.OperationalError) -> bool:
    message = str(error.orig).lower()
    return "locked" in message or "busy" in message


def _version(row: object) -> WikiPageVersion:
    r = row._mapping  # type: ignore[attr-defined]
    return WikiPageVersion.model_validate(
        {
            "version": r["version"],
            "op": r["op"],
            "sha256": r["sha256"],
            "bytes": r["bytes"],
            "author": WikiAuthor.model_validate_json(r["author_json"]).model_dump(mode="json"),
            "message": r["message"],
            "at": r["at"],
            "from": r["from_path"],
            "to": r["to_path"],
        }
    )


class SqliteWikiHistory:
    """`WikiHistory` SQLite 구현. 스레드 안전(쓰기는 잠금 + `BEGIN IMMEDIATE`).

    Args:
        path: SQLite 파일 경로(`":memory:"`·빈 문자열이면 프로세스 메모리 DB).
        create: True면 열 때 표를 만든다(계보 `wiki`가 올린 파일이면 아무 일도 하지 않는다).
        busy_timeout_seconds: 쓰기 잠금을 기다리는 시간.
        journal: 저널 방식(파일 DB, 기본 WAL).
    """

    def __init__(
        self,
        path: str | Path,
        *,
        create: bool = True,
        busy_timeout_seconds: float = 10.0,
        journal: str = "WAL",
    ) -> None:
        self._busy_timeout = busy_timeout_seconds
        self._journal = journal
        raw = str(path)
        self._memory = raw in ("", ":memory:")
        self.path = ":memory:" if self._memory else raw
        if not self._memory:
            Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._make_engine()
        self._lock = threading.RLock()
        if create:
            schema.metadata.create_all(self._engine)

    # ---- 연결·트랜잭션 -----------------------------------------------------------------

    def _make_engine(self) -> Engine:
        if self._memory:
            engine = create_engine(
                "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
            )
        else:
            engine = create_engine(
                URL.create("sqlite", database=str(Path(self.path).expanduser())),
                connect_args={"check_same_thread": False, "timeout": min(self._busy_timeout, 0.5)},
            )
        memory = self._memory
        journal = self._journal

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi: sqlite3.Connection, _record: object) -> None:
            dbapi.isolation_level = None  # 트랜잭션은 begin 이벤트에서 직접 연다
            if not memory:
                cursor = dbapi.cursor()
                try:
                    cursor.execute(f"PRAGMA journal_mode={journal}")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                except sqlite3.DatabaseError:
                    pass
                finally:
                    cursor.close()

        @event.listens_for(engine, "begin")
        def _on_begin(conn: Connection) -> None:
            conn.exec_driver_sql(conn.info.get(_BEGIN_KEY, "BEGIN"))

        return engine

    @contextlib.contextmanager
    def _reading(self) -> Iterator[Connection]:
        lock = self._lock if self._memory else contextlib.nullcontext()
        with lock, self._engine.connect() as conn:
            conn.info[_BEGIN_KEY] = "BEGIN"
            try:
                yield conn
            finally:
                conn.rollback()

    def _writing(self, fn: Callable[[Connection], _T]) -> _T:
        deadline = time.monotonic() + self._busy_timeout
        delay = 0.005
        while True:
            try:
                with self._lock, self._engine.connect() as conn:
                    conn.info[_BEGIN_KEY] = "BEGIN IMMEDIATE"
                    try:
                        result = fn(conn)
                        conn.commit()
                        return result
                    finally:
                        conn.info[_BEGIN_KEY] = "BEGIN"
            except sa_exc.OperationalError as error:
                if not _is_busy(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(delay * (0.5 + random.random()))
                delay = min(delay * 2, 0.1)

    def close(self) -> None:
        """연결을 닫는다(이후 사용 금지)."""
        self._engine.dispose()

    def __enter__(self) -> SqliteWikiHistory:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---- WikiHistory ---------------------------------------------------------------------

    def record(self, entries: Sequence[HistoryEntry]) -> list[WikiPageVersion]:
        """기록을 한 트랜잭션으로 남긴다. 실패하면 하나도 남지 않는다."""
        if not entries:
            return []

        def run(conn: Connection) -> list[WikiPageVersion]:
            next_no: dict[tuple[str, str], int] = {}
            out: list[WikiPageVersion] = []
            for entry in entries:
                key = (entry.wiki, entry.path)
                if key not in next_no:
                    top = conn.execute(
                        select(func.max(_V.c.version)).where(
                            _V.c.wiki_id == entry.wiki, _V.c.path == entry.path
                        )
                    ).scalar_one()
                    next_no[key] = int(top or 0) + 1
                number = next_no[key]
                next_no[key] = number + 1
                if entry.content is not None:
                    conn.execute(
                        sqlite_insert(_B)
                        .values(sha256=entry.sha256, content=bytes(entry.content))
                        .on_conflict_do_nothing(index_elements=["sha256"])
                    )
                conn.execute(
                    _V.insert().values(
                        wiki_id=entry.wiki,
                        path=entry.path,
                        version=number,
                        op=entry.op,
                        sha256=entry.sha256,
                        bytes=entry.bytes,
                        at=entry.at,
                        author_run_id=entry.author.run_id,
                        author_root_run_id=entry.author.root_run_id,
                        from_path=entry.from_,
                        to_path=entry.to,
                        message=entry.message,
                        author_json=entry.author.model_dump_json(),
                    )
                )
                out.append(
                    WikiPageVersion.model_validate(
                        {
                            "version": number,
                            "op": entry.op,
                            "sha256": entry.sha256,
                            "bytes": entry.bytes,
                            "author": entry.author.model_dump(mode="json"),
                            "message": entry.message,
                            "at": entry.at,
                            "from": entry.from_,
                            "to": entry.to,
                        }
                    )
                )
            return out

        return self._writing(run)

    def list(self, wiki: str, path: str, *, limit: int | None = None) -> WikiHistoryPage:
        """페이지 기록(최근 것부터)과 `pruned`(`max(version) > count(*)`)."""
        query = (
            select(*_COLUMNS)
            .where(_V.c.wiki_id == wiki, _V.c.path == path)
            .order_by(_V.c.version.desc())
        )
        if limit is not None:
            query = query.limit(max(0, limit))
        with self._reading() as conn:
            rows = conn.execute(query).all()
            top, count = conn.execute(
                select(func.max(_V.c.version), func.count()).where(
                    _V.c.wiki_id == wiki, _V.c.path == path
                )
            ).one()
        return WikiHistoryPage(
            items=[_version(r) for r in rows], pruned=bool(count) and int(top) > int(count)
        )

    def get(self, wiki: str, path: str, version: int) -> WikiPageVersion | None:
        with self._reading() as conn:
            row = conn.execute(
                select(*_COLUMNS).where(
                    _V.c.wiki_id == wiki, _V.c.path == path, _V.c.version == version
                )
            ).first()
        return _version(row) if row is not None else None

    def read(self, wiki: str, path: str, version: int) -> bytes | None:
        with self._reading() as conn:
            row = conn.execute(
                select(_B.c.content)
                .select_from(_V.join(_B, _B.c.sha256 == _V.c.sha256))
                .where(_V.c.wiki_id == wiki, _V.c.path == path, _V.c.version == version)
            ).first()
        return bytes(row[0]) if row is not None else None

    def latest(self, wiki: str, path: str) -> WikiPageVersion | None:
        with self._reading() as conn:
            row = conn.execute(
                select(*_COLUMNS)
                .where(_V.c.wiki_id == wiki, _V.c.path == path)
                .order_by(_V.c.version.desc())
                .limit(1)
            ).first()
        return _version(row) if row is not None else None

    def summaries(self, wiki: str) -> dict[str, HistorySummary]:
        """위키의 페이지마다 (첫 시각, 마지막 버전). 질의 한 번(창 함수)."""
        part = _V.c.path
        ranked = (
            select(
                _V.c.path,
                *_COLUMNS,
                func.row_number().over(partition_by=part, order_by=_V.c.version.desc()).label("rn"),
                func.first_value(_V.c.at)
                .over(
                    partition_by=part,
                    order_by=_V.c.version.asc(),
                    rows=(None, None),
                )
                .label("first_at"),
            )
            .where(_V.c.wiki_id == wiki)
            .subquery()
        )
        with self._reading() as conn:
            rows = conn.execute(select(ranked).where(ranked.c.rn == 1)).all()
        return {
            r._mapping["path"]: HistorySummary(
                path=r._mapping["path"], first_at=float(r._mapping["first_at"]), latest=_version(r)
            )
            for r in rows
        }

    def changes(
        self,
        wiki: str | None = None,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """최근 변경(최근 것부터). 커서는 마지막으로 돌려준 `seq`다."""
        size = max(1, limit)
        conditions = []
        if wiki is not None:
            conditions.append(_V.c.wiki_id == wiki)
        if ops:
            conditions.append(_V.c.op.in_(list(ops)))
        if author_run is not None:
            conditions.append(
                or_(_V.c.author_run_id == author_run, _V.c.author_root_run_id == author_run)
            )
        if cursor and cursor.isdigit():
            conditions.append(_V.c.seq < int(cursor))
        query = (
            select(_V.c.seq, _V.c.wiki_id, _V.c.path, *_COLUMNS)
            .where(*conditions)
            .order_by(_V.c.seq.desc())
            .limit(size + 1)
        )
        with self._reading() as conn:
            rows = conn.execute(query).all()
        page = rows[:size]
        items = [
            WikiChange.model_validate(
                {
                    **_version(r).model_dump(mode="json", by_alias=True),
                    "wiki": r._mapping["wiki_id"],
                    "path": r._mapping["path"],
                }
            )
            for r in page
        ]
        more = len(rows) > size
        return WikiChangePage(
            items=items, next_cursor=str(page[-1]._mapping["seq"]) if more and page else None
        )

    def prune(self, wiki: str, path: str, *, keep: int) -> int:
        """첫 버전을 남기고 오래된 것부터 지워 `keep`개만 남긴다(고아 블롭은 같은 트랜잭션에서)."""
        keep = max(1, keep)

        def run(conn: Connection) -> int:
            numbers = [
                int(n)
                for n in conn.execute(
                    select(_V.c.version)
                    .where(_V.c.wiki_id == wiki, _V.c.path == path)
                    .order_by(_V.c.version)
                ).scalars()
            ]
            if len(numbers) <= keep:
                return 0
            drop = numbers[1 : len(numbers) - keep + 1]
            span = and_(
                _V.c.wiki_id == wiki,
                _V.c.path == path,
                _V.c.version >= drop[0],
                _V.c.version <= drop[-1],
            )
            hashes = set(conn.execute(select(_V.c.sha256).where(span)).scalars())
            conn.execute(delete(_V).where(span))
            if hashes:
                still = select(literal_column("1")).where(_V.c.sha256 == _B.c.sha256).exists()
                conn.execute(delete(_B).where(_B.c.sha256.in_(hashes), ~still))
            return len(drop)

        return self._writing(run)
