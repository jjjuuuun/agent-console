"""메모리 색인. 질의 의미의 기준 구현이며 테스트·DB 없는 실행에 쓴다."""

from __future__ import annotations

import threading

from agent_console_contracts import HandoffMatrix
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogEvent,
    LogEventDetail,
    LogEventPage,
    LogLane,
    LogSessionSummary,
    LogTimeline,
    TokenSample,
)
from agent_console_logs import query as q
from agent_console_logs._filter import LogFilter, QueryContext
from agent_console_logs._index import (
    DEFAULT_MAX_EVIDENCE,
    DEFAULT_TIMELINE_LIMIT,
    BatchResult,
    IndexBatch,
    StoredCursor,
)

__all__ = ["MemoryLogIndex"]


def _out(sample: TokenSample) -> int:
    return -1 if sample.output_tokens is None else sample.output_tokens


class MemoryLogIndex:
    """`LogIndex` 메모리 구현(스레드 안전). 프로세스가 끝나면 사라진다."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, LogEvent] = {}
        self._seq = 0
        self._usage: dict[tuple[str, str, str], q.UsageRow] = {}
        self._agents: dict[str, LogLane] = {}
        self._cursors: dict[tuple[str, str], StoredCursor] = {}

    # ---------------------------------------------------------------- 쓰기

    def write(self, batch: IndexBatch) -> BatchResult:
        with self._lock:
            inserted = 0
            for record in batch.records:
                ev = record.event
                if ev.uid not in self._events:
                    self._seq += 1
                    self._events[ev.uid] = ev.model_copy(update={"seq": self._seq})
                    inserted += 1
                if record.usage is not None:
                    sample = record.usage
                    row = q.UsageRow(
                        source=ev.source,
                        session=ev.session,
                        cwd=ev.cwd,
                        repo_root=ev.repo_root,
                        sample=sample,
                    )
                    old = self._usage.get(row.key)
                    if old is None or _out(sample) >= _out(old.sample):
                        self._usage[row.key] = row
                if record.agent is not None:
                    self._merge_agent(record.agent)
            for cursor in batch.cursors:
                self._cursors[(cursor.source, cursor.ref)] = cursor
            return BatchResult(inserted=inserted, max_seq=self._seq or None)

    def _merge_agent(self, agent: LogLane) -> None:
        old = self._agents.get(agent.id)
        if old is None:
            self._agents[agent.id] = agent
            return
        self._agents[agent.id] = LogLane(
            id=agent.id,
            label=agent.label if agent.label is not None else old.label,
            parent_id=agent.parent_id if agent.parent_id is not None else old.parent_id,
        )

    def get_cursor(self, source: str, ref: str) -> StoredCursor | None:
        with self._lock:
            return self._cursors.get((source, ref))

    def list_cursors(self, source: str) -> list[StoredCursor]:
        with self._lock:
            return sorted(
                (c for (s, _r), c in self._cursors.items() if s == source), key=lambda c: c.ref
            )

    def max_seq(self) -> int | None:
        with self._lock:
            return max((e.seq for e in self._events.values()), default=None)

    def prune(self, before: float) -> int:
        with self._lock:
            old = [uid for uid, e in self._events.items() if q.effective_time(e) < before]
            for uid in old:
                del self._events[uid]
            for key in [
                k
                for k, r in self._usage.items()
                if r.sample.time is not None and r.sample.time < before
            ]:
                del self._usage[key]
            return len(old)

    # ---------------------------------------------------------------- 읽기

    def _snapshot(self) -> tuple[list[LogEvent], list[q.UsageRow]]:
        with self._lock:
            return list(self._events.values()), list(self._usage.values())

    def query_events(
        self, flt: LogFilter, ctx: QueryContext, *, with_total: bool = False
    ) -> LogEventPage:
        events, _ = self._snapshot()
        return q.page_events(events, flt, ctx, with_total=with_total)

    def get_event(
        self,
        uid: str,
        ctx: QueryContext,
        *,
        max_detail_bytes: int | None = None,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
    ) -> LogEventDetail | None:
        events, usage = self._snapshot()
        event = next((e for e in events if e.uid == uid), None)
        if event is None:
            return None
        sample = None
        if event.message_id:
            row = next(
                (r for r in usage if r.key == (event.source, event.thread, event.message_id)),
                None,
            )
            sample = row.sample if row else None
        candidates = q.evidence_candidates(event, events)[: max_evidence + 1]
        return q.event_detail(
            event,
            related=q.related_of(event, events),
            candidates=candidates,
            usage=sample,
            max_detail_bytes=max_detail_bytes,
            max_evidence=max_evidence,
        )

    def list_sessions(self, flt: LogFilter, ctx: QueryContext) -> list[LogSessionSummary]:
        events, usage = self._snapshot()
        return q.summarize_sessions(events, usage, flt, ctx)

    def timeline(
        self,
        session: str,
        ctx: QueryContext,
        *,
        flt: LogFilter | None = None,
        limit: int = DEFAULT_TIMELINE_LIMIT,
    ) -> LogTimeline | None:
        events, usage = self._snapshot()
        with self._lock:
            agents = dict(self._agents)
        return q.build_timeline(session, events, usage, agents, ctx, flt=flt, limit=limit)

    def aggregate(self, request: LogAggregateRequest, ctx: QueryContext) -> list[LogAggregateRow]:
        events, usage = self._snapshot()
        return q.aggregate_rows(request, events, usage, ctx)

    def handoffs(self, flt: LogFilter, ctx: QueryContext, *, limit: int = 40) -> HandoffMatrix:
        events, _ = self._snapshot()
        return q.handoff_matrix(events, flt, ctx, limit=limit)

    def token_samples(self, flt: LogFilter, ctx: QueryContext) -> list[TokenSample]:
        events, usage = self._snapshot()
        rows = q.usage_samples(usage, events, flt, ctx)
        return [r.sample for r in sorted(rows, key=lambda r: (r.sample.time or 0.0, r.key))]

    def lanes(self) -> list[LogLane]:
        with self._lock:
            return [self._agents[k] for k in sorted(self._agents)]
