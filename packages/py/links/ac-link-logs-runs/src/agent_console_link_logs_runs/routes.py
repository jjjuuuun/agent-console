"""REST: ``GET /runs/{id}/logs?<LogFilter>`` → ``LogEventPage``(``total`` 채움). 접두 없음.

필터는 쿼리 문자열 전체를 ``LogFilter``로 읽는다(모르는 이름은 422 ``validation_failed``,
``details.path``). 색인 호출이 막히는 호출이라 동기 함수로 두고 FastAPI 스레드 풀에서 돈다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

from agent_console_contracts import ErrorResponse
from agent_console_contracts.logs import LogEventPage
from agent_console_logs import parse_log_filter

from .views import RunLogs

SOURCE_PARAM = "source"
"""요청이 출처를 직접 고르는 필터 이름(``LogFilter.source``)."""

_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 422, 500)
}


def query_params(request: Request) -> dict[str, Any]:
    """쿼리 문자열 → 이름별 값(여러 번 나온 이름은 목록)."""
    out: dict[str, Any] = {}
    for name, value in request.query_params.multi_items():
        if name in out:
            prev = out[name]
            out[name] = [*prev, value] if isinstance(prev, list) else [prev, value]
        else:
            out[name] = value
    return out


def build_router(views: Callable[[], RunLogs]) -> APIRouter:
    """``/runs/{run_id}/logs`` 라우터."""
    router = APIRouter()

    @router.get("/runs/{run_id}/logs", response_model=LogEventPage, responses=_ERRORS)
    def run_logs(run_id: str, request: Request) -> LogEventPage:
        """이 실행의 에이전트 세션 로그(그 Run 세션 id들의 외부 세션 이벤트, ``total`` 채움).
        쿼리 이름은 ``GET /logs/schema``의 filters. ``source``를 주지 않으면 플랫폼 실행
        이벤트(실행 상세의 다른 탭)는 뺀다."""
        params = query_params(request)
        flt = parse_log_filter(params)
        return views().events(run_id, flt, explicit_source=SOURCE_PARAM in params)

    return router


__all__ = ["SOURCE_PARAM", "build_router", "query_params"]
