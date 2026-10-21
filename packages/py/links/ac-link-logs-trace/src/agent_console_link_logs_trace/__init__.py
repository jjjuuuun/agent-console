"""agent-console-link-logs-trace: 로그·추적 연동 모듈(design §4R.8, R8.3·R8.6).

공개 API:
    - ``build_log_trace(events) -> Trace``: 세션 로그 이벤트로 위임 흐름(순수 함수).
    - ``module``(``LogsTraceLink``): entry point ``agent_console.server_modules``의
      ``link-logs-trace``.
    - 포트(``ports``): 받음 ``LOGS_QUERY``(필수).
    - HTTP 없이 쓰는 부품: ``LogTraceViews``(색인에서 세션 이벤트를 읽어 흐름을 만든다).
    - ``build_router``: ``/logs/sessions/{session}/trace``.
"""

from __future__ import annotations

from .build import DEFAULT_LINK_KEYS, SPAN_KIND_THREAD, build_log_trace, thread_span_id
from .module import ERROR_MAP, MODULE_ID, WEB_ROLES, LogsTraceLink, module
from .ports import LOGS_QUERY, LogEventReader
from .routes import build_router
from .settings import DEFAULT_MAX_EVENTS, LogTraceSettings
from .views import PAGE_SIZE, LogTraceViews, SessionNotFoundError

__all__ = [
    "DEFAULT_LINK_KEYS",
    "DEFAULT_MAX_EVENTS",
    "ERROR_MAP",
    "LOGS_QUERY",
    "MODULE_ID",
    "PAGE_SIZE",
    "SPAN_KIND_THREAD",
    "WEB_ROLES",
    "LogEventReader",
    "LogTraceSettings",
    "LogTraceViews",
    "LogsTraceLink",
    "SessionNotFoundError",
    "build_log_trace",
    "build_router",
    "module",
    "thread_span_id",
]
