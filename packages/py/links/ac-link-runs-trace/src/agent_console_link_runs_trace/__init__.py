"""agent-console-link-runs-trace: 실행·추적 연동 모듈(design §3R.1.4 L6, R8.7).

공개 API:
    - ``module``(``RunsTraceLink``): entry point ``agent_console.server_modules``의
      ``link-runs-trace``.
    - 포트(``ports``): 받음 ``RUNS_READER``·``RUNS_EVENTS``(필수)·``DEFINITIONS_LOOKUP``(선택).
    - HTTP 없이 쓰는 부품: ``TraceViews``(위임 흐름·넘김 집계, 자식 Run 포함),
      ``call_edges``(그래프 → 호출 span 연결 표).
    - ``build_router``: ``/runs/{id}/trace``·``/runs/handoffs``.
"""

from __future__ import annotations

from .module import ERROR_MAP, MODULE_ID, WEB_ROLES, RunsTraceLink, module
from .ports import DEFINITIONS_LOOKUP, RUNS_EVENTS, RUNS_READER, EventReader, RunReader
from .routes import build_router
from .views import RunNotFoundError, TraceViews, call_edges

__all__ = [
    "DEFINITIONS_LOOKUP",
    "ERROR_MAP",
    "MODULE_ID",
    "RUNS_EVENTS",
    "RUNS_READER",
    "WEB_ROLES",
    "EventReader",
    "RunNotFoundError",
    "RunReader",
    "RunsTraceLink",
    "TraceViews",
    "build_router",
    "call_edges",
    "module",
]
