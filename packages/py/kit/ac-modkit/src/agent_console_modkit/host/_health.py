"""준비 신호 `GET <prefix>/health`(design §2R.13a, 3R.16). 토큰 없이 읽고 비밀을 담지 않는다.

**200이면 준비된 것이다.** ``ready``를 주면 그것이 거짓인 동안(모듈 시작 훅이 끝나기 전·종료 중)
``503 not_ready``로 답한다. ASGI 서버(uvicorn)는 lifespan 시작이 끝난 뒤에야 요청을 받지만,
lifespan 없이 앱을 부르는 경우(테스트 클라이언트를 컨텍스트 없이 쓰는 등)에도 다른 경로가 404인데
``/health``만 200인 구간이 생기지 않게 한다.
응답 모양은 호스트가 정한다(``payload``·``response_model`` 주입). 기본은 ``{"status": "ok"}``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from agent_console_modkit._errors import NOT_READY

from ._security import DEFAULT_ERROR_STATUS, error_body

NOT_READY_MESSAGE = "서버가 아직 준비되지 않았습니다(모듈 시작 중이거나 종료 중)"
"""``503 not_ready`` 응답 메시지."""


def _ok() -> dict[str, Any]:
    return {"status": "ok"}


def build_health_router(
    *,
    prefix: str = "",
    payload: Callable[[], Any] = _ok,
    response_model: Any = None,
    responses: Mapping[int | str, dict[str, Any]] | None = None,
    ready: Callable[[], bool] | None = None,
    error_status: Mapping[str, int] = DEFAULT_ERROR_STATUS,
) -> APIRouter:
    """`GET <prefix>/health` 라우터.

    Args:
        prefix: API 접두(예: ``"/api/v1"``).
        payload: 응답 본문을 만드는 함수(부를 때마다 새로).
        response_model: OpenAPI·검증용 응답 모델(없으면 None).
        responses: OpenAPI 추가 응답 문서.
        ready: 준비 여부 함수(보통 ``lambda: assembly.running``). 거짓이면 ``not_ready``
            (기본 503). None이면 늘 준비된 것으로 본다.
        error_status: 오류 코드 → HTTP 상태.
    """
    router = APIRouter(prefix=prefix)

    @router.get("/health", response_model=response_model, responses=dict(responses or {}))
    async def health() -> Any:
        """준비 신호. 셸·스크립트가 서버 기동을 기다릴 때 폴링한다(200 = 준비)."""
        if ready is not None and not ready():
            return Response(
                content=error_body(NOT_READY, NOT_READY_MESSAGE),
                status_code=error_status.get(NOT_READY, 503),
                media_type="application/json",
                headers={"cache-control": "no-store", "retry-after": "1"},
            )
        return payload()

    return router


__all__ = ["NOT_READY_MESSAGE", "build_health_router"]
