"""agent-console-link-runs-usage: 실행·사용량 연동 모듈(design §3R.1.4 L5·§3R.5, R8.6).

공개 API:
    - ``module``(``RunsUsageLink``): entry point ``agent_console.server_modules``의
      ``link-runs-usage``.
    - 포트(``ports``): 받음 ``RUNS_READER``·``RUNS_EVENTS``, 구독 ``RUNS_EVENT``, 제공
      ``USAGE_EVENT_QUERY``·``USAGE_TOKEN_ROLLUPS``.
    - HTTP 없이 쓰는 부품: ``IncrementalTokenRollups``(증분 캐시 토큰 집계).
"""

from __future__ import annotations

from .module import MODULE_ID, WEB_ROLES, RunsUsageLink, module
from .ports import RUNS_EVENT, RUNS_EVENTS, RUNS_READER, USAGE_EVENT_QUERY, USAGE_TOKEN_ROLLUPS
from .rollups import FINISHED_RUN_STATUSES, USAGE_EVENT_TYPES, IncrementalTokenRollups

__all__ = [
    "FINISHED_RUN_STATUSES",
    "MODULE_ID",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "USAGE_EVENT_QUERY",
    "USAGE_EVENT_TYPES",
    "USAGE_TOKEN_ROLLUPS",
    "WEB_ROLES",
    "IncrementalTokenRollups",
    "RunsUsageLink",
    "module",
]
