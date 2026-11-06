"""REST: ``.claude`` 등에서 복사 가져오기(design §R11). 원본은 읽기만 한다.

경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다. ``/resources/import/*``는 리소스 CRUD
(``/resources/{id}``)와 메서드·깊이가 겹치지 않는다.

5.7R.33k: 질의 ``project``(등록 id)가 출처 폴더를, ``target``(``project``·``library``)이 저장 위치를
정한다. 프로젝트 기능이 있는 조립에서 ``project``가 없으면 폴더가 필요 없는 출처만 있다(프로젝트
``.claude`` 출처 없음, ``target=project``는 422 ``project.required``). 등록되지 않은 id는 404
``project.not_found``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query

from agent_console_contracts import (
    ErrorResponse,
    ImportPreview,
    ImportPreviewRequest,
    ImportRequest,
    ImportResult,
    ImportSourceDescriptor,
)
from agent_console_imports import ImportService

from .projects import TARGET_LIBRARY, ImportScope, ImportTarget

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 413, 422, 500)
}

ProjectParam = Annotated[
    str | None,
    Query(description="등록 프로젝트 id(출처 = 그 폴더의 .claude)."),
]
TargetParam = Annotated[
    ImportTarget | None,
    Query(description="저장 위치: project(그 프로젝트 공간, 기본)·library(공용)."),
]


def build_router(scope: Callable[[str | None, ImportTarget | None], ImportScope]) -> APIRouter:
    """가져오기 라우터(``scope(project, target)``은 요청마다 부른다)."""
    router = APIRouter()

    def service(project: str | None, target: ImportTarget | None = None) -> ImportService:
        return scope(project, target).service

    @router.get(
        "/resources/import/sources",
        response_model=list[ImportSourceDescriptor],
        responses=_ERRORS,
    )
    async def import_sources(project: ProjectParam = None) -> list[ImportSourceDescriptor]:
        """가져오기 출처(플러그인이 만든다. 기본: 프로젝트 `.claude/`, 사용자 전역 출처 없음)."""
        # 출처 목록은 저장 위치와 무관하다(공용 저장소로 연다 — 공간을 열지 않는다).
        return service(project, TARGET_LIBRARY).descriptors()

    @router.post("/resources/import/preview", response_model=ImportPreview, responses=_ERRORS)
    async def import_preview(
        body: ImportPreviewRequest, project: ProjectParam = None, target: TargetParam = None
    ) -> ImportPreview:
        """후보 스캔. 원본·워크스페이스 모두 쓰지 않는다. 출처가 없으면 404.

        `target`을 주면 그 저장 위치 기준으로 겹침(`conflict`)을 계산한다."""
        return service(project, target).preview(body.source)

    @router.post("/resources/import", response_model=ImportResult, responses=_ERRORS)
    async def import_items(
        body: ImportRequest, project: ProjectParam = None, target: TargetParam = None
    ) -> ImportResult:
        """고른 후보를 저장 위치로 복사한다(원본은 읽기만). 비밀 평문은 저장하지 않는다."""
        found = scope(project, target)
        return found.service.apply(body, stamp=found.stamp)

    return router


__all__ = ["build_router"]
