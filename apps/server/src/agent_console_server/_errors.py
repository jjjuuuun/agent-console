"""호스트 수준 오류 → 계약 `ErrorResponse{error: ErrorInfo}` 변환(design §5.2 오류 코드 표).

기능 예외(저장소·실행 엔진 등)는 여기서 다루지 않는다. 각 모듈이 `ModuleParts.error_map`으로
알리고 호스트가 붙인다(3R.16). 여기에는 전송 계층 오류(요청 검증·HTTP 예외), 계약 모델 검증 실패,
처리되지 않은 예외(500, 메시지 숨김)만 있다.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    ErrorCodes,
    ErrorInfo,
    ErrorResponse,
    Issue,
)

_log = logging.getLogger("agent_console_server")

ISSUE_CODE_PREFIX = "request."
"""요청 본문 검증 실패를 `Issue`로 바꿀 때 code 접두어(뒤는 pydantic 오류 type)."""


class ApiError(Exception):
    """라우트가 던지는 계약 오류. 상태는 `HTTP_STATUS_BY_ERROR_CODE`(모르는 code는 `status`)."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.info = ErrorInfo(code=code, message=message, details=dict(details or {}))
        self.status = status or HTTP_STATUS_BY_ERROR_CODE.get(code, 400)


def status_of(code: str) -> int:
    return HTTP_STATUS_BY_ERROR_CODE.get(code, 400)


def error_response(
    info: ErrorInfo, status: int, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=info).model_dump(mode="json")
    return JSONResponse(body, status_code=status, headers=dict(headers or {}))


def _pointer(loc: Sequence[Any]) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in loc]
    return "".join("/" + p for p in parts)


def issues_from_errors(errors: Iterable[Mapping[str, Any]], *, drop_prefix: int = 0) -> list[Issue]:
    """pydantic 오류 목록 → `Issue[]`(입력 값은 담지 않는다). `path` = 본문 기준 JSON Pointer."""
    return [
        Issue(
            severity="error",
            code=ISSUE_CODE_PREFIX + str(e.get("type", "invalid")),
            message=str(e.get("msg", "")),
            path=_pointer(list(e.get("loc", ()))[drop_prefix:]),
        )
        for e in errors
    ]


def validation_failed(issues: Sequence[Issue], message: str) -> ApiError:
    """`validation_failed`(422). `details = {"issues": Issue[]}`(그래프·본문 검증 공통)."""
    return ApiError(
        ErrorCodes.VALIDATION_FAILED,
        message,
        {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]},
    )


def register_error_handlers(app: FastAPI, redact: Callable[[str], str] | None = None) -> None:
    """호스트 수준 오류를 `ErrorResponse` 하나로 보낸다. 500은 내부 메시지를 응답에 넣지 않는다.

    모듈 오류 맵(`install_error_map`)은 이 뒤에 붙인다(같은 예외 형식이면 모듈 것이 이긴다).
    `redact`: 메시지에서 비밀 값을 가리는 함수(보통 `secrets.redact` 포트).
    """

    def scrub(text: str) -> str:
        return redact(text) if redact is not None else text

    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError) -> JSONResponse:
        info = exc.info.model_copy(update={"message": scrub(exc.info.message)})
        return error_response(info, exc.status)

    @app.exception_handler(ValidationError)
    async def _model(_: Request, exc: ValidationError) -> JSONResponse:
        issues = issues_from_errors(exc.errors(include_input=False, include_url=False))
        api = validation_failed(issues, "본문이 계약 형식에 맞지 않습니다")
        return error_response(api.info, api.status)

    @app.exception_handler(RequestValidationError)
    async def _request(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = list(exc.errors())
        if any(e.get("type") == "json_invalid" for e in errors):
            info = ErrorInfo(code=ErrorCodes.BAD_REQUEST, message="JSON 형식이 아닙니다")
            return error_response(info, status_of(ErrorCodes.BAD_REQUEST))
        body = [e for e in errors if list(e.get("loc", ()))[:1] == ["body"]]
        other = [e for e in errors if e not in body]
        if other and not body:
            info = ErrorInfo(
                code=ErrorCodes.BAD_REQUEST,
                message="요청 인자가 잘못됐습니다",
                details={
                    "issues": [
                        i.model_dump(mode="json", exclude_none=True)
                        for i in issues_from_errors(other)
                    ]
                },
            )
            return error_response(info, status_of(ErrorCodes.BAD_REQUEST))
        api = validation_failed(
            issues_from_errors(body, drop_prefix=1), "본문이 계약 형식에 맞지 않습니다"
        )
        return error_response(api.info, api.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: ErrorCodes.UNAUTHORIZED,
            403: ErrorCodes.FORBIDDEN,
            404: ErrorCodes.NOT_FOUND,
            413: ErrorCodes.PAYLOAD_TOO_LARGE,
        }.get(
            exc.status_code,
            ErrorCodes.INTERNAL if exc.status_code >= 500 else ErrorCodes.BAD_REQUEST,
        )
        message = exc.detail if isinstance(exc.detail, str) else code
        return error_response(ErrorInfo(code=code, message=message), exc.status_code, exc.headers)

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        # 예외 메시지에 비밀이 섞일 수 있으므로 가린 뒤 남기고, 응답에는 넣지 않는다.
        _log.error(
            "처리되지 않은 오류: %s %s → %s: %s\n%s",
            request.method,
            request.url.path,
            exc.__class__.__name__,
            scrub(str(exc)),
            "".join(traceback.format_tb(exc.__traceback__)),  # 프레임 위치만(지역 변수·메시지 없음)
        )
        info = ErrorInfo(code=ErrorCodes.INTERNAL, message="서버 내부 오류")
        return error_response(info, status_of(ErrorCodes.INTERNAL))
