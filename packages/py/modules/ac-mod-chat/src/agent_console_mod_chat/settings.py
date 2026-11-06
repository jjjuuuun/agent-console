"""채팅 모듈 설정(``modules.options.mod-chat``, 5.7R.33y2).

대화 동작 설정(``chat.*``)은 공통 설정·팀 구성 층에 있다(``workspace.settings``). 이 모듈 설정은
설치자용 고급 값만 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat


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


SETTINGS_COMPAT = SettingsCompat(
    seeds=(
        SeedSetting("records_space_prefix", "modules.options.link-projects-records.space_prefix"),
    ),
)
"""기록 연동의 ``space_prefix``를 기록 공간 이름 접두의 기본값으로 이어받는다(값이 없을 때만)."""


__all__ = ["SETTINGS_COMPAT", "ChatModuleSettings"]
