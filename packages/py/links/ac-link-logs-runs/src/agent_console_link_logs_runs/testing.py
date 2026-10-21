"""테스트·예제용 도우미(공개, 운영 코드에서 쓰지 않는다).

- ``MemoryRunRecords``: ``runs.reader``(``.runs``)·``runs.events``(``.events``) 모양을 만족하는
  메모리 실행 기록. 실행 모듈(``mod-runs``)이나 저장소 패키지 없이 출처·경로를 시험할 때 쓴다.
- ``run_record``·``run_event``: 짧은 Run·RunEvent 만들기.
- ``PlatformRunsRig``: 실행 기록 + ``platform-runs`` 출처 + 메모리 색인 + 수집기 한 벌.
- ``runs_module``: ``runs.reader``·``runs.events``를 주는 작은 모듈(``mod-runs`` 대신).
- ``LocalLogs``·``local_logs_module``: ``logs.ingest``·``logs.query``를 메모리 색인으로 주는 작은
  모듈(``mod-logs`` 대신, 수집 예약은 바로 수집). 단독 실행이 ``--with`` 없이 실행되면 이것과 빈
  ``runs_module``을 붙인다.
"""

from __future__ import annotations

import builtins
import threading
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

from agent_console_contracts import NodeRun, Run, RunEvent, RunStatus
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogEventPage,
    LogScanReport,
    LogSettings,
    LogSourceSetting,
)
from agent_console_logs import (
    LogClassifier,
    LogFilter,
    LogIndex,
    LogIngestor,
    LogRegistries,
    LogSource,
    query_context,
)
from agent_console_logs.testing import MemoryLogIndex
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import LOG_SOURCES, LOGS_INGEST, LOGS_QUERY, RUNS_EVENTS, RUNS_READER
from .source import SOURCE_ID, PlatformRunsLogSource, platform_runs

__all__ = [
    "LOCAL_LOGS_ID",
    "LOCAL_RUNS_ID",
    "LocalLogs",
    "MemoryEvents",
    "MemoryRunRecords",
    "MemoryRuns",
    "PlatformRunsRig",
    "local_logs_module",
    "run_event",
    "run_record",
    "runs_module",
]

LOCAL_RUNS_ID = "memory-runs"
LOCAL_LOGS_ID = "memory-logs"


class MemoryRuns:
    """메모리 Run·NodeRun(``RunReader``)."""

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._nodes: dict[str, builtins.list[NodeRun]] = {}

    def save(self, run: Run) -> None:
        self._runs[run.id] = run

    def save_node_run(self, node_run: NodeRun) -> None:
        self._nodes.setdefault(node_run.run_id, []).append(node_run)

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(
        self,
        *,
        graph_id: str | None = None,
        status: Iterable[RunStatus] | None = None,
        conversation_id: str | None = None,
        agent: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]:
        """최신 생성순(``agent``는 보지 않는다)."""
        wanted = set(status) if status is not None else None
        rows = [
            r
            for r in self._runs.values()
            if (graph_id is None or r.graph_id == graph_id)
            and (wanted is None or r.status in wanted)
            and (conversation_id is None or r.conversation_id == conversation_id)
        ]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit] if limit is not None else rows

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        return list(self._nodes.get(run_id, []))


class MemoryEvents:
    """메모리 실행 이벤트(``EventReader``)."""

    def __init__(self) -> None:
        self._events: dict[str, builtins.list[RunEvent]] = {}

    def append(self, *events: RunEvent) -> None:
        for event in events:
            rows = self._events.setdefault(event.run_id, [])
            rows.append(event)
            rows.sort(key=lambda e: e.seq)

    def list(
        self, run_id: str, *, since_seq: int = 0, limit: int | None = None
    ) -> builtins.list[RunEvent]:
        rows = [e for e in self._events.get(run_id, []) if e.seq > since_seq]
        return rows[:limit] if limit is not None else rows

    def last_seq(self, run_id: str) -> int:
        rows = self._events.get(run_id)
        return rows[-1].seq if rows else 0


class MemoryRunRecords:
    """``runs``(``MemoryRuns``)·``events``(``MemoryEvents``) 묶음."""

    def __init__(self) -> None:
        self.runs = MemoryRuns()
        self.events = MemoryEvents()


def run_record(
    run_id: str = "r1", *, status: RunStatus = "completed", created_at: float = 1.0
) -> Run:
    """짧은 Run(그래프 ``g``, 입력 없음)."""
    return Run(
        id=run_id,
        graph_id="g",
        graph_version="v",
        status=status,
        input={},
        origin="api",
        created_at=created_at,
    )


def run_event(
    seq: int,
    type: str,
    payload: Mapping[str, Any] | None = None,
    path: Sequence[str] = ("a",),
    *,
    run_id: str = "r1",
    ts: float | None = None,
    actor: str | None = "pl",
) -> RunEvent:
    """짧은 RunEvent(시각 기본 ``100 + seq``, 노드 경로가 없으면 Run 수준)."""
    return RunEvent(
        event_id=f"{run_id}-{seq}",
        run_id=run_id,
        seq=seq,
        ts=100.0 + seq if ts is None else ts,
        node_path=list(path),
        attempt=1 if path else None,
        actor=actor if path else None,
        type=type,
        payload=dict(payload or {}),
    )


class PlatformRunsRig:
    """실행 기록 + ``platform-runs`` 출처 + 메모리 색인 + 수집기.

    Args:
        budget_bytes: 수집 한 번의 읽기 예산.
        page_size: 출처가 한 번에 읽는 이벤트 수.
    """

    def __init__(self, *, budget_bytes: int = 8_000_000, page_size: int = 500) -> None:
        self.records = MemoryRunRecords()
        self.item: PlatformRunsLogSource = platform_runs(
            self.records.runs, self.records.events, page_size=page_size
        )
        self.index = MemoryLogIndex()
        self.ingestor = LogIngestor(self.index, LogRegistries(), budget_bytes=budget_bytes)
        self.ingestor.add_runtime_source(self.item.source, classifier=self.item.classifier)

    def scan(self, config: Mapping[str, Any] | None = None) -> LogScanReport:
        """한 번 수집한다(``config`` = ``logs.sources[id=platform-runs].config``)."""
        settings = (
            LogSettings(sources=[LogSourceSetting(id=SOURCE_ID, config=dict(config))])
            if config is not None
            else None
        )
        return self.ingestor.scan(settings)


def runs_module(records: MemoryRunRecords, module_id: str = LOCAL_RUNS_ID) -> Module:
    """``runs.reader``·``runs.events``를 메모리 실행 기록으로 주는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUNS_READER, records.runs)
        ctx.provide(RUNS_EVENTS, records.events)
        return ModuleParts()

    return fake_module(
        module_id, kind="testing", provides=[RUNS_READER, RUNS_EVENTS], on_build=build
    )


class LocalLogs:
    """``logs.ingest``·``logs.query``의 작은 구현(메모리 색인 + 수집기, 설정 없음).

    Args:
        index: 색인(없으면 메모리).
        registries: 출처·분류기 레지스트리(없으면 빈 것 — 런타임 출처만).
    """

    def __init__(
        self, index: LogIndex | None = None, registries: LogRegistries | None = None
    ) -> None:
        self.index: LogIndex = index if index is not None else MemoryLogIndex()
        self.ingestor = LogIngestor(self.index, registries or LogRegistries())
        self._lock = threading.Lock()

    def add_runtime_source(self, source: LogSource, *, classifier: LogClassifier) -> None:
        self.ingestor.add_runtime_source(source, classifier=classifier)

    def request_scan(
        self, source_ids: Collection[str] | None = None, *, ref_hint: str | None = None
    ) -> None:
        """바로 수집한다(같은 스레드에서 막힌다 — 개발·테스트용)."""
        with self._lock:
            self.ingestor.scan(source_ids=source_ids)

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage:
        return self.index.query_events(flt, query_context(None), with_total=with_total)

    def aggregate(self, request: LogAggregateRequest) -> builtins.list[LogAggregateRow]:
        return self.index.aggregate(request, query_context(None))


def local_logs_module(module_id: str = LOCAL_LOGS_ID, *, logs: LocalLogs | None = None) -> Module:
    """``logs.ingest``·``logs.query`` 제공 모듈(``LocalLogs``).

    시작 때 ``logs.sources``(런타임 출처)를 붙인다.
    """
    found = logs if logs is not None else LocalLogs()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(LOGS_INGEST, found)
        ctx.provide(LOGS_QUERY, found)

        async def start() -> None:
            for item in ctx.ports(LOG_SOURCES):
                found.add_runtime_source(item.source, classifier=item.classifier)

        return ModuleParts(startup=[start])

    return fake_module(
        module_id,
        kind="testing",
        provides=[LOGS_INGEST, LOGS_QUERY],
        optional=[LOG_SOURCES],
        on_build=build,
    )
