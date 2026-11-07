"""REST: 위키 규칙(design §7R.7 ``/wiki/rules``, 6R.20a와 같은 결정 — 정의 모듈 없이도 동작).

저장소는 공간 이름이 없으면 앱 라이브러리(``definitions.store``에 규칙 종류가 있을 때), 없으면 단독
루트, 이름이 있으면 그 공간 저장소다(단독 공간 위키가 읽는 규칙과 같은 곳).

- ``GET /wiki/rules`` → ``WikiRulesListItem[]``(개수·지침 있음·``used_by`` — 공간 자기 규칙만)
- ``POST /wiki/rules``(규칙 문서, ``id`` 생략 = 이름에서) → 201 ``WikiRulesView`` + ``ETag``
- ``POST /wiki/rules/check``(``WikiRulesCheckRequest``) → ``WikiRulesCheckResult``(저장하지 않음)
- ``GET·PUT·DELETE /wiki/rules/{id}``: ``WikiRulesView`` + ``ETag``(PUT ``If-Match`` 필수 428)
- ``GET /wiki/rules/{id}/files``: ``ResourceFile[]``(본문 폴더 — 지침·페이지 틀)
- ``GET·PUT·DELETE /wiki/rules/{id}/files/{path}``: 바이트 ↔ ``WikiRulesView`` + ``ETag``
- ``GET /wiki/rules/{id}/versions[/{hash}]``: ``DefinitionVersion[]`` / ``DefinitionVersion``
- ``GET /wiki/rules/{id}/versions/{hash}/files[/{path}]``: 그 버전의 본문 파일 목록·내용
- ``POST /wiki/rules/{id}/versions/{hash}/restore``: ``DefinitionVersion`` + ``ETag``(0.14.2,
  ``/sdd/templates/{id}/versions``·``mod-versions``와 같은 모양)

``ETag``·``If-Match`` = 정의 버전(본문 파일 해시 포함). 파일 본문은 사용자 설정
``wiki.secret_scan``의 사람(``user``) 방식을 따른다(reject = 422 ``wiki.secret_rejected``, warn =
저장 + ``X-Console-Issues``). 저장 응답의 ``issues``는 규칙 검사 결과(저장은 막지 않는다).

되돌리기는 그 버전의 정의·본문으로 **새 버전**을 저장한다(이력은 그대로). 규칙이 있으면
``If-Match``(현재 버전) 필수(없음 428, 다름 412), 지운 규칙은 없이 되살린다. 그 버전의 본문 파일은
파일 쓰기와 같은 사람(``user``) 비밀 검사를 거친다(reject = 422 ``wiki.secret_rejected``, warn =
되돌림 + ``X-Console-Issues``). 공간 자기 규칙이면 쓸 수 있는 공간이어야 한다(409). 버전
비교(diff)는 이 경로에 없다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    DefinitionVersion,
    ErrorResponse,
    ResourceFile,
    RestoreVersionRequest,
)
from agent_console_contracts.wiki import (
    KnownWikiAuthorKinds,
    WikiRulesCheckRequest,
    WikiRulesCheckResult,
    WikiRulesDefinition,
    WikiRulesListItem,
    WikiRulesView,
)
from agent_console_modkit.host import (
    IfMatchHeader,
    SpaceQuery,
    attachment_response,
    etag,
    if_match_version,
    with_issues,
)
from agent_console_store import NotFound, StoredDefinition, VersionRequired
from agent_console_wiki import WikiSecretRejectedError

from .service import WikiScope, WikiService

_ERROR_STATUSES = (400, 404, 409, 412, 422, 428, 500)

RESTORE_MESSAGE = "restored from {hash}"
"""되돌리기 버전 메시지 기본 문구(``mod-versions``·``/sdd/templates``와 같은 문구)."""


def _errors() -> dict[int | str, dict[str, Any]]:
    return {s: {"model": ErrorResponse} for s in _ERROR_STATUSES}


def _view_json(
    svc: WikiService, sc: WikiScope, stored: StoredDefinition, *, status_code: int = 200
) -> JSONResponse:
    view = svc.rules_view(sc, stored)
    return JSONResponse(
        view.model_dump(mode="json", by_alias=True),
        status_code=status_code,
        headers={"ETag": etag(stored.version_hash)},
    )


def build_rules_router(service: Callable[[], WikiService]) -> APIRouter:
    """위키 규칙 라우터(``build_router``가 붙인다)."""
    router = APIRouter()

    @router.get("/wiki/rules", response_model=list[WikiRulesListItem], responses=_errors())
    def list_rules(space: SpaceQuery = None) -> list[WikiRulesListItem]:
        """위키 규칙 목록(본문 없음)."""
        svc = service()
        return svc.rules_list(svc.scope(space))

    @router.post("/wiki/rules", response_model=WikiRulesView, status_code=201, responses=_errors())
    def create_rules(
        body: Annotated[dict[str, Any], Body(description="위키 규칙 문서(`id` 생략 = 이름에서).")],
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """위키 규칙 만들기. 같은 id가 있으면 409 ``already_exists``."""
        svc = service()
        sc = svc.scope(space)
        return _view_json(svc, sc, svc.create_rules(sc, body), status_code=201)

    @router.post("/wiki/rules/check", response_model=WikiRulesCheckResult, responses=_errors())
    def check(body: WikiRulesCheckRequest, space: SpaceQuery = None) -> WikiRulesCheckResult:
        """규칙 검사(저장하지 않음). ``files``가 null이면 저장된 같은 id 규칙의 본문 파일을 본다.
        ``kind``를 생략하면 위키 규칙 종류로 본다."""
        svc = service()
        files = body.files
        if files is None:
            rule_id = body.rules.get("id")
            if isinstance(rule_id, str) and rule_id:
                files = svc.rule_files(svc.scope(space), rule_id)
        document = {"kind": svc.rules_kind.name, **body.rules}
        return WikiRulesCheckResult(issues=svc.check_rules(document, files=files))

    @router.get("/wiki/rules/{rule_id}", response_model=WikiRulesView, responses=_errors())
    def get_rules(rule_id: str, space: SpaceQuery = None) -> JSONResponse:
        """위키 규칙 + 쓰는 위키 + 검사 이슈 + ``ETag``. 없으면 404 ``not_found``."""
        svc = service()
        sc = svc.scope(space)
        return _view_json(svc, sc, svc.get_rules(sc, rule_id))

    @router.put("/wiki/rules/{rule_id}", response_model=WikiRulesView, responses=_errors())
    def put_rules(
        rule_id: str,
        body: WikiRulesDefinition,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """위키 규칙 저장(``If-Match`` 필수 — 없으면 428, 다르면 412). 본문 파일은 그대로."""
        svc = service()
        sc = svc.scope(space)
        stored = svc.save_rules(sc, rule_id, body, expected=if_match_version(if_match))
        return _view_json(svc, sc, stored)

    @router.delete("/wiki/rules/{rule_id}", status_code=204, responses=_errors())
    def delete_rules(
        rule_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """위키 규칙 지우기(정의와 본문 파일). 쓰던 위키는 ``wiki.rules_missing``을 보인다."""
        svc = service()
        svc.delete_rules(svc.scope(space), rule_id, expected=if_match_version(if_match))
        return Response(status_code=204)

    # ------------------------------------------------------------ 본문 파일

    @router.get(
        "/wiki/rules/{rule_id}/files", response_model=list[ResourceFile], responses=_errors()
    )
    def list_files(rule_id: str, space: SpaceQuery = None) -> list[ResourceFile]:
        """본문 폴더의 파일(경로 순). 규칙이 없으면 404."""
        svc = service()
        sc = svc.scope(space)
        svc.get_rules(sc, rule_id)
        return sc.rules_store.list_files(svc.rules_kind.name, rule_id)

    @router.get(
        "/wiki/rules/{rule_id}/files/{file_path:path}",
        response_class=Response,
        responses={**_errors(), 200: {"content": {"application/octet-stream": {}}}},
    )
    def read_file(rule_id: str, file_path: str, space: SpaceQuery = None) -> Response:
        """파일 하나(텍스트 형식이면 ``text/plain``) + ``ETag``(정의 버전)."""
        svc = service()
        sc = svc.scope(space)
        stored = svc.get_rules(sc, rule_id)
        kind = svc.rules_kind.name
        data = sc.rules_store.read_file(kind, rule_id, file_path)
        listed = sc.rules_store.list_files(kind, rule_id)
        media = next((f.media_type for f in listed if f.path == file_path), None)
        return attachment_response(data, media, headers={"ETag": etag(stored.version_hash)})

    @router.put(
        "/wiki/rules/{rule_id}/files/{file_path:path}",
        response_model=WikiRulesView,
        responses=_errors(),
        openapi_extra={
            "requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string"}}}}
        },
    )
    async def write_file(
        request: Request,
        rule_id: str,
        file_path: str,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """파일 하나 쓰기(요청 본문 = 바이트, ``If-Match`` 필수)."""
        data = await request.body()
        svc = service()
        sc = svc.scope(space)
        if sc.own_rules:
            svc.require_writable(sc)
        text = data.decode("utf-8", errors="replace")
        decision = svc.secret_policy(svc.settings()).check(
            text, KnownWikiAuthorKinds.USER, page=file_path
        )
        if decision.rejected:
            lines = [n for i in decision.issues for n in i.details.get("lines", [])]
            raise WikiSecretRejectedError(lines, issues=decision.issues)
        svc.get_rules(sc, rule_id)
        stored = sc.rules_store.write_file(
            svc.rules_kind.name,
            rule_id,
            file_path,
            data,
            expected_version=if_match_version(if_match),
            message=f"본문 파일 저장: {file_path}",
        )
        issues = [i.model_dump(mode="json", exclude_none=True) for i in decision.issues]
        return with_issues(_view_json(svc, sc, stored), issues)

    @router.delete(
        "/wiki/rules/{rule_id}/files/{file_path:path}",
        response_model=WikiRulesView,
        responses=_errors(),
    )
    def delete_file(
        rule_id: str, file_path: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> JSONResponse:
        """파일 하나 지우기(``If-Match`` 필수). 없는 파일은 404."""
        svc = service()
        sc = svc.scope(space)
        if sc.own_rules:
            svc.require_writable(sc)
        svc.get_rules(sc, rule_id)
        stored = sc.rules_store.delete_file(
            svc.rules_kind.name,
            rule_id,
            file_path,
            expected_version=if_match_version(if_match),
            message=f"본문 파일 삭제: {file_path}",
        )
        return _view_json(svc, sc, stored)

    # ------------------------------------------------------------ 버전

    @router.get(
        "/wiki/rules/{rule_id}/versions",
        response_model=list[DefinitionVersion],
        responses=_errors(),
    )
    def list_versions(rule_id: str, space: SpaceQuery = None) -> list[DefinitionVersion]:
        """버전 목록(최신순, ``content`` 없음). 지운 규칙의 이력도 남아 있다."""
        svc = service()
        return svc.scope(space).rules_store.list_versions(svc.rules_kind.name, rule_id)

    @router.get(
        "/wiki/rules/{rule_id}/versions/{version_hash}",
        response_model=DefinitionVersion,
        responses=_errors(),
    )
    def get_version(rule_id: str, version_hash: str, space: SpaceQuery = None) -> DefinitionVersion:
        """버전 하나(``content`` = 그 버전의 정의 원문). 없으면 404 ``not_found``."""
        svc = service()
        return svc.scope(space).rules_store.get_version(svc.rules_kind.name, rule_id, version_hash)

    @router.get(
        "/wiki/rules/{rule_id}/versions/{version_hash}/files",
        response_model=list[ResourceFile],
        responses=_errors(),
    )
    def list_version_files(
        rule_id: str, version_hash: str, space: SpaceQuery = None
    ) -> list[ResourceFile]:
        """그 버전의 본문 파일(경로 순). 본문 스냅샷이 없으면 404."""
        svc = service()
        return svc.scope(space).rules_store.list_version_files(
            svc.rules_kind.name, rule_id, version_hash
        )

    @router.get(
        "/wiki/rules/{rule_id}/versions/{version_hash}/files/{file_path:path}",
        response_class=Response,
        responses={**_errors(), 200: {"content": {"application/octet-stream": {}}}},
    )
    def read_version_file(
        rule_id: str, version_hash: str, file_path: str, space: SpaceQuery = None
    ) -> Response:
        """그 버전의 본문 파일 내용(텍스트 형식이면 ``text/plain``)."""
        svc = service()
        store = svc.scope(space).rules_store
        kind = svc.rules_kind.name
        data = store.read_version_file(kind, rule_id, version_hash, file_path)
        media = next(
            (
                f.media_type
                for f in store.list_version_files(kind, rule_id, version_hash)
                if f.path == file_path
            ),
            None,
        )
        return attachment_response(data, media)

    @router.post(
        "/wiki/rules/{rule_id}/versions/{version_hash}/restore",
        response_model=DefinitionVersion,
        responses=_errors(),
    )
    def restore_version(
        rule_id: str,
        version_hash: str,
        body: Annotated[RestoreVersionRequest | None, Body()] = None,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> JSONResponse:
        """되돌리기 = 그 버전의 정의·본문으로 새 버전 저장. 응답 = 새 버전(``content`` 포함) +
        ``ETag``(새 정의 버전)."""
        svc = service()
        sc = svc.scope(space)
        if sc.own_rules:
            svc.require_writable(sc)
        store = sc.rules_store
        kind = svc.rules_kind.name
        store.get_version(kind, rule_id, version_hash)
        policy = svc.secret_policy(svc.settings())
        warnings: list[Any] = []
        try:
            files = store.list_version_files(kind, rule_id, version_hash)
        except NotFound:
            files = []
        for file in files:
            text = store.read_version_file(kind, rule_id, version_hash, file.path).decode(
                "utf-8", errors="replace"
            )
            decision = policy.check(text, KnownWikiAuthorKinds.USER, page=file.path)
            if decision.rejected:
                lines = [n for i in decision.issues for n in i.details.get("lines", [])]
                raise WikiSecretRejectedError(lines, issues=decision.issues)
            warnings.extend(decision.issues)
        expected = if_match_version(if_match)
        try:
            store.get(kind, rule_id)
        except NotFound:
            pass
        else:
            if expected is None:
                raise VersionRequired(f"{kind}/{rule_id}: If-Match is required to restore")
        message = body.message if body is not None and body.message else None
        stored = store.restore_version(
            kind,
            rule_id,
            version_hash,
            expected_version=expected,
            message=message or RESTORE_MESSAGE.format(hash=version_hash),
        )
        restored = store.get_version(kind, rule_id, stored.version_hash)
        response = JSONResponse(
            content=restored.model_dump(mode="json"),
            headers={"ETag": etag(stored.version_hash)},
        )
        issues = [i.model_dump(mode="json", exclude_none=True) for i in warnings]
        return with_issues(response, issues)

    return router


__all__ = ["RESTORE_MESSAGE", "build_rules_router"]
