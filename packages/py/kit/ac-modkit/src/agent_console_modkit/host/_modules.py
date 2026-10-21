"""모듈 목록 `GET <prefix>/modules`(design §3R.1.8). 토큰 없이 읽고 비밀을 담지 않는다.

응답 모양은 호스트가 정한다(``payload``·``response_model`` 주입). 기본은 ``ModuleReport.to_dict()``
목록이다. 통합 서버는 계약 ``ModuleInfo`` 목록으로 바꿔 넘긴다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter

from agent_console_modkit._assemble import Assembly


def default_modules_payload(assembly: Assembly) -> Callable[[], list[dict[str, Any]]]:
    """``assembly.report``를 부를 때마다 dict 목록으로(시작 실패로 바뀐 상태도 반영)."""
    return lambda: [r.to_dict() for r in assembly.report]


def build_modules_router(
    *,
    payload: Callable[[], Any],
    prefix: str = "",
    response_model: Any = None,
    responses: Mapping[int | str, dict[str, Any]] | None = None,
) -> APIRouter:
    """`GET <prefix>/modules` 라우터.

    Args:
        payload: 응답 본문을 만드는 함수(부를 때마다 새로).
        prefix: API 접두(예: ``"/api/v1"``).
        response_model: OpenAPI·검증용 응답 모델(없으면 None).
        responses: OpenAPI 추가 응답 문서.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/modules", response_model=response_model, responses=dict(responses or {}))
    async def modules() -> Any:
        """설치된 모듈(기능·연동)과 상태. 웹은 이것으로 화면을 조립한다."""
        return payload()

    return router


__all__ = ["build_modules_router", "default_modules_payload"]
