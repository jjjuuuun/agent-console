"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다."""

from __future__ import annotations

from agent_console_contracts import ErrorCodes
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_store import StoreError, store_error_body

from .service import RestoreRejectedError


def store_error_reply(exc: Exception) -> ErrorReply:
    """``StoreError`` → 그 ``code``(공용 매핑 ``store_error_body``: 412는 현재 버전과 ``ETag``)."""
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def restore_rejected_reply(exc: Exception) -> ErrorReply:
    """``RestoreRejectedError`` → ``validation_failed``(``details.issues``)."""
    issues = exc.issues if isinstance(exc, RestoreRejectedError) else []
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        details={"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    StoreError: store_error_reply,
    RestoreRejectedError: restore_rejected_reply,
}
"""모듈 ``error_map``."""

__all__ = ["ERROR_MAP", "restore_rejected_reply", "store_error_reply"]
