"""REST: 위임 흐름(``GET /runs/{id}/trace``)·넘김 집계(``GET /runs/handoffs``). 접두 없음.

``/runs/handoffs``는 실행 모듈의 ``/runs/{run_id}``와 겹친다. 호스트는 연동 모듈 라우터를 기능 모듈
라우터보다 먼저 붙이므로(``agent_console_modkit.host.include_routers``) 고정 경로가 먼저 맞는다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query

from agent_console_contracts import ErrorResponse, HandoffMatrix, RunStatus, Trace

from .views import TraceViews

DEFAULT_HANDOFF_RUNS = 200
MAX_RUN_LIST_LIMIT = 1000

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def build_router(views: Callable[[], TraceViews]) -> APIRouter:
    router = APIRouter()

    @router.get("/runs/handoffs", response_model=HandoffMatrix, responses=_ERRORS)
    async def handoffs(
        graph_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        status: RunStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIST_LIMIT)] = DEFAULT_HANDOFF_RUNS,
    ) -> HandoffMatrix:
        """여러 실행의 "누가 누구에게 몇 번"(위임·넘기기). 필터는 실행 목록과 같다."""
        return views().handoffs(
            graph_id=graph_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            status=status,
            limit=limit,
        )

    @router.get("/runs/{run_id}/trace", response_model=Trace, responses=_ERRORS)
    async def run_trace(run_id: str) -> Trace:
        """위임 흐름(span·넘김 화살표·사용자 대기 구간)."""
        v = views()
        return v.trace(v.require_run(run_id))

    return router


__all__ = ["DEFAULT_HANDOFF_RUNS", "build_router"]
