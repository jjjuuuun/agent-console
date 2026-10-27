"""`LogIndex`의 SQLite 구현(SQLAlchemy Core). 질의 의미는 `agent_console_logs.query`와 같다.

SQL이 후보를 좁히고 집계한다. 프로젝트 묶기·짝 소요 시간·집계 지표처럼 의미를 가진 규칙은
같은 순수 함수(또는 같은 규칙의 SQL 표현)를 쓰고, 계약 테스트 묶음이 `MemoryLogIndex`와
같음을 확인한다.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine, FromClause
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import ColumnElement

from agent_console_contracts import HandoffCount, HandoffMatrix
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogEvent,
    LogEventDetail,
    LogEventPage,
    LogLane,
    LogProjectRef,
    LogSessionSummary,
    LogTimeline,
    TokenSample,
)
from agent_console_logs import query as q
from agent_console_logs._correlate import correlation_keys
from agent_console_logs._draft import TAG_TOOL
from agent_console_logs._filter import (
    DIMENSIONS,
    METRICS,
    LogFilter,
    LogQueryError,
    QueryContext,
    parse_log_filter,
    parse_tz,
)
from agent_console_logs._index import (
    DEFAULT_MAX_EVIDENCE,
    DEFAULT_TIMELINE_LIMIT,
    BatchResult,
    IndexBatch,
    StoredCursor,
)
from agent_console_logs._purge import PurgeResult, PurgeScope
from agent_console_logs._rows import (
    LogEventRow,
    LogEventRowPage,
    PageCallback,
    complete_event_row,
)
from agent_console_logs._windows import sum_samples

from ._clauses import Clause, error_expr, event_clauses, usage_clauses
from ._clauses import load_event as _load_event
from .schema import (
    log_agents,
    log_bodies,
    log_corr,
    log_cursors,
    log_events,
    log_links,
    log_search,
    log_tags,
    log_usage,
)

__all__ = ["SqliteLogIndex"]

_CHUNK = 500
"""IN 목록 한 번에 넣는 값 수."""
_PAIR_CHUNK = 2000

_DIMENSION_IDS = tuple(d.id for d in DIMENSIONS)
_METRIC_IDS = tuple(m.id for m in METRICS)
_TOKEN_COLUMNS = {
    "tokens.input": "input",
    "tokens.output": "output",
    "tokens.cache_read": "cache_read",
    "tokens.cache_creation": "cache_creation",
    "tokens.total": "total",
}
_SEP = "\x1f"


def _with_body(e: FromClause) -> Any:
    return e.join(log_bodies, log_bodies.c.seq == e.c.seq)


def _session_title(conn: Connection, mine: Sequence[Clause], ctx: QueryContext) -> str:
    """세션 제목 순위 규칙(`ctx.session_title_rules`)대로 고른 제목.

    메모리 색인의 `query.pick_session_title`과 같은 결과다(차등 테스트).
    """
    e = log_events
    title_expr = sa.func.json_extract(log_bodies.c.body, "$.title")
    for rule in ctx.session_title_rules:
        tagged = sa.select(log_tags.c.seq).where(log_tags.c.tag == rule.tag)
        desc = rule.pick == "last"
        title = conn.scalar(
            sa.select(title_expr)
            .select_from(_with_body(e))
            .where(*mine, e.c.seq.in_(tagged), sa.func.coalesce(title_expr, "") != "")
            .order_by(*((e.c.etime.desc(), e.c.seq.desc()) if desc else (e.c.etime, e.c.seq)))
            .limit(1)
        )
        if title:
            return str(title)
    return ""


def pair_times_select(
    pairs: Sequence[tuple[str, str]],
    where: Sequence[Clause],
    starts: Sequence[str],
    ends: Sequence[str],
) -> sa.Select[Any]:
    """짝 이벤트 시각 질의: (`thread`, `call_id`) 묶음마다 세션별 첫 시작·마지막 끝 시각(`t0`·`t1`).

    목록·타임라인의 `duration_ms`가 쓴다. 조건이 (`thread`, `call_id`) 행 값 `IN`이라 색인
    `ix_log_events_thread_call`을 탄다(실행 계획 테스트로 고정, 5R.19).
    """
    e = log_events
    is_start = e.c.stage.in_(starts)
    return (
        sa.select(
            e.c.session,
            e.c.thread,
            e.c.call_id,
            sa.func.min(sa.case((is_start, e.c.time))).label("t0"),
            sa.func.max(sa.case((sa.and_(~is_start, e.c.stage.in_(ends)), e.c.time))).label("t1"),
        )
        .where(*where, e.c.call_id != "", sa.tuple_(e.c.thread, e.c.call_id).in_(pairs))
        .group_by(e.c.session, e.c.thread, e.c.call_id)
    )


def _stored_row(stored: Any, durations: dict[str, float]) -> LogEventRow:
    """저장된 행(seq·body·uid) → 목록 행(짝 소요가 있으면 `duration_ms`)."""
    row = complete_event_row(json.loads(stored.body), seq=stored.seq)
    found = durations.get(stored.uid)
    if found is not None:
        row["duration_ms"] = found
    return row


def _chunks[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _out(sample: TokenSample) -> int:
    return -1 if sample.output_tokens is None else sample.output_tokens


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _local(t: float, tz: Any) -> datetime:
    return datetime.fromtimestamp(t, tz=tz) if tz else datetime.fromtimestamp(t).astimezone()


class SqliteLogIndex:
    """SQLite 로그 색인(스레드 안전).

    Args:
        engine: SQLite 엔진. 테이블은 호출하는 쪽이 만든다(모듈은 마이그레이션 계보 `logs`,
            단독 사용은 `open_log_index`가 `create_all`).
        owns_engine: True면 `close()`가 엔진을 닫는다.
    """

    def __init__(self, engine: Engine, *, owns_engine: bool = False) -> None:
        self._engine = engine
        self._owns = owns_engine
        self._lock = threading.RLock()
        # 메모리 DB(StaticPool)는 연결 하나를 모두가 나눠 쓰므로 읽기도 직렬화한다.
        self._serial = isinstance(engine.pool, StaticPool)

    @property
    def engine(self) -> Engine:
        """쓰는 엔진."""
        return self._engine

    def close(self) -> None:
        """소유한 엔진이면 연결을 모두 닫는다."""
        if self._owns:
            self._engine.dispose()

    @contextmanager
    def _read(self) -> Iterator[Connection]:
        if self._serial:
            with self._lock, self._engine.connect() as conn:
                yield conn
        else:
            with self._engine.connect() as conn:
                yield conn

    # ---------------------------------------------------------------- 쓰기

    def write(self, batch: IndexBatch) -> BatchResult:
        with self._lock, self._engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                # 쓰기 잠금을 먼저 잡아 "있는지 확인 → 넣기"가 다른 프로세스와 섞이지 않게 한다.
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            inserted = self._write_events(conn, batch)
            self._write_usage(conn, batch)
            self._write_agents(conn, batch)
            self._write_cursors(conn, batch)
            top = conn.scalar(sa.select(sa.func.max(log_events.c.seq)))
        return BatchResult(inserted=inserted, max_seq=top)

    @staticmethod
    def _write_events(conn: Connection, batch: IndexBatch) -> int:
        unique: dict[str, LogEvent] = {}
        for record in batch.records:
            unique.setdefault(record.event.uid, record.event)
        if not unique:
            return 0
        uids = list(unique)
        have: set[str] = set()
        for part in _chunks(uids, _CHUNK):
            have.update(conn.scalars(sa.select(log_events.c.uid).where(log_events.c.uid.in_(part))))
        fresh = [unique[uid] for uid in uids if uid not in have]
        if not fresh:
            return 0
        rows = [
            {
                "uid": ev.uid,
                "source": ev.source,
                "ref": ev.ref,
                "thread": ev.thread,
                "actor": ev.actor,
                "tool": ev.tool,
                "call_id": ev.call_id,
                "stage": ev.stage,
                "category": ev.category,
                "via": ev.via,
                "status": ev.status,
                "session": ev.session,
                "cwd": ev.cwd,
                "repo_root": ev.repo_root,
                "model": ev.model,
                "run_id": ev.run_id,
                "message_id": ev.message_id,
                "time": ev.time,
                "observed_at": ev.observed_at,
                "etime": q.effective_time(ev),
            }
            for ev in fresh
        ]
        conn.execute(sqlite_insert(log_events).on_conflict_do_nothing(index_elements=["uid"]), rows)
        seqs: dict[str, int] = {}
        fresh_uids = [ev.uid for ev in fresh]
        for part in _chunks(fresh_uids, _CHUNK):
            for uid, seq in conn.execute(
                sa.select(log_events.c.uid, log_events.c.seq).where(log_events.c.uid.in_(part))
            ):
                seqs[uid] = seq
        bodies: list[dict[str, Any]] = []
        search: list[dict[str, Any]] = []
        tags: list[dict[str, Any]] = []
        links: list[dict[str, Any]] = []
        corr: list[dict[str, Any]] = []
        for ev in fresh:
            seq = seqs[ev.uid]
            heavy = (
                _dump({"detail": ev.detail, "raw": ev.raw})
                if ev.detail is not None or ev.raw is not None
                else None
            )
            body = ev.model_dump_json(
                by_alias=True, exclude={"seq", "detail", "raw"}, exclude_defaults=True
            )
            bodies.append({"seq": seq, "body": body, "heavy": heavy})
            search.append({"seq": seq, "text": q.search_text(ev).lower()})
            tags.extend({"seq": seq, "tag": t} for t in dict.fromkeys([ev.category, *ev.tags]))
            links.extend(_links(seq, ev))
            corr.extend(
                {"seq": seq, "basis": b, "value": v} for b, v in dict.fromkeys(correlation_keys(ev))
            )
        conn.execute(sqlite_insert(log_bodies).on_conflict_do_nothing(), bodies)
        conn.execute(sqlite_insert(log_search).on_conflict_do_nothing(), search)
        conn.execute(sqlite_insert(log_tags).on_conflict_do_nothing(), tags)
        if links:
            conn.execute(sqlite_insert(log_links).on_conflict_do_nothing(), links)
        if corr:
            conn.execute(sqlite_insert(log_corr).on_conflict_do_nothing(), corr)
        return len(fresh)

    @staticmethod
    def _write_usage(conn: Connection, batch: IndexBatch) -> None:
        rows = []
        for record in batch.records:
            sample, ev = record.usage, record.event
            if sample is None:
                continue
            rows.append(
                {
                    "source": ev.source,
                    "thread": sample.thread,
                    "message_id": sample.message_id,
                    "session": ev.session,
                    "cwd": ev.cwd,
                    "repo_root": ev.repo_root,
                    "model": sample.model,
                    "time": sample.time,
                    "input_tokens": sample.input_tokens,
                    "cache_creation_input_tokens": sample.cache_creation_input_tokens,
                    "cache_read_input_tokens": sample.cache_read_input_tokens,
                    "output_tokens": sample.output_tokens,
                }
            )
        if not rows:
            return
        stmt = sqlite_insert(log_usage)
        keys = ("source", "thread", "message_id")
        stmt = stmt.on_conflict_do_update(
            index_elements=list(keys),
            set_={k: stmt.excluded[k] for k in rows[0] if k not in keys},
            # 같은 응답이 다시 오면 output이 크거나 같을 때만 바꾼다(F-8, 값 없음 = -1).
            where=sa.func.coalesce(stmt.excluded.output_tokens, -1)
            >= sa.func.coalesce(log_usage.c.output_tokens, -1),
        )
        conn.execute(stmt, rows)

    @staticmethod
    def _write_agents(conn: Connection, batch: IndexBatch) -> None:
        rows = [
            {
                "id": r.agent.id,
                "label": r.agent.label,
                "parent_id": r.agent.parent_id,
                "source": r.event.source,
            }
            for r in batch.records
            if r.agent is not None
        ]
        if not rows:
            return
        stmt = sqlite_insert(log_agents)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "label": sa.func.coalesce(stmt.excluded.label, log_agents.c.label),
                "parent_id": sa.func.coalesce(stmt.excluded.parent_id, log_agents.c.parent_id),
            },
        )
        conn.execute(stmt, rows)

    @staticmethod
    def _write_cursors(conn: Connection, batch: IndexBatch) -> None:
        rows = [
            {
                "source": c.source,
                "ref": c.ref,
                "offset": c.offset,
                "size": c.size,
                "mtime": c.mtime,
                "state": _dump(dict(c.state)),
                "updated_at": c.updated_at,
            }
            for c in batch.cursors
        ]
        if not rows:
            return
        stmt = sqlite_insert(log_cursors)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "ref"],
            set_={k: stmt.excluded[k] for k in rows[0] if k not in ("source", "ref")},
        )
        conn.execute(stmt, rows)

    def get_cursor(self, source: str, ref: str) -> StoredCursor | None:
        with self._read() as conn:
            row = conn.execute(
                sa.select(log_cursors).where(
                    log_cursors.c.source == source, log_cursors.c.ref == ref
                )
            ).first()
        return _cursor(row) if row is not None else None

    def list_cursors(self, source: str) -> list[StoredCursor]:
        with self._read() as conn:
            rows = conn.execute(
                sa.select(log_cursors)
                .where(log_cursors.c.source == source)
                .order_by(log_cursors.c.ref)
            ).all()
        return [_cursor(r) for r in rows]

    def max_seq(self) -> int | None:
        with self._read() as conn:
            top: int | None = conn.scalar(sa.select(sa.func.max(log_events.c.seq)))
        return top

    def prune(self, before: float) -> int:
        with self._lock, self._engine.begin() as conn:
            old = sa.select(log_events.c.seq).where(log_events.c.etime < before)
            for table in (log_tags, log_links, log_corr, log_bodies, log_search):
                conn.execute(sa.delete(table).where(table.c.seq.in_(old)))
            result = conn.execute(sa.delete(log_events).where(log_events.c.etime < before))
            conn.execute(
                sa.delete(log_usage).where(log_usage.c.time.is_not(None), log_usage.c.time < before)
            )
            return result.rowcount

    def purge(self, scope: PurgeScope, *, dry_run: bool) -> PurgeResult:
        """범위의 행을 지운다(규칙은 `agent_console_logs.PurgeableLogIndex`, 한 트랜잭션)."""

        def hit(e: FromClause) -> ColumnElement[bool]:
            parts: list[ColumnElement[bool]] = []
            if scope.sources is not None:
                parts.append(e.c.source.in_(scope.sources))
            if scope.categories is not None:
                parts.append(e.c.category.in_(scope.categories))
            if scope.before is not None:
                parts.append(e.c.etime < scope.before)
            return sa.and_(sa.true(), *parts)

        u = log_usage
        gone_e = log_events.alias("gone_e")
        kept_e = log_events.alias("kept_e")

        def same_key(e: FromClause) -> ColumnElement[bool]:
            return sa.and_(
                e.c.message_id != "",
                e.c.source == u.c.source,
                e.c.thread == u.c.thread,
                e.c.message_id == u.c.message_id,
            )

        usage_cond: ColumnElement[bool] = sa.and_(
            sa.exists().where(same_key(gone_e), hit(gone_e)),
            ~sa.exists().where(same_key(kept_e), ~hit(kept_e)),
        )
        if scope.categories is None:
            own: list[ColumnElement[bool]] = []
            if scope.sources is not None:
                own.append(u.c.source.in_(scope.sources))
            if scope.before is not None:
                own.append(sa.and_(u.c.time.is_not(None), u.c.time < scope.before))
            usage_cond = sa.or_(usage_cond, sa.and_(sa.true(), *own))
        cursor_cond: ColumnElement[bool] | None = None
        if scope.rescan:
            cursor_cond = (
                log_cursors.c.source.in_(scope.sources) if scope.sources is not None else sa.true()
            )
        agent_cond: ColumnElement[bool] | None = None
        if scope.whole_sources:
            agent_cond = (
                log_agents.c.source.in_(scope.sources) if scope.sources is not None else sa.true()
            )

        def count(conn: Connection, table: Any, cond: ColumnElement[bool] | None) -> int:
            if cond is None:
                return 0
            return int(conn.scalar(sa.select(sa.func.count()).select_from(table).where(cond)) or 0)

        with self._lock, self._engine.begin() as conn:
            if not dry_run and conn.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            result = PurgeResult(
                dry_run=dry_run,
                events=count(conn, log_events, hit(log_events)),
                usage=count(conn, u, usage_cond),
                cursors=count(conn, log_cursors, cursor_cond),
                agents=count(conn, log_agents, agent_cond),
            )
            if dry_run:
                return result
            # 표본 조건이 이벤트를 보므로 표본부터 지운다.
            if result.usage:
                conn.execute(sa.delete(u).where(usage_cond))
            if result.events:
                old = sa.select(log_events.c.seq).where(hit(log_events))
                for table in (log_tags, log_links, log_corr, log_bodies, log_search):
                    conn.execute(sa.delete(table).where(table.c.seq.in_(old)))
                conn.execute(sa.delete(log_events).where(hit(log_events)))
            if cursor_cond is not None and result.cursors:
                conn.execute(sa.delete(log_cursors).where(cursor_cond))
            if agent_cond is not None and result.agents:
                conn.execute(sa.delete(log_agents).where(agent_cond))
            return result

    # ---------------------------------------------------------------- 목록·상세

    def _page_rows(
        self,
        conn: Connection,
        flt: LogFilter,
        ctx: QueryContext,
        *,
        with_total: bool,
        pair_columns: bool = False,
    ) -> tuple[Sequence[Any], bool, int | None]:
        """목록 쪽의 (seq, body) 행(`limit`개까지), 더 있는지, 전체 수.

        `pair_columns`면 짝 계산 열(uid·세션·thread·call_id·단계)도 읽는다(본문을 풀지 않고 짝을
        찾을 때). 기본은 읽지 않는다 — 색인만으로 후보를 고르는 질의가 표를 더 읽지 않게.
        """
        e = log_events
        where = event_clauses(conn, flt, ctx, e)
        total = (
            conn.scalar(sa.select(sa.func.count()).select_from(e).where(*where))
            if with_total
            else None
        )
        columns: list[Any] = [e.c.seq, log_bodies.c.body]
        if pair_columns:
            columns += [e.c.uid, e.c.session, e.c.thread, e.c.call_id, e.c.stage]
        stmt = (
            sa.select(*columns)
            .select_from(e.join(log_bodies, log_bodies.c.seq == e.c.seq))
            .where(*where)
        )
        if flt.cursor is not None:
            c = int(flt.cursor)
            stmt = stmt.where(e.c.seq > c if flt.order == "asc" else e.c.seq < c)
        stmt = stmt.order_by(e.c.seq.asc() if flt.order == "asc" else e.c.seq.desc())
        rows = conn.execute(stmt.limit(flt.limit + 1)).all()
        return rows[: flt.limit], len(rows) > flt.limit, total

    def query_events(
        self, flt: LogFilter, ctx: QueryContext, *, with_total: bool = False
    ) -> LogEventPage:
        with self._read() as conn:
            rows, more, total = self._page_rows(conn, flt, ctx, with_total=with_total)
            items = [_load_event(r.seq, r.body) for r in rows]
            durations = self._pair_durations(conn, items, [], ctx)
        return LogEventPage(
            items=[
                ev.model_copy(update={"duration_ms": durations[ev.uid]})
                if ev.uid in durations  # 짝이 없는 이벤트는 복사하지 않는다(큰 범위 읽기 비용)
                else ev
                for ev in items
            ],
            total=total,
            next_cursor=str(items[-1].seq) if more and items else None,
        )

    def _raw_page(
        self, flt: LogFilter, ctx: QueryContext
    ) -> tuple[Sequence[Any], str | None, dict[str, float]]:
        """행 읽기용 쪽: 저장된 행(본문 문자열 그대로), 다음 커서, 짝 소요(uid → ms).

        짝은 색인 열(세션·thread·call_id·단계)로 찾으므로 본문을 풀지 않는다.
        """
        with self._read() as conn:
            rows, more, _total = self._page_rows(
                conn, flt, ctx, with_total=False, pair_columns=True
            )
            durations = self._pair_durations(conn, rows, [], ctx)
        return rows, (str(rows[-1].seq) if more and rows else None), durations

    def query_event_rows(self, flt: LogFilter, ctx: QueryContext) -> LogEventRowPage:
        """`query_events`와 같은 쪽을 모델 없이 행으로(선택 능력 `LogEventRowReader`).

        저장된 본문 JSON에 기본값을 채운다(`complete_event_row`) — 검증·덤프를 건너뛴다.
        """
        rows, next_cursor, durations = self._raw_page(flt, ctx)
        return LogEventRowPage(
            rows=[_stored_row(r, durations) for r in rows], next_cursor=next_cursor
        )

    def iter_event_rows(
        self, flt: LogFilter, ctx: QueryContext, *, on_page: PageCallback | None = None
    ) -> Iterator[LogEventRow]:
        """`flt.cursor`부터 끝까지 행. 쪽마다 본문 문자열만 읽어 두고 행은 하나씩 만든다(한 쪽의
        행 dict를 한꺼번에 들고 있지 않는다 — 큰 범위에서 메모리·GC 부담이 적다). 연결은 쪽을
        읽는 동안만 쓴다."""
        cursor = flt.cursor
        while True:
            rows, next_cursor, durations = self._raw_page(flt.with_(cursor=cursor), ctx)
            if on_page is not None:
                on_page(len(rows))
            for r in rows:
                yield _stored_row(r, durations)
            if next_cursor is None or not rows:
                return
            cursor = next_cursor

    def get_event(
        self,
        uid: str,
        ctx: QueryContext,
        *,
        max_detail_bytes: int | None = None,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
    ) -> LogEventDetail | None:
        e = log_events
        with self._read() as conn:
            row = conn.execute(
                sa.select(e.c.seq, log_bodies.c.body, log_bodies.c.heavy)
                .select_from(_with_body(e))
                .where(e.c.uid == uid)
            ).first()
            if row is None:
                return None
            event = _load_event(row.seq, row.body, row.heavy)
            sample = self._usage_of(conn, event)
            related = self._related(conn, event)
            candidates = self._candidates(conn, event, max_evidence + 1)
        return q.event_detail(
            event,
            related=related,
            candidates=candidates,
            usage=sample,
            max_detail_bytes=max_detail_bytes,
            max_evidence=max_evidence,
        )

    @staticmethod
    def _usage_of(conn: Connection, event: LogEvent) -> TokenSample | None:
        if not event.message_id:
            return None
        u = log_usage
        row = conn.execute(
            sa.select(u).where(
                u.c.source == event.source,
                u.c.thread == event.thread,
                u.c.message_id == event.message_id,
            )
        ).first()
        return _sample(row) if row is not None else None

    @staticmethod
    def _related(conn: Connection, event: LogEvent) -> list[LogEvent]:
        e = log_events
        same: list[ColumnElement[bool]] = []
        if event.call_id:
            same.append(e.c.call_id == event.call_id)
        if event.message_id:
            same.append(e.c.message_id == event.message_id)
        if not same:
            return []
        rows = conn.execute(
            sa.select(e.c.seq, log_bodies.c.body)
            .select_from(_with_body(e))
            .where(e.c.thread == event.thread, e.c.uid != event.uid, sa.or_(*same))
            .order_by(e.c.seq)
        ).all()
        return [_load_event(r.seq, r.body) for r in rows]

    @staticmethod
    def _candidates(conn: Connection, event: LogEvent, limit: int) -> list[LogEvent]:
        keys = list(dict.fromkeys(correlation_keys(event)))
        if not keys:
            return []
        e = log_events
        shared = sa.select(log_corr.c.seq).where(
            sa.tuple_(log_corr.c.basis, log_corr.c.value).in_(keys)
        )
        rows = conn.execute(
            sa.select(e.c.seq, log_bodies.c.body)
            .select_from(_with_body(e))
            .where(e.c.seq.in_(shared))
            .order_by(e.c.seq)
            .limit(limit)
        ).all()
        return [_load_event(r.seq, r.body) for r in rows]

    # ---------------------------------------------------------------- 세션·타임라인

    def list_sessions(self, flt: LogFilter, ctx: QueryContext) -> list[LogSessionSummary]:
        with self._read() as conn:
            return self._summaries(conn, flt, ctx, flt.limit)

    def _summaries(
        self, conn: Connection, flt: LogFilter, ctx: QueryContext, limit: int
    ) -> list[LogSessionSummary]:
        e = log_events
        where = [e.c.session != "", *event_clauses(conn, flt, ctx, e)]
        errors = sa.func.sum(sa.case((error_expr(e, ctx), 1), else_=0))
        last = sa.func.max(e.c.time)
        rows = conn.execute(
            sa.select(
                e.c.session,
                sa.func.count().label("n"),
                sa.func.min(e.c.time).label("first"),
                last.label("last"),
                errors.label("errors"),
                sa.func.count(sa.distinct(sa.func.nullif(e.c.thread, ""))).label("threads"),
                sa.func.json_group_array(sa.distinct(e.c.source)).label("sources"),
                sa.func.json_group_array(sa.distinct(sa.case((e.c.model != "", e.c.model)))).label(
                    "models"
                ),
            )
            .where(*where)
            .group_by(e.c.session)
            .order_by(sa.func.coalesce(last, 0.0).desc(), e.c.session)
            .limit(limit)
        ).all()
        if not rows:
            return []
        sessions = [r.session for r in rows]
        totals = self._session_tokens(conn, flt, ctx, sessions)
        out = []
        for r in rows:
            cwd, repo_root, title = self._session_head(conn, r.session, ctx)
            pid, label, _grouped = q.project_of(cwd, repo_root, ctx)
            out.append(
                LogSessionSummary(
                    session=r.session,
                    sources=sorted(json.loads(r.sources)),
                    title=title,
                    cwd=cwd,
                    repo_root=repo_root,
                    project=LogProjectRef(id=pid, label=label) if pid else None,
                    first_time=r.first,
                    last_time=r.last,
                    events=r.n,
                    errors=int(r.errors or 0),
                    thread_count=r.threads,
                    models=sorted(m for m in json.loads(r.models) if m),
                    tokens=totals.get(r.session),
                )
            )
        return out

    @staticmethod
    def _session_head(conn: Connection, session: str, ctx: QueryContext) -> tuple[str, str, str]:
        """세션의 첫 cwd·repo_root·제목. 세션 id 조건만 쓴다.

        목록 필터는 어느 세션이 보일지만 정한다. 제목 행(`ai-title`·`custom-title`)에는 cwd·actor가
        없어서 필터 조건을 붙이면 제목이 첫 입력으로 바뀐다(5.2R.38).
        """
        e = log_events
        order = (e.c.etime, e.c.seq)
        mine = [e.c.session == session]
        cwd = conn.scalar(sa.select(e.c.cwd).where(*mine, e.c.cwd != "").order_by(*order).limit(1))
        cwd = cwd or ""
        root = conn.scalar(
            sa.select(e.c.repo_root)
            .where(*mine, e.c.cwd == cwd, e.c.repo_root != "")
            .order_by(*order)
            .limit(1)
        )
        return cwd, root or "", _session_title(conn, mine, ctx)

    @staticmethod
    def _session_tokens(
        conn: Connection, flt: LogFilter, ctx: QueryContext, sessions: Sequence[str]
    ) -> dict[str, Any]:
        u = log_usage
        rows = conn.execute(
            sa.select(
                u.c.session,
                sa.func.sum(u.c.input_tokens).label("i"),
                sa.func.sum(u.c.output_tokens).label("o"),
                sa.func.sum(u.c.cache_read_input_tokens).label("cr"),
                sa.func.sum(u.c.cache_creation_input_tokens).label("cc"),
            )
            .where(u.c.session.in_(list(sessions)), *usage_clauses(conn, flt, ctx, u))
            .group_by(u.c.session)
        ).all()
        out: dict[str, Any] = {}
        for r in rows:
            totals = _totals(r.i, r.o, r.cr, r.cc)
            if totals is not None:
                out[r.session] = totals
        return out

    def timeline(
        self,
        session: str,
        ctx: QueryContext,
        *,
        flt: LogFilter | None = None,
        limit: int = DEFAULT_TIMELINE_LIMIT,
    ) -> LogTimeline | None:
        base = (flt or LogFilter()).with_(session=(session,), limit=1)
        e = log_events
        with self._read() as conn:
            summaries = self._summaries(conn, base, ctx, 1)
            if not summaries:
                return None
            where = event_clauses(conn, base, ctx, e)
            if ctx.hidden_categories:
                where.append(e.c.category.not_in(sorted(ctx.hidden_categories)))
            total = conn.scalar(sa.select(sa.func.count()).select_from(e).where(*where)) or 0
            rows = conn.execute(
                sa.select(e.c.seq, log_bodies.c.body)
                .select_from(_with_body(e))
                .where(*where)
                .order_by(e.c.etime, e.c.seq)
                .limit(limit)
            ).all()
            shown = [_load_event(r.seq, r.body) for r in rows]
            durations = self._pair_durations(conn, shown, where, ctx)
            agents = {
                r.id: LogLane(id=r.id, label=r.label, parent_id=r.parent_id)
                for r in conn.execute(sa.select(log_agents))
            }
        lanes = [
            agents.get(tid) or LogLane(id=tid)
            for tid in dict.fromkeys(ev.thread for ev in shown if ev.thread)
        ]
        return LogTimeline(
            session=summaries[0],
            lanes=lanes,
            events=[ev.model_copy(update={"duration_ms": durations.get(ev.uid)}) for ev in shown],
            total=total,
            truncated=total > limit,
        )

    @staticmethod
    def _pair_durations(
        conn: Connection,
        shown: Sequence[Any],
        where: Sequence[Clause],
        ctx: QueryContext,
    ) -> dict[str, float]:
        """`shown` 중 짝 이벤트(같은 세션·thread·`call_id`의 시작·끝 단계)의 소요 시간(ms).

        짝 후보는 `where`에 맞는 행에서 찾는다(목록은 빈 `where` — 필터와 상관없이 짝을 찾는다).
        """
        starts, ends = sorted(ctx.pair_start_stages), sorted(ctx.pair_end_stages)
        keys = {
            (ev.session, ev.thread, ev.call_id)
            for ev in shown
            if ev.call_id and (ev.stage in starts or ev.stage in ends)
        }
        pairs = list(dict.fromkeys((thread, call_id) for _, thread, call_id in keys))
        found: dict[tuple[str, str, str], float] = {}
        for part in _chunks(pairs, _PAIR_CHUNK):
            for r in conn.execute(pair_times_select(part, where, starts, ends)):
                key = (r.session, r.thread, r.call_id)
                if key not in keys or r.t0 is None or r.t1 is None:
                    continue
                duration = (r.t1 - r.t0) * 1000.0
                if duration >= 0:
                    found[key] = duration
        return {
            ev.uid: found[(ev.session, ev.thread, ev.call_id)]
            for ev in shown
            if (ev.session, ev.thread, ev.call_id) in found
            and (ev.stage in starts or ev.stage in ends)
        }

    # ---------------------------------------------------------------- 집계

    def aggregate(self, request: LogAggregateRequest, ctx: QueryContext) -> list[LogAggregateRow]:
        for i, dim in enumerate(request.group_by):
            if dim not in _DIMENSION_IDS:
                raise LogQueryError(f"모르는 차원: {dim}", f"group_by.{i}")
        if request.metric not in _METRIC_IDS:
            raise LogQueryError(f"모르는 지표: {request.metric}", "metric")
        flt = parse_log_filter(request.filter, path="filter", extra=ctx.extra_names)
        if request.tz:
            ctx = replace(ctx, tz=parse_tz(request.tz))
        dims = list(request.group_by)
        with self._read() as conn:
            _register_functions(conn, ctx)
            if request.metric in _TOKEN_COLUMNS:
                values = self._token_values(conn, dims, request.metric, flt, ctx)
            elif request.metric.startswith("duration_ms."):
                values = self._duration_values(conn, dims, request.metric, flt, ctx)
            else:
                values = self._count_values(conn, dims, request.metric, flt, ctx)
        rows = [
            LogAggregateRow(keys=dict(zip(dims, k, strict=True)), value=v)
            for k, v in values.items()
        ]
        rows.sort(key=lambda r: tuple((v is None, v or "") for v in r.keys.values()))
        return rows

    @staticmethod
    def _event_dims(dims: Sequence[str], e: FromClause) -> list[ColumnElement[Any]]:
        out: list[ColumnElement[Any]] = []
        for dim in dims:
            if dim == "project":
                col: ColumnElement[Any] = sa.func.ac_project(e.c.cwd, e.c.repo_root)
            elif dim == "agent":
                col = sa.func.nullif(
                    sa.func.coalesce(sa.func.nullif(e.c.thread, ""), e.c.actor), ""
                )
            elif dim == "day":
                col = sa.func.ac_day(e.c.etime)
            elif dim == "hour":
                col = sa.func.ac_hour(e.c.etime)
            elif dim == "tag":
                col = log_tags.c.tag
            else:
                col = sa.func.nullif(e.c[dim], "")
            out.append(col)
        return out

    def _count_values(
        self, conn: Connection, dims: Sequence[str], metric: str, flt: LogFilter, ctx: QueryContext
    ) -> dict[tuple[str | None, ...], float | None]:
        e = log_events
        where = event_clauses(conn, flt, ctx, e)
        if metric == "errors":
            where.append(error_expr(e, ctx))
        if metric == "tool_calls":
            where.append(e.c.seq.in_(sa.select(log_tags.c.seq).where(log_tags.c.tag == TAG_TOOL)))
        if metric == "tool_calls":
            value: ColumnElement[Any] = sa.func.count(
                sa.distinct(sa.case((e.c.call_id != "", e.c.thread + _SEP + e.c.call_id)))
            ) + sa.func.count(sa.case((e.c.call_id == "", 1)))
        else:
            value = sa.func.count()
        keys = [d.label(f"k{i}") for i, d in enumerate(self._event_dims(dims, e))]
        source: Any = e
        if "tag" in dims:
            source = e.outerjoin(log_tags, log_tags.c.seq == e.c.seq)
        stmt = sa.select(*keys, value.label("v")).select_from(source).where(*where)
        if keys:
            stmt = stmt.group_by(*[sa.literal_column(f"k{i}") for i in range(len(keys))])
        else:
            stmt = stmt.having(sa.func.count() > 0)
        return {tuple(r[:-1]): float(r[-1]) for r in conn.execute(stmt)}

    def _duration_values(
        self, conn: Connection, dims: Sequence[str], metric: str, flt: LogFilter, ctx: QueryContext
    ) -> dict[tuple[str | None, ...], float | None]:
        e = log_events
        starts, ends = sorted(ctx.pair_start_stages), sorted(ctx.pair_end_stages)
        is_start = e.c.stage.in_(starts)
        where = event_clauses(conn, flt, ctx, e)
        pairs = (
            sa.select(
                e.c.thread,
                e.c.call_id,
                sa.func.min(sa.case((is_start, e.c.time))).label("t0"),
                sa.func.max(sa.case((sa.and_(~is_start, e.c.stage.in_(ends)), e.c.time))).label(
                    "t1"
                ),
            )
            .where(*where, e.c.call_id != "")
            .group_by(e.c.thread, e.c.call_id)
            .cte("pairs")
        )
        ev = log_events.alias("d")
        keys = [d.label(f"k{i}") for i, d in enumerate(self._event_dims(dims, ev))]
        source: Any = ev.join(
            pairs, sa.and_(pairs.c.thread == ev.c.thread, pairs.c.call_id == ev.c.call_id)
        )
        if "tag" in dims:
            source = source.outerjoin(log_tags, log_tags.c.seq == ev.c.seq)
        stmt = (
            sa.select(*keys, ((pairs.c.t1 - pairs.c.t0) * 1000.0).label("v"))
            .select_from(source)
            .where(
                *event_clauses(conn, flt, ctx, ev),
                ev.c.stage.in_(ends),
                pairs.c.t0.is_not(None),
                pairs.c.t1.is_not(None),
                pairs.c.t1 >= pairs.c.t0,
            )
        )
        buckets: dict[tuple[str | None, ...], list[float]] = {}
        for r in conn.execute(stmt):
            buckets.setdefault(tuple(r[:-1]), []).append(float(r[-1]))
        kind = metric.split(".", 1)[1]
        return {
            k: (sum(ds) if kind == "sum" else sum(ds) / len(ds) if kind == "avg" else _p95(ds))
            for k, ds in buckets.items()
        }

    def _token_values(
        self, conn: Connection, dims: Sequence[str], metric: str, flt: LogFilter, ctx: QueryContext
    ) -> dict[tuple[str | None, ...], float | None]:
        u = log_usage
        keys: list[ColumnElement[Any]] = []
        for i, dim in enumerate(dims):
            if dim == "project":
                col: ColumnElement[Any] = sa.func.ac_project(u.c.cwd, u.c.repo_root)
            elif dim == "agent":
                col = sa.func.nullif(u.c.thread, "")
            elif dim == "day":
                col = sa.func.ac_day(u.c.time)
            elif dim == "hour":
                col = sa.func.ac_hour(u.c.time)
            elif dim in ("cwd", "session", "model", "source"):
                col = sa.func.nullif(u.c[dim], "")
            else:  # category·tool·tag는 표본에 없다
                col = sa.null()
            keys.append(col.label(f"k{i}"))
        stmt = sa.select(
            *keys,
            sa.func.sum(u.c.input_tokens),
            sa.func.sum(u.c.output_tokens),
            sa.func.sum(u.c.cache_read_input_tokens),
            sa.func.sum(u.c.cache_creation_input_tokens),
        ).where(*usage_clauses(conn, flt, ctx, u))
        if keys:
            stmt = stmt.group_by(*[sa.literal_column(f"k{i}") for i in range(len(keys))])
        else:
            stmt = stmt.having(sa.func.count() > 0)
        field = _TOKEN_COLUMNS[metric]
        out: dict[tuple[str | None, ...], float | None] = {}
        for r in conn.execute(stmt):
            totals = _totals(*r[len(keys) :], keep_empty=True)
            v = getattr(totals, field) if totals is not None else None
            out[tuple(r[: len(keys)])] = float(v) if v is not None else None
        return out

    # ---------------------------------------------------------------- handoff·토큰 표본

    def handoffs(self, flt: LogFilter, ctx: QueryContext, *, limit: int = 40) -> HandoffMatrix:
        e = log_events
        f, t = log_links.alias("lf"), log_links.alias("lt")
        with self._read() as conn:
            where = [
                *event_clauses(conn, flt, ctx, e),
                e.c.seq.in_(sa.select(log_links.c.seq).where(log_links.c.side == "from")),
                e.c.seq.in_(sa.select(log_links.c.seq).where(log_links.c.side == "to")),
            ]
            rows = conn.execute(
                sa.select(f.c.agent.label("src"), t.c.agent.label("dst"), e.c.via, sa.func.count())
                .select_from(e)
                .join(f, sa.and_(f.c.seq == e.c.seq, f.c.side == "from"))
                .join(t, sa.and_(t.c.seq == e.c.seq, t.c.side == "to"))
                .where(*where)
                .group_by(f.c.agent, t.c.agent, e.c.via)
                .order_by(sa.func.count().desc(), f.c.agent, t.c.agent, e.c.via)
                .limit(limit)
            ).all()
            runs = conn.scalar(sa.select(sa.func.count(sa.distinct(e.c.session))).where(*where))
        cells = [
            HandoffCount.model_validate(
                {"from": r[0], "to": r[1], "via": r[2] or None, "count": r[3]}
            )
            for r in rows
        ]
        return HandoffMatrix(cells=cells, runs=runs or 0)

    def token_samples(self, flt: LogFilter, ctx: QueryContext) -> list[TokenSample]:
        u = log_usage
        with self._read() as conn:
            rows = conn.execute(
                sa.select(u)
                .where(*usage_clauses(conn, flt, ctx, u))
                .order_by(sa.func.coalesce(u.c.time, 0.0), u.c.source, u.c.thread, u.c.message_id)
            ).all()
        return [_sample(r) for r in rows]

    def lanes(self) -> list[LogLane]:
        with self._read() as conn:
            rows = conn.execute(sa.select(log_agents).order_by(log_agents.c.id)).all()
        return [LogLane(id=r.id, label=r.label, parent_id=r.parent_id) for r in rows]


# ---------------------------------------------------------------- 도우미


def _links(seq: int, ev: LogEvent) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if ev.actor:
        out.append({"seq": seq, "agent": ev.actor, "side": "actor"})
    out.extend({"seq": seq, "agent": a, "side": "from"} for a in dict.fromkeys(ev.from_) if a)
    out.extend({"seq": seq, "agent": a, "side": "to"} for a in dict.fromkeys(ev.to) if a)
    return out


def _cursor(row: Any) -> StoredCursor:
    state = json.loads(row.state) if row.state else {}
    return StoredCursor(
        source=row.source,
        ref=row.ref,
        offset=row.offset,
        size=row.size,
        mtime=row.mtime,
        state=state,
        updated_at=row.updated_at,
    )


def _sample(row: Any) -> TokenSample:
    return TokenSample(
        thread=row.thread,
        message_id=row.message_id,
        model=row.model,
        time=row.time,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cache_read_input_tokens=row.cache_read_input_tokens,
        cache_creation_input_tokens=row.cache_creation_input_tokens,
    )


def _totals(
    inp: int | None,
    out: int | None,
    cache_read: int | None,
    cache_creation: int | None,
    *,
    keep_empty: bool = False,
) -> Any:
    """SQL 합 → `LogTokenTotals`(값이 하나도 없으면 None). `sum_samples`와 같은 규칙."""
    totals = sum_samples(
        [
            TokenSample(
                input_tokens=inp,
                output_tokens=out,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_creation,
            )
        ]
    )
    return totals if totals.total is not None or keep_empty else None


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def _register_functions(conn: Connection, ctx: QueryContext) -> None:
    """집계에 쓰는 SQL 함수를 이 연결에만 등록한다(시간대·프로젝트 규칙이 질의마다 다르다)."""
    raw = conn.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection):
        return
    projects: dict[tuple[str, str], str | None] = {}

    def project(cwd: str, repo_root: str) -> str | None:
        key = (cwd, repo_root)
        if key not in projects:
            projects[key] = q.project_of(cwd, repo_root, ctx)[0]
        return projects[key]

    def day(t: float | None) -> str | None:
        return None if t is None else _local(t, ctx.tz).strftime("%Y-%m-%d")

    def hour(t: float | None) -> str | None:
        return None if t is None else _local(t, ctx.tz).strftime("%Y-%m-%dT%H")

    raw.create_function("ac_project", 2, project, deterministic=True)
    raw.create_function("ac_day", 1, day, deterministic=True)
    raw.create_function("ac_hour", 1, hour, deterministic=True)
