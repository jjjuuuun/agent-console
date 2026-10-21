"""필터 → SQL 조건. 질의 의미는 `agent_console_logs.query`의 `event_matches`·`usage_matches`와 같다.

프로젝트 묶기는 글롭 규칙이라 SQL로 쓸 수 없다. 색인에 있는 서로 다른 (cwd, repo_root) 쌍만
순수 함수로 묶어 보고, 맞는 쌍을 조건으로 내린다(쌍 수는 이벤트 수가 아니라 작업 폴더 수다).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, FromClause
from sqlalchemy.sql.elements import ColumnElement

from agent_console_logs import query as q
from agent_console_logs._filter import LogFilter, QueryContext
from agent_console_logs._projects import UNGROUPED_PROJECT

from .schema import log_events, log_links, log_search, log_tags, log_usage

__all__ = ["error_expr", "event_clauses", "usage_clauses"]

Clause = ColumnElement[bool]

_PAIR_CHUNK = 5000
"""튜플 IN 한 번에 넣는 쌍 수(SQLite 변수 상한 32766 아래)."""


def _in(col: ColumnElement[Any], values: Sequence[str]) -> Clause:
    return col.in_(list(values))


def _project_clause(
    conn: Connection,
    table: FromClause,
    target: FromClause,
    wanted: Sequence[str],
    ctx: QueryContext,
) -> Clause:
    """`table`에 있는 쌍 중 맞는 것을 `target`(table 또는 그 별칭)의 열 조건으로 낸다."""
    pairs = conn.execute(sa.select(table.c["cwd"], table.c["repo_root"]).distinct()).all()
    cwd, root = target.c["cwd"], target.c["repo_root"]
    keep: list[tuple[str, str]] = []
    for pair_cwd, pair_root in pairs:
        pid, _label, grouped = q.project_of(pair_cwd, pair_root, ctx)
        for value in wanted:
            if (value == UNGROUPED_PROJECT and not grouped) or (pid is not None and value == pid):
                keep.append((pair_cwd, pair_root))
                break
    if not keep:
        return sa.false()
    parts = [
        sa.tuple_(cwd, root).in_(keep[i : i + _PAIR_CHUNK])
        for i in range(0, len(keep), _PAIR_CHUNK)
    ]
    return sa.or_(*parts)


def error_expr(ev: FromClause, ctx: QueryContext) -> Clause:
    """오류 이벤트 조건(태그 중 하나가 tone=danger 범주). 오류 범주가 없으면 항상 거짓."""
    cats = sorted(ctx.error_categories)
    if not cats:
        return sa.false()
    tagged = sa.select(log_tags.c.seq).where(log_tags.c.tag.in_(cats))
    return sa.or_(ev.c["category"].in_(cats), ev.c["seq"].in_(tagged))


def event_clauses(
    conn: Connection, flt: LogFilter, ctx: QueryContext, ev: FromClause
) -> list[Clause]:
    """`event_matches`와 같은 조건(커서·개수·정렬 제외). `ev`는 `log_events` 또는 그 별칭."""
    c = ev.c
    out: list[Clause] = []
    for col, wanted in (
        (c["source"], flt.source),
        (c["session"], flt.session),
        (c["cwd"], flt.cwd),
        (c["via"], flt.via),
        (c["tool"], flt.tool),
        (c["call_id"], flt.call_id),
        (c["model"], flt.model),
        (c["run_id"], flt.run_id),
        (c["stage"], flt.stage),
        (c["status"], flt.status),
    ):
        if wanted:
            out.append(_in(col, wanted))
    if flt.category:
        out.append(c["seq"].in_(sa.select(log_tags.c.seq).where(log_tags.c.tag.in_(flt.category))))
    for sides, wanted in ((None, flt.agent), (("from",), flt.from_), (("to",), flt.to)):
        if not wanted:
            continue
        sub = sa.select(log_links.c.seq).where(log_links.c.agent.in_(list(wanted)))
        if sides is not None:
            sub = sub.where(log_links.c.side.in_(sides))
        out.append(c["seq"].in_(sub))
    if flt.project:
        out.append(_project_clause(conn, log_events, ev, flt.project, ctx))
    if flt.since is not None:
        out.append(c["etime"] >= flt.since)
    if flt.until is not None:
        out.append(c["etime"] < flt.until)
    if flt.q:
        found = sa.select(sa.literal(1)).where(
            log_search.c.seq == c["seq"], sa.func.instr(log_search.c.text, flt.q.lower()) > 0
        )
        out.append(found.exists())
    return out


def usage_clauses(
    conn: Connection,
    flt: LogFilter,
    ctx: QueryContext,
    u: FromClause,
) -> list[Clause]:
    """`usage_samples`와 같은 조건(이벤트 전용 필터는 맞는 이벤트와 응답 키가 같은 표본만)."""
    c = u.c
    out: list[Clause] = []
    for col, wanted in (
        (c["source"], flt.source),
        (c["session"], flt.session),
        (c["cwd"], flt.cwd),
        (c["thread"], flt.agent),
        (c["model"], flt.model),
    ):
        if wanted:
            out.append(_in(col, wanted))
    if flt.project:
        out.append(_project_clause(conn, log_usage, u, flt.project, ctx))
    if flt.since is not None:
        out.append(c["time"] >= flt.since)
    if flt.until is not None:
        out.append(c["time"] < flt.until)
    if any(getattr(flt, name) for name in q.EVENT_ONLY_FILTERS):
        ev = log_events.alias("ue")
        matching = sa.select(sa.literal(1)).where(
            ev.c.source == c["source"],
            ev.c.thread == c["thread"],
            ev.c.message_id == c["message_id"],
            ev.c.message_id != "",
            *event_clauses(conn, flt, ctx, ev),
        )
        out.append(matching.exists())
    return out
