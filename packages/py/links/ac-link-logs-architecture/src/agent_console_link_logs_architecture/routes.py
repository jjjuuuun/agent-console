"""REST: 로그 범위 구조도·이벤트 멤버십. 접두 없음(호스트가 ``/api/v1``).

- ``GET /logs/architecture?<로그 필터>&profile=`` → ``ArchitectureView``
- ``GET /logs/events/{uid}/architecture?profile=`` → ``ArchitectureMembership``

색인 읽기는 막히는 호출이라 동기 함수로 두고 FastAPI 스레드 풀에서 돈다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

from agent_console_contracts import ErrorResponse
from agent_console_contracts.architecture import ArchitectureMembership, ArchitectureView

from .views import LogArchitectureViews

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


def build_router(views: Callable[[], LogArchitectureViews]) -> APIRouter:
    """구조도 라우터.

    Args:
        views: 계산 객체를 돌려주는 함수(요청마다 부른다).
    """
    router = APIRouter()

    @router.get("/logs/architecture", response_model=ArchitectureView, responses=_ERRORS)
    def log_architecture(request: Request) -> ArchitectureView:
        """로그 범위 구조도. 쿼리는 로그 필터(``GET /logs/schema`` filters)와
        ``profile``(없으면 기본
        프로필). 칸·연결을 누르면 결과의 ``selector``와 ``max_seq``를 이벤트 목록 질의에 더한다.
        프로필이 없으면 404 ``architecture.profile_not_found``, 범위가 상한을 넘으면 422
        ``architecture.scope_too_large``."""
        return views().architecture(query_params(request))

    @router.get(
        "/logs/events/{uid}/architecture",
        response_model=ArchitectureMembership,
        responses=_ERRORS,
    )
    def log_event_architecture(uid: str, profile: str | None = None) -> ArchitectureMembership:
        """이벤트 하나가 맞은 칸·연결·묶음(표에서 고른 이벤트 강조)."""
        return views().membership(uid, profile or None)

    return router


__all__ = ["build_router", "query_params"]
