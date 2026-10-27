"""link-runs-teams 설정(설치자 값, ``modules.options.link-runs-teams``)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_console_contracts import x_ui

from .fixes import DEFAULT_ISSUE_FIXES, IssueFixes, load_issue_fixes

__all__ = ["RunsTeamsLinkSettings", "issue_fixes_of"]

_log = logging.getLogger("agent_console_link_runs_teams")


class RunsTeamsLinkSettings(BaseModel):
    """팀 규칙 검증의 해결 버튼 표(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    issue_fixes_file: Path | None = Field(
        default=None,
        title="해결 버튼 표 파일",
        description=(
            "오류 코드별 해결 버튼 표(JSON). 비우면 기본 표, 규칙이 빈 표 파일이면 버튼 없음. "
            "상대 경로는 설정 파일 폴더 기준."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="issue-fixes.json",
            when="해결 버튼을 바꾸거나 끌 때.",
        ),
    )

    @field_validator("issue_fixes_file", mode="before")
    @classmethod
    def _blank_is_default(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


def issue_fixes_of(path: Path | None, base: Path | None = None) -> IssueFixes:
    """설치자 옵션 ``issue_fixes_file`` → 해결 버튼 표.

    Args:
        path: 표 파일(None = 패키지 기본 ``DEFAULT_ISSUE_FIXES``). 상대 경로는 ``base`` 기준.
        base: 설정 파일 폴더.

    Returns:
        해결 버튼 표. 파일이 없으면 경고를 남기고 빈 표(버튼 없음).

    Raises:
        ValueError: 파일 내용이 JSON이 아닐 때(``json.JSONDecodeError``).
    """
    if path is None:
        return DEFAULT_ISSUE_FIXES
    if not path.is_absolute() and base is not None:
        path = base / path
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        _log.warning("해결 버튼 표 파일이 없어 빈 표를 씁니다: %s", path)
        return IssueFixes()
    return load_issue_fixes(text)
