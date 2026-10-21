"""mod-exports 설정(설치자 값, ``modules.options.mod-exports``).

기본은 보관 파일(zip) 응답만이다. 폴더 쓰기는 ``roots``에 등록한 곳에서만 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SeedSetting, SettingsCompat


class ExportRootSetting(BaseModel):
    """내보내기 폴더 쓰기를 허용한 루트 하나(설치자만 등록, 웹에서 바꾸지 않는다)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        title="id",
        json_schema_extra=x_ui(tier="basic", when="새 폴더를 등록할 때 이름을 정합니다."),
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
        description="내보내기 화면에서 이 폴더를 고를 때 쓰는 이름.",
    )
    label: str = Field(
        title="화면 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default="",
        description="화면 이름(비우면 id).",
    )
    path: Path = Field(
        title="폴더",
        json_schema_extra=x_ui(tier="basic", when="내보낸 파일을 쓸 폴더를 바꿀 때."),
        description=(
            "내보낸 파일을 쓸 폴더(상대 경로는 설정 파일 폴더 기준). 있는 폴더여야 쓸 수 있다."
        ),
    )


class ExportModuleSettings(BaseModel):
    """설정 내보내기를 어디에 쓸 수 있는지 정합니다. 기본은 zip 내려받기만 합니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 내보내기(design §2R.7).

    model_config = ConfigDict(extra="forbid")

    roots: list[ExportRootSetting] = Field(
        title="쓰기 허용 폴더",
        json_schema_extra=x_ui(
            tier="basic", when="내보낸 파일을 zip이 아니라 폴더에 바로 쓰고 싶을 때."
        ),
        default_factory=list,
        description="폴더 쓰기를 허용한 곳. 비우면 폴더 쓰기 꺼짐(zip 내려받기만).",
    )
    home: Path | None = Field(
        title="기준 홈 폴더",
        json_schema_extra=x_ui(tier="advanced", example="~"),
        default=None,
        description=(
            "쓰기 금지 폴더를 찾을 홈(상대 경로는 설정 파일 폴더 기준). 비우면 HOME·USERPROFILE."
        ),
    )
    protected_in_home: list[str] = Field(
        title="홈 안 쓰기 금지 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: [".claude"],
        description=(
            "홈 기준 쓰기 금지 폴더(외부 도구 원본). 허용 폴더로 등록해도 이 안에는 쓰지 않는다."
        ),
    )
    protected: list[Path] = Field(
        title="그 밖의 쓰기 금지 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=list,
        description="그 밖의 쓰기 금지 폴더(상대 경로는 설정 파일 폴더 기준).",
    )
    options: dict[str, dict[str, Any]] = Field(
        title="형식별 옵션",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=dict,
        description=(
            "내보내기 형식 이름 → 그 형식이 받는 옵션(키는 형식이 정한다, 예: mapping·layout)."
        ),
    )
    expose_paths: bool = Field(
        title="폴더 경로 보이기",
        json_schema_extra=x_ui(tier="advanced"),
        default=True,
        description="내보내기 화면에 허용 폴더의 전체 경로를 보일지(로컬 앱이라 기본 표시).",
    )


SETTINGS_COMPAT = SettingsCompat(
    removed=(RemovedSetting("exports", new="modules.options.mod-exports"),),
    seeds=(SeedSetting("expose_paths", "security.expose_paths"),),
)
"""호스트 설정 호환: 옛 최상위 ``exports``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 안내). 호스트 ``security.expose_paths``는 루트 경로 표시의 기본값이다. ``home``은
이 모듈 자기 옵션이다(생략 시 HOME·USERPROFILE, 다른 모듈 설정을 기본값으로 읽지 않는다)."""


__all__ = ["SETTINGS_COMPAT", "ExportModuleSettings", "ExportRootSetting"]
