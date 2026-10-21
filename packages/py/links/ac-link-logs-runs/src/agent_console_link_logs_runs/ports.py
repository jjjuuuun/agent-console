"""link-logs-runs의 포트·토픽(이름 = 포트, design §3R.1.2·§4R.8).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``logs.ingest``: 수집 예약(``LogIngestLike.request_scan`` — 막히지 않음, 어느 스레드에서든).
- 필수 ``logs.query``: 색인 읽기(``LogQueryLike.events``·``aggregate``).
- 필수 ``runs.reader``: Run·NodeRun 조회(``RunReader`` — ``get``·``list``·``list_node_runs``).
- 필수 ``runs.events``: 실행 이벤트 조회(``EventReader`` — ``list``·``last_seq``).
- 토픽 ``runs.event``(구독): 이벤트가 생긴 Run의 수집을 예약한다(디바운스).

제공:

- ``logs.sources``(여러 제공자): 런타임 출처 ``platform-runs``(``RuntimeLogSource`` 모양 —
  ``source``·``classifier`` 속성).
"""

from __future__ import annotations

import builtins
from collections.abc import Collection, Iterable
from typing import Protocol, runtime_checkable

from agent_console_contracts import NodeRun, Run, RunEvent, RunStatus
from agent_console_contracts.logs import LogAggregateRequest, LogAggregateRow, LogEventPage
from agent_console_logs import LogClassifier, LogFilter, LogSource
from agent_console_modkit import PortKey, Topic


@runtime_checkable
class RunReader(Protocol):
    """``runs.reader`` 중 쓰는 부분."""

    def get(self, run_id: str) -> Run | None: ...

    def list(
        self,
        *,
        graph_id: str | None = None,
        status: Iterable[RunStatus] | None = None,
        conversation_id: str | None = None,
        agent: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]:
        """최신 생성순."""
        ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...


@runtime_checkable
class EventReader(Protocol):
    """``runs.events`` 중 쓰는 부분."""

    def list(
        self, run_id: str, *, since_seq: int = 0, limit: int | None = None
    ) -> builtins.list[RunEvent]:
        """``seq > since_seq``인 이벤트(seq 오름차순, 최대 ``limit``개)."""
        ...

    def last_seq(self, run_id: str) -> int:
        """마지막 seq(없으면 0)."""
        ...


@runtime_checkable
class LogIngestLike(Protocol):
    """``logs.ingest`` 중 쓰는 부분."""

    def request_scan(
        self, source_ids: Collection[str] | None = None, *, ref_hint: str | None = None
    ) -> None: ...


@runtime_checkable
class LogQueryLike(Protocol):
    """``logs.query`` 중 쓰는 부분(막히는 호출)."""

    def events(self, flt: LogFilter, *, with_total: bool = False) -> LogEventPage: ...

    def aggregate(self, request: LogAggregateRequest) -> builtins.list[LogAggregateRow]: ...


@runtime_checkable
class RuntimeLogSource(Protocol):
    """``logs.sources`` 항목 모양(출처 + 분류기)."""

    @property
    def source(self) -> LogSource: ...

    @property
    def classifier(self) -> LogClassifier: ...


class EventLike(Protocol):
    """``runs.event`` 항목 중 쓰는 부분."""

    @property
    def run_id(self) -> str: ...


LOGS_INGEST: PortKey[LogIngestLike] = PortKey("logs.ingest", "로그 수집(런타임 출처·수집 예약)")
LOGS_QUERY: PortKey[LogQueryLike] = PortKey("logs.query", "로그 색인 읽기")
RUNS_READER: PortKey[RunReader] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[EventReader] = PortKey("runs.events", "실행 이벤트 조회")
LOG_SOURCES: PortKey[RuntimeLogSource] = PortKey(
    "logs.sources", "런타임 로그 출처(출처 + 분류기)", multi=True
)
RUNS_EVENT: Topic[EventLike] = Topic("runs.event")
"""저장된 실행 이벤트(전부). 이 연동은 ``run_id``만 본다."""

__all__ = [
    "LOGS_INGEST",
    "LOGS_QUERY",
    "LOG_SOURCES",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "EventLike",
    "EventReader",
    "LogIngestLike",
    "LogQueryLike",
    "RunReader",
    "RuntimeLogSource",
]
