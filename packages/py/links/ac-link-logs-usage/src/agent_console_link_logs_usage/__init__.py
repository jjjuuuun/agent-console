"""agent-console-link-logs-usage: 로그·사용량 연동 모듈(design §4R.8, R8.7 출처 C).

공개 API:
    - ``module``(``LogsUsageLink``): entry point ``agent_console.server_modules``의
      ``link-logs-usage``. 설치자 설정 ``LogsUsageLinkSettings``.
    - ``LocalLogsUsageSource``: 사용량 출처(X13) ``local-logs`` — 서버 없이도 쓴다(토큰 표본 조회만
      주입).
    - 순수 계산(``estimate``): ``estimate_windows``·``parse_config``·``load_default_config``·
      ``CONFIG_SCHEMA``.
    - 이 PC에 있는 로그 출처 기본 켜기(``autoenable``): ``log_source_defaults``·
      ``load_auto_log_sources``·``AutoLogSource``.
    - 포트(``ports``): 받음 ``LOGS_QUERY``·``USAGE_SERVICE``(선택 ``LOGS_INGEST``), 구독
      ``LOGS_INGESTED``, 제공 ``USAGE_SOURCES``·``SOURCE_DEFAULTS``.
"""

from __future__ import annotations

from .autoenable import AutoLogSource, load_auto_log_sources, log_source_defaults
from .estimate import (
    CONFIG_SCHEMA,
    TOKEN_KINDS,
    WINDOW_KINDS,
    LocalLogsConfig,
    WindowSpec,
    estimate_windows,
    load_default_config,
    parse_config,
    window_infos,
)
from .module import MODULE_ID, WEB_ROLES, LogsUsageLink, LogsUsageLinkSettings, module
from .ports import (
    LOGS_INGEST,
    LOGS_INGESTED,
    LOGS_QUERY,
    SOURCE_DEFAULTS,
    USAGE_SERVICE,
    USAGE_SOURCES,
    LogIngest,
    LogTokenQuery,
)
from .source import DEFAULT_SOURCE_ID, LocalLogsUsageSource

__all__ = [
    "CONFIG_SCHEMA",
    "DEFAULT_SOURCE_ID",
    "LOGS_INGEST",
    "LOGS_INGESTED",
    "LOGS_QUERY",
    "MODULE_ID",
    "SOURCE_DEFAULTS",
    "TOKEN_KINDS",
    "USAGE_SERVICE",
    "USAGE_SOURCES",
    "WEB_ROLES",
    "WINDOW_KINDS",
    "AutoLogSource",
    "LocalLogsConfig",
    "LocalLogsUsageSource",
    "LogIngest",
    "LogTokenQuery",
    "LogsUsageLink",
    "LogsUsageLinkSettings",
    "WindowSpec",
    "estimate_windows",
    "load_auto_log_sources",
    "load_default_config",
    "log_source_defaults",
    "module",
    "parse_config",
    "window_infos",
]
