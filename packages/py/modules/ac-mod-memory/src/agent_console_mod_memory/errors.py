"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

``ac-memory`` 오류(``MemoryStoreError``, 본문·찾은 비밀 값을 싣지 않는다)를 REST 코드로 옮긴다.

| 예외 | 코드(HTTP) | details |
| --- | --- | --- |
| ``EntryNotFoundError`` | ``not_found``(404) | — |
| ``EntryExistsError`` | ``already_exists``(409) | ``entry_id`` |
| ``VersionConflictError`` | ``version_conflict``(412) | ``entry_id``·``current_version`` |
| ``InvalidKeyError`` | ``memory.invalid_key``(422) | — |
| ``TooLargeError`` | ``memory.too_large``(422) | ``limit``·``value`` |
| ``SecretRejectedError`` | ``memory.secret_rejected``(422) | ``MemorySecretRejectedDetails`` |
| ``InvalidArchiveError`` | ``validation_failed``(422) | ``path`` |
| 그 밖의 ``MemoryStoreError``(커서 형식 등) | ``bad_request``(400) | — |
| ``MemoryRequestError``(틀린 질의·본문) | ``validation_failed``(422) | ``path``·``issues`` |
| ``VersionRequiredError``(``If-Match`` 없음) | ``version_required``(428) | — |
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from agent_console_contracts import ErrorCodes, Issue
from agent_console_memory import (
    EntryExistsError,
    EntryNotFoundError,
    InvalidArchiveError,
    InvalidKeyError,
    MemoryStoreError,
    SecretRejectedError,
    TooLargeError,
    VersionConflictError,
)
from agent_console_modkit import ErrorMapping, ErrorReply

INVALID_REQUEST: Final = "memory.invalid_request"
"""요청 이슈 코드(``details.issues[].code``): 질의 인자·본문 모양이 틀렸다."""


class MemoryRequestError(ValueError):
    """질의 인자·본문이 틀렸다(422 ``validation_failed``). 입력 값은 메시지에 싣지 않는다.

    Attributes:
        path: 문제 위치(예: ``scope``·``sort``·``body``).
    """

    def __init__(self, message: str, path: str) -> None:
        super().__init__(message)
        self.path = path


class VersionRequiredError(ValueError):
    """``If-Match``가 필요한 요청에 없다(428 ``version_required``)."""


def _request(exc: Exception) -> ErrorReply:
    path = exc.path if isinstance(exc, MemoryRequestError) else ""
    message = str(exc)
    issue = Issue(severity="error", code=INVALID_REQUEST, message=message)
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message=message,
        details={"path": path, "issues": [issue.model_dump(mode="json", exclude_none=True)]},
    )


def _version_required(exc: Exception) -> ErrorReply:
    return ErrorReply(code=ErrorCodes.VERSION_REQUIRED, message=str(exc))


def _details(exc: MemoryStoreError) -> Mapping[str, Any]:
    if isinstance(exc, VersionConflictError):
        return {"entry_id": exc.entry_id, "current_version": exc.current_version}
    if isinstance(exc, EntryExistsError):
        return {"entry_id": exc.entry_id}
    if isinstance(exc, TooLargeError):
        return {"limit": exc.limit, "value": exc.value}
    if isinstance(exc, SecretRejectedError):
        return exc.details().model_dump(mode="json")
    if isinstance(exc, InvalidArchiveError):
        return {"path": "body"}
    return {}


def store_error_code(exc: MemoryStoreError) -> str:
    """저장소 오류 → REST 오류 코드."""
    if isinstance(exc, EntryNotFoundError):
        return ErrorCodes.NOT_FOUND
    if isinstance(exc, VersionConflictError):
        return ErrorCodes.VERSION_CONFLICT
    if isinstance(exc, EntryExistsError):
        return ErrorCodes.ALREADY_EXISTS
    if isinstance(exc, InvalidKeyError):
        return ErrorCodes.MEMORY_INVALID_KEY
    if isinstance(exc, TooLargeError):
        return ErrorCodes.MEMORY_TOO_LARGE
    if isinstance(exc, SecretRejectedError):
        return ErrorCodes.MEMORY_SECRET_REJECTED
    if isinstance(exc, InvalidArchiveError):
        return ErrorCodes.VALIDATION_FAILED
    return ErrorCodes.BAD_REQUEST


def _store(exc: Exception) -> ErrorReply:
    if not isinstance(exc, MemoryStoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.BAD_REQUEST)
    return ErrorReply(code=store_error_code(exc), message=exc.message, details=dict(_details(exc)))


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    MemoryStoreError: _store,
    MemoryRequestError: _request,
    VersionRequiredError: _version_required,
}
"""모듈 ``error_map``(하위 형식은 예외 처리기가 상속 순서로 찾는다)."""

__all__ = [
    "ERROR_MAP",
    "INVALID_REQUEST",
    "MemoryRequestError",
    "VersionRequiredError",
    "store_error_code",
]
