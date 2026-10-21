"""REST: 세션 위임 흐름(``GET /logs/sessions/{session}/trace``). 접두 없음(호스트가 ``/api/v1``).

색인 읽기는 막히는 호출이라 동기 함수로 두고 FastAPI 스레드 풀에서 돈다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from agent_console_contracts import ErrorResponse, Trace

from .views import LogTraceViews

_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 422, 500)
}


def build_router(views: Callable[[], LogTraceViews]) -> APIRouter:
    """``/logs/sessions/{session}/trace`` 라우터.

    Args:
        views: 계산 객체를 돌려주는 함수(요청마다 부른다).
    """
    router = APIRouter()

    @router.get("/logs/sessions/{session}/trace", response_model=Trace, responses=_ERRORS)
    def log_session_trace(session: str) -> Trace:
        """세션 위임 흐름: span = 에이전트 줄(thread), 부모 = 위임 호출 id로 이어진 줄,
        링크 = from→to. 명시 id가 없으면 부모 없이 남긴다. ``run_id``는 세션 id다."""
        return views().trace(session)

    return router


__all__ = ["build_router"]
