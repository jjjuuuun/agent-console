"""필터 → SQL 조건. 질의 의미는 `agent_console_logs.query`의 `event_matches`·`usage_matches`와 같다.

프로젝트 묶기는 글롭 규칙이라 SQL로 쓸 수 없다. 색인에 있는 서로 다른 (cwd, repo_root) 쌍만
순수 함수로 묶어 보고, 맞는 쌍을 조건으로 내린다(쌍 수는 이벤트 수가 아니라 작업 폴더 수다).

확장 판정 함수(`ctx.predicates`, X28)는 SQL로 쓸 수 없어 연결에만 등록한 SQL 함수
`ac_event_ok(seq, body, heavy)`로 부른다(본문을 읽어 `LogEvent`로 만든 뒤 판정, seq별 캐시).
SQL이 다른 조건으로 후보를 좁힌 뒤 부르므로 페이지·커서·집계는 그대로다. 행마다 본문 JSON을
읽으므로 큰 범위에서는 느리다(색인·후처리 기준은 5.5R.6).

판정 함수 중 행 기준 미리 거르기(`RowPredicate`, 6R.9 M-1)를 가진 것이 있으면 먼저
`ac_row_ok(seq, 열...)`이 후보 행의 열 값으로 답한다(1 맞음·0 안 맞음·2 모름). `CASE`가 2일 때만
`ac_event_ok`를 불러 본문을 읽으므로, 열 값으로 답이 나는 행은 본문을 읽지도 `LogEvent`를 만들지도
않는다.

값 목록 IN(`_in`)은 값이 `_IN_CHUNK`개 이하면 바인드 변수 IN, 넘으면 JSON 배열 하나를
`json_each`로 펼친 IN 부분 질의다(M-15). 변수 수가 값 수와 무관해 SQLite 변수 한도(배포판 기본
32,766)를 넘지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, FromClause
from sqlalchemy.sql.elements import ColumnElement

from agent_console_contracts.logs import LogEvent
from agent_console_logs import query as q
from agent_console_logs._filter import LogFilter, LogScope, QueryContext, require_refined
from agent_console_logs._projects import UNGROUPED_PROJECT
from agent_console_logs._rowcheck import RowCheck, row_check_of

from .schema import log_bodies, log_events, log_links, log_search, log_tags, log_usage

__all__ = ["error_expr", "event_clauses", "load_event", "usage_clauses"]

_IN_CHUNK = 500
"""바인드 변수 IN의 최대 값 수. 넘으면 `json_each` 부분 질의 하나로 바꾼다(SQLite 변수 한도)."""

_PREDICATE_FN = "ac_event_ok"
_ROW_PREDICATE_FN = "ac_row_ok"
_ROW_YES, _ROW_NO, _ROW_UNKNOWN = 1, 0, 2

Clause = ColumnElement[bool]

_PAIR_CHUNK = 5000
"""튜플 IN 한 번에 넣는 쌍 수(SQLite 변수 상한 32766 아래)."""


def _in(col: ColumnElement[Any], values: Iterable[str]) -> Clause:
    """`col IN values`. 값이 없으면 거짓, `_IN_CHUNK`개를 넘으면 `json_each` 부분 질의(변수 1개)."""
    ordered = list(dict.fromkeys(values))
    if not ordered:
        return sa.false()
    if len(ordered) <= _IN_CHUNK:
        return col.in_(ordered)
    each = sa.func.json_each(sa.bindparam(None, json.dumps(ordered), type_=sa.Text))
    return col.in_(sa.select(sa.column("value")).select_from(each))


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


def _in_chunked(col: ColumnElement[Any], values: frozenset[str]) -> Clause:
    """범위 목록 IN(정렬해 SQL 문이 값 순서에 따라 달라지지 않게)."""
    return _in(col, sorted(values))


def _scope_clause(scope: LogScope, ev: FromClause) -> Clause:
    """`LogScope.contains`와 같은 조건(빈 세션·run_id는 범위 밖)."""
    c = ev.c
    parts: list[Clause] = []
    if scope.sessions:
        parts.append(sa.and_(c["session"] != "", _in_chunked(c["session"], scope.sessions)))
    if scope.run_ids:
        parts.append(sa.and_(c["run_id"] != "", _in_chunked(c["run_id"], scope.run_ids)))
    return sa.or_(*parts) if parts else sa.false()


def load_event(seq: int, body: str, heavy: str | None = None) -> LogEvent:
    """저장된 본문(`body`, 선택 `heavy` = detail·raw) → `LogEvent`."""
    data = json.loads(body)
    data["seq"] = seq
    if heavy:
        extra = json.loads(heavy)
        data["detail"] = extra.get("detail")
        data["raw"] = extra.get("raw")
    return LogEvent.model_validate(data)


def _register_predicates(conn: Connection, ctx: QueryContext) -> bool:
    """판정 함수를 이 연결의 SQL 함수로 등록한다(질의마다 다시 등록). SQLite가 아니면 False."""
    raw = conn.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection):
        return False
    predicates = ctx.predicates
    cache: dict[int, int] = {}

    def ok(seq: int, body: str | None, heavy: str | None) -> int:
        hit = cache.get(seq)
        if hit is None:
            if body is None:
                hit = 0
            else:
                event = load_event(seq, body, heavy)
                hit = 1 if all(p(event) for p in predicates) else 0
            cache[seq] = hit
        return hit

    raw.create_function(_PREDICATE_FN, 3, ok)
    return True


def _row_checks(ctx: QueryContext) -> tuple[list[str], list[RowCheck]]:
    """미리 거르기를 가진 판정 함수들의 (열 이름 순서, 함수). 열 이름의 첫째는 `seq`다."""
    fields: set[str] = set()
    checks: list[RowCheck] = []
    for predicate in ctx.predicates:
        found = row_check_of(predicate)
        if found is None:
            continue
        fields |= found[0]
        checks.append(found[1])
    return ["seq", *sorted(fields - {"seq"})], checks


def _unknown_row(_row: Mapping[str, Any]) -> bool | None:
    return None


def _register_row_checks(
    conn: Connection, names: Sequence[str], checks: Sequence[RowCheck]
) -> None:
    """`ac_row_ok(seq, 열...)`: 모두 맞음 확정 1, 하나라도 안 맞음 확정 0, 그 밖 2."""
    raw = conn.connection.driver_connection
    assert isinstance(raw, sqlite3.Connection)

    def row_ok(*values: Any) -> int:
        row = dict(zip(names, values, strict=True))
        answer = _ROW_YES
        for check in checks:
            hit = check(row)
            if hit is False:
                return _ROW_NO
            if hit is None:
                answer = _ROW_UNKNOWN
        return answer

    raw.create_function(_ROW_PREDICATE_FN, len(names), row_ok)


def _predicate_clause(conn: Connection, ctx: QueryContext, ev: FromClause) -> Clause:
    if not _register_predicates(conn, ctx):
        raise NotImplementedError("확장 필터 판정은 SQLite 연결에서만 됩니다")
    seq = ev.c["seq"]
    b = log_bodies.alias("pb")  # 바깥 질의가 log_bodies를 조인해도 섞이지 않게 별칭
    body = sa.select(b.c.body).where(b.c.seq == seq).scalar_subquery()
    heavy = sa.select(b.c.heavy).where(b.c.seq == seq).scalar_subquery()
    call: ColumnElement[Any] = getattr(sa.func, _PREDICATE_FN)(seq, body, heavy)
    names, checks = _row_checks(ctx)
    if not checks:
        return call == 1
    if len(checks) < len(ctx.predicates):
        # 미리 거르기가 없는 판정이 있으면 "모두 맞음"을 확정할 수 없다(그 판정은 본문으로)
        checks.append(_unknown_row)
    _register_row_checks(conn, names, checks)
    row: ColumnElement[Any] = getattr(sa.func, _ROW_PREDICATE_FN)(*(ev.c[n] for n in names))
    decided = sa.case({_ROW_YES: 1, _ROW_UNKNOWN: call}, value=row, else_=0)
    return decided == 1


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
    """`event_matches`와 같은 조건(커서·개수·정렬 제외). `ev`는 `log_events` 또는 그 별칭.

    Raises:
        LogQueryError: `scope`·확장 필터를 풀지 않은 맥락(`require_refined`).
    """
    require_refined(flt, ctx)
    c = ev.c
    out: list[Clause] = []
    if flt.max_seq is not None:
        out.append(c["seq"] <= flt.max_seq)
    if ctx.scope is not None:
        out.append(_scope_clause(ctx.scope, ev))
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
        (c["thread"], flt.thread),
    ):
        if wanted:
            out.append(_in(col, wanted))
    if flt.category:
        out.append(c["seq"].in_(sa.select(log_tags.c.seq).where(_in(log_tags.c.tag, flt.category))))
    for sides, wanted in ((None, flt.agent), (("from",), flt.from_), (("to",), flt.to)):
        if not wanted:
            continue
        sub = sa.select(log_links.c.seq).where(_in(log_links.c.agent, wanted))
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
    if ctx.predicates:
        out.append(_predicate_clause(conn, ctx, ev))
    return out


def usage_clauses(
    conn: Connection,
    flt: LogFilter,
    ctx: QueryContext,
    u: FromClause,
) -> list[Clause]:
    """`usage_samples`와 같은 조건(이벤트 전용 필터는 맞는 이벤트와 응답 키가 같은 표본만)."""
    require_refined(flt, ctx)
    c = u.c
    out: list[Clause] = []
    for col, wanted in (
        (c["source"], flt.source),
        (c["session"], flt.session),
        (c["cwd"], flt.cwd),
        (c["thread"], flt.agent),
        (c["thread"], flt.thread),
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
    scope = ctx.scope
    if scope is not None:
        parts: list[Clause] = []
        if scope.sessions:
            parts.append(sa.and_(c["session"] != "", _in_chunked(c["session"], scope.sessions)))
        if scope.run_ids:
            rv = log_events.alias("us")
            parts.append(
                sa.select(sa.literal(1))
                .where(
                    rv.c.source == c["source"],
                    rv.c.thread == c["thread"],
                    rv.c.message_id == c["message_id"],
                    rv.c.message_id != "",
                    rv.c.run_id != "",
                    _in_chunked(rv.c.run_id, scope.run_ids),
                )
                .exists()
            )
        out.append(sa.or_(*parts) if parts else sa.false())
    if q.has_event_only(flt, ctx):
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
