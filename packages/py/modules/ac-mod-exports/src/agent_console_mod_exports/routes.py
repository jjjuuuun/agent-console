"""REST: 내보내기(X8, design §2R.7). 라우트는 요청 파싱 → ``ExportService`` 호출 → 응답 변환만 한다.

- `GET /exporters`: 형식 목록(플러그인이 정한다).
- `POST /exports/plan`: 미리보기(쓰기 없음). `root`·`subdir`를 주면 그 폴더 기준 충돌 계산.
- `POST /exports/archive`: 보관 파일(zip) 응답 — 서버 디스크에 쓰지 않는다(기본 경로).
- `GET /exports/roots`: 폴더 쓰기를 허용한 루트(설치자 설정 `roots`). 경로를 담으므로 읽기여도
  토큰이 필요하다. 빈 목록이면 웹은 폴더 쓰기 선택지를 숨긴다.
- `POST /exports/write`: 허용 루트 아래에 쓰기(토큰 필수, `on_conflict` 기본 fail).

경로는 접두 없이 만들고 호스트가 ``/api/v1``을 붙인다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request, Response

from agent_console_contracts import (
    ErrorResponse,
    ExporterDescriptor,
    ExportPlan,
    ExportRequest,
    ExportResult,
    ExportRootInfo,
    ExportWriteRequest,
)
from agent_console_exports import ExportService
from agent_console_modkit.host import TOKEN_HEADER

ZIP_MEDIA_TYPE = "application/zip"

_ERROR_STATUSES = (400, 401, 403, 404, 413, 422, 500)


class TokenRequiredError(PermissionError):
    """읽기 경로지만 토큰이 필요한데 없거나 맞지 않는다 → ``unauthorized``(401)."""


def _errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def require_token(request: Request) -> None:
    """호스트 보안 규칙(``app.state.policy``)으로 토큰을 확인한다. 규칙이 없으면 거부한다."""
    policy = getattr(request.app.state, "policy", None)
    token_ok = getattr(policy, "token_ok", None)
    if not callable(token_ok) or not token_ok(request.headers.get(TOKEN_HEADER)):
        raise TokenRequiredError("토큰이 없거나 맞지 않습니다")


def build_router(service: Callable[[], ExportService], *, expose_paths: bool = True) -> APIRouter:
    """내보내기 라우터(``service``는 요청마다 부른다).

    Args:
        service: 서비스를 돌려주는 함수.
        expose_paths: ``/exports/roots``에 절대 경로를 보일지.
    """
    router = APIRouter()

    @router.get("/exporters", response_model=list[ExporterDescriptor], responses=_errors())
    async def list_exporters() -> list[ExporterDescriptor]:
        """내보내기 형식(플러그인 entry point `agent_console.exporters`, 기본 `claude-dir`)."""
        return service().descriptors()

    @router.post("/exports/plan", response_model=ExportPlan, responses=_errors(409))
    async def plan_export(body: ExportRequest) -> ExportPlan:
        """미리보기: 파일 경로·크기·동작과 경고. 아무것도 쓰지 않는다. `root`가 있으면 그 폴더
        기준 동작(create·skip·conflict), 없으면 모두 create. 잘못된 종류·옵션·경로는 422."""
        return service().plan(body)

    @router.post(
        "/exports/archive",
        response_class=Response,
        responses={**_errors(), 200: {"content": {ZIP_MEDIA_TYPE: {}}}},
    )
    async def archive_export(body: ExportRequest) -> Response:
        """보관 파일(zip) 응답. 서버 디스크에 쓰지 않는다. 형식이 error 경고를 내면 422."""
        archive = service().archive(body)
        return Response(
            content=archive.data,
            media_type=ZIP_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{archive.filename}"'},
        )

    @router.get("/exports/roots", response_model=list[ExportRootInfo], responses=_errors())
    async def export_roots(request: Request) -> list[ExportRootInfo]:
        """폴더 쓰기를 허용한 루트(토큰 필수). 비면 폴더 쓰기 꺼짐. 설정 `expose_paths`가
        false면 경로를 비운다."""
        require_token(request)
        return service().roots(expose_paths=expose_paths)

    @router.post("/exports/write", response_model=ExportResult, responses=_errors(409))
    async def write_export(body: ExportWriteRequest) -> ExportResult:
        """허용 루트 아래 `subdir`에 쓴다. `on_conflict=fail`(기본)이면 다른 내용의 파일이 하나라도
        있을 때 아무것도 쓰지 않고 409 `already_exists`(`details.paths`). 경로 탈출·링크·보호
        위치(`~/.claude` 등)는 422, 모르는 루트는 404."""
        return service().write(body)

    return router


__all__ = ["ZIP_MEDIA_TYPE", "TokenRequiredError", "build_router", "require_token"]
