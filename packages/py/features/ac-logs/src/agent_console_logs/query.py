"""질의 의미를 정하는 순수 함수(design §4R.6). 색인 구현이 함께 쓴다.

`MemoryLogIndex`는 이 함수만으로 질의를 답한다. SQLite 구현(4R.5)은 SQL로 후보를 좁힌 뒤
같은 함수(프로젝트 묶기·짝 소요 시간·집계 지표 등)를 써서 결과가 같게 만든다.

규칙 요지:
- 이벤트 시각 = `time`, 없으면 `observed_at`(`effective_time`).
  기간 필터·정렬·day/hour가 이것을 쓴다.
- 오류 = 이벤트 태그 중 하나가 `ctx.error_categories`(분류 체계 tone=danger)에 있음.
- 토큰 지표는 `log_usage` 행(응답당 1회)으로 센다. 이벤트 전용 필터(범주·도구 등)가 있으면 그 필터에
  맞는 이벤트와 (출처, thread, message_id)가 같은 표본만 센다.
- 값이 없는 지표는 None이다(0으로 채우지 않음).
- 범위(`ctx.scope`, X27): 이벤트의 세션 또는 run_id가 합집합에 들어야 한다. 토큰 표본은 세션이
  범위에 들거나, run_id 범위에 드는 이벤트와 응답 키가 같아야 한다.
- 확장 판정(`ctx.predicates`, X28)·`max_seq`는 이벤트 전용 필터다(표본은 맞는 이벤트의 응답 키로).
  `scope`·확장 필터는 질의 전에 풀어야 한다(`require_refined`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

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
    LogTokenTotals,
    TokenSample,
)

from ._correlate import correlation_keys, link_events, pair_durations
from ._draft import TAG_TOOL
from ._filter import (
    DIMENSIONS,
    METRICS,
    LogFilter,
    LogQueryError,
    QueryContext,
    parse_log_filter,
    parse_tz,
    require_refined,
)
from ._projects import UNGROUPED_PROJECT, resolve_project
from ._titles import pick_session_title
from ._values import text
from ._windows import sum_samples

__all__ = [
    "EVENT_ONLY_FILTERS",
    "UsageRow",
    "aggregate_rows",
    "build_timeline",
    "clip_detail",
    "effective_time",
    "event_detail",
    "event_matches",
    "evidence_candidates",
    "handoff_matrix",
    "has_event_only",
    "is_error",
    "page_durations",
    "page_events",
    "project_of",
    "related_of",
    "search_text",
    "strip_body",
    "summarize_sessions",
    "usage_matches",
    "usage_samples",
]

EVENT_ONLY_FILTERS = (
    "category",
    "from_",
    "to",
    "via",
    "tool",
    "call_id",
    "run_id",
    "stage",
    "status",
    "q",
)
"""토큰 표본 행에 없는 필터. 있으면 맞는 이벤트와 응답 키가 같은 표본만 센다."""


@dataclass(frozen=True, slots=True)
class UsageRow:
    """`log_usage` 한 행: 응답(출처, thread, message_id) 하나의 토큰 표본과 위치."""

    source: str
    session: str
    cwd: str
    repo_root: str
    sample: TokenSample

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.sample.thread, self.sample.message_id)


# ---------------------------------------------------------------- 공통


def effective_time(event: LogEvent) -> float:
    """이벤트 시각(`time`, 없으면 `observed_at`)."""
    return event.time if event.time is not None else event.observed_at


def search_text(event: LogEvent) -> str:
    """검색 대상 문자열(원문 `raw` 제외, agent_bench 규칙). 비교는 소문자로 한다."""
    body = event.model_dump(mode="json", by_alias=True, exclude={"raw"})
    return text(body)


def is_error(event: LogEvent, ctx: QueryContext) -> bool:
    """오류 이벤트인지(태그 중 하나가 tone=danger 범주, F-25)."""
    return any(tag in ctx.error_categories for tag in event.tags) or (
        event.category in ctx.error_categories
    )


def project_of(cwd: str, repo_root: str, ctx: QueryContext) -> tuple[str | None, str, bool]:
    """(묶음 id 또는 None, 표시 이름, 묶기 규칙에 맞았는지)."""
    ref, grouped = resolve_project(
        cwd, repo_root, ctx.projects, ungrouped_label=ctx.ungrouped_label
    )
    if ref is None:
        return None, "", False
    return ref.id, ref.label, grouped


def _project_ok(cwd: str, repo_root: str, wanted: Sequence[str], ctx: QueryContext) -> bool:
    pid, _label, grouped = project_of(cwd, repo_root, ctx)
    for value in wanted:
        if value == UNGROUPED_PROJECT and not grouped:
            return True
        if pid is not None and value == pid:
            return True
    return False


def _time_ok(t: float | None, flt: LogFilter) -> bool:
    if flt.since is None and flt.until is None:
        return True
    if t is None:
        return False
    if flt.since is not None and t < flt.since:
        return False
    return not (flt.until is not None and t >= flt.until)


def event_matches(event: LogEvent, flt: LogFilter, ctx: QueryContext) -> bool:
    """이벤트가 필터에 맞는지(커서·개수·정렬은 보지 않는다).

    Raises:
        LogQueryError: `scope`·확장 필터를 풀지 않은 맥락(`require_refined`).
    """
    require_refined(flt, ctx)
    if flt.max_seq is not None and event.seq > flt.max_seq:
        return False
    if ctx.scope is not None and not ctx.scope.contains(event.session, event.run_id):
        return False
    checks: list[tuple[tuple[str, ...], Iterable[str]]] = [
        (flt.source, (event.source,)),
        (flt.session, (event.session,)),
        (flt.cwd, (event.cwd,)),
        (flt.via, (event.via,)),
        (flt.tool, (event.tool,)),
        (flt.call_id, (event.call_id,)),
        (flt.model, (event.model,)),
        (flt.run_id, (event.run_id,)),
        (flt.stage, (event.stage,)),
        (flt.status, (event.status,)),
        (flt.category, (*event.tags, event.category)),
        (flt.agent, (event.actor, *event.from_, *event.to)),
        (flt.thread, (event.thread,)),
        (flt.from_, event.from_),
        (flt.to, event.to),
    ]
    for wanted, have in checks:
        if wanted and not set(wanted).intersection(have):
            return False
    if flt.project and not _project_ok(event.cwd, event.repo_root, flt.project, ctx):
        return False
    if not _time_ok(effective_time(event), flt):
        return False
    if flt.q and flt.q.lower() not in search_text(event).lower():
        return False
    return all(p(event) for p in ctx.predicates)


def has_event_only(flt: LogFilter, ctx: QueryContext) -> bool:
    """토큰 표본을 맞는 이벤트의 응답 키로 한 번 더 걸러야 하는지(이벤트 전용 필터가 있는지)."""
    return (
        any(getattr(flt, name) for name in EVENT_ONLY_FILTERS)
        or flt.max_seq is not None
        or bool(ctx.predicates)
    )


def usage_matches(row: UsageRow, flt: LogFilter, ctx: QueryContext) -> bool:
    """표본 행이 표본에 있는 필터(출처·세션·프로젝트·cwd·에이전트=thread·모델·기간)에 맞는지.

    범위(`ctx.scope`)는 세션만 본다(run_id 범위는 `usage_samples`가 이벤트로 본다).
    """
    require_refined(flt, ctx)
    checks: list[tuple[tuple[str, ...], str]] = [
        (flt.source, row.source),
        (flt.session, row.session),
        (flt.cwd, row.cwd),
        (flt.agent, row.sample.thread),
        (flt.thread, row.sample.thread),
        (flt.model, row.sample.model),
    ]
    for wanted, have in checks:
        if wanted and have not in wanted:
            return False
    if flt.project and not _project_ok(row.cwd, row.repo_root, flt.project, ctx):
        return False
    return _time_ok(row.sample.time, flt)


def usage_samples(
    rows: Iterable[UsageRow], events: Iterable[LogEvent], flt: LogFilter, ctx: QueryContext
) -> list[UsageRow]:
    """필터에 맞는 표본 행(이벤트 전용 필터가 있으면 맞는 이벤트의 응답 키로 한 번 더 거른다).

    범위가 있으면 세션이 범위에 들거나 run_id 범위에 드는 이벤트와 응답 키가 같은 표본만 남긴다.
    """
    require_refined(flt, ctx)
    all_events: list[LogEvent] | None = None
    picked = [r for r in rows if usage_matches(r, flt, ctx)]
    scope = ctx.scope
    if scope is not None:
        run_keys: set[tuple[str, str, str]] = set()
        if scope.run_ids:
            all_events = list(events)
            run_keys = {
                (e.source, e.thread, e.message_id)
                for e in all_events
                if e.message_id and e.run_id and e.run_id in scope.run_ids
            }
        picked = [
            r for r in picked if (r.session and r.session in scope.sessions) or r.key in run_keys
        ]
    if has_event_only(flt, ctx):
        if all_events is None:
            all_events = list(events)
        keys = {
            (e.source, e.thread, e.message_id)
            for e in all_events
            if e.message_id and event_matches(e, flt, ctx)
        }
        picked = [r for r in picked if r.key in keys]
    return picked


def strip_body(event: LogEvent) -> LogEvent:
    """목록용 사본(`detail`·`raw` 없음)."""
    if event.detail is None and event.raw is None:
        return event
    return event.model_copy(update={"detail": None, "raw": None})


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def clip_detail(event: LogEvent, max_bytes: int | None) -> tuple[LogEvent, bool]:
    """`detail`·`raw`가 `max_bytes`(UTF-8 JSON 크기)를 넘으면 앞부분 문자열로 바꾼다.

    Returns:
        (사본, 잘렸는지).
    """
    if max_bytes is None:
        return event, False
    update: dict[str, Any] = {}
    for name in ("detail", "raw"):
        value = getattr(event, name)
        if value is not None and _size(value) > max_bytes:
            raw = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            update[name] = raw[:max_bytes].decode("utf-8", errors="ignore")
    if not update:
        return event, False
    return event.model_copy(update=update), True


# ---------------------------------------------------------------- 목록


def page_events(
    events: Iterable[LogEvent], flt: LogFilter, ctx: QueryContext, *, with_total: bool = False
) -> LogEventPage:
    """키셋 페이지(seq 기준). `events`는 아무 순서여도 된다.

    짝 이벤트(같은 세션·thread·`call_id`의 시작·끝 단계)에는 `duration_ms`를 채운다. 짝은 목록
    필터와 상관없이 같은 세션의 모든 이벤트에서 찾는다(끝 단계만 거른 목록에도 소요 시간이 보인다).
    """
    require_refined(flt, ctx)
    all_events = list(events)
    matched = sorted((e for e in all_events if event_matches(e, flt, ctx)), key=lambda e: e.seq)
    if flt.order == "desc":
        matched.reverse()
    total = len(matched) if with_total else None
    if flt.cursor is not None:
        c = int(flt.cursor)
        matched = [e for e in matched if (e.seq > c if flt.order == "asc" else e.seq < c)]
    items = matched[: flt.limit]
    more = len(matched) > flt.limit
    durations = page_durations(items, all_events, ctx)
    return LogEventPage(
        items=[
            strip_body(e).model_copy(update={"duration_ms": durations.get(e.uid)}) for e in items
        ],
        total=total,
        next_cursor=str(items[-1].seq) if more and items else None,
    )


def page_durations(
    page: Sequence[LogEvent], events: Iterable[LogEvent], ctx: QueryContext
) -> dict[str, float]:
    """목록 페이지 이벤트의 짝 소요 시간(ms, uid → 값).

    `events`에서 페이지 이벤트와 세션·thread·`call_id`가 같은 이벤트만 모아 `pair_durations`로
    계산한다(색인 구현이 짝 후보만 읽어 넘겨도 같은 값).
    """
    starts, ends = ctx.pair_start_stages, ctx.pair_end_stages
    keys = {
        (e.session, e.thread, e.call_id)
        for e in page
        if e.call_id and (e.stage in starts or e.stage in ends)
    }
    if not keys:
        return {}
    partners = [e for e in events if (e.session, e.thread, e.call_id) in keys]
    by_session: dict[str, list[LogEvent]] = {}
    for e in partners:
        by_session.setdefault(e.session, []).append(e)
    out: dict[str, float] = {}
    for group in by_session.values():
        out.update(pair_durations(group, start_stages=starts, end_stages=ends))
    wanted = {e.uid for e in page}
    return {uid: d for uid, d in out.items() if uid in wanted}


def event_detail(
    event: LogEvent,
    *,
    related: Iterable[LogEvent],
    candidates: Sequence[LogEvent],
    usage: TokenSample | None,
    max_detail_bytes: int | None,
    max_evidence: int,
) -> LogEventDetail:
    """상세 응답을 만든다.

    Args:
        related: 같은 thread의 같은 `call_id` 또는 `message_id` 이벤트(자기 제외는 여기서).
        candidates: 같은 상관 키를 가진 후보(seq 순, `max_evidence + 1`개까지 주면 잘림 판정).
    """
    truncated = len(candidates) > max_evidence
    pool = list(candidates[:max_evidence])
    if not any(e.uid == event.uid for e in pool):
        pool.append(event)
    links = link_events(pool).get(event.uid, [])
    body, detail_truncated = clip_detail(event, max_detail_bytes)
    return LogEventDetail(
        event=body,
        related=[strip_body(e) for e in sorted(related, key=lambda e: e.seq) if e.uid != event.uid],
        evidence_links=links,
        truncated=truncated,
        detail_truncated=detail_truncated,
        usage=usage,
    )


def related_of(event: LogEvent, events: Iterable[LogEvent]) -> list[LogEvent]:
    """같은 thread에서 같은 call_id 또는 message_id를 가진 다른 이벤트."""
    out = []
    for e in events:
        if e.uid == event.uid or e.thread != event.thread:
            continue
        if (event.call_id and e.call_id == event.call_id) or (
            event.message_id and e.message_id == event.message_id
        ):
            out.append(e)
    return out


def evidence_candidates(event: LogEvent, events: Iterable[LogEvent]) -> list[LogEvent]:
    """이 이벤트와 상관 키(근거, 값)를 하나라도 공유하는 이벤트(seq 순)."""
    keys = set(correlation_keys(event))
    if not keys:
        return []
    return sorted(
        (e for e in events if keys.intersection(correlation_keys(e))), key=lambda e: e.seq
    )


# ---------------------------------------------------------------- 세션·타임라인


def _totals(rows: Iterable[UsageRow]) -> LogTokenTotals | None:
    samples = [r.sample for r in rows]
    if not samples:
        return None
    totals = sum_samples(samples)
    return totals if totals.total is not None else None


def summarize_sessions(
    events: Iterable[LogEvent],
    usage: Iterable[UsageRow],
    flt: LogFilter,
    ctx: QueryContext,
) -> list[LogSessionSummary]:
    """세션별 요약(마지막 시각 내림차순, `flt.limit`개). 세션 id가 빈 이벤트는 뺀다.

    필터는 어느 세션이 보일지와 집계(개수·시각·토큰)만 정한다. 제목·첫 cwd는 필터와 상관없이
    세션의 모든 이벤트에서 고른다(제목 행에는 cwd·actor가 없다, 5.2R.38).
    """
    require_refined(flt, ctx)
    all_events = list(events)
    groups: dict[str, list[LogEvent]] = {}
    for e in all_events:
        if e.session and event_matches(e, flt, ctx):
            groups.setdefault(e.session, []).append(e)
    heads = _session_events(all_events, groups.keys())
    usage_rows = usage_samples(usage, all_events, flt, ctx)
    by_session: dict[str, list[UsageRow]] = {}
    for r in usage_rows:
        by_session.setdefault(r.session, []).append(r)
    out = [
        _summary(sid, evs, by_session.get(sid, []), ctx, head=heads[sid])
        for sid, evs in groups.items()
    ]
    out.sort(key=lambda s: (-(s.last_time or 0.0), s.session))
    return out[: flt.limit]


def _session_events(
    events: Iterable[LogEvent], sessions: Iterable[str]
) -> dict[str, list[LogEvent]]:
    """세션 id 조건만으로 모은 이벤트(제목·첫 cwd용)."""
    out: dict[str, list[LogEvent]] = {sid: [] for sid in sessions}
    for e in events:
        bucket = out.get(e.session)
        if bucket is not None:
            bucket.append(e)
    return out


def _summary(
    session: str,
    events: list[LogEvent],
    usage: list[UsageRow],
    ctx: QueryContext,
    *,
    head: list[LogEvent],
) -> LogSessionSummary:
    """`events`(필터 통과)로 집계하고, `head`(세션의 모든 이벤트)로 제목·첫 cwd를 고른다."""
    ordered = sorted(events, key=lambda e: (effective_time(e), e.seq))
    whole = sorted(head, key=lambda e: (effective_time(e), e.seq))
    cwd = next((e.cwd for e in whole if e.cwd), "")
    repo_root = next((e.repo_root for e in whole if e.cwd == cwd and e.repo_root), "")
    title = pick_session_title(whole, ctx.session_title_rules)
    pid, label, _ = project_of(cwd, repo_root, ctx)
    times = [e.time for e in ordered if e.time is not None]
    return LogSessionSummary(
        session=session,
        sources=sorted({e.source for e in ordered}),
        title=title,
        cwd=cwd,
        repo_root=repo_root,
        project=LogProjectRef(id=pid, label=label) if pid else None,
        first_time=min(times) if times else None,
        last_time=max(times) if times else None,
        events=len(ordered),
        errors=sum(1 for e in ordered if is_error(e, ctx)),
        thread_count=len({e.thread for e in ordered if e.thread}),
        models=sorted({e.model for e in ordered if e.model}),
        tokens=_totals(usage),
    )


def build_timeline(
    session: str,
    events: Iterable[LogEvent],
    usage: Iterable[UsageRow],
    agents: Mapping[str, LogLane],
    ctx: QueryContext,
    *,
    flt: LogFilter | None = None,
    limit: int,
) -> LogTimeline | None:
    """세션 타임라인: 보이는 이벤트(시각 → seq), 줄 = thread, 짝 이벤트 `duration_ms`.

    Returns:
        세션 이벤트가 없으면 None.
    """
    base = (flt or LogFilter()).with_(session=(session,), limit=1)
    require_refined(base, ctx)
    all_events = list(events)
    mine = [e for e in all_events if e.session == session and event_matches(e, base, ctx)]
    if not mine:
        return None
    usage_rows = usage_samples(usage, all_events, base, ctx)
    head = [e for e in all_events if e.session == session]
    summary = _summary(session, mine, usage_rows, ctx, head=head)
    visible = [e for e in mine if e.category not in ctx.hidden_categories]
    visible.sort(key=lambda e: (effective_time(e), e.seq))
    durations = pair_durations(
        visible, start_stages=ctx.pair_start_stages, end_stages=ctx.pair_end_stages
    )
    shown = visible[:limit]
    threads = list(dict.fromkeys(e.thread for e in shown if e.thread))
    lanes: list[LogLane] = []
    added: set[str] = set()

    def add(tid: str) -> None:
        if tid in added:
            return
        added.add(tid)
        lane = agents.get(tid)
        lanes.append(lane if lane is not None else LogLane(id=tid))

    for tid in threads:
        add(tid)
    return LogTimeline(
        session=summary,
        lanes=lanes,
        events=[
            strip_body(e).model_copy(update={"duration_ms": durations.get(e.uid)}) for e in shown
        ],
        total=len(visible),
        truncated=len(visible) > limit,
    )


# ---------------------------------------------------------------- 집계


_DIMENSION_IDS = tuple(d.id for d in DIMENSIONS)
_METRIC_IDS = tuple(m.id for m in METRICS)
_TOKEN_FIELDS = {
    "tokens.input": "input",
    "tokens.output": "output",
    "tokens.cache_read": "cache_read",
    "tokens.cache_creation": "cache_creation",
    "tokens.total": "total",
}


def _local(t: float, ctx: QueryContext) -> datetime:
    return (
        datetime.fromtimestamp(t, tz=ctx.tz) if ctx.tz else datetime.fromtimestamp(t).astimezone()
    )


def _event_keys(event: LogEvent, dim: str, ctx: QueryContext) -> list[str | None]:
    if dim == "project":
        return [project_of(event.cwd, event.repo_root, ctx)[0]]
    if dim == "agent":
        return [event.thread or event.actor or None]
    if dim == "day":
        return [_local(effective_time(event), ctx).strftime("%Y-%m-%d")]
    if dim == "hour":
        return [_local(effective_time(event), ctx).strftime("%Y-%m-%dT%H")]
    if dim == "tag":
        return list(event.tags) or [None]
    value = getattr(event, dim)
    return [value or None]


def _usage_keys(row: UsageRow, dim: str, ctx: QueryContext) -> list[str | None]:
    s = row.sample
    if dim == "project":
        return [project_of(row.cwd, row.repo_root, ctx)[0]]
    if dim == "cwd":
        return [row.cwd or None]
    if dim == "session":
        return [row.session or None]
    if dim == "agent":
        return [s.thread or None]
    if dim == "model":
        return [s.model or None]
    if dim == "source":
        return [row.source or None]
    if dim in ("day", "hour"):
        if s.time is None:
            return [None]
        fmt = "%Y-%m-%d" if dim == "day" else "%Y-%m-%dT%H"
        return [_local(s.time, ctx).strftime(fmt)]
    return [None]  # category·tool·tag는 표본에 없다


def _combos(per_dim: list[list[str | None]]) -> list[tuple[str | None, ...]]:
    out: list[tuple[str | None, ...]] = [()]
    for values in per_dim:
        out = [(*prefix, v) for prefix in out for v in values]
    return out


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def aggregate_rows(
    request: LogAggregateRequest,
    events: Iterable[LogEvent],
    usage: Iterable[UsageRow],
    ctx: QueryContext,
) -> list[LogAggregateRow]:
    """집계(design §4R.6). 결과는 키 오름차순(None은 뒤).

    - `events`: 맞는 이벤트 수. `tool_calls`: `TAG_TOOL` 이벤트의 서로 다른 (thread, call_id)
      (call_id 없는 도구 이벤트는 하나씩). `errors`: 오류 이벤트 수.
    - `tokens.*`: 표본 합(그 항목이 어느 표본에도 없으면 None).
      표본에 없는 차원(category·tool·tag)은 키 None.
    - `duration_ms.*`: 짝 이벤트 소요 시간(끝 이벤트의 차원으로 센다, 짝 없으면 None).
      p95는 최근접 순위.

    Raises:
        LogQueryError: 모르는 차원(`group_by.N`)·지표(`metric`)·필터(`filter.X`)·시간대(`tz`).
    """
    for i, dim in enumerate(request.group_by):
        if dim not in _DIMENSION_IDS:
            raise LogQueryError(f"모르는 차원: {dim}", f"group_by.{i}")
    if request.metric not in _METRIC_IDS:
        raise LogQueryError(f"모르는 지표: {request.metric}", "metric")
    flt = parse_log_filter(request.filter, path="filter", extra=ctx.extra_names)
    require_refined(flt, ctx)
    if request.tz:
        ctx = replace(ctx, tz=parse_tz(request.tz))
    dims = list(request.group_by)
    metric = request.metric
    all_events = list(events)

    buckets: dict[tuple[str | None, ...], list[Any]] = {}
    if metric in _TOKEN_FIELDS:
        for row in usage_samples(usage, all_events, flt, ctx):
            for combo in _combos([_usage_keys(row, d, ctx) for d in dims]):
                buckets.setdefault(combo, []).append(row.sample)
        values: dict[tuple[str | None, ...], float | None] = {}
        for k, samples in buckets.items():
            totals = sum_samples(samples)
            v = getattr(totals, _TOKEN_FIELDS[metric])
            values[k] = float(v) if v is not None else None
    else:
        matched = [e for e in all_events if event_matches(e, flt, ctx)]
        values = {}
        if metric.startswith("duration_ms."):
            durations = pair_durations(
                matched, start_stages=ctx.pair_start_stages, end_stages=ctx.pair_end_stages
            )
            for e in matched:
                if e.uid in durations and e.stage in ctx.pair_end_stages:
                    for combo in _combos([_event_keys(e, d, ctx) for d in dims]):
                        buckets.setdefault(combo, []).append(durations[e.uid])
            kind = metric.split(".", 1)[1]
            for k, ds in buckets.items():
                values[k] = (
                    sum(ds) if kind == "sum" else sum(ds) / len(ds) if kind == "avg" else _p95(ds)
                )
        else:
            for e in matched:
                if metric == "errors" and not is_error(e, ctx):
                    continue
                if metric == "tool_calls" and TAG_TOOL not in e.tags:
                    continue
                for combo in _combos([_event_keys(e, d, ctx) for d in dims]):
                    buckets.setdefault(combo, []).append(e)
            for k, evs in buckets.items():
                if metric == "tool_calls":
                    ids = {(e.thread, e.call_id) if e.call_id else ("~", e.uid) for e in evs}
                    values[k] = float(len(ids))
                else:
                    values[k] = float(len(evs))
    rows = [
        LogAggregateRow(keys=dict(zip(dims, k, strict=True)), value=v) for k, v in values.items()
    ]
    rows.sort(key=lambda r: tuple((v is None, v or "") for v in r.keys.values()))
    return rows


# ---------------------------------------------------------------- handoff


def handoff_matrix(
    events: Iterable[LogEvent], flt: LogFilter, ctx: QueryContext, *, limit: int = 40
) -> HandoffMatrix:
    """from·to가 둘 다 있는 이벤트의 (from, to, via) 횟수(많은 순 `limit`개, agent_bench edges).

    범주 이름을 보지 않는다. 전달을 나타내는 이벤트에 from·to를 채우는 것은 분류기의 몫이다.
    `runs`는 이 집계에 쓰인 서로 다른 세션 수다.
    """
    require_refined(flt, ctx)
    counts: dict[tuple[str, str, str], int] = {}
    sessions: set[str] = set()
    for e in events:
        if not e.from_ or not e.to or not event_matches(e, flt, ctx):
            continue
        sessions.add(e.session)
        for src in e.from_:
            for dst in e.to:
                if src and dst:
                    k = (src, dst, e.via)
                    counts[k] = counts.get(k, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    cells = [
        HandoffCount.model_validate({"from": s, "to": t, "via": v or None, "count": n})
        for (s, t, v), n in ordered
    ]
    return HandoffMatrix(cells=cells, runs=len(sessions))
