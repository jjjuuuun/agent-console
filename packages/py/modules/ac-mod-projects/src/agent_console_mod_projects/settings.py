"""mod-projects 설정(설치자 값, ``modules.options.mod-projects``)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import SeedSetting, SettingsCompat

DEFAULT_DIRECTORY = "projects"
"""프로젝트 파일 폴더(워크스페이스 기준, ``projects/<id>.yaml``, design §UX-P.4)."""


class ProjectModuleSettings(BaseModel):
    """프로젝트 모듈 설정."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(
        title="프로젝트 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_DIRECTORY,
        pattern=r"^[A-Za-z0-9_\-]+$",
        description="프로젝트 파일을 둘 워크스페이스 안 폴더 이름.",
    )
    messages: dict[str, str] = Field(
        title="범위 검사 문구",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=dict,
        description=(
            "범위 검사 문구 바꾸기(문제 코드 → 문구 틀, $이름 자리 채움). 비운 코드는 기본 문구."
        ),
    )
    working_directory: Path | None = Field(
        default=None,
        title="앱 작업 폴더",
        description=(
            "폴더를 정하지 않은 프로젝트의 폴더이자 현재 프로젝트를 고르는 기준. 비우면 실행 "
            "설정의 작업 폴더, 그것도 없으면 설정 파일 폴더."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            example="./project",
            when="실행 모듈 없이 프로젝트 폴더 기준을 따로 정해야 할 때.",
        ),
    )
    snapshot_ttl_seconds: float = Field(
        title="정의 목록 재사용 시간",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
        default=2.0,
        ge=0,
        description=(
            "범위 검사가 읽은 정의 목록을 다시 쓰는 시간. 정의를 저장하면 바로 버린다. 0이면 매번 "
            "읽는다."
        ),
    )


SETTINGS_COMPAT = SettingsCompat(
    seeds=(SeedSetting("working_directory", "modules.options.mod-runs.working_directory"),),
)
"""실행 모듈의 작업 폴더를 앱 작업 폴더 기본값으로 쓴다(값이 없을 때만)."""


__all__ = ["DEFAULT_DIRECTORY", "SETTINGS_COMPAT", "ProjectModuleSettings"]
