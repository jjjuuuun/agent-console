"""모듈 예외와 오류 본문 대응(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``ProfileNotFoundError`` → ``architecture.profile_not_found``(404),
  ``details.profile`` = 요청한 id.
- ``ScopeTooLargeError`` → ``architecture.scope_too_large``(422), ``details`` =
  ``ArchitectureScopeTooLargeDetails{events, limit}``.
"""

from __future__ import annotations

from agent_console_contracts import ErrorCodes
from agent_console_contracts.architecture import ArchitectureScopeTooLargeDetails
from agent_console_modkit import ErrorMapping, ErrorReply


class ProfileNotFoundError(LookupError):
    """구조도 프로필이 없다.

    Attributes:
        profile: 요청한 id(기본 프로필을 요청했는데 프로필이 하나도 없으면 None).
    """

    def __init__(self, profile: str | None) -> None:
        self.profile = profile
        message = (
            f"구조도 프로필 {profile!r}이(가) 없습니다"
            if profile is not None
            else "구조도 프로필이 하나도 없습니다"
        )
        super().__init__(message)


class ScopeTooLargeError(ValueError):
    """투영할 이벤트 수가 상한을 넘었다.

    Attributes:
        events: 이벤트 수.
        limit: 상한.
    """

    def __init__(self, events: int, limit: int) -> None:
        self.events = events
        self.limit = limit
        super().__init__(f"이벤트가 {events}건으로 구조도 상한({limit})을 넘었습니다")


def profile_not_found_reply(exc: Exception) -> ErrorReply:
    """``ProfileNotFoundError`` → 오류 본문."""
    profile = exc.profile if isinstance(exc, ProfileNotFoundError) else None
    return ErrorReply(
        code=ErrorCodes.ARCHITECTURE_PROFILE_NOT_FOUND,
        message=str(exc),
        details={"profile": profile},
    )


def scope_too_large_reply(exc: Exception) -> ErrorReply:
    """``ScopeTooLargeError`` → 오류 본문."""
    events = exc.events if isinstance(exc, ScopeTooLargeError) else 0
    limit = exc.limit if isinstance(exc, ScopeTooLargeError) else 0
    details = ArchitectureScopeTooLargeDetails(events=events, limit=limit)
    return ErrorReply(
        code=ErrorCodes.ARCHITECTURE_SCOPE_TOO_LARGE,
        message=str(exc),
        details=details.model_dump(mode="json"),
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    ProfileNotFoundError: profile_not_found_reply,
    ScopeTooLargeError: scope_too_large_reply,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "ProfileNotFoundError",
    "ScopeTooLargeError",
    "profile_not_found_reply",
    "scope_too_large_reply",
]
