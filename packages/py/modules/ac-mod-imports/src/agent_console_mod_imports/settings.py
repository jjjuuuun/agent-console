"""mod-imports 설정(설치자 값, ``modules.options.mod-imports``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SettingsCompat


class ImportModuleSettings(BaseModel):
    """가져오기 출처를 만들 위치(원본은 읽기만 한다)."""

    # 출처는 프로젝트 폴더 안(.claude/, CLAUDE.md, .mcp.json)뿐이다. 사용자 전역 구성(~/.claude)은
    # 읽지 않는다(5.7R.30b) — 옛 home 키는 SETTINGS_COMPAT이 안내한다.

    model_config = ConfigDict(extra="forbid")
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


HOME_REMOVED_REASON = (
    "사용자 전역 Claude Code 구성(~/.claude) 가져오기는 지원하지 않습니다. 앱은 등록된 프로젝트 "
    "폴더와 자기 workspace 밖을 연동하지 않습니다. 프로젝트 폴더의 .claude/를 가져오세요"
)
"""옛 설정 ``modules.options.mod-imports.home``(사용자 홈) 거부 이유(5.7R.30b)."""


SETTINGS_COMPAT = SettingsCompat(
    removed=(
        RemovedSetting("imports", new="modules.options.mod-imports"),
        RemovedSetting("modules.options.mod-imports.home", HOME_REMOVED_REASON),
    )
)
"""호스트 설정 호환: 옛 최상위 ``imports``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 안내). ``project_dir``는 이 모듈 자기 옵션이다(생략 시 호스트 ``paths.base_dir``,
다른 모듈 설정을 기본값으로 읽지 않는다 — H3). 옛 ``home``(사용자 ``~/.claude`` 출처)은 5.7R.30b에서
없앴다(``settings.removed_key`` 오류로 이유 안내)."""


__all__ = [
    "HOME_REMOVED_REASON",
    "SETTINGS_COMPAT",
    "ImportModuleSettings",
]
