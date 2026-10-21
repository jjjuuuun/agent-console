"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``StoreError`` → 그 ``code``. 412(``version_conflict``)는 ``details``(현재 버전)와 ``ETag``.
- ``DefinitionRejectedError``(저장 전 검사 error) → ``validation_failed``(``details.issues``).
- ``IdMismatchError``(경로 id ≠ 본문 id) → ``bad_request``(``details.path_id``·``body_id``).
- pydantic ``ValidationError``(손으로 고친 파일이 계약에 맞지 않음) → ``validation_failed``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes, Issue
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_store import StoreError, store_error_body

ISSUE_CODE_PREFIX = "request."
"""모델 검증 실패를 ``Issue``로 바꿀 때 code 접두어(뒤는 pydantic 오류 type)."""


class DefinitionRejectedError(Exception):
    """저장 전 검사에 error 이슈가 있어 저장하지 않았다(422).

    Args:
        issues: 모든 검사 이슈(path = 요청 문서 기준, 메시지에 값 없음).
        what: 사람이 읽는 정의 이름(예: ``"에이전트 설정"``).
    """

    def __init__(self, issues: Sequence[Issue], what: str) -> None:
        super().__init__(f"{what}에 오류가 있어 저장하지 않았습니다")
        self.issues = list(issues)


class IdMismatchError(Exception):
    """경로의 id와 본문의 id가 다르다(400)."""

    def __init__(self, path_id: str, body_id: str, what: str) -> None:
        super().__init__(f"경로의 id와 본문의 {what} id가 다릅니다")
        self.path_id = path_id
        self.body_id = body_id


def reject_errors(issues: Sequence[Issue], what: str) -> None:
    """검사 이슈에 error가 있으면 ``DefinitionRejectedError``."""
    if any(i.severity == "error" for i in issues):
        raise DefinitionRejectedError(issues, what)


def _pointer(loc: Iterable[Any]) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in loc]
    return "".join("/" + p for p in parts)


def issues_from_errors(errors: Iterable[Mapping[str, Any]]) -> list[Issue]:
    """pydantic 오류 목록 → ``Issue[]``(입력 값은 담지 않는다)."""
    return [
        Issue(
            severity="error",
            code=ISSUE_CODE_PREFIX + str(e.get("type", "invalid")),
            message=str(e.get("msg", "")),
            path=_pointer(e.get("loc", ())),
        )
        for e in errors
    ]


def _issues_body(issues: Iterable[Issue]) -> dict[str, Any]:
    return {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]}


def store_error_reply(exc: Exception) -> ErrorReply:
    """``StoreError`` → 그 ``code``(공용 매핑 ``store_error_body``: 412는 현재 버전과 ``ETag``)."""
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def rejected_reply(exc: Exception) -> ErrorReply:
    issues = exc.issues if isinstance(exc, DefinitionRejectedError) else []
    return ErrorReply(code=ErrorCodes.VALIDATION_FAILED, details=_issues_body(issues))


def id_mismatch_reply(exc: Exception) -> ErrorReply:
    details = (
        {"path_id": exc.path_id, "body_id": exc.body_id} if isinstance(exc, IdMismatchError) else {}
    )
    return ErrorReply(code=ErrorCodes.BAD_REQUEST, details=details)


def model_error_reply(exc: Exception) -> ErrorReply:
    issues = (
        issues_from_errors(exc.errors(include_input=False, include_url=False))
        if isinstance(exc, ValidationError)
        else []
    )
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="본문이 계약 형식에 맞지 않습니다",
        details=_issues_body(issues),
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    StoreError: store_error_reply,
    DefinitionRejectedError: rejected_reply,
    IdMismatchError: id_mismatch_reply,
    ValidationError: model_error_reply,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "DefinitionRejectedError",
    "IdMismatchError",
    "id_mismatch_reply",
    "issues_from_errors",
    "model_error_reply",
    "reject_errors",
    "rejected_reply",
    "store_error_reply",
]
