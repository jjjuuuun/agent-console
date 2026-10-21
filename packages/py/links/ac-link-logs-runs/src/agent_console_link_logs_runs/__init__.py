"""agent-console-link-logs-runs: 로그·실행 연동 모듈(design §4R.8 연동 표 첫 행, R8.1·R8.4).

공개 API:
    - ``module``(``LogsRunsLink``): entry point ``agent_console.server_modules``의
      ``link-logs-runs``.
    - 포트(``ports``): 받음 ``LOGS_INGEST``·``LOGS_QUERY``·``RUNS_READER``·``RUNS_EVENTS``(필수),
      구독 ``RUNS_EVENT``, 제공 ``LOG_SOURCES``.
    - HTTP 없이 쓰는 부품: ``PlatformRunsSource``·``PlatformRunsClassifier``(``platform_runs``로
      한 쌍), 대응표 ``EventMap``(``load_default_event_map`` — 패키지 데이터
      ``run_event_map.yaml``), ``ScanDebouncer``, ``RunLogs``(``/runs/{id}/logs`` 계산).
    - ``build_router``: ``/runs/{id}/logs``.
"""

from __future__ import annotations

from .errors import ERROR_MAP, INVALID_QUERY
from .event_map import (
    DEFAULT_FALLBACK_CATEGORY,
    EVENT_MAP_SCHEMA,
    RULE_SCHEMA,
    EventMap,
    EventRule,
    load_default_event_map,
    load_event_map,
)
from .module import (
    DEFAULT_DEBOUNCE_SECONDS,
    MODULE_ID,
    WEB_ROLES,
    LogsRunsLink,
    LogsRunsSettings,
    module,
)
from .ports import (
    LOG_SOURCES,
    LOGS_INGEST,
    LOGS_QUERY,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    EventReader,
    LogIngestLike,
    LogQueryLike,
    RunReader,
    RuntimeLogSource,
)
from .routes import build_router
from .scheduler import ScanDebouncer
from .source import (
    CLASSIFIER_ID,
    SOURCE_ID,
    SOURCE_SCHEMA,
    PlatformRunsClassifier,
    PlatformRunsLogSource,
    PlatformRunsSource,
    platform_runs,
)
from .views import RunLogs, RunNotFoundError

__all__ = [
    "CLASSIFIER_ID",
    "DEFAULT_DEBOUNCE_SECONDS",
    "DEFAULT_FALLBACK_CATEGORY",
    "ERROR_MAP",
    "EVENT_MAP_SCHEMA",
    "INVALID_QUERY",
    "LOGS_INGEST",
    "LOGS_QUERY",
    "LOG_SOURCES",
    "MODULE_ID",
    "RULE_SCHEMA",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "SOURCE_ID",
    "SOURCE_SCHEMA",
    "WEB_ROLES",
    "EventMap",
    "EventReader",
    "EventRule",
    "LogIngestLike",
    "LogQueryLike",
    "LogsRunsLink",
    "LogsRunsSettings",
    "PlatformRunsClassifier",
    "PlatformRunsLogSource",
    "PlatformRunsSource",
    "RunLogs",
    "RunNotFoundError",
    "RunReader",
    "RuntimeLogSource",
    "ScanDebouncer",
    "build_router",
    "load_default_event_map",
    "load_event_map",
    "module",
    "platform_runs",
]
