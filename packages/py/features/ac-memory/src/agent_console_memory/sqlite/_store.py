"""SQLite 메모리 저장소(`SqliteMemoryStore`, X31 구현).

- 쓰기는 `BEGIN IMMEDIATE` 트랜잭션 하나로 줄을 세운다(같은 프로세스는 잠금 + 다른 프로세스는
  SQLite 잠금, 바쁨이면 짧게 쉬며 다시 시도). 버전 번호는 겹치지 않는다.
- 전문 검색은 FTS5 `trigram`(3글자 이상). 3글자 미만이거나 FTS5를 쓸 수 없으면
  `LIKE`식 포함 검색이다.
- 메모리 구현(`InMemoryMemoryStore`)과 같은 의미다(`testing.contract.MemoryStoreContractTests` +
  무작위 연산열 차등 테스트).
"""

from __future__ import annotations

import contextlib
import json
import random
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypeVar

from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    Integer,
    Row,
    create_engine,
    delete,
    event,
    exists,
    func,
    insert,
    or_,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import TextClause

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.definitions import Issue
from agent_console_contracts.memory import (
    MEMORY_DEFAULT_CONTENT_TYPE,
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryEntrySummary,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryVersion,
    MemoryVersionOp,
    MemoryVersionSummary,
)
from agent_console_memory._errors import (
    EntryExistsError,
    EntryNotFoundError,
    TooLargeError,
    VersionConflictError,
)
from agent_console_memory._keys import check_key
from agent_console_memory._memory_store import _append
from agent_console_memory._policy import MemoryPolicy, check_secret_field, prepare_write
from agent_console_memory._scan import EntryHead
from agent_console_memory._shared import (
    check_sort,
    decode_cursor,
    encode_cursor,
    versions_to_drop,
)
from agent_console_memory._store import MemoryQuery, MemoryWriteOutcome, WriteMode

from . import schema

SearchBackend = Literal["fts5", "like"]
"""검색 방식: `fts5` = FTS5 trigram(3글자 이상), `like` = 포함 검색만."""

MIN_FTS_CHARS = 3
SCAN_PAGE_SIZE = 2_000
"""`scan_entries`가 한 번에 읽는 항목 수."""
"""trigram 색인이 답할 수 있는 최소 검색어 길이(글자)."""

_T = TypeVar("_T")
_BEGIN_KEY = "ac_memory_begin"
_E = schema.entries
_V = schema.versions
_T_TAGS = schema.tags
_STATS = schema.stats
_SUMMARY_COLUMNS = [c for c in _E.c if c.name != "content"]
_SCAN_COLUMNS = [_E.c.rid, *(c for c in _E.c if c.name not in ("rid", "preview"))]
_META_NAMES = (
    "rid",
    "id",
    "scope_kind",
    "scope_id",
    "key",
    "content_type",
    "tags",
    "pinned",
    "archived",
    "version",
    "bytes",
    "sha256",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "last_read_at",
    "deleted_at",
)
_META_COLUMNS = [_E.c[name] for name in _META_NAMES]  # 순서 고정: `_head`가 자리로 읽는다
_MUTABLE = (
    "scope_kind",
    "scope_id",
    "key",
    "content_type",
    "tags",
    "pinned",
    "archived",
    "version",
    "bytes",
    "sha256",
    "updated_at",
    "updated_by",
    "author_run_id",
    "last_read_at",
    "deleted_at",
    "content",
)


def fts5_trigram_available() -> bool:
    """이 SQLite에서 FTS5 `trigram` 가상 표를 만들 수 있으면 참(임시 메모리 DB로 시험)."""
    try:
        with contextlib.closing(sqlite3.connect(":memory:")) as probe:
            probe.execute("CREATE VIRTUAL TABLE _probe USING fts5(x, tokenize='trigram')")
    except sqlite3.Error:
        return False
    return True


def _fold(value: str | None) -> str | None:
    return value.casefold() if isinstance(value, str) else value


def _entry_columns(entry: MemoryEntry) -> dict[str, Any]:
    """항목 → 표 열 값(`rid`·`preview` 제외)."""
    return {
        "id": entry.id,
        "scope_kind": entry.scope.kind,
        "scope_id": entry.scope.id,
        "key": entry.key,
        "content_type": entry.content_type,
        "tags": json.dumps(entry.tags, ensure_ascii=False),
        "pinned": entry.pinned,
        "archived": entry.archived,
        "version": entry.version,
        "bytes": entry.bytes,
        "sha256": entry.sha256,
        "created_at": entry.created_at,
        "created_by": entry.created_by.model_dump_json(),
        "updated_at": entry.updated_at,
        "updated_by": entry.updated_by.model_dump_json(),
        "author_run_id": entry.updated_by.run_id,
        "last_read_at": entry.last_read_at,
        "deleted_at": entry.deleted_at,
        "content": entry.content,
    }


def _version_columns(entry: MemoryEntry, op: MemoryVersionOp) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "version": entry.version,
        "op": op,
        "scope_kind": entry.scope.kind,
        "scope_id": entry.scope.id,
        "key": entry.key,
        "bytes": entry.bytes,
        "sha256": entry.sha256,
        "author": entry.updated_by.model_dump_json(),
        "run_id": entry.updated_by.run_id,
        "at": entry.updated_at,
        "content": entry.content,
    }


def _live_size(entry: MemoryEntry) -> int:
    return entry.bytes if entry.deleted_at is None else 0


def _entry_fields(row: Mapping[Any, Any]) -> dict[str, Any]:
    """표 행 → 항목 필드(본문·미리보기 제외)."""
    return {
        "id": row["id"],
        "scope": _scope(row["scope_kind"], row["scope_id"]),
        "key": row["key"],
        "content_type": row["content_type"],
        "tags": list(_tags(row["tags"])),
        "pinned": bool(row["pinned"]),
        "archived": bool(row["archived"]),
        "version": row["version"],
        "bytes": row["bytes"],
        "sha256": row["sha256"],
        "created_at": row["created_at"],
        "created_by": _author(row["created_by"]),
        "updated_at": row["updated_at"],
        "updated_by": _author(row["updated_by"]),
        "last_read_at": row["last_read_at"],
        "deleted_at": row["deleted_at"],
    }


@lru_cache(maxsize=4096)
def _author(raw: str) -> MemoryAuthor:
    """쓴 주체 JSON → 모델. 같은 값이 수없이 되풀이되므로(실행·에이전트 단위) 캐시한다.

    같은 인스턴스를 여러 항목이 나눠 가진다(메모리 구현도 쓸 때 받은 주체를 그대로 나눠 가진다).
    """
    return MemoryAuthor.model_validate_json(raw)


@lru_cache(maxsize=4096)
def _tags(raw: str) -> tuple[str, ...]:
    """태그 JSON → 튜플(같은 묶음이 되풀이되므로 캐시, 항목에는 목록 사본을 준다)."""
    return tuple(json.loads(raw))


@lru_cache(maxsize=4096)
def _scope(kind: str, scope_id: str) -> MemoryScopeRef:
    return MemoryScopeRef(kind=kind, id=scope_id)


def _to_entry(row: Mapping[Any, Any]) -> MemoryEntry:
    return MemoryEntry(**_entry_fields(row), content=row["content"])


def _head(row: Sequence[Any]) -> EntryHead:
    """`_META_COLUMNS` 순서의 행 → 머리(`EntryHead`). 값 변환은 `_entry_fields`와 같다.

    계약 모델을 만들지 않는다(검증·사전 만들기가 훑기 비용의 대부분이었다, 측정).
    """
    return EntryHead(
        row[1],
        _scope(row[2], row[3]),
        row[4],
        row[5],
        _tags(row[6]),
        bool(row[7]),
        bool(row[8]),
        row[9],
        row[10],
        row[11],
        row[12],
        _author(row[13]),
        row[14],
        _author(row[15]),
        row[16],
        row[17],
    )


def _search_values(key: str, content: str, tags: Sequence[str]) -> dict[str, str]:
    """전문 검색 색인에 넣는 값. 태그는 줄바꿈으로 잇는다(JSON 기호가 검색에 걸리지 않게)."""
    return {"k": key, "c": content, "t": "\n".join(tags)}


def _phrase(needle: str) -> str:
    """검색어 → FTS5 구문(따옴표 안의 글자 그대로, trigram은 부분 문자열 일치)."""
    return '"' + needle.replace('"', '""') + '"'


def _is_busy(error: sa_exc.OperationalError) -> bool:
    message = str(error.orig).lower()
    return "locked" in message or "busy" in message


class SqliteMemoryStore:
    """`MemoryStore` SQLite 구현. `open_sqlite_memory_store`로 만든다.

    Attributes:
        policy: 쓰기 정책(바꿔 끼울 수 있다).
        path: DB 파일 경로(메모리 DB면 ``":memory:"``).
    """

    def __init__(
        self,
        path: str | Path,
        *,
        policy: MemoryPolicy | None = None,
        clock: Callable[[], float] = time.time,
        new_id: Callable[[], str] | None = None,
        use_fts: bool | None = None,
        busy_timeout_seconds: float = 10.0,
        create: bool = True,
    ) -> None:
        self.policy = policy if policy is not None else MemoryPolicy()
        self._clock = clock
        self._new_id: Callable[[], str] = (
            new_id if new_id is not None else (lambda: str(uuid.uuid4()))
        )
        self._busy_timeout = busy_timeout_seconds
        raw = str(path)
        self._memory = raw in ("", ":memory:")
        self.path = ":memory:" if self._memory else raw
        if not self._memory:
            Path(raw).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._engine = self._make_engine()
        self._lock = threading.RLock()
        available = fts5_trigram_available()
        wanted = available if use_fts is None else (use_fts and available)
        self._fts = wanted
        self._fallback_reason: str | None = None
        if not wanted:
            self._fallback_reason = (
                "이 SQLite에는 FTS5 trigram이 없다" if not available else "사용자가 껐다"
            )
        if create:
            self._create_all()

    # ---- 연결·트랜잭션 -----------------------------------------------------------------

    def _make_engine(self) -> Engine:
        if self._memory:
            engine = create_engine(
                "sqlite://",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        else:
            engine = create_engine(
                URL.create("sqlite", database=str(Path(self.path).expanduser())),
                connect_args={"check_same_thread": False, "timeout": min(self._busy_timeout, 0.5)},
            )
        memory = self._memory

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi: sqlite3.Connection, _record: object) -> None:
            dbapi.isolation_level = None  # 트랜잭션은 begin 이벤트에서 직접 연다
            dbapi.create_function("ac_fold", 1, _fold, deterministic=True)
            cursor = dbapi.cursor()
            if not memory:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA secure_delete=ON")  # 완전 삭제한 원문을 파일에서도 덮어쓴다
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
        """`BEGIN IMMEDIATE` 트랜잭션 안에서 `fn`을 실행한다. 바쁨이면 쉬었다 다시 한다."""
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

    # ---- 표 만들기·검색 방식 -----------------------------------------------------------

    def _create_all(self) -> None:
        schema.metadata.create_all(self._engine)
        if not self._fts:
            return

        def make(conn: Connection) -> bool:
            had = conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE name = :n"), {"n": schema.SEARCH_TABLE}
            ).first()
            conn.exec_driver_sql(schema.SEARCH_TABLE_DDL)
            return had is None

        created = self._writing(make)
        if created and self._count_entries() > 0:
            self.reindex()

    def _count_entries(self) -> int:
        with self._reading() as conn:
            return int(conn.execute(select(func.count()).select_from(_E)).scalar_one())

    @property
    def search_backend(self) -> SearchBackend:
        """지금 쓰는 검색 방식."""
        return "fts5" if self._fts else "like"

    def warnings(self) -> list[Issue]:
        """서버 경고로 올릴 값.

        FTS5를 쓸 수 없어 포함 검색으로 떨어졌을 때만 한 건(`memory.search_fallback`).
        """
        if self._fts or self._fallback_reason is None:
            return []
        return [
            Issue(
                severity="warning",
                code=KnownIssueCodes.MEMORY_SEARCH_FALLBACK,
                message=(
                    "전문 검색(FTS5 trigram)을 쓰지 않고 단순 포함 검색으로 찾는다"
                    f"({self._fallback_reason})."
                ),
                details={"reason": self._fallback_reason},
            )
        ]

    def reindex(self) -> int:
        """전문 검색 색인을 항목 표에서 다시 만든다. FTS5를 쓰지 않으면 0.

        FTS5 없이 쓴 뒤 FTS5가 있는 환경에서 다시 열었을 때 쓴다(없던 색인은 열 때 자동으로 만든다).

        Returns:
            색인한 항목 수.
        """
        if not self._fts:
            return 0

        def run(conn: Connection) -> int:
            conn.exec_driver_sql(
                f"INSERT INTO {schema.SEARCH_TABLE}({schema.SEARCH_TABLE}) VALUES ('delete-all')"
            )
            done = 0
            last = 0
            while True:
                rows = conn.execute(
                    select(_E.c.rid, _E.c.key, _E.c.content, _E.c.tags)
                    .where(_E.c.rid > last)
                    .order_by(_E.c.rid)
                    .limit(1000)
                ).all()
                if not rows:
                    return done
                for rid, key, content, tags_json in rows:
                    self._fts_insert(conn, rid, key, content, json.loads(tags_json))
                last = rows[-1][0]
                done += len(rows)

        return self._writing(run)

    def close(self) -> None:
        """연결을 닫는다(이후 사용 금지)."""
        self._engine.dispose()

    def __enter__(self) -> SqliteMemoryStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---- 내부: 읽기 ---------------------------------------------------------------------

    @staticmethod
    def _load(conn: Connection, *where: ColumnElement[bool]) -> tuple[int, MemoryEntry] | None:
        row = conn.execute(select(_E).where(*where)).mappings().first()
        return None if row is None else (row["rid"], _to_entry(row))

    def _load_live(
        self, conn: Connection, scope: MemoryScopeRef, key: str
    ) -> tuple[int, MemoryEntry] | None:
        return self._load(
            conn,
            _E.c.scope_kind == scope.kind,
            _E.c.scope_id == scope.id,
            _E.c.key == key,
            _E.c.deleted_at.is_(None),
        )

    def _row(
        self, conn: Connection, entry_id: str, *, include_deleted: bool = False
    ) -> tuple[int, MemoryEntry]:
        conds = [_E.c.id == entry_id]
        if not include_deleted:
            conds.append(_E.c.deleted_at.is_(None))
        found = self._load(conn, *conds)
        if found is None:
            raise EntryNotFoundError("항목이 없다")
        return found

    @staticmethod
    def _check_version(entry: MemoryEntry, if_version: int | None) -> None:
        if if_version is not None and if_version != entry.version:
            raise VersionConflictError(
                "다른 쪽이 먼저 고쳤다", entry_id=entry.id, current_version=entry.version
            )

    @staticmethod
    def _scope_count(conn: Connection, scope: MemoryScopeRef) -> int:
        return int(
            conn.execute(
                select(func.count()).where(
                    _E.c.scope_kind == scope.kind,
                    _E.c.scope_id == scope.id,
                    _E.c.deleted_at.is_(None),
                )
            ).scalar_one()
        )

    def _check_scope_room(self, conn: Connection, scope: MemoryScopeRef) -> None:
        limit = self.policy.limits.max_entries_per_scope
        if self._scope_count(conn, scope) >= limit:
            raise TooLargeError(
                f"범위 하나에 항목은 {limit}개까지다", limit="max_entries_per_scope", value=limit
            )

    @staticmethod
    def _live_bytes(conn: Connection) -> int:
        """지우지 않은 항목의 본문 바이트 합(통계 행, 없으면 한 번 세어 만든다)."""
        row = conn.execute(select(_STATS.c.value).where(_STATS.c.name == schema.LIVE_BYTES)).first()
        if row is not None:
            return int(row[0])
        total = int(
            conn.execute(
                select(func.coalesce(func.sum(_E.c.bytes), 0)).where(_E.c.deleted_at.is_(None))
            ).scalar_one()
        )
        conn.execute(insert(_STATS).values(name=schema.LIVE_BYTES, value=total))
        return total

    def _adjust_live(self, conn: Connection, delta: int) -> None:
        """통계 행을 `delta`만큼 고친다.

        항목 행을 바꾸기 **전에** 부른다(처음이면 그때의 합을 센다).
        """
        if delta == 0:
            return
        self._live_bytes(conn)
        conn.execute(
            update(_STATS)
            .where(_STATS.c.name == schema.LIVE_BYTES)
            .values(value=_STATS.c.value + delta)
        )

    def _check_total(self, conn: Connection, delta: int) -> None:
        limit = self.policy.limits.max_total_bytes
        if delta <= 0:
            return
        if self._live_bytes(conn) + delta > limit:
            raise TooLargeError(
                f"저장소 전체 본문은 {limit}바이트까지다", limit="max_total_bytes", value=limit
            )

    # ---- 내부: 쓰기 ---------------------------------------------------------------------

    def _fts_insert(
        self, conn: Connection, rid: int, key: str, content: str, tags: Sequence[str]
    ) -> None:
        conn.execute(
            text(
                f"INSERT INTO {schema.SEARCH_TABLE}(rowid, key, content, tags) "
                "VALUES (:r, :k, :c, :t)"
            ),
            {"r": rid, **_search_values(key, content, tags)},
        )

    def _fts_delete(
        self, conn: Connection, rid: int, key: str, content: str, tags: Sequence[str]
    ) -> None:
        conn.execute(
            text(
                f"INSERT INTO {schema.SEARCH_TABLE}("
                f"{schema.SEARCH_TABLE}, rowid, key, content, tags) "
                "VALUES ('delete', :r, :k, :c, :t)"
            ),
            {"r": rid, **_search_values(key, content, tags)},
        )

    @staticmethod
    def _write_tags(
        conn: Connection, entry_id: str, old: Sequence[str], new: Sequence[str]
    ) -> None:
        gone = sorted(set(old) - set(new))
        added = sorted(set(new) - set(old))
        if gone:
            conn.execute(
                delete(_T_TAGS).where(_T_TAGS.c.entry_id == entry_id, _T_TAGS.c.tag.in_(gone))
            )
        if added:
            conn.execute(insert(_T_TAGS), [{"entry_id": entry_id, "tag": t} for t in added])

    def _record(self, conn: Connection, entry: MemoryEntry, op: MemoryVersionOp) -> None:
        conn.execute(insert(_V).values(**_version_columns(entry, op)))
        have = [
            row[0]
            for row in conn.execute(select(_V.c.version).where(_V.c.entry_id == entry.id)).all()
        ]
        stale = versions_to_drop(have, self.policy.max_versions_per_entry)
        if stale:
            conn.execute(delete(_V).where(_V.c.entry_id == entry.id, _V.c.version.in_(stale)))

    def _insert(self, conn: Connection, entry: MemoryEntry) -> None:
        self._adjust_live(conn, entry.bytes)
        result = conn.execute(
            insert(_E).values(**_entry_columns(entry), preview=self._preview_of(entry.content))
        )
        key = result.inserted_primary_key
        assert key is not None
        rid = int(key[0])
        self._write_tags(conn, entry.id, (), entry.tags)
        if self._fts:
            self._fts_insert(conn, rid, entry.key, entry.content, entry.tags)
        self._record(conn, entry, "create")

    def _save(
        self,
        conn: Connection,
        rid: int,
        old: MemoryEntry,
        new: MemoryEntry,
        op: MemoryVersionOp,
    ) -> None:
        """바뀐 열만 고치고, 태그·검색 색인·버전 기록·바이트 통계를 맞춘다."""
        self._adjust_live(conn, _live_size(new) - _live_size(old))
        before = _entry_columns(old)
        after = _entry_columns(new)
        changed = {k: after[k] for k in _MUTABLE if before[k] != after[k]}
        if old.content != new.content:
            changed["preview"] = self._preview_of(new.content)
        if changed:
            conn.execute(update(_E).where(_E.c.rid == rid).values(**changed))
        if old.tags != new.tags:
            self._write_tags(conn, new.id, old.tags, new.tags)
        if self._fts and (old.key, old.content, old.tags) != (new.key, new.content, new.tags):
            self._fts_delete(conn, rid, old.key, old.content, old.tags)
            self._fts_insert(conn, rid, new.key, new.content, new.tags)
        self._record(conn, new, op)

    def _bump(self, entry: MemoryEntry, author: MemoryAuthor, **changes: Any) -> MemoryEntry:
        return entry.model_copy(
            update={
                **changes,
                "version": entry.version + 1,
                "updated_at": self._clock(),
                "updated_by": author,
            }
        )

    def _apply_update(
        self,
        conn: Connection,
        rid: int,
        entry: MemoryEntry,
        *,
        author: MemoryAuthor,
        content: str | None,
        content_type: str | None,
        tags: Sequence[str] | None,
        pinned: bool | None,
    ) -> MemoryEntry:
        prepared = prepare_write(
            self.policy,
            entry.key,
            entry.content if content is None else content,
            entry.tags if tags is None else list(tags),
        )
        self._check_total(conn, prepared.bytes - entry.bytes)
        changes: dict[str, Any] = {
            "content": prepared.content,
            "tags": prepared.tags,
            "bytes": prepared.bytes,
            "sha256": prepared.sha256,
        }
        if content_type is not None:
            changes["content_type"] = content_type
        if pinned is not None:
            changes["pinned"] = pinned
        new = self._bump(entry, author, **changes)
        self._save(conn, rid, entry, new, "update")
        return new

    # ---- MemoryStore --------------------------------------------------------------------

    def write(
        self,
        scope: MemoryScopeRef,
        key: str,
        content: str,
        *,
        author: MemoryAuthor,
        tags: Sequence[str] | None = None,
        content_type: str | None = None,
        pinned: bool | None = None,
        if_version: int | None = None,
        mode: WriteMode = "replace",
        create_only: bool = False,
    ) -> MemoryWriteOutcome:
        """`MemoryStore.write`."""

        def run(conn: Connection) -> MemoryWriteOutcome:
            check_key(key, max_chars=self.policy.limits.max_key_chars)
            found = self._load_live(conn, scope, key)
            if found is None:
                if if_version is not None and if_version != 0:
                    raise VersionConflictError("항목이 없다", entry_id="", current_version=0)
                prepared = prepare_write(self.policy, key, content, list(tags or ()))
                self._check_scope_room(conn, scope)
                self._check_total(conn, prepared.bytes)
                at = self._clock()
                entry = MemoryEntry(
                    id=self._new_id(),
                    scope=scope,
                    key=key,
                    content=prepared.content,
                    content_type=content_type or MEMORY_DEFAULT_CONTENT_TYPE,
                    tags=prepared.tags,
                    pinned=bool(pinned),
                    version=1,
                    bytes=prepared.bytes,
                    sha256=prepared.sha256,
                    created_at=at,
                    created_by=author,
                    updated_at=at,
                    updated_by=author,
                )
                self._insert(conn, entry)
                return MemoryWriteOutcome(entry=entry, created=True)
            rid, existing = found
            if create_only:
                raise EntryExistsError("같은 키의 항목이 이미 있다", entry_id=existing.id)
            self._check_version(existing, if_version)
            new_content = _append(existing.content, content) if mode == "append" else content
            entry = self._apply_update(
                conn,
                rid,
                existing,
                author=author,
                content=new_content,
                content_type=content_type,
                tags=tags,
                pinned=pinned,
            )
            return MemoryWriteOutcome(entry=entry, created=False)

        return self._writing(run)

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry | None:
        """`MemoryStore.get`."""
        conds = [_E.c.id == entry_id]
        if not include_deleted:
            conds.append(_E.c.deleted_at.is_(None))
        with self._reading() as conn:
            found = self._load(conn, *conds)
        return None if found is None else found[1]

    def find(self, scope: MemoryScopeRef, key: str) -> MemoryEntry | None:
        """`MemoryStore.find`."""
        with self._reading() as conn:
            found = self._load_live(conn, scope, key)
        return None if found is None else found[1]

    def mark_read(self, entry_id: str) -> None:
        """`MemoryStore.mark_read`."""

        def run(conn: Connection) -> None:
            rid, _entry = self._row(conn, entry_id)
            conn.execute(update(_E).where(_E.c.rid == rid).values(last_read_at=self._clock()))

        self._writing(run)

    def update(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        content: str | None = None,
        content_type: str | None = None,
        tags: Sequence[str] | None = None,
        pinned: bool | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """`MemoryStore.update`."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id)
            self._check_version(entry, if_version)
            return self._apply_update(
                conn,
                rid,
                entry,
                author=author,
                content=content,
                content_type=content_type,
                tags=tags,
                pinned=pinned,
            )

        return self._writing(run)

    def delete(
        self, entry_id: str, *, author: MemoryAuthor, if_version: int | None = None
    ) -> MemoryEntry:
        """`MemoryStore.delete`."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id)
            self._check_version(entry, if_version)
            new = self._bump(entry, author, deleted_at=self._clock())
            self._save(conn, rid, entry, new, "delete")
            return new

        return self._writing(run)

    def purge(self, entry_id: str) -> MemoryEntry:
        """`MemoryStore.purge`(항목·버전·태그·검색 색인 행을 모두 지운다)."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id, include_deleted=True)
            self._adjust_live(conn, -_live_size(entry))
            if self._fts:
                self._fts_delete(conn, rid, entry.key, entry.content, entry.tags)
            conn.execute(delete(_T_TAGS).where(_T_TAGS.c.entry_id == entry_id))
            conn.execute(delete(_V).where(_V.c.entry_id == entry_id))
            conn.execute(delete(_E).where(_E.c.rid == rid))
            return entry

        return self._writing(run)

    def restore(
        self, entry_id: str, *, author: MemoryAuthor, version: int | None = None
    ) -> MemoryEntry:
        """`MemoryStore.restore`."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id, include_deleted=True)
            content = entry.content
            if version is not None:
                old = conn.execute(
                    select(_V.c.content).where(_V.c.entry_id == entry_id, _V.c.version == version)
                ).first()
                if old is None:
                    raise EntryNotFoundError("그 버전이 없다")
                content = old[0]
            if entry.deleted_at is not None:
                other = self._load_live(conn, entry.scope, entry.key)
                if other is not None:
                    raise EntryExistsError("같은 키의 항목이 이미 있다", entry_id=other[1].id)
                self._check_scope_room(conn, entry.scope)
            prepared = prepare_write(self.policy, entry.key, content, entry.tags)
            self._check_total(
                conn, prepared.bytes - (entry.bytes if entry.deleted_at is None else 0)
            )
            new = self._bump(
                entry,
                author,
                content=prepared.content,
                tags=prepared.tags,
                bytes=prepared.bytes,
                sha256=prepared.sha256,
                deleted_at=None,
            )
            self._save(conn, rid, entry, new, "restore")
            return new

        return self._writing(run)

    def archive(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        archived: bool = True,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """`MemoryStore.archive`."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id)
            self._check_version(entry, if_version)
            if entry.archived == archived:
                return entry
            new = self._bump(entry, author, archived=archived)
            self._save(conn, rid, entry, new, "archive" if archived else "unarchive")
            return new

        return self._writing(run)

    def move(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        to_scope: MemoryScopeRef | None = None,
        to_key: str | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """`MemoryStore.move`."""

        def run(conn: Connection) -> MemoryEntry:
            rid, entry = self._row(conn, entry_id)
            self._check_version(entry, if_version)
            scope = to_scope if to_scope is not None else entry.scope
            key = to_key if to_key else entry.key
            check_key(key, max_chars=self.policy.limits.max_key_chars)
            check_secret_field(self.policy.secrets, "key", key)
            if (scope.kind, scope.id, key) == (entry.scope.kind, entry.scope.id, entry.key):
                return entry
            other = self._load_live(conn, scope, key)
            if other is not None:
                raise EntryExistsError("옮길 곳에 같은 키의 항목이 이미 있다", entry_id=other[1].id)
            if (scope.kind, scope.id) != (entry.scope.kind, entry.scope.id):
                self._check_scope_room(conn, scope)
            new = self._bump(entry, author, scope=scope, key=key)
            self._save(conn, rid, entry, new, "move")
            return new

        return self._writing(run)

    def history(self, entry_id: str) -> list[MemoryVersionSummary]:
        """`MemoryStore.history`."""
        with self._reading() as conn:
            self._row(conn, entry_id, include_deleted=True)
            rows = (
                conn.execute(
                    select(*[c for c in _V.c if c.name != "content"])
                    .where(_V.c.entry_id == entry_id)
                    .order_by(_V.c.version)
                )
                .mappings()
                .all()
            )
        return [MemoryVersionSummary(**_version_fields(row)) for row in rows]

    def get_version(self, entry_id: str, version: int) -> MemoryVersion | None:
        """`MemoryStore.get_version`."""
        with self._reading() as conn:
            row = (
                conn.execute(select(_V).where(_V.c.entry_id == entry_id, _V.c.version == version))
                .mappings()
                .first()
            )
        return (
            None if row is None else MemoryVersion(**_version_fields(row), content=row["content"])
        )

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        """`MemoryStore.search`."""
        check_sort(query.sort, query.order)
        offset = decode_cursor(query.cursor)
        if query.scopes is not None and not query.scopes:
            return MemoryEntryPage(items=[], next_cursor=None, total=0)
        where = self._query_conditions(query)
        order = getattr(_E.c, query.sort)
        order = order.desc() if query.order == "desc" else order.asc()
        size = max(query.limit, 1)
        with self._reading() as conn:
            total = int(
                conn.execute(select(func.count()).select_from(_E).where(*where)).scalar_one()
            )
            # 먼저 순서대로 행 번호만 고른 뒤(색인만 읽음) 그 쪽의 본문만 읽는다.
            rids = [
                row[0]
                for row in conn.execute(
                    select(_E.c.rid)
                    .where(*where)
                    .order_by(order, _E.c.id.asc())
                    .limit(size)
                    .offset(offset)
                )
            ]
            by_rid = (
                {
                    row["rid"]: row
                    for row in conn.execute(
                        select(*_SUMMARY_COLUMNS).where(_E.c.rid.in_(rids))
                    ).mappings()
                }
                if rids
                else {}
            )
        end = offset + len(rids)
        return MemoryEntryPage(
            items=[self._summary(by_rid[rid]) for rid in rids],
            next_cursor=encode_cursor(end) if end < total else None,
            total=total,
        )

    def _preview_of(self, content: str) -> str:
        """목록용 미리보기: 본문 전체를 가린 뒤 앞부분을 자른다(`summarize`와 같은 규칙)."""
        return self.policy.secrets.preview(content)[: self.policy.limits.preview_chars]

    def _summary(self, row: Mapping[Any, Any]) -> MemoryEntrySummary:
        """목록 요약. 저장된 미리보기를 지금 규칙으로 한 번 더 가린다(규칙이 나중에 늘어도 안전)."""
        preview = self.policy.secrets.preview(row["preview"])[: self.policy.limits.preview_chars]
        return MemoryEntrySummary(**_entry_fields(row), preview=preview)

    def _query_conditions(self, query: MemoryQuery) -> list[ColumnElement[bool] | TextClause]:
        where: list[ColumnElement[bool] | TextClause] = []
        if not query.include_deleted:
            where.append(_E.c.deleted_at.is_(None))
        if not query.include_archived:
            where.append(_E.c.archived.is_(False))
        if query.scopes is not None:
            # 행 값 IN은 범위마다 색인으로 바로 찾아간다(OR은 색인 전체를 훑는다).
            pairs = list(dict.fromkeys((s.kind, s.id) for s in query.scopes))
            where.append(tuple_(_E.c.scope_kind, _E.c.scope_id).in_(pairs))
        for tag in dict.fromkeys(query.tags):
            where.append(exists().where(_T_TAGS.c.entry_id == _E.c.id, _T_TAGS.c.tag == tag))
        if query.author_run is not None:
            where.append(_E.c.author_run_id == query.author_run)
        if query.author_kind is not None:
            where.append(func.json_extract(_E.c.updated_by, "$.kind") == query.author_kind)
        if query.text:
            where.append(self._text_condition(query.text, scoped=query.scopes is not None))
        return where

    def _text_condition(self, raw: str, *, scoped: bool) -> ColumnElement[bool] | TextClause:
        if self._fts and len(raw) >= MIN_FTS_CHARS:
            # 범위가 있으면 `+`로 이 조건을 색인 탐색에서 빼서, 범위 색인을 먼저 타고 맞은 행 번호
            # 집합으로 거른다(맞은 행이 많을 때 행마다 본문 표를 찾아가지 않는다).
            lead = "+" if scoped else ""
            return text(
                f"{lead}{schema.ENTRIES_TABLE}.rid IN (SELECT rowid FROM {schema.SEARCH_TABLE} "
                f"WHERE {schema.SEARCH_TABLE} MATCH :m)"
            ).bindparams(m=_phrase(raw))
        needle = raw.casefold()
        return or_(
            func.instr(func.ac_fold(_E.c.key), needle) > 0,
            func.instr(func.ac_fold(_E.c.content), needle) > 0,
            exists().where(
                _T_TAGS.c.entry_id == _E.c.id, func.instr(func.ac_fold(_T_TAGS.c.tag), needle) > 0
            ),
        )

    def list_scopes(self, *, kind: str | None = None) -> list[MemoryScopeSummary]:
        """`MemoryStore.list_scopes`."""
        stmt = (
            select(
                _E.c.scope_kind,
                _E.c.scope_id,
                func.count(),
                func.sum(_E.c.archived, type_=Integer),
                func.sum(_E.c.bytes),
                func.max(_E.c.updated_at),
            )
            .where(_E.c.deleted_at.is_(None))
            .group_by(_E.c.scope_kind, _E.c.scope_id)
            .order_by(_E.c.scope_kind, _E.c.scope_id)
        )
        if kind is not None:
            stmt = stmt.where(_E.c.scope_kind == kind)
        with self._reading() as conn:
            rows = conn.execute(stmt).all()
        return [
            MemoryScopeSummary(
                scope=MemoryScopeRef(kind=k, id=s),
                entries=int(n),
                archived=int(a or 0),
                bytes=int(b or 0),
                updated_at=u,
            )
            for k, s, n, a, b, u in rows
        ]

    def scan_entries(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
        page_size: int = SCAN_PAGE_SIZE,
    ) -> Iterator[MemoryEntry]:
        """`EntryScanner`: 지우지 않은 항목을 본문까지 낸다(순서는 행 번호 `rid`).

        행 번호를 기준으로 `page_size`개씩 끊어 읽는다(쪽마다 짧은 읽기 트랜잭션이라 쓰기를 오래
        막지 않고, 오프셋이 없어 뒤쪽도 느려지지 않는다). 훑는 동안 새로 쓴 항목은 나올 수도 안
        나올 수도 있고, 같은 항목을 두 번 내지 않는다. 미리보기 가림·정렬·개수 세기를 하지 않는다.
        """
        for rows in self._scan_pages(_SCAN_COLUMNS, scopes, include_archived, page_size):
            yield from [_to_entry(row._mapping) for row in rows]

    def scan_heads(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
        page_size: int = SCAN_PAGE_SIZE,
    ) -> Iterator[EntryHead]:
        """`HeadScanner`: `scan_entries`와 같은 항목·순서를 본문 없는 머리로 낸다.

        본문·미리보기 열을 읽지 않는다(본문은 행 맨 뒤라 넘침 쪽도 읽지 않는다). 정리 계획처럼
        머리 정보(`bytes` 포함)만 판단할 때 쓴다.
        """
        for rows in self._scan_pages(_META_COLUMNS, scopes, include_archived, page_size):
            yield from [_head(row) for row in rows]

    def count_tags(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> dict[str, int]:
        """`TagCounter`: 태그 → 그 태그를 가진 지우지 않은 항목 수(`memory_tags` 색인 집계).

        항목 행은 본문을 읽지 않고 색인(`id`)으로만 맞춘다. 범위·보관 조건은 항목 쪽에서 거른다.
        """
        if scopes is not None and not scopes:
            return {}
        where: list[ColumnElement[bool]] = [
            _E.c.id == _T_TAGS.c.entry_id,
            _E.c.deleted_at.is_(None),
        ]
        if not include_archived:
            where.append(_E.c.archived.is_(False))
        if scopes is not None:
            pairs = list(dict.fromkeys((s.kind, s.id) for s in scopes))
            where.append(tuple_(_E.c.scope_kind, _E.c.scope_id).in_(pairs))
        with self._reading() as conn:
            rows = conn.execute(
                select(_T_TAGS.c.tag, func.count()).where(*where).group_by(_T_TAGS.c.tag)
            ).all()
        return {str(tag): int(count) for tag, count in rows}

    def _scan_pages(
        self,
        columns: Sequence[Any],
        scopes: Sequence[MemoryScopeRef] | None,
        include_archived: bool,
        page_size: int,
    ) -> Iterator[Sequence[Row[Any]]]:
        """지우지 않은 행을 `rid` 순서로 쪽마다 낸다(첫 열은 `rid`여야 한다)."""
        where: list[ColumnElement[bool]] = [_E.c.deleted_at.is_(None)]
        if not include_archived:
            where.append(_E.c.archived.is_(False))
        if scopes is not None:
            if not scopes:
                return
            pairs = list(dict.fromkeys((s.kind, s.id) for s in scopes))
            where.append(tuple_(_E.c.scope_kind, _E.c.scope_id).in_(pairs))
        size = max(page_size, 1)
        last = 0
        while True:
            with self._reading() as conn:
                rows = conn.execute(
                    select(*columns).where(*where, _E.c.rid > last).order_by(_E.c.rid).limit(size)
                ).all()
            if rows:
                yield rows
            if len(rows) < size:
                return
            last = rows[-1][0]

    # ---- 대량 적재(규모 측정·가져오기 도구) -------------------------------------------------

    def bulk_insert(self, entries: Iterable[MemoryEntry], *, batch: int = 1000) -> int:
        """항목을 정책 검사 없이 한꺼번에 넣는다(id·버전·시각 그대로, 버전 기록은 1건씩).

        규모 측정 도구와 가져오기가 쓴다. 같은 (범위, 키) 중복·id 중복은 호출자가 막는다.
        비밀·크기 검사는 호출자가 이미 했다고 본다.

        Returns:
            넣은 항목 수.
        """
        total = 0
        pending: list[MemoryEntry] = []

        def flush(rows: list[MemoryEntry]) -> None:
            def run(conn: Connection) -> None:
                self._adjust_live(conn, sum(_live_size(e) for e in rows))
                top = conn.execute(select(func.coalesce(func.max(_E.c.rid), 0))).scalar_one()
                values = []
                for offset, entry in enumerate(rows, start=1):
                    values.append(
                        {
                            "rid": int(top) + offset,
                            **_entry_columns(entry),
                            "preview": self._preview_of(entry.content),
                        }
                    )
                conn.execute(insert(_E), values)
                conn.execute(
                    insert(_V),
                    [_version_columns(entry, "create") for entry in rows],
                )
                tag_rows = [
                    {"entry_id": entry.id, "tag": tag}
                    for entry in rows
                    for tag in dict.fromkeys(entry.tags)
                ]
                if tag_rows:
                    conn.execute(insert(_T_TAGS), tag_rows)
                if self._fts:
                    for value in values:
                        self._fts_insert(
                            conn,
                            value["rid"],
                            value["key"],
                            value["content"],
                            json.loads(value["tags"]),
                        )

            self._writing(run)

        for entry in entries:
            pending.append(entry)
            if len(pending) >= batch:
                flush(pending)
                total += len(pending)
                pending = []
        if pending:
            flush(pending)
            total += len(pending)
        return total

    def optimize(self) -> None:
        """통계 갱신(`ANALYZE`)과 FTS5 색인 합치기. 대량 적재 뒤에 부른다."""

        def run(conn: Connection) -> None:
            conn.exec_driver_sql("ANALYZE")
            if self._fts:
                conn.exec_driver_sql(
                    f"INSERT INTO {schema.SEARCH_TABLE}({schema.SEARCH_TABLE}) VALUES ('optimize')"
                )

        self._writing(run)


def _version_fields(row: Mapping[Any, Any]) -> dict[str, Any]:
    return {
        "entry_id": row["entry_id"],
        "version": row["version"],
        "op": row["op"],
        "scope": MemoryScopeRef(kind=row["scope_kind"], id=row["scope_id"]),
        "key": row["key"],
        "bytes": row["bytes"],
        "sha256": row["sha256"],
        "author": MemoryAuthor.model_validate_json(row["author"]),
        "at": row["at"],
    }


def open_sqlite_memory_store(
    path: str | Path = ":memory:",
    *,
    policy: MemoryPolicy | None = None,
    clock: Callable[[], float] = time.time,
    new_id: Callable[[], str] | None = None,
    use_fts: bool | None = None,
    busy_timeout_seconds: float = 10.0,
    create: bool = True,
) -> SqliteMemoryStore:
    """SQLite 메모리 저장소를 연다(없는 표는 만든다).

    Args:
        path: DB 파일(``":memory:"``나 빈 문자열 = 프로세스 메모리 DB). 상위 폴더는 만든다.
        policy: 쓰기 정책(기본: 기본 한도·비밀 거부·버전 50개).
        clock: 시각(Unix epoch 초).
        new_id: 항목 id 생성기(기본 UUID4).
        use_fts: None = FTS5 trigram을 쓸 수 있으면 쓴다. False = 끄고 포함 검색만. True도
            FTS5가 없으면 포함 검색이다(``warnings()``에 사유).
        busy_timeout_seconds: 다른 쪽이 쓰기 잠금을 쥐고 있을 때 기다리는 총 시간.
        create: False면 표를 만들지 않는다(마이그레이션이 만든 DB에 붙을 때).

    Returns:
        ``SqliteMemoryStore``(``with``로 닫을 수 있다).
    """
    return SqliteMemoryStore(
        path,
        policy=policy,
        clock=clock,
        new_id=new_id,
        use_fts=use_fts,
        busy_timeout_seconds=busy_timeout_seconds,
        create=create,
    )
