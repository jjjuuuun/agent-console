"""REST: 로그(design §4R.10). 출처·범주·차원 이름을 모른다(레지스트리·설정·질의 엔진 데이터).

경로는 접두 없이 만들고 호스트가 ``/api/v1`` 아래 붙인다. 질의 경로는 막히는 색인 호출이라 동기
함수로 두고 FastAPI 스레드 풀에서 돈다. 필터는 쿼리 문자열 전체를 ``LogFilter``로 읽는다(모르는
이름은 422 ``validation_failed``, ``details.path``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, tzinfo
from typing import Any

from fastapi import APIRouter, Request, Response, status

from agent_console_contracts import ErrorResponse, HandoffMatrix
from agent_console_contracts.logs import (
    LogAggregateRequest,
    LogAggregateRow,
    LogArchive,
    LogClassifierDescriptor,
    LogDashboard,
    LogEventDetail,
    LogEventPage,
    LogQuerySchema,
    LogScanReport,
    LogSessionSummary,
    LogSourceInfo,
    LogTaxonomy,
    LogTimeline,
)
from agent_console_logs import (
    DEFAULT_ARCHIVE_TITLE,
    LogFilter,
    LogQueryError,
    parse_log_filter,
    parse_tz,
    render_archive,
)

from .errors import LogNotFoundError
from .service import LogsService
from .settings import DEFAULT_ARCHIVE_FILE_PREFIX

_ERRORS: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 422, 500)
}


SCAN_BODY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_ids": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "수집할 출처 id(생략 = 켜진 출처 전부).",
        }
    },
}
"""``POST /logs/scan`` 본문 모양(계약 밖 컴포넌트를 만들지 않으려고 인라인 스키마로 문서화)."""


async def read_scan_ids(request: Request) -> list[str] | None:
    """``POST /logs/scan`` 본문 → 출처 id 목록(본문 없음·``null`` = 전부).

    Raises:
        LogQueryError: 본문이 객체가 아니거나 ``source_ids``가 문자열 목록이 아님.
    """
    raw = await request.body()
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        raise LogQueryError("본문이 JSON이 아닙니다", "body") from None
    if data is None:
        return None
    if not isinstance(data, dict):
        raise LogQueryError("본문은 객체여야 합니다", "body")
    unknown = sorted(set(data) - {"source_ids"})
    if unknown:
        raise LogQueryError(f"모르는 필드: {unknown[0]}", unknown[0])
    ids = data.get("source_ids")
    if ids is None:
        return None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise LogQueryError("source_ids: 문자열 목록이어야 합니다", "source_ids")
    return list(ids)


def filter_params(request: Request) -> dict[str, Any]:
    """쿼리 문자열 → 이름별 값(여러 번 나온 이름은 목록)."""
    out: dict[str, Any] = {}
    for name, value in request.query_params.multi_items():
        if name in out:
            prev = out[name]
            out[name] = [*prev, value] if isinstance(prev, list) else [prev, value]
        else:
            out[name] = value
    return out


def read_filter(request: Request) -> LogFilter:
    """쿼리 문자열 → ``LogFilter``.

    Raises:
        LogQueryError: 모르는 이름·틀린 값(422로 바뀐다).
    """
    return parse_log_filter(filter_params(request))


ARCHIVE_FORMATS: dict[str, str] = {
    "json": "application/json",
    "html": "text/html; charset=utf-8",
}
"""보관본 형식 → 응답 미디어 형식."""

ARCHIVE_PARAMS = frozenset({"format", "tz"})
"""``GET /logs/archive``에서 ``LogFilter``가 아닌 쿼리 이름."""


def archive_options(params: dict[str, Any]) -> tuple[str, tzinfo | None, dict[str, Any]]:
    """``/logs/archive`` 쿼리 → (형식, 표시 시간대, 필터 이름별 값).

    Raises:
        LogQueryError: 모르는 형식(``format``)·시간대(``tz``).
    """
    rest = {k: v for k, v in params.items() if k not in ARCHIVE_PARAMS}

    def last(name: str) -> str | None:
        value = params.get(name)
        if isinstance(value, list):
            value = value[-1] if value else None
        return None if value in (None, "") else str(value)

    fmt = last("format") or "json"
    if fmt not in ARCHIVE_FORMATS:
        raise LogQueryError(f"format: {' 또는 '.join(ARCHIVE_FORMATS)}", "format")
    return fmt, parse_tz(last("tz")), rest


def archive_filename(prefix: str, exported_at: float, fmt: str) -> str:
    """내려받기 파일 이름(``<prefix>-<UTC YYYYmmdd-HHMMSS>.<fmt>``)."""
    stamp = datetime.fromtimestamp(exported_at, UTC).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}.{fmt}"


def build_router(
    service: Callable[[], LogsService],
    *,
    archive_file_prefix: str = DEFAULT_ARCHIVE_FILE_PREFIX,
    archive_title: str = DEFAULT_ARCHIVE_TITLE,
) -> APIRouter:
    """``/logs…`` 라우터.

    Args:
        service: 서비스를 돌려주는 함수(요청마다 부른다).
        archive_file_prefix: 보관본 파일 이름 앞부분(영문·숫자·``._-``).
        archive_title: 보관본 HTML 제목.
    """
    router = APIRouter()

    @router.get("/logs/sources", response_model=list[LogSourceInfo], responses=_ERRORS)
    def log_sources() -> list[LogSourceInfo]:
        """출처 목록: 디스크립터(설정 스키마 포함) + 켜짐 + 출처(plugin·runtime) + 수집 상태."""
        return service().sources()

    @router.get(
        "/logs/classifiers", response_model=list[LogClassifierDescriptor], responses=_ERRORS
    )
    def log_classifiers() -> list[LogClassifierDescriptor]:
        """등록된 분류기 디스크립터."""
        return service().classifiers()

    @router.post(
        "/logs/scan",
        response_model=LogScanReport,
        status_code=status.HTTP_202_ACCEPTED,
        responses=_ERRORS,
        openapi_extra={
            "requestBody": {
                "required": False,
                "content": {"application/json": {"schema": SCAN_BODY_SCHEMA}},
            }
        },
    )
    async def log_scan(request: Request) -> LogScanReport:
        """켜진 출처를 지금 한 번 수집한다(``source_ids``를 주면 그것만). 진행 중인 수집이
        요청을 덮으면 그 결과를 기다린다."""
        return await service().scan(await read_scan_ids(request))

    @router.get("/logs/events", response_model=LogEventPage, responses=_ERRORS)
    def log_events(request: Request) -> LogEventPage:
        """필터 목록(키셋 페이지, detail·raw 없음). 쿼리 이름은 ``GET /logs/schema``의 filters."""
        return service().events(read_filter(request))

    @router.get("/logs/events/{uid}", response_model=LogEventDetail, responses=_ERRORS)
    def log_event(uid: str) -> LogEventDetail:
        """이벤트 상세(본문·관련 이벤트·근거 연결 최대 1000·토큰 표본)."""
        found = service().event(uid)
        if found is None:
            raise LogNotFoundError("이벤트", uid)
        return found

    @router.get("/logs/sessions", response_model=list[LogSessionSummary], responses=_ERRORS)
    def log_sessions(request: Request) -> list[LogSessionSummary]:
        """세션 요약(마지막 시각 내림차순, ``limit``개)."""
        return service().sessions(read_filter(request))

    @router.get("/logs/sessions/{session}/timeline", response_model=LogTimeline, responses=_ERRORS)
    def log_timeline(session: str, request: Request) -> LogTimeline:
        """세션 하나의 보이는 이벤트(시각 → seq), 줄 = thread, 짝 이벤트 소요 시간."""
        flt = read_filter(request)
        found = service().timeline(session, flt)
        if found is None:
            raise LogNotFoundError("세션", session)
        return found

    @router.post("/logs/aggregate", response_model=list[LogAggregateRow], responses=_ERRORS)
    def log_aggregate(body: LogAggregateRequest) -> list[LogAggregateRow]:
        """집계(차원별 지표, 값 없는 지표는 null)."""
        return service().aggregate(body)

    @router.get("/logs/handoffs", response_model=HandoffMatrix, responses=_ERRORS)
    def log_handoffs(request: Request) -> HandoffMatrix:
        """from·to가 있는 이벤트의 (from, to, via) 횟수(많은 순)."""
        return service().handoffs(read_filter(request))

    @router.get("/logs/taxonomy", response_model=LogTaxonomy, responses=_ERRORS)
    def log_taxonomy() -> LogTaxonomy:
        """유효 분류 체계(기본 + 설정 ``logs.taxonomy``)."""
        return service().taxonomy()

    @router.get("/logs/dashboard-templates", response_model=list[LogDashboard], responses=_ERRORS)
    def log_dashboard_templates() -> list[LogDashboard]:
        """대시보드 템플릿(패키지 기본 데이터, 기간 필터 없음)."""
        return service().dashboard_templates()

    @router.get("/logs/schema", response_model=LogQuerySchema, responses=_ERRORS)
    def log_schema() -> LogQuerySchema:
        """집계 차원(``kind``)·지표(``unit``)·필터 이름 목록."""
        return service().schema()

    @router.get(
        "/logs/archive",
        response_model=LogArchive,
        responses={
            **_ERRORS,
            200: {
                "description": "보관본(첨부). json = LogArchive, html = 스크립트 없는 HTML",
                "content": {"text/html": {"schema": {"type": "string"}}},
            },
        },
    )
    def log_archive(request: Request) -> Response:
        """필터 범위의 오프라인 보관본(첨부).

        쿼리 = ``LogFilter`` + ``format``(json·html, 기본 json) + ``tz``(HTML 시각 표시 시간대,
        기본 서버 로컬). ``limit``·``cursor``는 쓰지 않고 설치자 상한(``archive_max_events``·
        ``archive_max_bytes``)까지 담는다(넘으면 ``truncated``).
        """
        fmt, tz, params = archive_options(filter_params(request))
        archive = service().archive(parse_log_filter(params))
        if fmt == "html":
            shown = tz or datetime.fromtimestamp(archive.exported_at).astimezone().tzinfo
            body = render_archive(archive, tz=shown, title=archive_title).encode("utf-8")
        else:
            body = archive.model_dump_json(by_alias=True).encode("utf-8")
        name = archive_filename(archive_file_prefix, archive.exported_at, fmt)
        return Response(
            content=body,
            media_type=ARCHIVE_FORMATS[fmt],
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    return router


__all__ = [
    "ARCHIVE_FORMATS",
    "ARCHIVE_PARAMS",
    "SCAN_BODY_SCHEMA",
    "archive_filename",
    "archive_options",
    "build_router",
    "filter_params",
    "read_filter",
    "read_scan_ids",
]
