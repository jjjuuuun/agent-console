"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``LogQueryError``(모르는 필터·차원·지표, 틀린 값) → 422 ``validation_failed``,
  ``details = {path, issues: [Issue]}``(``path``는 문제 위치, 예: ``filter.foo``·``metric``).
- ``LogNotFoundError``(없는 이벤트·세션) → 404 ``not_found``.
- ``LogPurgeUnsupportedError``(색인이 비우기를 지원하지 않음) → ``logs.purge_unsupported``
  (계약 상태 표에 없는 코드라 400), ``details.index`` = 색인 형식 이름.
"""

from __future__ import annotations

from agent_console_contracts import ErrorCodes, Issue
from agent_console_logs import LogQueryError
from agent_console_modkit import ErrorMapping, ErrorReply

INVALID_QUERY = "logs.invalid_query"
"""질의 이슈 코드(``details.issues[].code``)."""

PURGE_UNSUPPORTED = "logs.purge_unsupported"
"""오류 코드: 지금 색인 구현이 비우기(``PurgeableLogIndex``)를 지원하지 않는다."""


class LogNotFoundError(LookupError):
    """없는 이벤트·세션."""

    def __init__(self, kind: str, key: str) -> None:
        super().__init__(f"{kind}이(가) 없습니다: {key}")
        self.kind = kind
        self.key = key


class LogPurgeUnsupportedError(TypeError):
    """색인이 비우기를 지원하지 않는다(서버 오류가 아니라 요청을 받을 수 없는 상태).

    Attributes:
        index: 색인 형식 이름.
    """

    def __init__(self, index: str) -> None:
        super().__init__(f"이 로그 색인({index})은 비우기를 지원하지 않습니다")
        self.index = index


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


def _purge_unsupported(exc: Exception) -> ErrorReply:
    index = exc.index if isinstance(exc, LogPurgeUnsupportedError) else ""
    return ErrorReply(code=PURGE_UNSUPPORTED, message=str(exc), details={"index": index})


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    LogQueryError: _query,
    LogNotFoundError: _not_found,
    LogPurgeUnsupportedError: _purge_unsupported,
}

__all__ = [
    "ERROR_MAP",
    "INVALID_QUERY",
    "PURGE_UNSUPPORTED",
    "LogNotFoundError",
    "LogPurgeUnsupportedError",
]
