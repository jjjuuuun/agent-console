"""연동 설정(``modules.options.link-runs-usage``).

설치자용 고급 값만 둔다. 기록 공간 이름 접두는 기록 연동(``link-projects-records``)의
``space_prefix``를 이어받는다(값이 없을 때만).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat


class RunsUsageSettings(BaseModel):
    """실행·사용량 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    records_space_prefix: str = Field(
        default="project:",
        title="기록 공간 이름 접두",
        description=(
            "프로젝트 기록 DB 공간 이름 = 이 접두 + 프로젝트 id(기록 연동 설정 space_prefix를 "
            "이어받는다). 계정 사용량 창을 프로젝트 기록에서도 찾을 때 쓴다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )


SETTINGS_COMPAT = SettingsCompat(
    seeds=(
        SeedSetting("records_space_prefix", "modules.options.link-projects-records.space_prefix"),
    ),
)
"""기록 연동의 ``space_prefix``를 기록 공간 이름 접두의 기본값으로 이어받는다(값이 없을 때만)."""


__all__ = ["SETTINGS_COMPAT", "RunsUsageSettings"]
