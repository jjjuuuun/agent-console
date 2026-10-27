"""런타임 로그 출처 ``platform-runs``와 분류기 ``platform-run-event``(X5r·X6, design §4R.3·§4R.8).

- 출처: 최근 Run마다 단위 하나(``ref`` = run id). 커서 ``offset``은 그 Run에서 마지막으로 읽은
  이벤트 seq(워터마크)이고, ``state.sessions``에 노드 경로 → 세션 id(대응표 ``session_from`` 규칙의
  이벤트에서 배운 값)를 둔다. 세션을 알리는 이벤트가 없으면 NodeRun ``backend_session_id``를 쓴다.
  ``state.cwd``에는 대응표 ``cwd_from`` 규칙의 이벤트(기본: ``run.started``의 Run 유효 작업
  폴더)에서 배운 작업 폴더를 두고, 그 뒤 이 Run의 모든 이벤트의 ``cwd``로 싣는다(로그 프로젝트
  묶기, 5.2R.34).
- 분류기: 행 단위 무상태(F-7). 대응표(``event_map``)의 규칙으로 초안을 만든다. 대응표 덮어쓰기는
  출처 설정 ``event_map``에서 ``SourceRef.meta``로 넘어온다(분류기에 넘길 맥락).
- 실행 기록은 읽기만 한다(포트 ``runs.reader``·``runs.events``).
"""

from __future__ import annotations

import builtins
import json
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, ClassVar

from agent_console_contracts import NodeRun, RunEvent, x_ui
from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogLane,
    LogSourceDescriptor,
    TokenSample,
)
from agent_console_logs import (
    ClassifyContext,
    Cursor,
    JsonValue,
    LogEventDraft,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
    json_pointer,
)

from .event_map import (
    EVENT_MAP_SCHEMA,
    TOKEN_KEYS,
    EventMap,
    EventRule,
    load_default_event_map,
    names_for,
    overrides_of,
    render,
    resolve,
)
from .ports import EventReader, RunReader

__all__ = [
    "CLASSIFIER_ID",
    "DEFAULT_MAX_RUNS",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_TITLE_CHARS",
    "SOURCE_ID",
    "SOURCE_SCHEMA",
    "PlatformRunsClassifier",
    "PlatformRunsLogSource",
    "PlatformRunsSource",
    "platform_runs",
]

SOURCE_ID = "platform-runs"
"""출처 id(설정 ``logs.sources[id=platform-runs]``)."""

CLASSIFIER_ID = "platform-run-event"
"""분류기 id(레지스트리 없이 출처가 직접 지정한다)."""

DEFAULT_MAX_RUNS = 200
"""수집할 최근 Run 수 기본값(설정 ``max_runs``)."""

DEFAULT_PAGE_SIZE = 500
"""``runs.events``에서 한 번에 읽는 이벤트 수."""

DEFAULT_TITLE_CHARS = 200
"""제목 최대 글자 수(긴 메시지 본문은 detail에 남는다)."""

SESSIONS_STATE = "sessions"
"""커서 ``state`` 키: 노드 경로(``a/b``) → 세션 id."""

CWD_STATE = "cwd"
"""커서 ``state`` 키: 이 Run의 작업 폴더(``cwd_from`` 규칙에서 배운 값)."""

META_SESSION = "session"
META_CWD = "cwd"
META_EVENT_MAP = "event_map"

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "interrupted"})
"""더 이벤트가 생기지 않는 Run 상태(마지막 seq 캐시용, 계약 ``RunStatus``의 종료 값)."""

SOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "max_runs": {
            "type": "integer",
            "minimum": 1,
            "default": DEFAULT_MAX_RUNS,
            "title": "최근 실행 수",
            "description": "수집 때 살펴볼 최근 Run 수(오래된 Run은 이미 색인된 것만 남는다).",
            **x_ui(tier="advanced"),
        },
        "event_map": {**EVENT_MAP_SCHEMA, "default": {}, **x_ui(tier="advanced")},
    },
    "additionalProperties": False,
}
"""``platform-runs`` 출처 설정 스키마."""


def _event_size(data: Mapping[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))


def _key(path: Sequence[str]) -> str:
    return "/".join(path)


def _session_for(
    path: Sequence[str], learned: Mapping[str, str], node_sessions: Mapping[str, str]
) -> str:
    for i in range(len(path), 0, -1):
        found = learned.get(_key(path[:i]))
        if found:
            return found
    for node in reversed(path):
        found = node_sessions.get(node)
        if found:
            return found
    return ""


class PlatformRunsSource:
    """플랫폼 실행 이벤트를 읽는 런타임 출처(기본 켜짐 — 이미 플랫폼 데이터).

    Args:
        runs: Run·NodeRun 조회.
        events: 실행 이벤트 조회.
        event_map: 기본 대응표(없으면 패키지 데이터). 세션을 알리는 규칙(``session_from``)을 본다.
        source_id: 출처 id.
        page_size: 한 번에 읽는 이벤트 수.
    """

    def __init__(
        self,
        runs: RunReader,
        events: EventReader,
        *,
        event_map: EventMap | None = None,
        source_id: str = SOURCE_ID,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size는 0보다 커야 합니다")
        self._runs = runs
        self._events = events
        self._map = event_map if event_map is not None else load_default_event_map()
        self._page = page_size
        self._finished: dict[str, int] = {}
        self._lock = threading.Lock()
        self.descriptor = LogSourceDescriptor(
            id=source_id,
            title="플랫폼 실행",
            format=CLASSIFIER_ID,
            description=(
                "이 콘솔에서 실행한 팀 구성의 실행 이벤트(RunEvent)를 읽는다. "
                "hook·MCP 관측 이벤트도 여기서 보인다. 실행 기록은 읽기만 한다."
            ),
            config_schema=SOURCE_SCHEMA,
            default_enabled=True,
            reads_paths=False,
        )

    @property
    def event_map(self) -> EventMap:
        """기본 대응표."""
        return self._map

    def invalidate(self, run_id: str | None = None) -> None:
        """끝난 Run의 마지막 seq 캐시를 지운다(새 이벤트·기록 정리 뒤)."""
        with self._lock:
            if run_id is None:
                self._finished.clear()
            else:
                self._finished.pop(run_id, None)

    def discover(self, ctx: LogSourceContext) -> Iterable[SourceRef]:
        """최근 Run(설정 ``max_runs``개)을 오래된 것부터. ``size`` = 마지막 seq."""
        limit = ctx.config.get("max_runs")
        runs = self._runs.list(limit=limit if isinstance(limit, int) else DEFAULT_MAX_RUNS)
        overrides = overrides_of(ctx.config.get(META_EVENT_MAP))
        meta: dict[str, JsonValue] = {META_EVENT_MAP: overrides} if overrides else {}
        refs: list[SourceRef] = []
        for run in reversed(runs):
            with self._lock:
                last = self._finished.get(run.id)
            if last is None:
                last = self._events.last_seq(run.id)
                if run.status in TERMINAL_STATUSES:
                    with self._lock:
                        self._finished[run.id] = last
            refs.append(SourceRef(ref=run.id, size=last, mtime=None, meta=meta))
        return refs

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        """워터마크(``cursor.offset`` = seq) 뒤 이벤트를 예산만큼 읽는다."""
        event_map = self._map.with_overrides(overrides_of(ref.meta.get(META_EVENT_MAP)))
        learned_raw = cursor.state.get(SESSIONS_STATE)
        learned: dict[str, str] = (
            {str(k): str(v) for k, v in learned_raw.items()}
            if isinstance(learned_raw, Mapping)
            else {}
        )
        cwd_raw = cursor.state.get(CWD_STATE)
        cwd = cwd_raw if isinstance(cwd_raw, str) else ""
        node_sessions = _node_sessions(self._runs.list_node_runs(ref.ref))
        offset = cursor.offset
        used = 0
        records: list[RawRecord] = []
        exhausted = False
        while not exhausted and used < budget:
            page = self._events.list(ref.ref, since_seq=offset, limit=self._page)
            for event in page:
                data = event.model_dump(mode="json")
                path = [str(p) for p in event.node_path]
                rule = event_map.rule_for(event.type)
                pointer = rule.get("session_from")
                if isinstance(pointer, str) and path:
                    announced = json_pointer(data, pointer)
                    if isinstance(announced, str) and announced:
                        learned[_key(path)] = announced
                cwd_pointer = rule.get("cwd_from")
                if isinstance(cwd_pointer, str):
                    found_cwd = json_pointer(data, cwd_pointer)
                    if isinstance(found_cwd, str) and found_cwd:
                        cwd = found_cwd
                meta: dict[str, JsonValue] = {
                    **ref.meta,
                    META_SESSION: _session_for(path, learned, node_sessions),
                    "thread": _key(path),
                }
                if cwd:
                    meta[META_CWD] = cwd
                records.append(RawRecord(origin=ref.ref, offset=event.seq, data=data, meta=meta))
                offset = event.seq
                used += _event_size(data)
                if used >= budget:
                    break
            else:
                exhausted = len(page) < self._page
        state: dict[str, JsonValue] = {SESSIONS_STATE: dict(learned)} if learned else {}
        if cwd:
            state[CWD_STATE] = cwd
        return ReadResult(
            records=records,
            cursor=Cursor(offset=offset, state=state),
            read_bytes=used,
            exhausted=exhausted,
        )


def _node_sessions(node_runs: Sequence[NodeRun]) -> dict[str, str]:
    out: dict[str, str] = {}
    for node_run in node_runs:  # 시작 순 — 뒤 시도가 이긴다
        if node_run.backend_session_id:
            out[node_run.node_id] = node_run.backend_session_id
    return out


def _string_tuple(value: str) -> tuple[str, ...]:
    return (value,) if value else ()


class PlatformRunsClassifier:
    """실행 이벤트 한 행 → 초안(대응표 규칙). 행 단위 무상태(F-7).

    Args:
        event_map: 기본 대응표(없으면 패키지 데이터). 행의 ``SourceRef.meta.event_map``이 덮어쓴다.
        title_chars: 제목 최대 글자 수.
        inferred_evidence: 소요 시간으로 계산한 시작 이벤트의 ``evidence``.
    """

    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id=CLASSIFIER_ID,
        formats=[CLASSIFIER_ID],
        title="플랫폼 실행 이벤트",
        description="실행 이벤트 형식 → 범주·필드 대응표(데이터)로 분류한다.",
    )

    def __init__(
        self,
        event_map: EventMap | None = None,
        *,
        title_chars: int = DEFAULT_TITLE_CHARS,
        inferred_evidence: str = "inferred",
    ) -> None:
        self._map = event_map if event_map is not None else load_default_event_map()
        self._title_chars = title_chars
        self._inferred = inferred_evidence
        self._merged: dict[str, EventMap] = {}
        self._lock = threading.Lock()

    def _effective(self, overrides: Mapping[str, Mapping[str, Any]]) -> EventMap:
        if not overrides:
            return self._map
        key = json.dumps(overrides, sort_keys=True, ensure_ascii=False, default=str)
        with self._lock:
            found = self._merged.get(key)
            if found is None:
                if len(self._merged) > 16:
                    self._merged.clear()
                found = self._merged[key] = self._map.with_overrides(overrides)
        return found

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> builtins.list[LogEventDraft]:
        data = record.data
        if not isinstance(data, Mapping):
            raise ValueError("실행 이벤트가 객체가 아닙니다")
        event = RunEvent.model_validate(data)
        event_map = self._effective(overrides_of(ctx.ref.meta.get(META_EVENT_MAP)))
        rule = event_map.rule_for(event.type)
        if rule.skip:
            return []
        session = record.meta.get(META_SESSION)
        cwd = record.meta.get(META_CWD)
        drafts = self._drafts(
            event,
            data,
            rule,
            session if isinstance(session, str) else "",
            event_map.fallback_category,
        )
        if isinstance(cwd, str) and cwd:
            drafts = [replace(d, cwd=cwd) for d in drafts]
        return drafts

    def _drafts(
        self,
        event: RunEvent,
        data: Mapping[str, Any],
        rule: EventRule,
        session: str,
        fallback: str,
    ) -> builtins.list[LogEventDraft]:
        path = tuple(str(p) for p in event.node_path)
        thread = _key(path)
        names = names_for(data, thread)

        def value(name: str) -> str:
            return resolve(rule.get(name), data, names)

        call_id = value("call_id")
        correlation: dict[str, str | list[str]] = {}
        if session:
            correlation["session"] = session
        if call_id:
            correlation["call_id"] = call_id
        extra = rule.get("correlation")
        if isinstance(extra, Mapping):
            for basis, spec in extra.items():
                found = render(spec, data, names) if isinstance(spec, str) else ""
                if found:
                    correlation[str(basis)] = found
        tags = rule.get("tags")
        title = value("title") or event.type
        if len(title) > self._title_chars:
            title = title[: self._title_chars - 1] + "…"
        draft = LogEventDraft(
            category=value("category") or fallback,
            title=title,
            stage=value("stage") or "info",
            status=value("status"),
            thread=thread,
            role=value("role"),
            actor=event.actor or "",
            from_=_string_tuple(value("from")),
            to=_string_tuple(value("to")),
            via=value("via"),
            tool=value("tool"),
            call_id=call_id,
            message_id=value("message_id"),
            session=session,
            model=value("model"),
            run_id=event.run_id,
            node_path=path,
            time=event.ts,
            evidence=event.evidence,
            tags=tuple(str(t) for t in tags) if isinstance(tags, list) else (),
            correlation=correlation,
            detail=dict(event.payload),
            raw=event.raw,
            usage=_usage(rule, data, value("message_id"), value("model"), event),
            agent=(
                LogLane(
                    id=thread,
                    label=event.actor or path[-1],
                    parent_id=_key(path[:-1]) or None,
                )
                if path
                else None
            ),
        )
        duration = _duration_ms(rule, data)
        if duration is None:
            return [draft]
        span_id = call_id or f"{event.run_id}:{event.seq}"
        span_corr = {**correlation, "call_id": correlation.get("call_id", span_id)}
        start = replace(
            draft,
            stage="start",
            status="",
            call_id=span_id,
            time=event.ts - duration / 1000.0,
            evidence=self._inferred,
            correlation=span_corr,
            usage=None,
        )
        end = replace(draft, stage="complete", call_id=span_id, correlation=span_corr)
        return [start, end]


def _duration_ms(rule: EventRule, data: Mapping[str, Any]) -> float | None:
    pointer = rule.get("duration_ms")
    if not isinstance(pointer, str):
        return None
    found = json_pointer(data, pointer)
    if isinstance(found, bool) or not isinstance(found, int | float) or found < 0:
        return None
    return float(found)


def _usage(
    rule: EventRule, data: Mapping[str, Any], message_id: str, model: str, event: RunEvent
) -> TokenSample | None:
    spec = rule.get("usage")
    if not isinstance(spec, Mapping):
        return None
    values: dict[str, int] = {}
    for key in TOKEN_KEYS:
        pointer = spec.get(key)
        found = json_pointer(data, pointer) if isinstance(pointer, str) else None
        if isinstance(found, int) and not isinstance(found, bool) and found >= 0:
            values[key] = found
    if not values:
        return None
    attempt = event.attempt or 1
    return TokenSample(
        thread=_key([str(p) for p in event.node_path]),
        message_id=message_id or f"{event.run_id}:{_key(event.node_path)}:{attempt}",
        model=model,
        time=event.ts,
        **values,
    )


@dataclass(frozen=True)
class PlatformRunsLogSource:
    """``logs.sources`` 포트 항목: 출처 + 분류기."""

    source: PlatformRunsSource
    classifier: PlatformRunsClassifier


def platform_runs(
    runs: RunReader,
    events: EventReader,
    *,
    event_map: EventMap | None = None,
    source_id: str = SOURCE_ID,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> PlatformRunsLogSource:
    """출처와 분류기를 같은 기본 대응표로 만든다."""
    found = event_map if event_map is not None else load_default_event_map()
    return PlatformRunsLogSource(
        source=PlatformRunsSource(
            runs, events, event_map=found, source_id=source_id, page_size=page_size
        ),
        classifier=PlatformRunsClassifier(found),
    )
