"""REST: 프로젝트 CRUD·범위 검사·옮기기·삭제 계획(design §UX-P.5). 호스트가 ``/api/v1``을 붙인다.

- ``GET /projects``(저장 원문 목록)·``POST /projects``(201, ``ETag``)
- ``GET·PUT·DELETE /projects/{id}``: PUT은 요청에 쓴 필드만(``If-Match`` 선택),
  DELETE ``?mode=move_to_shared|delete_definitions``(생략 = 공용으로 옮기고 삭제, 204)
- ``POST /projects/{id}/delete-plan`` → ``DeletePlan``
- ``POST /projects/move-plan``(``MovePlanRequest``) → ``MovePlan``(저장하지 않음)
- ``POST /projects/move``(``MovePlan`` — 계획 그대로 또는 고른 ``moves``만) → 적용한 ``MovePlan``
- ``POST /projects/scope-issues`` → 워크스페이스 전체 범위 이슈(``Issue[]``)

응답은 저장 원문("생략 = 기본값")이다. 모델로 직렬화하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    DeletePlan,
    ErrorResponse,
    Issue,
    MovePlan,
    MovePlanRequest,
    Project,
    ProjectCreate,
    ProjectDeleteMode,
    ProjectUpdate,
)
from agent_console_modkit.host import IfMatchHeader, if_match_version, json_with_etag

from .service import ProjectService, issues_payload

_ERROR_STATUSES = (400, 401, 403, 404, 409, 422, 500)


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def build_router(service: Callable[[], ProjectService]) -> APIRouter:
    """프로젝트 경로. ``service``는 요청마다 부른다."""
    router = APIRouter(tags=["projects"])

    @router.get("/projects", response_model=list[Project], responses=errors())
    async def list_projects() -> JSONResponse:
        """모든 프로젝트(id 순, 저장 원문)."""
        return JSONResponse([s.document for s in service().projects.documents()])

    @router.post("/projects", response_model=Project, status_code=201, responses=errors())
    async def create_project(body: ProjectCreate) -> JSONResponse:
        """만들기. 같은 id가 있으면 409 ``already_exists``."""
        stored = service().projects.create(body)
        return json_with_etag(stored.document, version=stored.version_hash, status_code=201)

    @router.post("/projects/move-plan", response_model=MovePlan, responses=errors())
    async def plan_move(body: MovePlanRequest) -> JSONResponse:
        """정의 하나를 다른 범위로 옮길 때의 계획(저장하지 않음)."""
        plan = service().move_plan(body)
        return JSONResponse(plan.model_dump(mode="json", by_alias=True))

    @router.post("/projects/move", response_model=MovePlan, responses=errors(412))
    async def apply_move(body: MovePlan) -> JSONResponse:
        """계획의 ``moves``를 적용한다. 정의 기능이 꺼져 있으면 409 ``feature_unavailable``."""
        plan = service().apply_moves(body)
        return JSONResponse(plan.model_dump(mode="json", by_alias=True))

    @router.post("/projects/scope-issues", response_model=list[Issue], responses=errors())
    async def list_scope_issues() -> JSONResponse:
        """워크스페이스 전체의 범위 이슈(경고·정보, 저장을 막지 않음)."""
        return JSONResponse(issues_payload(service().scope_issues()))

    @router.get("/projects/{project_id}", response_model=Project, responses=errors())
    async def get_project(project_id: str) -> JSONResponse:
        """저장 원문 + ``ETag``."""
        stored = service().projects.get(project_id)
        return json_with_etag(stored.document, version=stored.version_hash)

    @router.put("/projects/{project_id}", response_model=Project, responses=errors(412))
    async def put_project(
        project_id: str, body: ProjectUpdate, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """고치기(요청에 쓴 필드만). ``If-Match``는 선택(주면 지금 버전과 같아야 한다)."""
        stored = service().projects.update(
            project_id, body, expected_version=if_match_version(if_match)
        )
        return json_with_etag(stored.document, version=stored.version_hash)

    @router.delete("/projects/{project_id}", status_code=204, responses=errors(412))
    async def delete_project(
        project_id: str,
        mode: Annotated[
            ProjectDeleteMode,
            Query(description="이 프로젝트 정의 처리: 공용으로 옮기기(기본) 또는 함께 삭제."),
        ] = "move_to_shared",
        if_match: IfMatchHeader = None,
    ) -> Response:
        """삭제(204). 실행·대화의 ``project_id``는 그대로 남는다."""
        service().delete(project_id, mode=mode, expected_version=if_match_version(if_match))
        return Response(status_code=204)

    @router.post(
        "/projects/{project_id}/delete-plan", response_model=DeletePlan, responses=errors()
    )
    async def plan_delete(project_id: str) -> JSONResponse:
        """삭제하면 바뀌는 것(저장하지 않음)."""
        plan = service().delete_plan(project_id)
        return JSONResponse(plan.model_dump(mode="json", by_alias=True))

    return router


__all__ = ["build_router", "errors"]
