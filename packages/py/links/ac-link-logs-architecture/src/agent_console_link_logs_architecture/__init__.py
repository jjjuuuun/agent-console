"""agent-console-link-logs-architecture: 로그·구조도 연동 모듈(design §5.5R.3, R8.8·R8.6·R4.2).

공개 API:
    - ``module``(``LogsArchitectureLink``): entry point ``agent_console.server_modules``의
      ``link-logs-architecture``. 웹 역할 ``logs:architecture``.
    - HTTP 없이 쓰는 부품: ``LogArchitectureViews``(로그 범위 → ``ArchitectureView``·멤버십, 결과
      캐시·증분 읽기), ``ArchitectureFilter``(X28 필터 ``arch``·``arch_group``·``arch_sources``),
      ``ScopeCache``·``MemoMatcher``(범위 캐시·판정 결과 재사용).
    - 포트(``ports``): 받음 ``LOGS_QUERY``·``ARCHITECTURE_CATALOG``(필수), 제공
      ``LOG_FILTER_PREDICATES``.
    - ``build_router``: ``/logs/architecture``, ``/logs/events/{uid}/architecture``.
    - 테스트·단독 실행: 모듈 ``agent_console_link_logs_architecture.testing``.
"""

from __future__ import annotations

from .errors import (
    ERROR_MAP,
    ArchitectureQueryError,
    EventNotFoundError,
    ProfileNotFoundError,
    ScopeTooLargeError,
)
from .filters import ArchitectureFilter, selector_fields, selector_from_values
from .module import MODULE_ID, WEB_ROLES, LogsArchitectureLink, module
from .ports import (
    ARCHITECTURE_CATALOG,
    LOG_FILTER_PREDICATES,
    LOGS_QUERY,
    ArchitectureCatalogReader,
    LogQueryReader,
)
from .routes import build_router
from .scopes import MemoMatcher, ScopeCache, ScopeEvents, profile_key, scope_key
from .settings import LogsArchitectureSettings
from .views import PROFILE_PARAM, LogArchitectureViews, ViewStats

__all__ = [
    "ARCHITECTURE_CATALOG",
    "ERROR_MAP",
    "LOGS_QUERY",
    "LOG_FILTER_PREDICATES",
    "MODULE_ID",
    "PROFILE_PARAM",
    "WEB_ROLES",
    "ArchitectureCatalogReader",
    "ArchitectureFilter",
    "ArchitectureQueryError",
    "EventNotFoundError",
    "LogArchitectureViews",
    "LogQueryReader",
    "LogsArchitectureLink",
    "LogsArchitectureSettings",
    "MemoMatcher",
    "ProfileNotFoundError",
    "ScopeCache",
    "ScopeEvents",
    "ScopeTooLargeError",
    "ViewStats",
    "build_router",
    "module",
    "profile_key",
    "scope_key",
    "selector_fields",
    "selector_from_values",
]
