"""mod-imports 설정(설치자 값, ``modules.options.mod-imports``)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SettingsCompat

HOME_ENV_NAMES: tuple[str, ...] = ("HOME", "USERPROFILE")
"""``home``을 비웠을 때 사용자 홈을 찾는 환경변수(앞쪽 우선)."""


class ImportModuleSettings(BaseModel):
    """가져오기 출처를 만들 위치(원본은 읽기만 한다)."""

    model_config = ConfigDict(extra="forbid")

    home: Path | None = Field(
        title="사용자 홈",
        json_schema_extra=x_ui(tier="advanced", example="~"),
        default=None,
        description="사용자 홈(`~/.claude`가 있는 곳). 비우면 환경변수 HOME·USERPROFILE.",
    )
    project_dir: Path | None = Field(
        title="프로젝트 폴더",
        json_schema_extra=x_ui(
            tier="basic", example="./my-project", when="다른 프로젝트의 .claude 설정을 가져올 때."
        ),
        default=None,
        description=(
            "가져올 프로젝트 폴더(`.claude/`·`.mcp.json`, 상대 경로는 설정 파일 폴더 기준). "
            "비우면 그 폴더."
        ),
    )
    options: dict[str, dict[str, Any]] = Field(
        title="출처별 옵션",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=dict,
        description="가져오기 출처 이름 → 그 출처가 받는 옵션(키는 출처가 정한다).",
    )


def resolve_home(
    configured: Path | None, environ: Mapping[str, str], base: Path | None
) -> Path | None:
    """설정 ``home``(상대 경로는 ``base`` 기준) 또는 환경변수의 홈. 둘 다 없으면 None."""
    if configured is not None:
        return configured if configured.is_absolute() or base is None else base / configured
    for name in HOME_ENV_NAMES:
        if environ.get(name):
            return Path(environ[name])
    return None


SETTINGS_COMPAT = SettingsCompat(
    removed=(RemovedSetting("imports", new="modules.options.mod-imports"),)
)
"""호스트 설정 호환: 옛 최상위 ``imports``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 안내). ``project_dir``는 이 모듈 자기 옵션이다(생략 시 호스트 ``paths.base_dir``,
다른 모듈 설정을 기본값으로 읽지 않는다 — H3)."""


__all__ = [
    "HOME_ENV_NAMES",
    "SETTINGS_COMPAT",
    "ImportModuleSettings",
    "resolve_home",
]
