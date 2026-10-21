"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``LogQueryError``(모르는 필터·차원·지표, 틀린 값) → 422 ``validation_failed``,
  ``details = {path, issues: [Issue]}``(``path``는 문제 위치, 예: ``filter.foo``·``metric``).
- ``LogNotFoundError``(없는 이벤트·세션) → 404 ``not_found``.
"""

from __future__ import annotations

from agent_console_contracts import ErrorCodes, Issue
from agent_console_logs import LogQueryError
from agent_console_modkit import ErrorMapping, ErrorReply

INVALID_QUERY = "logs.invalid_query"
"""질의 이슈 코드(``details.issues[].code``)."""


class LogNotFoundError(LookupError):
    """없는 이벤트·세션."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"{kind}이(가) 없습니다: {key}")
        self.kind = kind
        self.key = key


def _query(exc: Exception) -> ErrorReply:
    path = exc.path if isinstance(exc, LogQueryError) else ""
    message = str(exc)
    issue = Issue(severity="error", code=INVALID_QUERY, message=message)
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message=message,
        details={"path": path, "issues": [issue.model_dump(mode="json", exclude_none=True)]},
    )


def _not_found(exc: Exception) -> ErrorReply:
    return ErrorReply(code=ErrorCodes.NOT_FOUND, message=str(exc))


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    LogQueryError: _query,
    LogNotFoundError: _not_found,
}

__all__ = ["ERROR_MAP", "INVALID_QUERY", "LogNotFoundError"]
