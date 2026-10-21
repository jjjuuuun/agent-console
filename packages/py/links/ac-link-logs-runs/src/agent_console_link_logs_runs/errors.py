"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). ``mod-logs``의 ``/logs…``와 같은 모양이다.

- ``LogQueryError``(모르는 필터, 틀린 값) → 422 ``validation_failed``,
  ``details = {path, issues: [Issue(code = logs.invalid_query)]}``.
- ``RunNotFoundError`` → 404 ``not_found``.
"""

from __future__ import annotations

from agent_console_contracts import ErrorCodes, Issue
from agent_console_logs import LogQueryError
from agent_console_modkit import ErrorMapping, ErrorReply

from .views import RunNotFoundError

INVALID_QUERY = "logs.invalid_query"
"""질의 이슈 코드(``details.issues[].code``, ``mod-logs``와 같은 값)."""


def _query(exc: Exception) -> ErrorReply:
    path = exc.path if isinstance(exc, LogQueryError) else ""
    message = str(exc)
    issue = Issue(severity="error", code=INVALID_QUERY, message=message)
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message=message,
        details={"path": path, "issues": [issue.model_dump(mode="json", exclude_none=True)]},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    LogQueryError: _query,
    RunNotFoundError: ErrorCodes.NOT_FOUND,
}

__all__ = ["ERROR_MAP", "INVALID_QUERY"]
