"""플랫폼 실행분 토큰 집계의 증분 캐시(``usage.token_rollups``, design §3R.5·E-14).

- Run마다 사용량 재료(``agent.session_started``·``agent.subagent_stopped`` 이벤트)를 모으고,
  마지막으로 반영한 이벤트 seq(워터마크) **뒤만** 다시 읽는다.
- 끝난 Run(``completed``·``failed``·``cancelled``·``interrupted``)의 기록은 그 Run에 새 이벤트가
  생기기(``runs.event`` 구독 → ``mark``) 전까지 다시 읽지 않는다. 끝나지 않은 Run은 매번
  증분만 읽는다.
- 루트 Run만 센다(``ac-usage.counts_toward_usage``): 자식 Run(중첩 팀)의 사용량은 부른 부모 노드의
  NodeRun ``usage``로 루트 Run에 이미 들어 있다(design §5R.7, 이중 집계 방지).
- 메모리 캐시라 재시작하면 다시 계산한다. 목록 범위(루트 Run 최근 ``limit``개, ``root_only``) 밖으로
  나간 Run은 버린다.
  이벤트 보존 정리(prune)처럼 기록이 줄어드는 작업 뒤에는 ``invalidate``로 전부 버린다.
- 출처(요청 11/08): 기본 출처(앱 기록, 키 ``app``) + 추가 출처(``extra`` — 예: 등록 프로젝트 기록
  DB마다 하나). 캐시·워터마크는 ``(출처 키, run_id)``로 따로 둔다. ``project_id``가 없으면 "계정
  전체"(모든 출처 합, 최근 ``limit``개), 있으면 "이 프로젝트"(그 프로젝트 출처 + 앱 기록 중
  ``Run.project_id``가 같은 옛 Run). 추가 출처 하나가 실패하면 경고하고 그것만 뺀다. 계정 전체 집계
  때 사라진 출처(보관·삭제된 프로젝트)의 캐시는 버린다.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from agent_console_contracts import Run, RunEvent, TokenRollupRow
from agent_console_usage import (
    RollupEventSource,
    RollupRunSource,
    UsageRecord,
    counts_toward_usage,
    token_rollup,
    usage_records,
)

USAGE_EVENT_TYPES: tuple[str, ...] = ("agent.session_started", "agent.subagent_stopped")
"""집계 재료가 되는 이벤트 형식(``ac-usage.usage_records``가 읽는 것)."""

_log = logging.getLogger(__name__)

APP_SOURCE_KEY = "app"
"""기본 출처(생성자 ``runs``·``events``)의 캐시 키."""

FINISHED_RUN_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "interrupted"}
)
"""더 바뀌지 않는 Run 상태(계약 ``RunStatus`` 중 끝난 것)."""


@dataclass(frozen=True)
class RollupSource:
    """토큰 집계 출처 하나(예: 프로젝트 기록 DB).

    Attributes:
        key: 캐시·워터마크 이름공간(출처마다 달라야 한다, 예 ``project:p1``). ``app``은 기본 출처.
        runs: 그 출처의 Run·NodeRun 조회.
        events: 그 출처의 이벤트 조회.
    """

    key: str
    runs: RollupRunSource
    events: RollupEventSource


ExtraSources = Callable[[str | None], Iterable[RollupSource]]
"""``project_id`` → 추가 출처들. None = 전부(계정 전체), 문자열 = 그 프로젝트 출처만."""


def _no_extra(project_id: str | None) -> Iterable[RollupSource]:
    return ()


@dataclass
class _Entry:
    events: list[RunEvent] = field(default_factory=list)
    watermarks: dict[str, int] = field(default_factory=dict)
    records: list[UsageRecord] = field(default_factory=list)
    finished: bool = False


class IncrementalTokenRollups:
    """``rollups(limit=, tz=, project_id=)``: 최근 Run ``limit``개의 토큰 집계(증분 캐시).

    Args:
        runs: 기본 출처(앱 기록) Run·NodeRun 조회.
        events: 기본 출처 이벤트 조회(``list(run_id, since_seq=, type_prefix=)``).
        event_types: 집계 재료 이벤트 형식.
        extra: 추가 출처(부를 때마다 다시 읽는다). 기본은 없음(앱 기록만).
    """

    def __init__(
        self,
        runs: RollupRunSource,
        events: RollupEventSource,
        *,
        event_types: Sequence[str] = USAGE_EVENT_TYPES,
        extra: ExtraSources = _no_extra,
    ) -> None:
        self._base = RollupSource(APP_SOURCE_KEY, runs, events)
        self._extra = extra
        self._types = tuple(event_types)
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._dirty: set[str] = set()

    def mark(self, event: Any) -> None:
        """이 이벤트의 Run을 다시 읽게 표시한다(``runs.event`` 구독, 출처와 무관하게 run_id로)."""
        run_id = getattr(event, "run_id", None)
        if isinstance(run_id, str):
            with self._lock:
                self._dirty.add(run_id)

    def invalidate(self) -> None:
        """캐시를 전부 버린다(기록이 줄어드는 작업 뒤)."""
        with self._lock:
            self._entries.clear()
            self._dirty.clear()

    def rollups(
        self, *, limit: int, tz: tzinfo, project_id: str | None = None
    ) -> list[TokenRollupRow]:
        """최근 Run ``limit``개 범위의 집계(일 단위는 ``tz`` 기준). 막히는 호출이다.

        범위는 루트 Run만 센 최근 ``limit``개다(저장소의 ``root_only``로 자식 Run을 먼저 걸러
        ``limit``이 자식 Run에 먹히지 않는다, 5.2R.32). 출처마다 ``limit``개를 읽어 생성 시각
        내림차순으로 합친 뒤 ``limit``개로 자른다.

        Args:
            project_id: None이면 계정 전체(모든 출처). 주면 그 프로젝트 출처 + 앱 기록 중 같은
                ``project_id``의 Run만.
        """
        sources = [self._base, *self._extra_sources(project_id)]
        candidates: list[tuple[RollupSource, Run]] = []
        for source in sources:
            try:
                listed = source.runs.list(root_only=True, limit=limit)
            except Exception:
                if source is self._base:
                    raise
                _log.warning("토큰 집계 출처를 읽지 못했습니다: %s", source.key, exc_info=True)
                continue
            for run in listed:
                if not counts_toward_usage(run):
                    continue
                if source is self._base and project_id is not None and run.project_id != project_id:
                    continue
                candidates.append((source, run))
        candidates.sort(key=lambda item: item[1].created_at, reverse=True)
        candidates = candidates[:limit]

        with self._lock:
            dirty = set(self._dirty)
            self._dirty.difference_update(run.id for _, run in candidates)
            entries = dict(self._entries)
        fresh: dict[tuple[str, str], _Entry] = {}
        records: list[UsageRecord] = []
        for source, run in candidates:
            key = (source.key, run.id)
            entry = entries.get(key)
            if entry is None or not entry.finished or run.id in dirty:
                try:
                    entry = self._refresh(source, run, entry)
                except Exception:
                    if source is self._base:
                        raise
                    _log.warning("토큰 집계 출처를 읽지 못했습니다: %s", source.key, exc_info=True)
                    if entry is None:
                        continue
            fresh[key] = entry
            records.extend(entry.records)
        with self._lock:
            if project_id is None:
                self._entries = fresh  # 범위 밖 Run·사라진 출처는 버린다
            else:
                # 프로젝트 범위 집계는 그 출처 캐시만 정리한다(앱 기록·다른 프로젝트 캐시는 그대로)
                scoped = {s.key for s in sources if s is not self._base}
                kept = {k: v for k, v in self._entries.items() if k[0] not in scoped}
                kept.update(fresh)
                self._entries = kept
        return token_rollup(records, tz=tz)

    def _extra_sources(self, project_id: str | None) -> list[RollupSource]:
        try:
            return [s for s in self._extra(project_id) if s.key != APP_SOURCE_KEY]
        except Exception:
            _log.warning("토큰 집계 추가 출처 목록을 읽지 못했습니다", exc_info=True)
            return []

    def _refresh(self, source: RollupSource, run: Run, entry: _Entry | None) -> _Entry:
        # 사본에 더한다(동시에 부른 다른 집계가 같은 항목을 읽고 있을 수 있다)
        current = (
            _Entry(events=list(entry.events), watermarks=dict(entry.watermarks))
            if entry is not None
            else _Entry()
        )
        for type_name in self._types:
            since = current.watermarks.get(type_name, 0)
            new = source.events.list(run.id, since_seq=since, type_prefix=type_name)
            if new:
                current.events.extend(new)
                current.watermarks[type_name] = max(e.seq for e in new)
        current.events.sort(key=lambda e: e.seq)
        current.records = usage_records(run, source.runs.list_node_runs(run.id), current.events)
        current.finished = run.status in FINISHED_RUN_STATUSES
        return current


__all__ = [
    "APP_SOURCE_KEY",
    "FINISHED_RUN_STATUSES",
    "USAGE_EVENT_TYPES",
    "ExtraSources",
    "IncrementalTokenRollups",
    "RollupSource",
]
