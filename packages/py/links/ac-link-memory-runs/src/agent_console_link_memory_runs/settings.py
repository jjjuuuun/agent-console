"""link-memory-runs 설정(설치자 값, ``modules.options.link-memory-runs``)."""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

DEFAULT_MAX_WRITES_PER_RUN: Final = 200
"""실행 하나의 메모리 쓰기 한도 기본값(design §5.7R.8)."""


class MemoryRunsSettings(BaseModel):
    """실행 중 에이전트가 쓰는 메모리 도구의 한도를 정하는 설치자 설정입니다."""

    model_config = ConfigDict(extra="forbid")

    max_writes_per_run: int | None = Field(
        default=DEFAULT_MAX_WRITES_PER_RUN,
        ge=1,
        title="실행당 쓰기 한도",
        description=(
            "실행 하나에서 에이전트들이 메모리에 쓸 수 있는 최대 횟수입니다. 넘으면 쓰기 도구가 "
            "rate_limited로 실패하고 실행은 계속됩니다. 비우면 한도가 없습니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="에이전트가 메모리를 너무 많이 쓰거나, 긴 실행에서 쓰기가 막힐 때 바꾸세요.",
            unit="회",
        ),
    )


__all__ = ["DEFAULT_MAX_WRITES_PER_RUN", "MemoryRunsSettings"]
