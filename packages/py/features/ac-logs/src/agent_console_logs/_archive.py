"""오프라인 보관본 만들기(`LogArchive` v1, design §4R.10·§4R.13, F-13).

agent_bench `LogStore.export`를 옮겨 색인 프로토콜(`LogIndex`) 위에서 필터 범위만 담도록 정리했다.
보관본은 색인 사본(수집 때 비밀 가림 후)이고, 내보낼 때 `redact`를 주면 지금 규칙으로 한 번 더
가린다.
크기는 이벤트 수(`max_events`)와 이벤트 JSON 바이트 합(`max_bytes`)으로 묶고, 넘으면 앞부분만 담고
`truncated = True`다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import fields
from typing import Any

from agent_console_contracts.logs import (
    LogArchive,
    LogEvent,
    LogLane,
    LogSessionSummary,
    LogTaxonomy,
)

from ._correlate import link_events
from ._filter import LogFilter, QueryContext
from ._index import LogIndex
from ._values import JsonValue, scrub_surrogates

__all__ = [
    "ARCHIVE_PAGE_SIZE",
    "ARCHIVE_VERSION",
    "DEFAULT_ARCHIVE_MAX_BYTES",
    "DEFAULT_ARCHIVE_MAX_EVENTS",
    "build_archive",
    "filter_to_params",
]

ARCHIVE_VERSION = 1
"""보관본 형식 버전(`LogArchive.version`)."""

DEFAULT_ARCHIVE_MAX_EVENTS = 5000
"""보관본 이벤트 수 상한 기본값."""

DEFAULT_ARCHIVE_MAX_BYTES = 20_000_000
"""보관본 이벤트 JSON 바이트 합 상한 기본값(약 20 MB)."""

ARCHIVE_PAGE_SIZE = 200
"""색인에서 한 번에 읽는 이벤트 수(`LogFilter.limit` 상한과 같다)."""

_SESSION_CHUNK = 200
"""세션 요약을 묻는 세션 id 묶음 크기(SQL `IN` 목록 길이)."""

_PAGING_FIELDS = frozenset({"limit", "cursor"})
"""보관본 범위에 쓰지 않는 필터 필드(페이지 넘김은 보관본이 한다)."""


def filter_to_params(flt: LogFilter) -> dict[str, JsonValue]:
    """`LogFilter` → 쿼리 이름별 값(기본값·페이지 필드 제외). `parse_log_filter`로 되돌린다."""
    default = LogFilter()
    out: dict[str, JsonValue] = {}
    for f in fields(LogFilter):
        if f.name in _PAGING_FIELDS:
            continue
        value = getattr(flt, f.name)
        if value == getattr(default, f.name):
            continue
        name = f.name.rstrip("_")
        out[name] = list(value) if isinstance(value, tuple) else value
    return out


def _clean(event: LogEvent) -> tuple[LogEvent, int]:
    """(외톨이 서로게이트를 바꾼 이벤트, JSON UTF-8 크기). 다른 색인 구현이 준 값도 방어한다."""
    try:
        return event, len(event.model_dump_json(by_alias=True).encode("utf-8"))
    except (ValueError, UnicodeError):  # PydanticSerializationError는 ValueError
        cleaned = scrub_surrogates(event)
        return cleaned, len(cleaned.model_dump_json(by_alias=True).encode("utf-8"))


def _redact_event(event: LogEvent, redact: Callable[[JsonValue], JsonValue]) -> LogEvent:
    update: dict[str, Any] = {
        "title": redact(event.title),
        "summary": redact(event.summary),
        "detail": redact(event.detail),
        "raw": redact(event.raw),
    }
    return event.model_copy(update=update)


def _lanes_of(events: Iterable[LogEvent], known: Iterable[LogLane]) -> list[LogLane]:
    """이벤트에 나온 줄과 그 조상 줄(알려진 표시 정보, 없으면 id만)."""
    table = {lane.id: lane for lane in known}
    wanted: dict[str, LogLane] = {}
    for event in events:
        lane_id: str | None = event.thread
        while lane_id and lane_id not in wanted:
            lane = table.get(lane_id, LogLane(id=lane_id))
            wanted[lane_id] = lane
            lane_id = lane.parent_id
    return [wanted[k] for k in sorted(wanted)]


def _sessions_of(
    index: LogIndex, flt: LogFilter, ctx: QueryContext, sessions: list[str]
) -> list[LogSessionSummary]:
    out: list[LogSessionSummary] = []
    for start in range(0, len(sessions), _SESSION_CHUNK):
        chunk = tuple(sessions[start : start + _SESSION_CHUNK])
        out.extend(
            index.list_sessions(flt.with_(session=chunk, limit=len(chunk), cursor=None), ctx)
        )
    out.sort(key=lambda s: (-(s.last_time or 0.0), s.session))
    return out


def build_archive(
    index: LogIndex,
    flt: LogFilter,
    ctx: QueryContext,
    *,
    exported_at: float,
    taxonomy: LogTaxonomy | None = None,
    max_events: int = DEFAULT_ARCHIVE_MAX_EVENTS,
    max_bytes: int = DEFAULT_ARCHIVE_MAX_BYTES,
    with_detail: bool = True,
    max_detail_bytes: int | None = None,
    redact: Callable[[JsonValue], JsonValue] | None = None,
) -> LogArchive:
    """필터에 맞는 이벤트로 보관본을 만든다(색인 읽기만).

    Args:
        index: 색인.
        flt: 범위 필터. `limit`·`cursor`는 쓰지 않는다(보관본이 끝까지 넘긴다). `order`는 지킨다.
        ctx: 질의 맥락(분류 체계·프로젝트 묶기).
        exported_at: 내보낸 시각(epoch 초, 호출자가 시계에서 준다).
        taxonomy: 보관본에 담을 유효 분류 체계(화면 표시용). None이면 빈 분류 체계.
        max_events: 이벤트 수 상한(1 이상).
        max_bytes: 이벤트 JSON(UTF-8) 바이트 합 상한. 넘는 이벤트부터 담지 않는다.
        with_detail: 이벤트마다 본문(`detail`·`raw`)을 담는다(이벤트마다 상세 질의 한 번).
        max_detail_bytes: 이벤트 하나의 `detail`·`raw` 상한(넘으면 앞부분 문자열).
        redact: 내보내기 직전 가리기(제목·요약·본문·원문·세션 제목·필터 값). None이면 색인 사본
            그대로.

    Returns:
        `LogArchive` v1. 상한에 걸리면 `truncated = True`.

    Raises:
        ValueError: `max_events` 또는 `max_bytes`가 1보다 작다.
    """
    if max_events < 1 or max_bytes < 1:
        raise ValueError("max_events·max_bytes는 1 이상이어야 합니다")
    page_flt = flt.with_(limit=ARCHIVE_PAGE_SIZE, cursor=None)
    events: list[LogEvent] = []
    used = 0
    truncated = False
    cursor: str | None = None
    while not truncated:
        page = index.query_events(page_flt.with_(cursor=cursor), ctx)
        for item in page.items:
            if len(events) >= max_events:
                truncated = True
                break
            event = item
            if with_detail:
                found = index.get_event(
                    item.uid, ctx, max_detail_bytes=max_detail_bytes, max_evidence=0
                )
                if found is not None:
                    event = found.event.model_copy(update={"seq": item.seq})
            if redact is not None:
                event = _redact_event(event, redact)
            event, size = _clean(event)
            if used + size > max_bytes:
                truncated = True
                break
            used += size
            events.append(event)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    session_ids = list(dict.fromkeys(e.session for e in events if e.session))
    sessions = _sessions_of(index, flt, ctx, session_ids)
    if redact is not None:
        sessions = [s.model_copy(update={"title": redact(s.title)}) for s in sessions]
    sessions = [scrub_surrogates(s) for s in sessions]
    links = {uid: found for uid, found in link_events(events).items() if found}
    params: dict[str, JsonValue] = filter_to_params(flt)
    if redact is not None:
        params = {k: redact(v) for k, v in params.items()}
    params = scrub_surrogates(params)
    return LogArchive(
        version=ARCHIVE_VERSION,
        exported_at=exported_at,
        filter=params,
        taxonomy=scrub_surrogates(taxonomy) if taxonomy is not None else LogTaxonomy(),
        lanes=[scrub_surrogates(lane) for lane in _lanes_of(events, index.lanes())],
        sessions=sessions,
        events=events,
        evidence_links=links,
        truncated=truncated,
    )
