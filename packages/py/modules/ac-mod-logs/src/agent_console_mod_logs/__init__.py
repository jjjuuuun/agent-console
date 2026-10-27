"""Agent Console 로그 기능 모듈(``mod-logs``, design §4R.8·§4R.10).

- ``module``: 서버 모듈(entry point ``agent_console.server_modules``). 경로 ``/logs…``, WS ``logs``.
- ``LogsService``: 수집 스케줄 + 질의(HTTP 없이도 쓴다, ``logs.query``·``logs.ingest`` 포트 구현).
- ``plugins.load_plugins``: 호스트 플러그인 로더(X5·X6 entry point → 묶음의 ``log_sources``·
  ``log_classifiers``).
- ``POST /logs/index/purge``(M-3): 색인 비우기(``LogPurgeRequest``·``LogPurgeResponse``,
  모듈 안 모델).
- ``storage``: 마이그레이션 계보 ``logs``와 색인 열기(``open_log_storage``).
- ``load_dashboard_templates``: 대시보드 템플릿(패키지 데이터 또는 설치자 폴더).
"""

from __future__ import annotations

from .errors import INVALID_QUERY, LogNotFoundError
from .module import (
    MODULE_ID,
    WEB_ROLES,
    LogsModule,
    base_taxonomy_of,
    log_registries_of,
    module,
)
from .ports import (
    LOG_FILTER_PREDICATES,
    LOG_SCOPE_KINDS,
    LOG_SOURCES,
    LOGS_INGEST,
    LOGS_INGESTED,
    LOGS_QUERY,
    SECRET_RULES,
    SERVER_WARNINGS,
    SOURCE_DEFAULTS,
    WORKSPACE_SETTINGS,
    LogIngestPort,
    LogQueryPort,
    RuntimeLogSource,
)
from .purge import LogPurgeRequest, LogPurgeResponse
from .redaction import LogRedaction
from .service import LogsService
from .settings import LogsModuleSettings
from .source_defaults import SourceDefaults, apply_source_defaults, collect_source_defaults
from .storage import BRANCH, LogStorage, open_log_storage
from .templates import load_dashboard_templates, parse_dashboard
from .ws import LOGS_TOPIC

__all__ = [
    "BRANCH",
    "INVALID_QUERY",
    "LOGS_INGEST",
    "LOGS_INGESTED",
    "LOGS_QUERY",
    "LOGS_TOPIC",
    "LOG_FILTER_PREDICATES",
    "LOG_SCOPE_KINDS",
    "LOG_SOURCES",
    "MODULE_ID",
    "SECRET_RULES",
    "SERVER_WARNINGS",
    "SOURCE_DEFAULTS",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "LogIngestPort",
    "LogNotFoundError",
    "LogPurgeRequest",
    "LogPurgeResponse",
    "LogQueryPort",
    "LogRedaction",
    "LogStorage",
    "LogsModule",
    "LogsModuleSettings",
    "LogsService",
    "RuntimeLogSource",
    "SourceDefaults",
    "apply_source_defaults",
    "base_taxonomy_of",
    "collect_source_defaults",
    "load_dashboard_templates",
    "log_registries_of",
    "module",
    "open_log_storage",
    "parse_dashboard",
]
