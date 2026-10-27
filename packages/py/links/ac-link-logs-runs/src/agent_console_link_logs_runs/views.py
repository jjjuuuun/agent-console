"""``GET /runs/{id}/logs``의 계산(FastAPI를 모른다).

그 Run의 세션 id들(NodeRun ``backend_session_id`` + 색인된 플랫폼 실행 이벤트의 ``session``)에
해당하는 **외부 세션 이벤트**를 돌려준다. 플랫폼 실행 이벤트 자체(``platform-runs`` 출처)는 실행
상세의 다른 탭에 있으므로 기본으로 빼고, 요청이 ``source``를 직접 주면 그것을 따른다.
``total``은 항상 채운다(탭 배지 수).
"""

from __future__ import annotations

from collections.abc import Collection

from agent_console_contracts.logs import LogAggregateRequest, LogEventPage
from agent_console_logs import LogFilter

from .ports import LogQueryLike, RunReader
from .scopes import run_sessions
from .source import SOURCE_ID

__all__ = ["RunLogs", "RunNotFoundError"]

SOURCE_DIMENSION = "source"
COUNT_METRIC = "events"
"""``ac-logs`` 질의 엔진의 차원·지표 이름(``agent_console_logs.DIMENSIONS``·``METRICS``)."""


class RunNotFoundError(LookupError):
    """Run이 없다(404)."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id}이(가) 없습니다")
        self.run_id = run_id


class RunLogs:
    """실행 하나의 세션 로그.

    Args:
        runs: Run·NodeRun 조회.
        logs: 색인 읽기.
        source_id: 플랫폼 실행 출처 id(기본으로 결과에서 뺀다).
    """

    def __init__(self, runs: RunReader, logs: LogQueryLike, *, source_id: str = SOURCE_ID) -> None:
        self._runs = runs
        self._logs = logs
        self._source = source_id

    def sessions(self, run_id: str) -> list[str]:
        """Run의 세션 id(정렬). Run이 없으면 ``RunNotFoundError``."""
        if self._runs.get(run_id) is None:
            raise RunNotFoundError(run_id)
        found = run_sessions(self._runs, self._logs, [run_id], source_id=self._source)
        return sorted(found)

    def _other_sources(self, sessions: Collection[str]) -> list[str]:
        rows = self._logs.aggregate(
            LogAggregateRequest(
                group_by=[SOURCE_DIMENSION],
                metric=COUNT_METRIC,
                filter={"session": sorted(sessions)},
            )
        )
        values = {row.keys.get(SOURCE_DIMENSION) for row in rows}
        return sorted(v for v in values if v and v != self._source)

    def events(self, run_id: str, flt: LogFilter, *, explicit_source: bool) -> LogEventPage:
        """그 Run 세션들의 이벤트 페이지(``total`` 채움).

        Args:
            flt: 요청 필터. ``session``을 주면 Run 세션과의 교집합만 본다.
            explicit_source: 요청이 ``source``를 직접 줬는가(아니면 플랫폼 실행 출처를 뺀다).
        """
        sessions = self.sessions(run_id)
        if flt.session:
            sessions = [s for s in sessions if s in set(flt.session)]
        if not sessions:
            return LogEventPage(items=[], total=0)
        sources = flt.source
        if not explicit_source:
            sources = tuple(self._other_sources(sessions))
            if not sources:
                return LogEventPage(items=[], total=0)
        return self._logs.events(
            flt.with_(session=tuple(sessions), source=tuple(sources)), with_total=True
        )
