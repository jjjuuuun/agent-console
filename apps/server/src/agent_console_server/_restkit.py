"""호스트 경로 공용 값: API 접두와 OpenAPI 공통 오류 응답 문서.

기능 라우트 도구(If-Match·ETag·정의 원문 응답 등)는 각 모듈과 `agent_console_modkit.host`에 있다.
"""

from __future__ import annotations

from typing import Any

from agent_console_contracts import ErrorResponse

API_PREFIX = "/api/v1"

_ERRORS: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 413, 422, 500)
}


def errors(*extra: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses`: 공통 오류 + 추가 상태(모두 `ErrorResponse`)."""
    return {**_ERRORS, **{s: {"model": ErrorResponse} for s in extra}}


__all__ = ["API_PREFIX", "errors"]
