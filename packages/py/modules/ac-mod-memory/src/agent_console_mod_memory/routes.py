"""REST: 공유 메모리(design §5.7R.5.2). 범위 종류·태그·키 이름을 모른다(전부 데이터).

경로는 접두 없이 만들고 호스트가 ``/api/v1`` 아래 붙인다. 저장소를 부르는 처리기는 동기 함수라
FastAPI가 스레드에서 부른다(이벤트 루프를 막지 않는다). 응답에 비밀 의심 값·찾은 값을 싣지
않는다(쓰기 거부 422의 ``details``는 필드·규칙 id만).

- 고치기(``PUT``)는 ``If-Match: <version>``이 필수다(없으면 428 ``version_required``, 다르면 412
  ``version_conflict`` + ``details.current_version``). 옮기기·보관·지우기는 ``If-Match``가 선택이다.
- 만들기는 같은 범위·키가 있으면 409 ``already_exists``(``details.entry_id``).
- 쓰기 검사 실패는 422 ``memory.invalid_key``·``memory.too_large``·``memory.secret_rejected``.
- 공간(5.7R.33z): 항목·범위·태그·정리·내보내기/가져오기 경로와 ``/memory/scope-kinds``는 질의
  ``?project=<id>``(``modkit.host.SpaceQuery``, 정의 경로와 같은 이름)로 공간을 고른다. 없으면
  라이브러리. 공간 제공자가 없으면 409 ``feature_unavailable``, 모르는 공간은 404
  ``project.not_found``. 범위 종류·설정 검사는 공간과 무관하다(앱 설정 하나).
  ``POST /memory/copy``는 본문 ``source``·``target``으로 공간을 받는다.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from typing import IO, Annotated, Any, Final, cast, get_args

from fastapi import APIRouter, Body, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from agent_console_contracts import ErrorResponse, Issue
from agent_console_contracts.memory import (
    MEMORY_ENTRY_SORTS,
    MemoryCopyRequest,
    MemoryCopyResult,
    MemoryEntry,
    MemoryEntryPage,
    MemoryImportPolicy,
    MemoryImportResult,
    MemoryMoveRequest,
    MemoryRetentionPlan,
    MemoryRetentionPlanRequest,
    MemoryRetentionResult,
    MemoryScopeKindList,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryTagList,
    MemoryUpdateRequest,
    MemoryVersion,
    MemoryVersionSummary,
    MemoryWriteRequest,
)
from agent_console_memory import MemoryQuery, TooLargeError
from agent_console_modkit.host import IfMatchHeader, SpaceQuery, if_match_version, json_with_etag

from .errors import MemoryRequestError, VersionRequiredError
from .service import MemoryService

EXPORT_MEDIA_TYPE: Final = "application/zip"
"""내보내기 응답 형식."""

EXPORT_FILE_NAME: Final = "memory.zip"
"""내보내기 파일 이름(``Content-Disposition``)."""

SPOOL_BYTES: Final = 8 * 1024 * 1024
"""내보내기·가져오기 임시 버퍼를 메모리에 두는 최대 크기(넘으면 임시 파일)."""

_CHUNK: Final = 64 * 1024
_ORDERS: Final = ("asc", "desc")

ScopeQuery = Annotated[
    list[str] | None,
    Query(description="범위 `<종류>:<범위 id>`(여러 번 줄 수 있다, 생략 = 모든 범위)."),
]


def _errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorResponse} for status in statuses}


def parse_scopes(values: list[str] | None, *, name: str = "scope") -> list[MemoryScopeRef] | None:
    """질의 ``scope`` 값들 → 범위 목록(None = 조건 없음).

    Raises:
        MemoryRequestError: 범위 종류 id 형식이 틀림.
    """
    if not values:
        return None
    out: list[MemoryScopeRef] = []
    for value in values:
        try:
            out.append(MemoryScopeRef.parse(value))
        except (ValidationError, ValueError):
            raise MemoryRequestError("범위는 <종류>:<범위 id> 모양이어야 합니다", name) from None
    return out


def parse_version(value: str | None, *, required: bool) -> int | None:
    """``If-Match`` 값 → 버전(정수). 없으면 None(필수면 ``VersionRequiredError``).

    Raises:
        VersionRequiredError: 필수인데 없음.
        MemoryRequestError: 정수가 아님.
    """
    raw = if_match_version(value)
    if raw is None:
        if required:
            raise VersionRequiredError("고치려면 If-Match에 지금 버전을 주세요")
        return None
    if not raw.isdigit() or int(raw) < 1:
        raise MemoryRequestError("If-Match는 1 이상의 버전 번호여야 합니다", "If-Match")
    return int(raw)


def _entry_response(entry: MemoryEntry, *, status_code: int = 200) -> Response:
    return json_with_etag(
        entry.model_dump(mode="json"), version=str(entry.version), status_code=status_code
    )


def _iter_file(handle: IO[bytes]) -> Iterator[bytes]:
    try:
        handle.seek(0)
        while chunk := handle.read(_CHUNK):
            yield chunk
    finally:
        handle.close()


async def read_limited_body(request: Request, limit: int) -> IO[bytes]:
    """요청 본문을 임시 버퍼에 읽는다(``limit`` 바이트를 넘으면 그만 읽고 ``TooLargeError``)."""
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)  # noqa: SIM115 - 호출자가 닫는다
    size = 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise TooLargeError(
                    "가져올 파일이 상한을 넘었다", limit="max_archive_bytes", value=limit
                )
            spool.write(chunk)
    except BaseException:
        spool.close()
        raise
    spool.seek(0)
    return spool


def build_router(service: Callable[[], MemoryService]) -> APIRouter:
    """``/memory/*`` 라우터.

    Args:
        service: 라이브러리 서비스를 돌려주는 함수(요청마다 부른다). 공간은 그 서비스의
            ``space(name)``으로 고른다.
    """
    router = APIRouter()

    def pick(space: str | None) -> MemoryService:
        return service().space(space or None)

    # ---- 범위 ---------------------------------------------------------------------------

    @router.get(
        "/memory/scope-kinds",
        response_model=MemoryScopeKindList,
        responses=_errors(401, 403, 500),
    )
    def scope_kinds(space: SpaceQuery = None) -> MemoryScopeKindList:
        """병합된 범위 종류(패키지 기본 → 플러그인 → 사용자, 끈 종류는 ``disabled: true``).

        공간을 주면 그 공간이 열리는지 확인한 뒤 같은 목록(``context_fields`` 포함)을 준다.
        """
        return pick(space).scope_kinds()

    @router.get(
        "/memory/scopes",
        response_model=list[MemoryScopeSummary],
        responses=_errors(401, 403, 500),
    )
    def scopes(
        kind: Annotated[str | None, Query(description="범위 종류 id(생략 = 전부).")] = None,
        space: SpaceQuery = None,
    ) -> list[MemoryScopeSummary]:
        """항목이 있는 범위 요약(항목 수·보관 수·크기·최근 시각·``kind_known``)."""
        return pick(space).scopes(kind)

    @router.get("/memory/tags", response_model=MemoryTagList, responses=_errors(401, 403, 422, 500))
    def tags(
        scope: ScopeQuery = None,
        include_archived: Annotated[bool, Query(description="보관 항목도 센다.")] = False,
        space: SpaceQuery = None,
    ) -> MemoryTagList:
        """태그와 항목 수(항목 수 내림차순). 지운 항목은 세지 않는다.

        상한을 넘으면 ``truncated``.
        """
        return pick(space).tags(parse_scopes(scope), include_archived=include_archived)

    # ---- 항목 ---------------------------------------------------------------------------

    @router.get(
        "/memory/entries",
        response_model=MemoryEntryPage,
        responses=_errors(400, 401, 403, 422, 500),
    )
    def list_entries(
        scope: ScopeQuery = None,
        q: Annotated[str, Query(description="키·본문·태그 검색어(빈 값 = 조건 없음).")] = "",
        tag: Annotated[list[str] | None, Query(description="모두 붙어 있어야 하는 태그.")] = None,
        author_run: Annotated[str | None, Query(description="마지막으로 쓴 실행 id.")] = None,
        author_kind: Annotated[str | None, Query(description="마지막으로 쓴 주체 종류.")] = None,
        include_archived: bool = False,
        include_deleted: bool = False,
        sort: Annotated[str, Query(description="정렬 필드(`MEMORY_ENTRY_SORTS`).")] = "updated_at",
        order: Annotated[str, Query(description="정렬 방향(asc·desc).")] = "desc",
        cursor: Annotated[str | None, Query(description="앞 쪽 응답의 `next_cursor`.")] = None,
        limit: Annotated[int, Query(ge=1, description="쪽 크기(설치자 상한 이하로 줄인다).")] = 50,
        space: SpaceQuery = None,
    ) -> MemoryEntryPage:
        """목록·검색(``q`` = 키·본문·태그 전문 검색). 모르는 ``sort``·``order``는 422."""
        if sort not in MEMORY_ENTRY_SORTS:
            raise MemoryRequestError(
                f"정렬 값은 {', '.join(MEMORY_ENTRY_SORTS)} 중 하나여야 합니다", "sort"
            )
        if order not in _ORDERS:
            raise MemoryRequestError("정렬 방향은 asc·desc 중 하나여야 합니다", "order")
        query = MemoryQuery(
            scopes=parse_scopes(scope),
            text=q,
            tags=tuple(tag or ()),
            author_run=author_run or None,
            author_kind=author_kind or None,
            include_archived=include_archived,
            include_deleted=include_deleted,
            sort=sort,
            order="asc" if order == "asc" else "desc",
            cursor=cursor or None,
            limit=limit,
        )
        return pick(space).entries(query)

    @router.post(
        "/memory/entries",
        response_model=MemoryEntry,
        status_code=201,
        responses=_errors(401, 403, 409, 422, 500),
    )
    def create_entry(body: MemoryWriteRequest, space: SpaceQuery = None) -> Response:
        """새 항목(버전 1, 쓴 주체 = 사용자). 같은 범위·키가 있으면 409 ``already_exists``."""
        return _entry_response(pick(space).create(body), status_code=201)

    @router.get(
        "/memory/entries/{entry_id}",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 500),
    )
    def get_entry(
        entry_id: str, include_deleted: bool = False, space: SpaceQuery = None
    ) -> Response:
        """항목 하나(본문 포함, ``ETag`` = 버전). 지운 항목은 ``include_deleted``일 때만."""
        return _entry_response(pick(space).get(entry_id, include_deleted=include_deleted))

    @router.put(
        "/memory/entries/{entry_id}",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 412, 422, 428, 500),
    )
    def update_entry(
        entry_id: str,
        body: MemoryUpdateRequest,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> Response:
        """고치기(생략 = 그대로). ``If-Match`` 없음 → 428, 다름 → 412(``current_version``)."""
        version = parse_version(if_match, required=True)
        assert version is not None
        return _entry_response(pick(space).update(entry_id, body, if_version=version))

    @router.delete(
        "/memory/entries/{entry_id}",
        response_model=MemoryEntry,
        responses={
            **_errors(401, 403, 404, 412, 422, 500),
            204: {"description": "완전 삭제됨(purge=true)"},
        },
    )
    def delete_entry(
        entry_id: str,
        purge: Annotated[
            bool, Query(description="true면 버전·검색 행까지 완전히 지운다(되돌릴 수 없음).")
        ] = False,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> Response:
        """표시 삭제(기본, 지운 항목을 돌려준다) 또는 완전 삭제(``purge=true``, 204)."""
        if purge:
            pick(space).purge(entry_id)
            return Response(status_code=204)
        version = parse_version(if_match, required=False)
        return _entry_response(pick(space).delete(entry_id, if_version=version))

    @router.post(
        "/memory/entries/{entry_id}/move",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 409, 412, 422, 500),
    )
    def move_entry(
        entry_id: str,
        body: MemoryMoveRequest,
        if_match: IfMatchHeader = None,
        space: SpaceQuery = None,
    ) -> Response:
        """범위·키 옮기기(id 그대로, 같은 공간 안). 대상에 같은 키가 있으면 409."""
        version = parse_version(if_match, required=False)
        return _entry_response(pick(space).move(entry_id, body, if_version=version))

    @router.post(
        "/memory/entries/{entry_id}/archive",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 412, 422, 500),
    )
    def archive_entry(
        entry_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """보관(이미 보관이면 그대로)."""
        version = parse_version(if_match, required=False)
        return _entry_response(pick(space).archive(entry_id, archived=True, if_version=version))

    @router.post(
        "/memory/entries/{entry_id}/unarchive",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 412, 422, 500),
    )
    def unarchive_entry(
        entry_id: str, if_match: IfMatchHeader = None, space: SpaceQuery = None
    ) -> Response:
        """보관 풀기(이미 풀려 있으면 그대로)."""
        version = parse_version(if_match, required=False)
        return _entry_response(pick(space).archive(entry_id, archived=False, if_version=version))

    @router.post(
        "/memory/entries/{entry_id}/restore",
        response_model=MemoryEntry,
        responses=_errors(401, 403, 404, 409, 422, 500),
    )
    def restore_entry(
        entry_id: str,
        version: Annotated[
            int | None, Query(ge=1, description="이 버전의 본문으로(생략 = 지운 항목 되살리기).")
        ] = None,
        space: SpaceQuery = None,
    ) -> Response:
        """되돌리기. 되살릴 범위·키에 다른 항목이 있으면 409."""
        return _entry_response(pick(space).restore(entry_id, version=version))

    @router.get(
        "/memory/entries/{entry_id}/versions",
        response_model=list[MemoryVersionSummary],
        responses=_errors(401, 403, 404, 500),
    )
    def list_versions(entry_id: str, space: SpaceQuery = None) -> list[MemoryVersionSummary]:
        """버전 목록(오름차순, 본문 없음). 지운 항목도 본다."""
        return pick(space).versions(entry_id)

    @router.get(
        "/memory/entries/{entry_id}/versions/{version}",
        response_model=MemoryVersion,
        responses=_errors(401, 403, 404, 500),
    )
    def get_version(entry_id: str, version: int, space: SpaceQuery = None) -> MemoryVersion:
        """버전 하나(본문 포함)."""
        return pick(space).version(entry_id, version)

    # ---- 정리 ---------------------------------------------------------------------------

    @router.post(
        "/memory/retention/plan",
        response_model=MemoryRetentionPlan,
        responses=_errors(401, 403, 422, 500),
    )
    def retention_plan(
        body: Annotated[MemoryRetentionPlanRequest | None, Body()] = None,
        space: SpaceQuery = None,
    ) -> MemoryRetentionPlan:
        """정리 미리보기(아무것도 바꾸지 않는다). 본문 ``rules``로 저장 전 규칙을 시험할 수 있다.

        규칙 문제는 ``issues``(위치 ``/rules/<i>``, 저장된 규칙이면
        ``/memory/retention/rules/<i>``).
        """
        return pick(space).plan_retention(body)

    @router.post(
        "/memory/retention/apply",
        response_model=MemoryRetentionResult,
        responses=_errors(401, 403, 500),
    )
    def retention_apply(space: SpaceQuery = None) -> MemoryRetentionResult:
        """저장된 정리 규칙을 지금 적용한다.

        보관·표시 삭제만 하고, 쓴 주체가 ``system``인 버전으로 남아 되돌릴 수 있다.
        """
        return pick(space).apply_retention()

    @router.post(
        "/memory/settings/check",
        response_model=list[Issue],
        responses=_errors(401, 403, 500),
    )
    def check_settings(
        body: Annotated[
            dict[str, Any] | None,
            Body(description="편집 중인 `memory` 섹션(생략 = 빈 섹션)."),
        ] = None,
    ) -> list[Issue]:
        """설정 섹션 검사(형식·범위 종류 id 틀·정리 규칙 연산자). 저장을 막지 않는다."""
        return service().check_settings(body or {})

    # ---- 내보내기·가져오기 ------------------------------------------------------------------

    @router.get(
        "/memory/export",
        responses={
            **_errors(401, 403, 422, 500),
            200: {
                "description": "마크다운 zip(`<범위 종류>/<범위 id 또는 _>/<키>.md` + YAML 머리)",
                "content": {EXPORT_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            },
        },
    )
    def export(
        scope: ScopeQuery = None,
        include_archived: Annotated[bool, Query(description="보관 항목도 내보낸다.")] = True,
        space: SpaceQuery = None,
    ) -> StreamingResponse:
        """지우지 않은 항목을 마크다운 zip으로 내려받는다(폴더에 쓰지 않는다)."""
        scopes = parse_scopes(scope)
        svc = pick(space)
        spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)  # noqa: SIM115 - 응답이 닫는다
        try:
            svc.export_to(spool, scopes, include_archived=include_archived)
        except BaseException:
            spool.close()
            raise
        return StreamingResponse(
            _iter_file(spool),
            media_type=EXPORT_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{EXPORT_FILE_NAME}"',
                "Cache-Control": "no-store",
            },
        )

    @router.post(
        "/memory/import",
        response_model=MemoryImportResult,
        responses=_errors(401, 403, 422, 500),
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    EXPORT_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}},
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                },
            }
        },
    )
    async def import_archive(
        request: Request,
        policy: Annotated[
            str, Query(description="같은 범위·키가 있을 때: skip·overwrite·rename.")
        ] = "skip",
        dry_run: Annotated[bool, Query(description="true면 쓰지 않고 같은 수를 센다.")] = False,
        space: SpaceQuery = None,
    ) -> MemoryImportResult:
        """마크다운 zip(본문 그대로)을 가져온다. 경로 공격·암호화 항목은 그 파일만 거부하고,
        크기·항목 수 상한(zip 폭탄)은 422 ``memory.too_large``, zip이 아니면 422
        ``validation_failed``로 묶음 전체를 거부한다."""
        if policy not in get_args(MemoryImportPolicy):
            raise MemoryRequestError("policy는 skip·overwrite·rename 중 하나여야 합니다", "policy")
        svc = await run_in_threadpool(pick, space)
        chosen = cast(MemoryImportPolicy, policy)
        data = await read_limited_body(request, svc.transfer_limits.max_archive_bytes)
        try:
            return await run_in_threadpool(svc.import_archive, data, policy=chosen, dry_run=dry_run)
        finally:
            data.close()

    # ---- 공간 사이 복사 ---------------------------------------------------------------------

    @router.post(
        "/memory/copy",
        response_model=MemoryCopyResult,
        responses=_errors(400, 401, 403, 404, 409, 422, 500),
    )
    def copy(body: MemoryCopyRequest) -> MemoryCopyResult:
        """공간 사이 메모리 복사(라이브러리 ↔ 프로젝트, 프로젝트 ↔ 프로젝트).

        ``filter``로 고른 원본 항목을 대상에 새 항목으로 쓴다(쓴 주체 = 사용자, 버전 기록은 옮기지
        않음). 복사 뒤 독립이고 출처를 기록하지 않는다. 같은 범위·키가 대상에 있으면
        ``on_conflict``(skip·overwrite·rename)를 따르고 ``conflicts``에 남긴다. ``remap``은 범위 id
        바꾸기(어느 범위 종류가 대상인지는 화면이 범위 종류의 ``context_fields``로 판단한다).
        원본과 대상이 같으면 400 ``bad_request``.
        """
        return service().copy(body)

    return router


__all__ = [
    "EXPORT_FILE_NAME",
    "EXPORT_MEDIA_TYPE",
    "build_router",
    "parse_scopes",
    "parse_version",
    "read_limited_body",
]
