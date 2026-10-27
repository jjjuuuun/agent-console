"""프로필 검사 보탬(X32 ``architecture.profile_checks``, M-4): 목록 본문에 없는 조건 경로 경고.

구조도 판정은 목록용 이벤트(상세 본문이 비어 있는 ``LogEvent``)로만 한다. 그래서 목록에서 빠지는
경로를 보는 조건은 늘 맞지 않는다. 어떤 경로가 빠지는지는 로그 쪽 사정이므로 이 연동이 데이터
(설치자 옵션 ``unlisted_paths``, 기본값 ``settings.DEFAULT_UNLISTED_PATHS``)로 낸다.
"""

from __future__ import annotations

from collections.abc import Iterable

from agent_console_architecture import unlisted_path_issues
from agent_console_contracts import Issue
from agent_console_contracts.architecture import ArchitectureProfile


class UnlistedPathCheck:
    """조건 경로가 ``prefixes`` 아래면 warning ``architecture.condition_path_unlisted``.

    Args:
        prefixes: 목록 본문에 없는 경로 접두(JSON Pointer). 비우면 아무것도 내지 않는다.
    """

    def __init__(self, prefixes: Iterable[str]) -> None:
        self.prefixes: tuple[str, ...] = tuple(prefixes)

    def check(self, profile: ArchitectureProfile, profile_id: str | None) -> list[Issue]:
        """``architecture.profile_checks`` 포트 모양. ``profile_id``는 쓰지 않는다."""
        del profile_id
        return unlisted_path_issues(profile, self.prefixes)

    def __repr__(self) -> str:
        return f"UnlistedPathCheck({list(self.prefixes)!r})"


__all__ = ["UnlistedPathCheck"]
