"""모듈 예외와 오류 본문 대응(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``ArchitectureQueryError``(모르는 필터 이름·틀린 값) → 422 ``validation_failed``,
  ``details.path``.
- ``ProfileNotFoundError``(구조도 프로필이 하나도 없음) → 404 ``architecture.profile_not_found``.
- ``ScopeTooLargeError``(범위 이벤트가 ``max_scope_events``를 넘음) → 422
  ``architecture.scope_too_large``, ``details`` = ``ArchitectureScopeTooLargeDetails``.
- ``EventNotFoundError``(없는 이벤트 uid) → 404 ``not_found``.
"""

from __future__ import annotations

from typing import Final

from agent_console_contracts import ErrorCodes, Issue
from agent_console_contracts.architecture import ArchitectureScopeTooLargeDetails
from agent_console_modkit import ErrorMapping, ErrorReply

INVALID_QUERY: Final = "architecture.invalid_query"
"""질의 이슈 코드(``details.issues[].code``)."""


class ArchitectureQueryError(ValueError):
    """구조도 질의 인자가 틀렸다.

    Attributes:
        path: 문제 위치(쿼리 이름, 예: ``scope``·``profile``).
    """

    def __init__(self, message: str, path: str) -> None:
        super().__init__(message)
        self.path = path


class ProfileNotFoundError(LookupError):
    """그릴 구조도 프로필이 없다(프로필이 하나도 없거나 끈 프로필만 있음)."""

    def __init__(self, profile: str | None) -> None:
        self.profile = profile
        super().__init__(
            "구조도 프로필이 하나도 없습니다"
            if profile is None
            else f"구조도 프로필 {profile!r}을(를) 쓸 수 없습니다(프로필이 하나도 없습니다)"
        )


class ScopeTooLargeError(ValueError):
    """범위 이벤트 수가 상한을 넘었다.

    Attributes:
        events: 센 이벤트 수(상한을 넘은 순간까지 — 실제는 더 많을 수 있다).
        limit: 상한.
    """

    def __init__(self, events: int, limit: int) -> None:
        self.events = events
        self.limit = limit
        super().__init__(
            f"범위 이벤트가 {events}건 이상이라 구조도 상한({limit})을 넘었습니다. "
            "필터를 좁혀 주세요"
        )


class EventNotFoundError(LookupError):
    """없는 로그 이벤트."""

    def __init__(self, uid: str) -> None:
        self.uid = uid
        super().__init__(f"이벤트가 없습니다: {uid}")


def _query(exc: Exception) -> ErrorReply:
    path = exc.path if isinstance(exc, ArchitectureQueryError) else ""
    message = str(exc)
    issue = Issue(severity="error", code=INVALID_QUERY, message=message)
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message=message,
        details={"path": path, "issues": [issue.model_dump(mode="json", exclude_none=True)]},
    )


def _profile(exc: Exception) -> ErrorReply:
    profile = exc.profile if isinstance(exc, ProfileNotFoundError) else None
    return ErrorReply(
        code=ErrorCodes.ARCHITECTURE_PROFILE_NOT_FOUND,
        message=str(exc),
        details={"profile": profile},
    )


def _too_large(exc: Exception) -> ErrorReply:
    events = exc.events if isinstance(exc, ScopeTooLargeError) else 0
    limit = exc.limit if isinstance(exc, ScopeTooLargeError) else 0
    details = ArchitectureScopeTooLargeDetails(events=events, limit=limit)
    return ErrorReply(
        code=ErrorCodes.ARCHITECTURE_SCOPE_TOO_LARGE,
        message=str(exc),
        details=details.model_dump(mode="json"),
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    ArchitectureQueryError: _query,
    ProfileNotFoundError: _profile,
    ScopeTooLargeError: _too_large,
    EventNotFoundError: ErrorCodes.NOT_FOUND,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "INVALID_QUERY",
    "ArchitectureQueryError",
    "EventNotFoundError",
    "ProfileNotFoundError",
    "ScopeTooLargeError",
]
