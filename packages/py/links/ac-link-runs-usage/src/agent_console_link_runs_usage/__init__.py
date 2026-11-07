"""agent-console-link-runs-usage: 실행·사용량 연동 모듈(design §3R.1.4 L5·§3R.5, R8.6).

공개 API:
    - ``module``(``RunsUsageLink``): entry point ``agent_console.server_modules``의
      ``link-runs-usage``.
    - 포트(``ports``): 받음 ``RUNS_READER``·``RUNS_EVENTS``, 선택 ``PROJECTS_LOOKUP``·
      ``RECORDS_SPACES``, 구독 ``RUNS_EVENT``, 제공 ``USAGE_EVENT_QUERY``·``USAGE_TOKEN_ROLLUPS``.
    - HTTP 없이 쓰는 부품: ``IncrementalTokenRollups``(증분 캐시 토큰 집계),
      ``MergedEventQuery``·``project_event_sources``(앱 + 프로젝트 기록 이벤트 합친 조회).
    - 설정 ``RunsUsageSettings``(``records_space_prefix``).
"""

from __future__ import annotations

from .events import MergedEventQuery, project_event_sources
from .module import MODULE_ID, WEB_ROLES, RunsUsageLink, module
from .ports import (
    PROJECTS_LOOKUP,
    RECORDS_SPACES,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    USAGE_EVENT_QUERY,
    USAGE_TOKEN_ROLLUPS,
)
from .rollups import FINISHED_RUN_STATUSES, USAGE_EVENT_TYPES, IncrementalTokenRollups
from .settings import RunsUsageSettings

__all__ = [
    "FINISHED_RUN_STATUSES",
    "MODULE_ID",
    "PROJECTS_LOOKUP",
    "RECORDS_SPACES",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "USAGE_EVENT_QUERY",
    "USAGE_EVENT_TYPES",
    "USAGE_TOKEN_ROLLUPS",
    "WEB_ROLES",
    "IncrementalTokenRollups",
    "MergedEventQuery",
    "RunsUsageLink",
    "RunsUsageSettings",
    "module",
    "project_event_sources",
]
