"""mod-presets 설정(설치자 값, ``modules.options.mod-presets``)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import (
    PATHSEP,
    EnvSetting,
    FlagSetting,
    RemovedSetting,
    SettingsCompat,
)


class PresetModuleSettings(BaseModel):
    """프리셋 폴더·시작 시 적용."""

    model_config = ConfigDict(extra="forbid")

    directories: list[Path] = Field(
        title="프리셋 폴더",
        json_schema_extra=x_ui(tier="advanced", example=["presets"]),
        default_factory=list,
        description=(
            "프리셋을 찾을 폴더 목록(앞쪽 우선, 상대 경로는 설정 파일 폴더 기준). 기본은 비어 있다."
        ),
    )
    apply_on_start: list[str] = Field(
        title="시작할 때 적용할 프리셋",
        json_schema_extra=x_ui(
            tier="basic",
            example=["starter-team"],
            when="새 워크스페이스를 늘 같은 팀 구성으로 시작하고 싶을 때.",
        ),
        default_factory=list,
        description="서버 시작 때 워크스페이스에 복사할 프리셋 id. 없는 id면 시작이 실패한다.",
    )
    on_conflict: Literal["skip", "overwrite", "rename"] = Field(
        title="같은 id가 있을 때",
        json_schema_extra=x_ui(tier="advanced"),
        default="skip",
        description="같은 id가 이미 있을 때 기본 처리(skip = 내가 만든 정의를 그대로 둔다).",
    )


SETTINGS_COMPAT = SettingsCompat(
    # 옛 최상위 presets(그 아래 2R.20에서 지운 set_default_entry 포함)는 통째로 거부한다.
    removed=(RemovedSetting("presets", new="modules.options.mod-presets"),),
    env=(
        EnvSetting("PRESET_DIRS", ("directories",), split=PATHSEP),
        EnvSetting("APPLY_PRESETS", ("apply_on_start",), split=","),
    ),
    flags=(
        FlagSetting(
            "apply-preset",
            ("apply_on_start",),
            help="시작할 때 workspace에 적용할 프리셋 id(여러 번 가능, 충돌 시 건너뜀)",
            metavar="ID",
            repeat=True,
        ),
    ),
)
"""호스트 설정 호환: 옛 최상위 ``presets``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 안내). 환경변수 ``<접두어>PRESET_DIRS``
(경로 구분자)·``APPLY_PRESETS``(쉼표), 명령행 ``--apply-preset ID``."""


__all__ = ["SETTINGS_COMPAT", "PresetModuleSettings"]
