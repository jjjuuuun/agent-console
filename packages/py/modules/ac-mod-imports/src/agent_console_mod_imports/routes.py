"""REST: ``.claude`` 등에서 복사 가져오기(design §R11). 원본은 읽기만 한다.

경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다. ``/resources/import/*``는 리소스 CRUD
(``/resources/{id}``)와 메서드·깊이가 겹치지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from agent_console_contracts import (
    ErrorResponse,
    ImportPreview,
    ImportPreviewRequest,
    ImportRequest,
    ImportResult,
    ImportSourceDescriptor,
)
from agent_console_imports import ImportService

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def build_router(service: Callable[[], ImportService]) -> APIRouter:
    """가져오기 라우터(``service``는 요청마다 부른다)."""
    router = APIRouter()

    @router.get(
        "/resources/import/sources",
        response_model=list[ImportSourceDescriptor],
        responses=_ERRORS,
    )
    async def import_sources() -> list[ImportSourceDescriptor]:
        """가져오기 출처(플러그인이 만든다. 기본: 프로젝트 `.claude/`)."""
        return service().descriptors()

    @router.post("/resources/import/preview", response_model=ImportPreview, responses=_ERRORS)
    async def import_preview(body: ImportPreviewRequest) -> ImportPreview:
        """후보 스캔. 원본·워크스페이스 모두 쓰지 않는다. 출처가 없으면 404."""
        return service().preview(body.source)

    @router.post("/resources/import", response_model=ImportResult, responses=_ERRORS)
    async def import_items(body: ImportRequest) -> ImportResult:
        """고른 후보를 워크스페이스로 복사한다(원본은 읽기만). 비밀 평문은 저장하지 않는다."""
        return service().apply(body)

    return router


__all__ = ["build_router"]
