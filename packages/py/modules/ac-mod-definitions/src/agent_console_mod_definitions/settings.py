"""mod-definitions 설정(설치자 값, ``modules.options.mod-definitions``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SettingsCompat
from agent_console_store import DEFAULT_MAX_CONTENT_BYTES

DEFAULT_PLAIN_SECRET_ISSUE_CODES: tuple[str, ...] = (
    "resource.plain_secret",
    "resource.override_secret_suspected",
)
"""저장 전 검사 이슈 중 "평문 비밀"을 뜻하는 기본 코드(평문 점검 경고로 옮긴다)."""


class DefinitionModuleSettings(BaseModel):
    """정의 저장소·평문 점검 설정."""

    model_config = ConfigDict(extra="forbid")

    max_content_bytes: int | None = Field(
        title="본문 최대 크기",
        json_schema_extra=x_ui(tier="advanced", unit="바이트"),
        default=DEFAULT_MAX_CONTENT_BYTES,
        ge=0,
        description=(
            "정의 하나(리소스 등)의 본문 파일 총량 한도. 비우면 무제한. 화면·가져오기·되돌리기에 "
            "같은 한도."
        ),
    )
    plain_secret_issue_codes: list[str] = Field(
        title="평문 비밀 문제 코드",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: list(DEFAULT_PLAIN_SECRET_ISSUE_CODES),
        description="저장 전 검사 문제 중 평문 비밀 경고로 옮길 코드.",
    )


PRESETS_REMOVED_REASON = "프리셋 기능은 삭제되었습니다. 설정 파일에서 이 키를 지우세요"
"""삭제된 프리셋 기능의 설정 키가 남아 있을 때의 거부 이유(정의를 직접 만들거나 가져오기를 쓴다)."""

SETTINGS_COMPAT = SettingsCompat(
    removed=(
        RemovedSetting("resources", new="modules.options.mod-definitions"),
        RemovedSetting("presets", PRESETS_REMOVED_REASON),
        RemovedSetting("modules.options.mod-presets", PRESETS_REMOVED_REASON),
    )
)
"""호스트 설정 호환(``settings.removed_key`` 오류로 시작 거부):

- 옛 최상위 ``resources``(``max_content_bytes``): 새 위치 ``modules.options.mod-definitions`` 안내.
- 삭제된 프리셋 기능의 설정(최상위 ``presets``, ``modules.options.mod-presets``): 지우라고 안내.
  프리셋은 정의를 쓰던 기능이라 정의 모듈이 거부 선언을 맡는다.
"""


__all__ = [
    "DEFAULT_PLAIN_SECRET_ISSUE_CODES",
    "PRESETS_REMOVED_REASON",
    "SETTINGS_COMPAT",
    "DefinitionModuleSettings",
]
