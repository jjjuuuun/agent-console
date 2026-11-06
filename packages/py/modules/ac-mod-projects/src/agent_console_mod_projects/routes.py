"""REST: 프로젝트 등록·폴더·복사(design §PI.10). 호스트가 ``/api/v1``을 붙인다.

| 메서드·경로 | 요청 → 응답 |
| --- | --- |
| ``GET /projects`` | → ``ProjectView[]``(보관 포함, id 순) |
| ``POST /projects`` | ``ProjectCreate`` → 201 ``ProjectView`` + ``ETag`` |
| ``GET /projects/{id}`` | → ``ProjectView`` + ``ETag`` |
| ``PUT /projects/{id}`` | ``ProjectUpdate`` (+``If-Match`` 선택) → ``ProjectView`` + ``ETag`` |
| ``DELETE /projects/{id}`` | (+``If-Match`` 선택) → 204(등록 해제 = 보관) |
| ``POST /projects/{id}/manifest/reset`` | ``ManifestResetRequest`` → ``ManifestResetResult`` |
| ``POST /projects/{id}/gitignore/append`` | → ``ProjectView`` |
| ``POST /projects/{id}/legacy/plan`` | → ``CopyPlan``(라이브러리 → 이 프로젝트) |
| ``POST /projects/copy/plan`` | ``CopyPlanRequest`` → ``CopyPlan`` |
| ``POST /projects/copy/apply`` | ``CopyApplyRequest`` → ``CopyApplyResult`` |
| ``GET /projects/folders?path=&hidden=`` | → ``FolderListing`` |
| ``POST /projects/folders/check`` | ``FolderCheckRequest`` → ``FolderCheck`` |
| ``GET /projects/folders/capabilities`` | → ``FolderCapabilities`` |
| ``POST /projects/folders/pick`` | ``FolderPickRequest`` → ``FolderPickResult``(끊기면 창 닫음) |
| (deprecated) ``POST /projects/move-plan``·``/move``·``/scope-issues`` | 옛 범위 정리(33t 삭제) |
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    CopyApplyRequest,
    CopyApplyResult,
    CopyPlan,
    CopyPlanRequest,
    ErrorResponse,
    FolderCapabilities,
    FolderCheck,
    FolderCheckRequest,
    FolderListing,
    FolderPickRequest,
    FolderPickResult,
    Issue,
    ManifestResetRequest,
    ManifestResetResult,
    MovePlan,
    MovePlanRequest,
    ProjectCreate,
    ProjectUpdate,
    ProjectView,
)
from agent_console_modkit.host import IfMatchHeader, if_match_version, json_with_etag

from .copying import CopyService
from .folders import FolderPicker, FolderService
from .projects import ProjectManager
from .service import ScopeService, issues_payload

_ERROR_STATUSES = (400, 401, 403, 404, 409, 422, 500)


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def _json(model: Any) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json", by_alias=True))


def _view(view: ProjectView, status_code: int = 200) -> JSONResponse:
    return json_with_etag(
        view.model_dump(mode="json"), version=view.version_hash, status_code=status_code
    )


@dataclass(frozen=True)
class Services:
    """경로가 쓰는 서비스(요청마다 부른다 — 설정이 바뀌어도 새 값)."""

    projects: Callable[[], ProjectManager]
    folders: Callable[[], FolderService]
    picker: Callable[[], FolderPicker]
    copies: Callable[[], CopyService]
    scope: Callable[[], ScopeService]


async def _pick(
    picker: FolderPicker, body: FolderPickRequest, request: Request
) -> FolderPickResult:
    """선택 창을 스레드로 띄우고, 요청이 끊기면 ``cancel``을 켠다."""
    cancel = threading.Event()
    task = asyncio.ensure_future(asyncio.to_thread(picker.pick, body, cancel))
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if not done and await request.is_disconnected():
                cancel.set()
        return task.result()
    finally:
        if not task.done():
            cancel.set()


def build_router(services: Services) -> APIRouter:
    """프로젝트 경로."""
    router = APIRouter(tags=["projects"])
    s = services

    # ---------------------------------------------------------------- 폴더(경로 순서: {id} 앞)

    @router.get("/projects/folders", response_model=FolderListing, responses=errors())
    async def list_folders(
        path: Annotated[str | None, Query(description="나열할 폴더(생략 = 첫 시작 위치).")] = None,
        hidden: Annotated[bool, Query(description="숨김 폴더도 보인다.")] = False,
    ) -> JSONResponse:
        """하위 폴더 이름만(파일 없음). 루프백 서버 전용(아니면 403 remote_disabled)."""
        listing = await asyncio.to_thread(s.folders().listing, path, hidden=hidden)
        return _json(listing)

    @router.post("/projects/folders/check", response_model=FolderCheck, responses=errors())
    async def check_folder(body: FolderCheckRequest) -> JSONResponse:
        """폴더 확인(등록 겹침·기존 구성 개수·id 제안). ``create: true``면 한 단계 만든다."""
        return _json(await asyncio.to_thread(s.folders().check, body))

    @router.get(
        "/projects/folders/capabilities", response_model=FolderCapabilities, responses=errors()
    )
    async def folder_capabilities() -> JSONResponse:
        """이 서버에서 쓸 수 있는 폴더 고르기 방법(앱 안 찾아보기·네이티브 선택 창)."""
        folders = s.folders()
        return _json(s.picker().capabilities(browse=folders.allowed))

    @router.post("/projects/folders/pick", response_model=FolderPickResult, responses=errors())
    async def pick_folder(body: FolderPickRequest, request: Request) -> JSONResponse:
        """서버 컴퓨터에 폴더 선택 창을 띄워 고른 경로를 돌려준다(한 번에 하나, 시간 상한)."""
        return _json(await _pick(s.picker(), body, request))

    # ---------------------------------------------------------------- 복사

    @router.post("/projects/copy/plan", response_model=CopyPlan, responses=errors())
    async def plan_copy(body: CopyPlanRequest) -> JSONResponse:
        """공간 사이 복사 계획(저장하지 않음)."""
        return _json(await asyncio.to_thread(s.copies().plan, body))

    @router.post("/projects/copy/apply", response_model=CopyApplyResult, responses=errors())
    async def apply_copy(body: CopyApplyRequest) -> JSONResponse:
        """복사 적용(항목별 결과, 계획 뒤 바뀐 항목만 conflict)."""
        return _json(await asyncio.to_thread(s.copies().apply, body))

    # ---------------------------------------------------------------- (deprecated) 옛 범위

    @router.post("/projects/move-plan", response_model=MovePlan, responses=errors())
    async def plan_move(body: MovePlanRequest) -> JSONResponse:
        """(deprecated) 옛 정의 범위 옮기기 계획."""
        return _json(s.scope().move_plan(body))

    @router.post("/projects/move", response_model=MovePlan, responses=errors(412))
    async def apply_move(body: MovePlan) -> JSONResponse:
        """(deprecated) 옛 정의 범위 옮기기 적용."""
        return _json(s.scope().apply_moves(body))

    @router.post("/projects/scope-issues", response_model=list[Issue], responses=errors())
    async def list_scope_issues() -> JSONResponse:
        """(deprecated) 워크스페이스 전체의 옛 범위 이슈."""
        return JSONResponse(issues_payload(s.scope().scope_issues()))

    # ---------------------------------------------------------------- 등록

    @router.get("/projects", response_model=list[ProjectView], responses=errors())
    async def list_projects() -> JSONResponse:
        """모든 등록(보관 포함)과 상태."""
        views = await asyncio.to_thread(s.projects().list_views)
        return JSONResponse([v.model_dump(mode="json") for v in views])

    @router.post("/projects", response_model=ProjectView, status_code=201, responses=errors())
    async def create_project(body: ProjectCreate) -> JSONResponse:
        """폴더를 프로젝트로 등록한다(매니페스트·.gitignore는 없을 때만, 있으면 채택)."""
        return _view(await asyncio.to_thread(s.projects().create, body), 201)

    @router.get("/projects/{project_id}", response_model=ProjectView, responses=errors())
    async def get_project(project_id: str) -> JSONResponse:
        """한 프로젝트와 상태 + ``ETag``(합친 해시)."""
        return _view(await asyncio.to_thread(s.projects().get_view, project_id))

    @router.put("/projects/{project_id}", response_model=ProjectView, responses=errors(412))
    async def put_project(
        project_id: str, body: ProjectUpdate, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """고치기(쓴 필드만). ``folder`` = 경로 다시 지정, ``archived: false`` = 다시 등록."""
        expected = if_match_version(if_match)

        def run() -> ProjectView:
            return s.projects().update(project_id, body, expected_version=expected)

        return _view(await asyncio.to_thread(run))

    @router.delete("/projects/{project_id}", status_code=204, responses=errors(412))
    async def delete_project(project_id: str, if_match: IfMatchHeader = None) -> Response:
        """등록 해제(보관, 204). 폴더 내용·기록은 지우지 않는다."""
        expected = if_match_version(if_match)
        await asyncio.to_thread(lambda: s.projects().archive(project_id, expected_version=expected))
        return Response(status_code=204)

    @router.post(
        "/projects/{project_id}/manifest/reset",
        response_model=ManifestResetResult,
        responses=errors(),
    )
    async def reset_manifest(project_id: str, body: ManifestResetRequest) -> JSONResponse:
        """깨진 설정 파일을 백업하고 새로 만든다(상태 manifest_invalid일 때만)."""
        return _json(await asyncio.to_thread(s.projects().reset_manifest, project_id, body))

    @router.post(
        "/projects/{project_id}/gitignore/append", response_model=ProjectView, responses=errors()
    )
    async def append_gitignore(project_id: str) -> JSONResponse:
        """``.gitignore``에 빠진 줄만 끝에 덧붙인다(기존 줄은 그대로)."""
        return _view(await asyncio.to_thread(s.projects().append_gitignore, project_id))

    @router.post("/projects/{project_id}/legacy/plan", response_model=CopyPlan, responses=errors())
    async def plan_legacy(project_id: str) -> JSONResponse:
        """옛 프로젝트 전용 정의를 이 프로젝트 공간으로 옮기는 복사 계획(적용은 copy/apply)."""
        return _json(await asyncio.to_thread(s.copies().legacy_plan, project_id))

    return router


__all__ = ["Services", "build_router", "errors"]
