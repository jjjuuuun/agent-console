"""link-logs-trace 설정(설치자 값, ``modules.options.link-logs-trace``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

from .build import DEFAULT_LINK_KEYS

DEFAULT_MAX_EVENTS = 20_000


class LogTraceSettings(BaseModel):
    """연결 키·읽을 이벤트 상한."""

    model_config = ConfigDict(extra="forbid")

    link_keys: list[str] = Field(
        title="부모 찾기 키",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=lambda: list(DEFAULT_LINK_KEYS),
        min_length=1,
        description=(
            "서브에이전트 기록의 부모를 찾는 연결 키 이름. 기본은 Claude Code 기록의 tool_use_id."
        ),
    )
    max_events: int = Field(
        title="읽을 이벤트 상한",
        json_schema_extra=x_ui(tier="advanced", unit="개"),
        default=DEFAULT_MAX_EVENTS,
        ge=1,
        description="세션 하나에서 읽을 이벤트 상한(넘으면 앞부분만으로 그린다).",
    )


__all__ = ["DEFAULT_MAX_EVENTS", "LogTraceSettings"]
