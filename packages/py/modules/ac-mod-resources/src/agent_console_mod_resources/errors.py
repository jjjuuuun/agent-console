"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes, Issue
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_store import StoreError, store_error_body

NOT_MULTI_FILE = "resource.not_multi_file"
"""여러 파일 본문을 쓰지 않는 종류에 파일을 쓰려 했다(이슈 코드)."""

RESERVED_FILE_NAME = "resource.reserved_file_name"
"""여러 파일 본문 경로에 예약 이름(설정 ``reserved_file_names``)이 있다(warning 이슈 코드,
저장은 된다)."""


class ResourceRejectedError(Exception):
    """리소스 종류 검사 등에 error 이슈가 있어 쓰지 않았다(422, ``details.issues``)."""

    def __init__(self, issues: Sequence[Issue], message: str) -> None:
        super().__init__(message)
        self.issues = list(issues)


class IdMismatchError(Exception):
    """경로의 id와 본문의 id가 다르다(400)."""

    def __init__(self, path_id: str, body_id: str) -> None:
        super().__init__("경로의 id와 본문의 리소스 id가 다릅니다")
        self.path_id = path_id
        self.body_id = body_id


class ContentNotFoundError(Exception):
    """리소스에 본문이 없다(404)."""


def _pointer(loc: Iterable[Any]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in loc)


def _issues_body(issues: Iterable[Issue]) -> dict[str, Any]:
    return {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]}


def store_error_reply(exc: Exception) -> ErrorReply:
    """``StoreError`` → 그 ``code``(공용 매핑 ``store_error_body``: 412는 현재 버전과 ``ETag``)."""
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def rejected_reply(exc: Exception) -> ErrorReply:
    issues = exc.issues if isinstance(exc, ResourceRejectedError) else []
    return ErrorReply(code=ErrorCodes.VALIDATION_FAILED, details=_issues_body(issues))


def id_mismatch_reply(exc: Exception) -> ErrorReply:
    details: Mapping[str, Any] = (
        {"path_id": exc.path_id, "body_id": exc.body_id} if isinstance(exc, IdMismatchError) else {}
    )
    return ErrorReply(code=ErrorCodes.BAD_REQUEST, details=details)


def model_error_reply(exc: Exception) -> ErrorReply:
    errors = (
        exc.errors(include_input=False, include_url=False)
        if isinstance(exc, ValidationError)
        else []
    )
    issues = [
        Issue(
            severity="error",
            code="request." + str(e.get("type", "invalid")),
            message=str(e.get("msg", "")),
            path=_pointer(e.get("loc", ())),
        )
        for e in errors
    ]
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="본문이 계약 형식에 맞지 않습니다",
        details=_issues_body(issues),
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    StoreError: store_error_reply,
    ResourceRejectedError: rejected_reply,
    IdMismatchError: id_mismatch_reply,
    ContentNotFoundError: ErrorCodes.NOT_FOUND,
    ValidationError: model_error_reply,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "NOT_MULTI_FILE",
    "ContentNotFoundError",
    "IdMismatchError",
    "ResourceRejectedError",
    "store_error_reply",
]
