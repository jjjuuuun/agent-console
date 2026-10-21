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
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from agent_console_contracts import RunEvent, TokenRollupRow
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

FINISHED_RUN_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "interrupted"}
)
"""더 바뀌지 않는 Run 상태(계약 ``RunStatus`` 중 끝난 것)."""


@dataclass
class _Entry:
    events: list[RunEvent] = field(default_factory=list)
    watermarks: dict[str, int] = field(default_factory=dict)
    records: list[UsageRecord] = field(default_factory=list)
    finished: bool = False


class IncrementalTokenRollups:
    """``rollups(limit=, tz=)``: 최근 Run ``limit``개의 토큰 집계(증분 캐시).

    Args:
        runs: Run·NodeRun 조회.
        events: 이벤트 조회(``list(run_id, since_seq=, type_prefix=)``).
        event_types: 집계 재료 이벤트 형식.
    """

    def __init__(
        self,
        runs: RollupRunSource,
        events: RollupEventSource,
        *,
        event_types: Sequence[str] = USAGE_EVENT_TYPES,
    ) -> None:
        self._runs = runs
        self._events = events
        self._types = tuple(event_types)
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}
        self._dirty: set[str] = set()

    def mark(self, event: Any) -> None:
        """이 이벤트의 Run을 다시 읽게 표시한다(``runs.event`` 구독)."""
        run_id = getattr(event, "run_id", None)
        if isinstance(run_id, str):
            with self._lock:
                self._dirty.add(run_id)

    def invalidate(self) -> None:
        """캐시를 전부 버린다(기록이 줄어드는 작업 뒤)."""
        with self._lock:
            self._entries.clear()
            self._dirty.clear()

    def rollups(self, *, limit: int, tz: tzinfo) -> list[TokenRollupRow]:
        """최근 Run ``limit``개 범위의 집계(일 단위는 ``tz`` 기준). 막히는 호출이다.

        범위는 루트 Run만 센 최근 ``limit``개다(저장소의 ``root_only``로 자식 Run을 먼저 걸러
        ``limit``이 자식 Run에 먹히지 않는다, 5.2R.32).
        """
        runs = [
            run for run in self._runs.list(root_only=True, limit=limit) if counts_toward_usage(run)
        ]
        records: list[UsageRecord] = []
        with self._lock:
            dirty = set(self._dirty)
            self._dirty.difference_update(r.id for r in runs)
            entries = dict(self._entries)
        fresh: dict[str, _Entry] = {}
        for run in runs:
            entry = entries.get(run.id)
            if entry is None or not entry.finished or run.id in dirty:
                entry = self._refresh(run, entry)
            fresh[run.id] = entry
            records.extend(entry.records)
        with self._lock:
            self._entries = fresh  # 범위 밖 Run은 버린다
        return token_rollup(records, tz=tz)

    def _refresh(self, run: Any, entry: _Entry | None) -> _Entry:
        # 사본에 더한다(동시에 부른 다른 집계가 같은 항목을 읽고 있을 수 있다)
        current = (
            _Entry(events=list(entry.events), watermarks=dict(entry.watermarks))
            if entry is not None
            else _Entry()
        )
        for type_name in self._types:
            since = current.watermarks.get(type_name, 0)
            new = self._events.list(run.id, since_seq=since, type_prefix=type_name)
            if new:
                current.events.extend(new)
                current.watermarks[type_name] = max(e.seq for e in new)
        current.events.sort(key=lambda e: e.seq)
        current.records = usage_records(run, self._runs.list_node_runs(run.id), current.events)
        current.finished = run.status in FINISHED_RUN_STATUSES
        return current


__all__ = ["FINISHED_RUN_STATUSES", "USAGE_EVENT_TYPES", "IncrementalTokenRollups"]
