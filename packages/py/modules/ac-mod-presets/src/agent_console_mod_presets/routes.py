"""REST: 프리셋 목록·적용(design §2.2). 경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body

from agent_console_contracts import (
    ApplyPresetRequest,
    ApplyPresetResult,
    ErrorResponse,
    PresetSummary,
)

from .service import PresetService, scope_stamp, to_result

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def build_router(service: Callable[[], PresetService]) -> APIRouter:
    """``/presets``·``/presets/{id}/apply`` 라우터(``service``는 요청마다 부른다)."""
    router = APIRouter()

    @router.get("/presets", response_model=list[PresetSummary], responses=_ERRORS)
    async def get_presets() -> list[PresetSummary]:
        """설정 `directories`의 프리셋(없으면 빈 목록 — 프리셋 없이도 동작)."""
        return service().presets()

    @router.post("/presets/{preset_id}/apply", response_model=ApplyPresetResult, responses=_ERRORS)
    async def apply_preset(
        preset_id: str, body: Annotated[ApplyPresetRequest | None, Body()] = None
    ) -> ApplyPresetResult:
        """프리셋 항목을 workspace로 복사한다(기본 충돌 정책 skip). 없는 id면 404.

        ``project``가 있으면 만든 정의에 그 프로젝트 범위를 찍는다(생략 = 공용).
        """
        req = body or ApplyPresetRequest()
        [report] = service().apply(
            [preset_id], on_conflict=req.on_conflict, stamp=scope_stamp(req.project)
        )
        return to_result(report)

    return router


__all__ = ["build_router"]
