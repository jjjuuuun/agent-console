"""mod-usage 설정(설치자 값, ``modules.options.mod-usage``).

출처 켜기·출처 설정은 사용자 데이터(워크스페이스 설정 ``usage.sources``)라 여기 없다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui
from agent_console_modkit import RemovedSetting, SettingsCompat


class UsageModuleSettings(BaseModel):
    """사용량 수집·보존(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    retention_seconds: float | None = Field(
        title="보존 기간",
        json_schema_extra=x_ui(
            tier="basic", unit="초", when="사용량 기록을 더 오래 보거나 저장 공간을 줄일 때."
        ),
        default=30 * 24 * 3600,
        gt=0,
        description="이보다 오래된 사용량 기록을 지운다. 비우면 지우지 않는다.",
    )
    prune_interval_seconds: float = Field(
        title="정리 주기",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
        default=3600,
        gt=0,
        description="오래된 사용량 기록을 지우는 주기. 시작할 때 한 번, 이후 이 간격.",
    )
    rollup_run_limit: int = Field(
        title="집계할 최근 실행 수",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=500,
        ge=1,
        description="토큰 집계에 쓰는 최근 실행 수.",
    )
    source_timeout_seconds: float | None = Field(
        title="출처 응답 한도",
        json_schema_extra=x_ui(tier="advanced", unit="초"),
        default=10.0,
        gt=0,
        description="사용량 출처 하나를 기다리는 최대 시간. 비우면 무기한.",
    )
    agent_console_command: str = Field(
        title="agent-console 명령",
        json_schema_extra=x_ui(tier="advanced", example="agent-console"),
        default="agent-console",
        min_length=1,
        description=(
            "연결 안내 조각에 넣을 agent-console 명령. 이름만 주면 찾은 절대 경로로 바꾼다."
        ),
    )


SETTINGS_COMPAT = SettingsCompat(
    removed=(RemovedSetting("usage", new="modules.options.mod-usage"),)
)
"""호스트 설정 호환: 옛 최상위 ``usage``는 4R.18에서 읽기 호환을 끝냈다(``settings.removed_key``
오류로 새 위치 ``modules.options.mod-usage`` 안내)."""


__all__ = ["SETTINGS_COMPAT", "UsageModuleSettings"]
