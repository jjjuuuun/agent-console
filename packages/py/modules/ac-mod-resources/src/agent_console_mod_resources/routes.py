"""REST: 리소스 라이브러리(design §R12, §2R.3, §2R.8)와 리소스 종류·병합 전략 목록.

ETag = 정의 ``version_hash``(본문 포함 해시). 본문·파일 쓰기도 같은 버전으로 ``If-Match`` 한다.
가져오기(``/resources/import/*``)는 ``mod-imports``가 붙인다(메서드·경로 깊이가 겹치지 않는다).
붙은 곳(``/resources/{id}/usages``)은 정의·팀 연동(``link-definitions-teams``)이 붙인다.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    ErrorResponse,
    Issue,
    MergeStrategyInfo,
    Resource,
    ResourceFile,
    ResourceSummary,
    ResourceTypeDescriptor,
)
from agent_console_modkit.host import (
    IfMatchHeader,
    attachment_response,
    etag,
    if_match_version,
    json_with_etag,
    with_issues,
)
from agent_console_store import StoredDefinition

from .errors import ContentNotFoundError, IdMismatchError
from .service import ResourceService, merge_strategies

TEXT_MEDIA_TYPE = "text/plain; charset=utf-8"
_ERROR_STATUSES = (400, 401, 403, 404, 413, 422, 500)


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses``: 공통 오류 + 추가 상태(모두 ``ErrorResponse``)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def resource_response(stored: StoredDefinition, *, status_code: int = 200) -> JSONResponse:
    """정의 원문 응답(``Resource``로 검증만, ``ETag`` = ``version_hash``)."""
    stored.model(Resource)
    return json_with_etag(
        copy.deepcopy(stored.document), version=stored.version_hash, status_code=status_code
    )


def _issue_dicts(issues: Sequence[Issue]) -> list[dict[str, Any]]:
    """응답 헤더에 실을 이슈(값을 담지 않는 계약 ``Issue``)."""
    return [i.model_dump(mode="json", exclude_none=True) for i in issues]


def _media_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip().lower() or None


def build_router(service: Callable[[], ResourceService]) -> APIRouter:
    """리소스 경로 라우터(``service``는 요청마다 부른다)."""
    router = APIRouter()

    # ------------------------------------------------------------ 목록·디스크립터

    @router.get("/resource-types", response_model=list[ResourceTypeDescriptor], responses=errors())
    async def list_resource_types() -> list[ResourceTypeDescriptor]:
        """리소스 종류(X14): 플러그인 + ``<workspace>/resource-types/*.yaml`` 선언형."""
        return service().descriptors()

    @router.get("/merge-strategies", response_model=list[MergeStrategyInfo], responses=errors())
    async def list_merge_strategies() -> list[MergeStrategyInfo]:
        """설정 ``settings_merge``에 쓸 수 있는 병합 전략 이름(유효 설정 계산과 같은 전략 표)."""
        return merge_strategies()

    # ------------------------------------------------------------ CRUD

    @router.get("/resources", response_model=list[ResourceSummary], responses=errors())
    async def list_resources(type: str | None = None) -> list[ResourceSummary]:
        """리소스 요약(id 순). ``type``으로 종류를 거른다. ``usage_count`` = 붙은 곳 수
        (계산하는 모듈이 꺼져 있으면 null)."""
        return service().summaries(type)

    @router.post("/resources", response_model=Resource, status_code=201, responses=errors(409))
    async def create_resource(resource: Resource) -> JSONResponse:
        """만들기. 검사(종류 검사 + ``definitions.checks``)에 error 이슈(예: 평문 비밀)가 있으면
        422 ``validation_failed``. warning·info는 저장하고 ``X-Console-Issues`` 헤더로 싣는다."""
        svc = service()
        issues = svc.check(resource)
        return with_issues(
            resource_response(svc.store.create(svc.kind, resource), status_code=201),
            _issue_dicts(issues),
        )

    @router.get("/resources/{resource_id}", response_model=Resource, responses=errors())
    async def get_resource(resource_id: str) -> JSONResponse:
        """저장 원문 + ``ETag``."""
        svc = service()
        return resource_response(svc.store.get(svc.kind, resource_id))

    @router.put("/resources/{resource_id}", response_model=Resource, responses=errors(412, 428))
    async def put_resource(
        resource_id: str, resource: Resource, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """저장. ``If-Match`` 필수(428), 불일치 412. 검사 error는 422(버전 검사보다 먼저),
        warning·info는 ``X-Console-Issues`` 헤더."""
        if resource_id != resource.id:
            raise IdMismatchError(resource_id, resource.id)
        svc = service()
        issues = svc.check(resource)
        stored = svc.store.save(svc.kind, resource, expected_version=if_match_version(if_match))
        return with_issues(resource_response(stored), _issue_dicts(issues))

    @router.delete("/resources/{resource_id}", status_code=204, responses=errors(412))
    async def delete_resource(resource_id: str, if_match: IfMatchHeader = None) -> Response:
        """삭제(본문 포함). ``If-Match``는 선택."""
        svc = service()
        svc.store.delete(svc.kind, resource_id, expected_version=if_match_version(if_match))
        return Response(status_code=204)

    # ------------------------------------------------------------ 본문

    @router.get(
        "/resources/{resource_id}/content",
        response_class=Response,
        responses={**errors(), 200: {"content": {"text/plain": {}}}},
    )
    async def get_content(resource_id: str) -> Response:
        """본문(텍스트) + ``ETag``(정의 버전). 본문이 없으면 404."""
        svc = service()
        stored = svc.store.get(svc.kind, resource_id)
        data = svc.store.read_content(svc.kind, resource_id)
        if data is None:
            raise ContentNotFoundError(f"리소스 {resource_id}의 본문이(가) 없습니다")
        content = stored.document.get("content")
        media = content.get("media_type") if isinstance(content, dict) else None
        media_type = (
            f"{media}; charset=utf-8"
            if isinstance(media, str) and media.startswith("text/")
            else TEXT_MEDIA_TYPE
        )
        return Response(
            content=data,
            media_type=media_type,
            headers={"ETag": etag(stored.version_hash), "Cache-Control": "no-store"},
        )

    @router.put(
        "/resources/{resource_id}/content",
        response_model=Resource,
        responses=errors(412, 428),
        openapi_extra={"requestBody": {"content": {"text/plain": {"schema": {"type": "string"}}}}},
    )
    async def put_content(
        request: Request, resource_id: str, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """본문 저장(요청 본문 = 텍스트, ``Content-Type`` = 형식). ``If-Match`` 필수, 새 ``ETag``.
        config를 바꾸지 않으므로 종류 검사는 하지 않는다."""
        svc = service()
        current = svc.store.get(svc.kind, resource_id)
        media = _media_type(request.headers.get("content-type"))
        file = svc.content_file_for(media, current.document)
        stored = svc.store.write_content(
            svc.kind,
            resource_id,
            await request.body(),
            file=file,
            # 클라이언트 기본 형식(text/plain)은 기존 형식(예: text/markdown)을 바꾸지 않는다.
            media_type=media if media and (media != "text/plain" or file is not None) else None,
            expected_version=if_match_version(if_match),
        )
        return resource_response(stored)

    # ------------------------------------------------------------ 여러 파일 본문

    @router.get(
        "/resources/{resource_id}/files", response_model=list[ResourceFile], responses=errors()
    )
    async def list_files(resource_id: str) -> list[ResourceFile]:
        """본문 폴더의 파일 목록(경로 순, 링크·규칙 위반 이름 제외). 리소스가 없으면 404."""
        svc = service()
        return svc.store.list_files(svc.kind, resource_id)

    @router.get(
        "/resources/{resource_id}/files/{file_path:path}",
        response_class=Response,
        responses={**errors(), 200: {"content": {"application/octet-stream": {}}}},
    )
    async def read_file(resource_id: str, file_path: str) -> Response:
        """파일 하나(텍스트 형식이면 ``text/plain``, 그 밖 바이너리) + ``ETag``(정의 버전)."""
        svc = service()
        stored = svc.store.get(svc.kind, resource_id)
        data = svc.store.read_file(svc.kind, resource_id, file_path)
        media = next(
            (
                f.media_type
                for f in svc.store.list_files(svc.kind, resource_id)
                if f.path == file_path
            ),
            None,
        )
        return attachment_response(data, media, headers={"ETag": etag(stored.version_hash)})

    @router.put(
        "/resources/{resource_id}/files/{file_path:path}",
        response_model=Resource,
        responses=errors(412, 428),
        openapi_extra={
            "requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string"}}}}
        },
    )
    async def write_file(
        request: Request, resource_id: str, file_path: str, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """파일 하나를 쓴다(만들기·덮어쓰기, 요청 본문 = 바이트). ``If-Match`` 필수.

        경로에 예약 이름(설정 ``reserved_file_names``, 기본 ``.git``·``_bundle``)이 있으면 저장은
        하고 ``X-Console-Issues`` 헤더로 warning 이슈(``resource.reserved_file_name``)를
        돌려준다."""
        svc = service()
        svc.require_multi_file(svc.store.get(svc.kind, resource_id))
        stored = svc.store.write_file(
            svc.kind,
            resource_id,
            file_path,
            await request.body(),
            expected_version=if_match_version(if_match),
        )
        return with_issues(resource_response(stored), _issue_dicts(svc.file_path_issues(file_path)))

    @router.delete(
        "/resources/{resource_id}/files/{file_path:path}",
        response_model=Resource,
        responses=errors(412, 428),
    )
    async def delete_file(
        resource_id: str, file_path: str, if_match: IfMatchHeader = None
    ) -> JSONResponse:
        """파일 하나를 지운다. ``If-Match`` 필수. 없는 파일은 404."""
        svc = service()
        svc.require_multi_file(svc.store.get(svc.kind, resource_id))
        stored = svc.store.delete_file(
            svc.kind, resource_id, file_path, expected_version=if_match_version(if_match)
        )
        return resource_response(stored)

    return router


__all__ = ["build_router", "errors", "resource_response"]
