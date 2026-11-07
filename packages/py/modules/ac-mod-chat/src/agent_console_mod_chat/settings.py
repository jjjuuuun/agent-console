"""채팅 모듈 설정(``modules.options.mod-chat``, 5.7R.33y2).

대화 동작 설정(``chat.*``)은 공통 설정·팀 구성 층에 있다(``workspace.settings``). 이 모듈 설정은
설치자용 고급 값만 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat

from .spaces import DEFAULT_LOCATE_LIMIT


class ChatModuleSettings(BaseModel):
    """채팅 모듈 설정."""

    model_config = ConfigDict(extra="forbid")

    records_space_prefix: str = Field(
        default="project:",
        title="기록 공간 이름 접두",
        description=(
            "프로젝트 기록 DB 공간 이름 = 이 접두 + 프로젝트 id(기록 연동 설정 space_prefix를 "
            "이어받는다)."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )
    locate_max_projects: int = Field(
        default=DEFAULT_LOCATE_LIMIT,
        ge=0,
        title="대화 위치 찾기 프로젝트 수 상한",
        description=(
            "주소로 바로 연 대화가 어느 프로젝트 기록에 있는지 찾을 때 읽는 등록 프로젝트 기록 DB "
            "최대 개수(0 = 이 서버가 이미 연 프로젝트와 앱 기록만)."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )


SETTINGS_COMPAT = SettingsCompat(
    seeds=(
        SeedSetting("records_space_prefix", "modules.options.link-projects-records.space_prefix"),
    ),
)
"""기록 연동의 ``space_prefix``를 기록 공간 이름 접두의 기본값으로 이어받는다(값이 없을 때만)."""


__all__ = ["SETTINGS_COMPAT", "ChatModuleSettings"]
