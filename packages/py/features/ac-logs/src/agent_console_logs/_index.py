"""로그 색인 프로토콜(design §4R.5·§4R.6). 구현: `testing.MemoryLogIndex`, SQLite(4R.5).

질의 의미는 `agent_console_logs.query`의 순수 함수가 정의한다. 다른 구현은
`testing.LogIndexContractTests`(계약 테스트 묶음)를 통과해야 한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

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

from ._draft import AgentInfo
from ._filter import LogFilter, QueryContext
from ._values import JsonValue

__all__ = [
    "DEFAULT_MAX_EVIDENCE",
    "DEFAULT_TIMELINE_LIMIT",
    "BatchResult",
    "IndexBatch",
    "IndexRecord",
    "LogIndex",
    "StoredCursor",
]

DEFAULT_MAX_EVIDENCE = 1000
"""상세의 근거 후보 상한(넘으면 `truncated`)."""

DEFAULT_TIMELINE_LIMIT = 5000
"""타임라인 이벤트 상한(넘으면 앞부분만, `truncated`)."""


@dataclass(frozen=True, slots=True)
class StoredCursor:
    """`log_cursors` 한 행: 출처 단위의 읽은 위치와 출처 상태."""

    source: str
    ref: str
    offset: int = 0
    size: int | None = None
    mtime: float | None = None
    state: Mapping[str, JsonValue] = field(default_factory=dict)
    updated_at: float | None = None


@dataclass(frozen=True, slots=True)
class IndexRecord:
    """색인에 넣을 이벤트 하나.

    Attributes:
        event: 완성된 이벤트(가림·크기 제한 적용 후). `seq`는 무시하고 색인이 매긴다.
        identity: 중복 판정 키. 같은 `event.uid`(= sha256(identity)[:24])가 있으면 넣지 않는다.
        usage: 토큰 표본. 키 (event.source, sample.thread, sample.message_id). 같은 키가 다시 오면
            output이 크거나 같을 때만 바꾼다(F-8). 이벤트가 중복이어도 표본 규칙은 적용한다.
        agent: thread 표시 이름·부모. 값이 있는 필드만 덮어쓴다.
    """

    event: LogEvent
    identity: str
    usage: TokenSample | None = None
    agent: AgentInfo | None = None


@dataclass(frozen=True, slots=True)
class IndexBatch:
    """한 트랜잭션으로 쓸 묶음: 이벤트 + 커서 갱신(커서는 이벤트와 함께 원자적으로)."""

    records: Sequence[IndexRecord] = ()
    cursors: Sequence[StoredCursor] = ()


@dataclass(frozen=True, slots=True)
class BatchResult:
    """쓰기 결과."""

    inserted: int
    max_seq: int | None


@runtime_checkable
class LogIndex(Protocol):
    """로그 색인. 쓰기(수집기)와 읽기(질의)를 한 객체가 맡는다. 스레드 안전해야 한다."""

    # ---------------------------------------------------------------- 쓰기·커서

    def write(self, batch: IndexBatch) -> BatchResult:
        """묶음을 한 트랜잭션으로 쓴다(이벤트 `INSERT OR IGNORE`, 태그·링크·에이전트·토큰·커서)."""
        ...

    def get_cursor(self, source: str, ref: str) -> StoredCursor | None:
        """저장된 커서(없으면 None)."""
        ...

    def list_cursors(self, source: str) -> list[StoredCursor]:
        """출처의 모든 커서(ref 순)."""
        ...

    def max_seq(self) -> int | None:
        """지금 최대 seq(비었으면 None)."""
        ...

    def prune(self, before: float) -> int:
        """시각(없으면 색인 시각)이 `before`보다 이른 이벤트·토큰 표본을 지운다.

        Returns:
            지운 이벤트 수.
        """
        ...

    # ---------------------------------------------------------------- 질의

    def query_events(
        self, flt: LogFilter, ctx: QueryContext, *, with_total: bool = False
    ) -> LogEventPage:
        """필터 목록(키셋 페이지, `detail`·`raw` 없음)."""
        ...

    def get_event(
        self,
        uid: str,
        ctx: QueryContext,
        *,
        max_detail_bytes: int | None = None,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
    ) -> LogEventDetail | None:
        """상세(본문·관련 이벤트·근거 연결·토큰 표본). 없으면 None."""
        ...

    def list_sessions(self, flt: LogFilter, ctx: QueryContext) -> list[LogSessionSummary]:
        """세션 요약(마지막 시각 내림차순, `flt.limit`개)."""
        ...

    def timeline(
        self,
        session: str,
        ctx: QueryContext,
        *,
        flt: LogFilter | None = None,
        limit: int = DEFAULT_TIMELINE_LIMIT,
    ) -> LogTimeline | None:
        """세션의 보이는 이벤트(시각 → seq), 줄 = thread, 짝 이벤트 `duration_ms`. 없으면 None."""
        ...

    def aggregate(self, request: LogAggregateRequest, ctx: QueryContext) -> list[LogAggregateRow]:
        """집계(차원·지표는 `DIMENSIONS`·`METRICS`). 모르는 이름은 `LogQueryError`."""
        ...

    def handoffs(self, flt: LogFilter, ctx: QueryContext, *, limit: int = 40) -> HandoffMatrix:
        """from·to가 둘 다 있는 이벤트의 (from, to, via) 횟수(많은 순 `limit`개)."""
        ...

    def token_samples(self, flt: LogFilter, ctx: QueryContext) -> list[TokenSample]:
        """필터에 맞는 토큰 표본(시각순, 창 추정용)."""
        ...

    def lanes(self) -> list[LogLane]:
        """알려진 thread 표시 정보(`log_agents`, id 순)."""
        ...
