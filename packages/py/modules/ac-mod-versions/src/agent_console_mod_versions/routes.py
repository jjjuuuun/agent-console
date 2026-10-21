"""REST: 정의 종류 공통 버전 기록·비교·되돌리기(design §2R.9, R2.5).

경로(컬렉션마다 같은 모양, 컬렉션 표는 설정 데이터 ``collections``):

- `GET  {컬렉션}/{id}/versions` -- 버전 목록(본문 없음, 최신순)
- `GET  {컬렉션}/{id}/versions/{hash}` -- 버전 하나(`content` = 정의 원문, 가리지 않음)
- `GET  {컬렉션}/{id}/versions/{a}/diff[/{b}]` -- 비교(b 생략 = 현재). 비밀 위치 값은 `***`
- `GET  {컬렉션}/{id}/versions/{hash}/files[/{path}]` -- 그 버전의 본문 파일 목록·내용
- `POST {컬렉션}/{id}/versions/{hash}/restore` -- 되돌리기 = 새 버전 저장(`If-Match` = 현재 해시)

싱글턴 종류(설정)는 `{id}` 없이 `/settings/versions…`. 경로는 접두 없이 만들고 호스트가
``/api/v1``을 붙인다.

이 모듈은 경로 매개변수 이름(`graph_id` 등)을 컬렉션 표에서 정하므로 `from __future__ import
annotations`를 쓰지 않는다(FastAPI가 지역 `Annotated` 별칭을 읽어야 한다).
"""

from collections.abc import Callable, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, Path, Response
from fastapi.responses import JSONResponse

from agent_console_contracts import (
    DefinitionDiff,
    DefinitionVersion,
    ErrorResponse,
    ResourceFile,
    RestoreVersionRequest,
)

from .service import VersionService
from .settings import VersionedCollectionSetting

TEXT_FILE_MEDIA_TYPE = "text/plain; charset=utf-8"
BINARY_FILE_MEDIA_TYPE = "application/octet-stream"

_ERROR_STATUSES = (400, 401, 403, 404, 413, 422, 500)

IfMatch = Annotated[
    str | None,
    Header(alias="If-Match", description="마지막으로 받은 version_hash(ETag)."),
]


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses`: 공통 오류 + 추가 상태(모두 `ErrorResponse`)."""
    return {s: {"model": ErrorResponse} for s in (*_ERROR_STATUSES, *extra)}


def expected(if_match: str | None) -> str | None:
    """`If-Match` 값 → 기대 버전. 따옴표·약한 비교 접두어(`W/`)를 벗긴다."""
    if if_match is None:
        return None
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:]
    return value.strip('"') or None


def file_response(data: bytes, media_type: str | None) -> Response:
    """버전 본문 파일 응답. 텍스트는 `text/plain`(같은 출처에서 HTML로 그려지지 않게), 그 밖은
    바이너리. 원래 형식은 파일 목록(`ResourceFile.media_type`)에 있다."""
    is_text = media_type is not None and (
        media_type.startswith("text/") or media_type in ("application/json",)
    )
    return Response(
        content=data,
        media_type=TEXT_FILE_MEDIA_TYPE if is_text else BINARY_FILE_MEDIA_TYPE,
        headers={"Cache-Control": "no-store", "Content-Disposition": "attachment"},
    )


def _id_dependency(collection: VersionedCollectionSetting) -> Callable[..., str]:
    if collection.id_param is None:
        singleton = collection.kind

        def fixed() -> str:
            return singleton

        return fixed

    def from_path(item_id: Annotated[str, Path(alias=collection.id_param)]) -> str:
        return item_id

    return from_path


def _add_collection(
    router: APIRouter,
    collection: VersionedCollectionSetting,
    service: Callable[[], VersionService],
) -> None:
    kind = collection.kind
    label = collection.label or kind
    base = (
        collection.path
        if collection.id_param is None
        else f"{collection.path}/{{{collection.id_param}}}"
    )
    ItemId = Annotated[str, Depends(_id_dependency(collection))]  # noqa: N806
    tag = collection.path.strip("/").replace("/", "_")

    @router.get(
        f"{base}/versions",
        response_model=list[DefinitionVersion],
        responses=errors(),
        name=f"list_{tag}_versions",
    )
    async def list_versions(item_id: ItemId) -> list[DefinitionVersion]:
        """버전 목록(최신순, `content` 없음). 지운 정의의 이력도 남아 있다."""
        return service().store.list_versions(kind, item_id)

    @router.get(
        f"{base}/versions/{{version_hash}}",
        response_model=DefinitionVersion,
        responses=errors(),
        name=f"get_{tag}_version",
    )
    async def get_version(item_id: ItemId, version_hash: str) -> DefinitionVersion:
        """버전 하나(`content` = 그 버전의 정의 원문 -- 정의 GET처럼 가리지 않는다)."""
        return service().store.get_version(kind, item_id, version_hash)

    @router.get(
        f"{base}/versions/{{version_hash}}/diff",
        response_model=DefinitionDiff,
        responses=errors(),
        name=f"diff_{tag}_version_with_current",
    )
    async def diff_with_current(item_id: ItemId, version_hash: str) -> DefinitionDiff:
        """이 버전 → 현재 버전 비교. 정의가 지워졌으면 404(두 버전 비교를 쓴다)."""
        return service().diff(kind, item_id, version_hash, None)

    @router.get(
        f"{base}/versions/{{version_hash}}/diff/{{to_hash}}",
        response_model=DefinitionDiff,
        responses=errors(),
        name=f"diff_{tag}_versions",
    )
    async def diff_versions(item_id: ItemId, version_hash: str, to_hash: str) -> DefinitionDiff:
        """`version_hash` → `to_hash` 비교. `changes[].path`는 RFC 6901 JSON Pointer
        (`remove`·`replace` = 이전 버전 문서 기준, `add` = 이후 버전 문서 기준). 비밀 위치는
        `secret=true`이고 값은 `***`. `content_changes`는 본문 파일 sha256 비교."""
        return service().diff(kind, item_id, version_hash, to_hash)

    @router.get(
        f"{base}/versions/{{version_hash}}/files",
        response_model=list[ResourceFile],
        responses=errors(),
        name=f"list_{tag}_version_files",
    )
    async def list_files(item_id: ItemId, version_hash: str) -> list[ResourceFile]:
        """그 버전의 본문 파일(경로 순). 본문 스냅샷이 없으면 404(본문이 없는 종류, 0003 이전
        버전)."""
        return service().store.list_version_files(kind, item_id, version_hash)

    @router.get(
        f"{base}/versions/{{version_hash}}/files/{{file_path:path}}",
        response_class=Response,
        responses={**errors(), 200: {"content": {"application/octet-stream": {}}}},
        name=f"read_{tag}_version_file",
    )
    async def read_file(item_id: ItemId, version_hash: str, file_path: str) -> Response:
        """그 버전의 본문 파일 내용(텍스트는 `text/plain`, 그 밖은 `application/octet-stream`)."""
        store = service().store
        data = store.read_version_file(kind, item_id, version_hash, file_path)
        media = next(
            (
                f.media_type
                for f in store.list_version_files(kind, item_id, version_hash)
                if f.path == file_path
            ),
            None,
        )
        return file_response(data, media)

    @router.post(
        f"{base}/versions/{{version_hash}}/restore",
        response_model=DefinitionVersion,
        responses=errors(409, 412, 428),
        name=f"restore_{tag}_version",
    )
    async def restore(
        item_id: ItemId,
        version_hash: str,
        body: Annotated[RestoreVersionRequest | None, Body()] = None,
        if_match: IfMatch = None,
    ) -> JSONResponse:
        """되돌리기: 그 버전의 문서·본문으로 **새 버전**을 저장한다(이력은 지우지 않는다).

        정의가 있으면 `If-Match`(현재 해시) 필수(없음 428, 다름 412). 지운 정의는 `If-Match` 없이
        되살린다. 저장 전 검사(저장 라우트와 같음)에 error가 있으면 422(평문 비밀이 든 옛 버전 등).
        응답 = 새 버전(`content` 포함) + `ETag`. 메시지 기본값 "restored from <hash>".
        """
        svc = service()
        stored = svc.restore(
            kind,
            item_id,
            version_hash,
            expected_version=expected(if_match),
            message=body.message if body is not None else None,
            label=label,
        )
        version = svc.store.get_version(kind, item_id, stored.version_hash)
        return JSONResponse(
            content=version.model_dump(mode="json"),
            headers={"ETag": f'"{stored.version_hash}"'},
        )


def build_router(
    service: Callable[[], VersionService],
    collections: Sequence[VersionedCollectionSetting],
) -> APIRouter:
    """버전 기록·비교·되돌리기 라우트(컬렉션 표마다 같은 경로)."""
    router = APIRouter()
    for collection in collections:
        _add_collection(router, collection, service)
    return router


__all__ = ["build_router", "errors", "expected", "file_response"]
