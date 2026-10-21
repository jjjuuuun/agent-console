"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``StoreError`` → 그 ``code``(404·409·412 등, 412는 현재 버전과 ``ETag``).
- pydantic ``ValidationError``(손으로 고친 파일이 계약에 맞지 않음) → ``validation_failed``.
"""

from __future__ import annotations

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_store import StoreError, store_error_body


def store_error_reply(exc: Exception) -> ErrorReply:
    """``StoreError`` → 그 ``code``(공용 매핑 ``store_error_body``)."""
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def model_error_reply(exc: Exception) -> ErrorReply:
    """저장된 파일이 계약 형식에 맞지 않음(입력 값은 담지 않는다)."""
    count = len(exc.errors()) if isinstance(exc, ValidationError) else 0
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="저장된 프로젝트 파일이 형식에 맞지 않습니다",
        details={"errors": count},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    StoreError: store_error_reply,
    ValidationError: model_error_reply,
}
"""모듈 ``error_map``."""

__all__ = ["ERROR_MAP", "model_error_reply", "store_error_reply"]
