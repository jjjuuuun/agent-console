"""세션 로그 → 위임 흐름(``build_log_trace``)에 색인 이벤트를 넘긴다. FastAPI를 모른다."""

from __future__ import annotations

from collections.abc import Sequence

from agent_console_contracts import Trace
from agent_console_contracts.logs import LogEvent
from agent_console_logs import LogFilter

from .build import DEFAULT_LINK_KEYS, build_log_trace
from .ports import LogEventReader
from .settings import DEFAULT_MAX_EVENTS

PAGE_SIZE = 200
"""한 번에 읽는 이벤트 수(``ac-logs`` 목록 상한과 같다)."""


class SessionNotFoundError(LookupError):
    """색인에 그 세션 이벤트가 없다(404)."""

    def __init__(self, session: str) -> None:
        super().__init__(f"세션 {session}이(가) 없습니다")
        self.session = session


class LogTraceViews:
    """세션 위임 흐름 계산.

    Args:
        query: ``logs.query``(이벤트 목록).
        link_keys: 부모 연결 키(``build_log_trace`` 참고).
        max_events: 세션 하나에서 읽을 이벤트 상한.
        page_size: 한 페이지 크기.
    """

    def __init__(
        self,
        query: LogEventReader,
        *,
        link_keys: Sequence[str] = DEFAULT_LINK_KEYS,
        max_events: int = DEFAULT_MAX_EVENTS,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self._query = query
        self._link_keys = tuple(link_keys)
        self._max_events = max_events
        self._page_size = page_size

    def session_events(self, session: str) -> list[LogEvent]:
        """세션 이벤트(``seq`` 오름차순, 숨김 범주 포함 — 연결 근거는 숨김과 무관), 상한까지."""
        out: list[LogEvent] = []
        cursor: str | None = None
        while len(out) < self._max_events:
            limit = min(self._page_size, self._max_events - len(out))
            page = self._query.events(
                LogFilter(session=(session,), order="asc", limit=limit, cursor=cursor)
            )
            out.extend(page.items)
            cursor = page.next_cursor
            if not cursor or not page.items:
                break
        return out

    def trace(self, session: str) -> Trace:
        """세션 위임 흐름.

        Raises:
            SessionNotFoundError: 그 세션 이벤트가 없다.
        """
        events = self.session_events(session)
        if not events:
            raise SessionNotFoundError(session)
        return build_log_trace(events, session=session, link_keys=self._link_keys)


__all__ = ["PAGE_SIZE", "LogTraceViews", "SessionNotFoundError"]
