"""REST: 문서 틀 하나 — 정의·뼈대 파일·버전(6R.20a, screen-sdd §11.1).

모든 경로가 ``?project=<공간 이름>``을 받는다. 저장소는 ``/sdd/templates`` 목록과 같다(design
§6R.13 ``[구현]`` 틀 저장소 결정): 공간 이름이 없으면 앱 라이브러리(``definitions.store``에 틀
종류가 있을 때), 없으면 단독 루트, 이름이 있으면 그 공간 저장소. 그래서 정의 모듈이 꺼진 조립에서도
단독 루트 틀을 만들고 고칠 수 있다.

- ``POST /sdd/templates``: ``SpecTemplateCreateRequest`` → 201 ``SpecTemplate`` + ``ETag``
- ``GET·PUT·DELETE /sdd/templates/{id}``: ``SpecTemplate`` + ``ETag``(PUT ``If-Match`` 필수 428)
- ``GET /sdd/templates/{id}/variables``: ``TemplateVariable[]``(실행 입력 틀 변수)
- ``GET /sdd/templates/{id}/files``: ``ResourceFile[]``(본문 폴더, 경로 순)
- ``GET·PUT·DELETE /sdd/templates/{id}/files/{path}``: 바이트 ↔ ``SpecTemplate`` + ``ETag``
- ``GET /sdd/templates/{id}/versions[/{hash}]``: ``DefinitionVersion[]`` / ``DefinitionVersion``
- ``GET /sdd/templates/{id}/versions/{hash}/files[/{path}]``: 그 버전의 본문 파일 목록·내용
- ``POST /sdd/templates/{id}/versions/{hash}/restore``: ``DefinitionVersion`` + ``ETag``

``ETag``·``If-Match`` = 정의 버전(``version_hash``, 본문 파일 해시 포함) — 파일 쓰기도 같은
값으로 맞춘다(다중 파일 리소스 편집기와 같은 규칙). 파일 경로는 본문 폴더 기준 상대 경로만
(``..``·절대 경로는 400 ``bad_request``). 파일 본문은 사용자 설정 ``secret_scan``을 따른다
(reject = 422 ``sdd.secret_rejected``, warn = 저장 + ``X-Console-Issues``). 버전 비교(diff)는
이 경로에 없다.

경로 예약어(``TEMPLATE_ROUTE_WORDS``): 같은 깊이의 고정 경로(``/sdd/templates/variables``·
``/check``)와 겹치는 id는 만들기에서 거부하고 이름에서 만든 id도 피한다(그 id의 GET이 고정 경로에
가려지므로).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    DefinitionVersion,
    ErrorCodes,
    ErrorResponse,
    ResourceFile,
    RestoreVersionRequest,
)
from agent_console_contracts.sdd import (
    SpecTemplate,
    SpecTemplateCreateRequest,
    TemplateVariable,
)
from agent_console_modkit.host import (
    IfMatchHeader,
    SpaceQuery,
    attachment_response,
    etag,
    if_match_version,
    json_with_etag,
    with_issues,
)
from agent_console_sdd import StoredSpec, run_input_variables
from agent_console_store import NotFound, StoredDefinition, VersionRequired

from .errors import SddRequestError
from .secrets import SCAN_REJECT, SecretRejectedError, document_issues
from .service import SddScope, SddService

TEMPLATE_ROUTE_WORDS: tuple[str, ...] = ("variables", "check")
"""``/sdd/templates/<이 말>``이 이미 고정 경로라 문서 틀 id로 쓸 수 없는 말(경로 어휘)."""

RESTORE_MESSAGE = "restored from {hash}"
"""되돌리기 버전 메시지 기본 문구(``mod-versions``와 같은 문구)."""

_ERROR_STATUSES = (400, 401, 403, 404, 409, 422, 500)


def _errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def _template_json(stored: StoredSpec, *, status_code: int = 200) -> JSONResponse:
    """정의 원문 응답(``SpecTemplate``으로 검증만, 모르는 키 보존, ``ETag`` = 버전)."""
    stored.template  # noqa: B018 - 형식 검증(깨진 파일은 422)
    return json_with_etag(
        dict(stored.document), version=stored.version_hash, status_code=status_code
    )


def _issue_dicts(issues: list[Any]) -> list[dict[str, Any]]:
    return [i.model_dump(mode="json", exclude_none=True) for i in issues]


def build_template_router(service: Callable[[], SddService]) -> APIRouter:
    """문서 틀 단건 라우터(``build_router``가 마지막에 붙인다 — 고정 경로가 먼저 맞는다)."""
    router = APIRouter()

    def scope(space: str | None) -> SddScope:
        return service().scope(space)

    def kind_of(sc: SddScope) -> str:
        return sc.repository.template_kind

    @router.post(
        "/sdd/templates", response_model=SpecTemplate, status_code=201, responses=_errors()
    )
    async def create_template(
        body: SpecTemplateCreateRequest, space: SpaceQuery = None
    ) -> JSONResponse:
        """빈 문서 틀 만들기(문서 0개, 규칙 비움). 같은 id가 있으면 409 ``already_exists``."""
        if body.id is not None and body.id.casefold() in TEMPLATE_ROUTE_WORDS:
            raise SddRequestError(
                "이 id는 경로 이름과 겹쳐 쓸 수 없습니다.",
                code=ErrorCodes.VALIDATION_FAILED,
                details={"id": body.id, "reserved": list(TEMPLATE_ROUTE_WORDS)},
            )
        stored = scope(space).repository.create_template(
            name=body.name,
            id=body.id,
            description=body.description or None,
            taken=TEMPLATE_ROUTE_WORDS,
        )
        return _template_json(stored, status_code=201)

    @router.get("/sdd/templates/{template_id}", response_model=SpecTemplate, responses=_errors())
    async def get_template(template_id: str, space: SpaceQuery = None) -> JSONResponse:
        """정의 원문 + ``ETag``. 없으면 404 ``sdd.not_found``."""
        return _template_json(scope(space).repository.get_template(template_id))

    @router.put(
        "/sdd/templates/{template_id}", response_model=SpecTemplate, responses=_errors(412, 428)
    )
    async def put_template(
        template_id: str,
        body: SpecTemplate,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """규칙·문서 목록 저장(``If-Match`` 필수 — 없으면 428, 다르면 412). 본문 파일은 그대로."""
        if body.id != template_id:
            raise SddRequestError(
                "경로의 id와 본문의 문서 틀 id가 다릅니다.",
                details={"path_id": template_id, "body_id": body.id},
            )
        stored = scope(space).repository.save_template(
            body, expected_version=if_match_version(if_match), message="문서 틀 저장"
        )
        return _template_json(stored)

    @router.delete("/sdd/templates/{template_id}", status_code=204, responses=_errors(412))
    async def delete_template(
        template_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """삭제(정의와 본문 파일). 이미 만든 스펙에는 영향이 없다. ``If-Match``는 선택."""
        scope(space).repository.delete_template(
            template_id, expected_version=if_match_version(if_match)
        )
        return Response(status_code=204)

    @router.get(
        "/sdd/templates/{template_id}/variables",
        response_model=list[TemplateVariable],
        responses=_errors(),
    )
    async def template_variables(
        template_id: str, space: SpaceQuery = None
    ) -> list[TemplateVariable]:
        """이 틀 기준 실행 입력 틀 변수(``GET /sdd/templates/variables?template=``와 같다)."""
        repo = scope(space).repository
        tpl = repo.get_template(template_id).template
        syntax = repo.syntax(tpl)
        task = syntax.syntax.task
        fields = list(task.roles) if task is not None and task.roles else []
        return run_input_variables(tpl.documents, fields=fields)

    # ------------------------------------------------------------ 뼈대 파일

    @router.get(
        "/sdd/templates/{template_id}/files",
        response_model=list[ResourceFile],
        responses=_errors(),
    )
    async def list_files(template_id: str, space: SpaceQuery = None) -> list[ResourceFile]:
        """본문 폴더의 파일(경로 순, 링크·규칙 위반 이름 제외). 틀이 없으면 404."""
        sc = scope(space)
        sc.repository.get_template(template_id)
        return sc.repository.template_store.list_files(kind_of(sc), template_id)

    @router.get(
        "/sdd/templates/{template_id}/files/{file_path:path}",
        response_class=Response,
        responses={**_errors(), 200: {"content": {"application/octet-stream": {}}}},
    )
    async def read_file(template_id: str, file_path: str, space: SpaceQuery = None) -> Response:
        """파일 하나(텍스트 형식이면 ``text/plain``) + ``ETag``(정의 버전). 없으면 404."""
        sc = scope(space)
        stored = sc.repository.get_template(template_id)
        store = sc.repository.template_store
        data = store.read_file(kind_of(sc), template_id, file_path)
        listed = store.list_files(kind_of(sc), template_id)
        media = next((f.media_type for f in listed if f.path == file_path), None)
        return attachment_response(data, media, headers={"ETag": etag(stored.version_hash)})

    @router.put(
        "/sdd/templates/{template_id}/files/{file_path:path}",
        response_model=SpecTemplate,
        responses=_errors(412, 428),
        openapi_extra={
            "requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string"}}}}
        },
    )
    async def write_file(
        request: Request,
        template_id: str,
        file_path: str,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """파일 하나 쓰기(만들기·덮어쓰기, 요청 본문 = 바이트). ``If-Match`` 필수. 비밀 검사는
        사용자 설정 ``secret_scan``(reject = 422, warn = 저장 + ``X-Console-Issues``)."""
        svc = service()
        sc = svc.scope(space)
        data = await request.body()
        findings = svc.document_findings(data.decode("utf-8", errors="replace"), document=file_path)
        if findings and svc.secret_mode() == SCAN_REJECT:
            raise SecretRejectedError(findings)
        sc.repository.get_template(template_id)
        stored = sc.repository.template_store.write_file(
            kind_of(sc),
            template_id,
            file_path,
            data,
            expected_version=if_match_version(if_match),
            message=f"뼈대 파일 저장: {file_path}",
        )
        return with_issues(_template_json(_as_spec(stored)), _issue_dicts(findings))

    @router.delete(
        "/sdd/templates/{template_id}/files/{file_path:path}",
        response_model=SpecTemplate,
        responses=_errors(412, 428),
    )
    async def delete_file(
        template_id: str,
        file_path: str,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """파일 하나 지우기. ``If-Match`` 필수. 없는 파일은 404."""
        sc = scope(space)
        sc.repository.get_template(template_id)
        stored = sc.repository.template_store.delete_file(
            kind_of(sc),
            template_id,
            file_path,
            expected_version=if_match_version(if_match),
            message=f"뼈대 파일 삭제: {file_path}",
        )
        return _template_json(_as_spec(stored))

    # ------------------------------------------------------------ 버전

    @router.get(
        "/sdd/templates/{template_id}/versions",
        response_model=list[DefinitionVersion],
        responses=_errors(),
    )
    async def list_versions(template_id: str, space: SpaceQuery = None) -> list[DefinitionVersion]:
        """버전 목록(최신순, ``content`` 없음). 지운 틀의 이력도 남아 있다."""
        sc = scope(space)
        return sc.repository.template_store.list_versions(kind_of(sc), template_id)

    @router.get(
        "/sdd/templates/{template_id}/versions/{version_hash}",
        response_model=DefinitionVersion,
        responses=_errors(),
    )
    async def get_version(
        template_id: str, version_hash: str, space: SpaceQuery = None
    ) -> DefinitionVersion:
        """버전 하나(``content`` = 그 버전의 정의 원문)."""
        sc = scope(space)
        return sc.repository.template_store.get_version(kind_of(sc), template_id, version_hash)

    @router.get(
        "/sdd/templates/{template_id}/versions/{version_hash}/files",
        response_model=list[ResourceFile],
        responses=_errors(),
    )
    async def list_version_files(
        template_id: str, version_hash: str, space: SpaceQuery = None
    ) -> list[ResourceFile]:
        """그 버전의 본문 파일(경로 순). 본문 스냅샷이 없으면 404."""
        sc = scope(space)
        return sc.repository.template_store.list_version_files(
            kind_of(sc), template_id, version_hash
        )

    @router.get(
        "/sdd/templates/{template_id}/versions/{version_hash}/files/{file_path:path}",
        response_class=Response,
        responses={**_errors(), 200: {"content": {"application/octet-stream": {}}}},
    )
    async def read_version_file(
        template_id: str, version_hash: str, file_path: str, space: SpaceQuery = None
    ) -> Response:
        """그 버전의 본문 파일 내용."""
        sc = scope(space)
        store = sc.repository.template_store
        kind = kind_of(sc)
        data = store.read_version_file(kind, template_id, version_hash, file_path)
        media = next(
            (
                f.media_type
                for f in store.list_version_files(kind, template_id, version_hash)
                if f.path == file_path
            ),
            None,
        )
        return attachment_response(data, media)

    @router.post(
        "/sdd/templates/{template_id}/versions/{version_hash}/restore",
        response_model=DefinitionVersion,
        responses=_errors(412, 428),
    )
    async def restore_version(
        template_id: str,
        version_hash: str,
        body: Annotated[RestoreVersionRequest | None, Body()] = None,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """되돌리기 = 그 버전의 문서·본문으로 **새 버전** 저장(이력은 그대로). 틀이 있으면
        ``If-Match``(현재 버전) 필수(없음 428, 다름 412), 지운 틀은 없이 되살린다. 그 버전 문서에
        비밀로 보이는 값이 있으면 422 ``sdd.secret_rejected``."""
        svc = service()
        sc = svc.scope(space)
        store = sc.repository.template_store
        kind = kind_of(sc)
        version = store.get_version(kind, template_id, version_hash)
        suspected = document_issues(svc.rules(), version.content or {})
        if suspected:
            raise SecretRejectedError(suspected)
        expected = if_match_version(if_match)
        exists = True
        try:
            store.get(kind, template_id)
        except NotFound:
            exists = False
        if exists and expected is None:
            raise VersionRequired(f"{kind}/{template_id}: If-Match is required to restore")
        message = body.message if body is not None and body.message else None
        stored = store.restore_version(
            kind,
            template_id,
            version_hash,
            expected_version=expected,
            message=message or RESTORE_MESSAGE.format(hash=version_hash),
        )
        restored = store.get_version(kind, template_id, stored.version_hash)
        return JSONResponse(
            content=restored.model_dump(mode="json"),
            headers={"ETag": etag(stored.version_hash)},
        )

    return router


def _as_spec(stored: StoredDefinition) -> StoredSpec:
    return StoredSpec(
        id=stored.id,
        document=stored.document,
        version_hash=stored.version_hash,
        saved_at=stored.saved_at,
    )


__all__ = ["RESTORE_MESSAGE", "TEMPLATE_ROUTE_WORDS", "build_template_router"]
