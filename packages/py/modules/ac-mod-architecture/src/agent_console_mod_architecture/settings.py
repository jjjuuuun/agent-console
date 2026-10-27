"""mod-architecture 설정(설치자 값, ``modules.options.mod-architecture``, design §5.5R.2.2).

프로필·기본 프로필 사용 여부는 사용자 데이터(워크스페이스 설정 ``architecture`` 섹션, 계약
``ArchitectureSettings``)라 여기 없다. 설치자 값은 투영 상한만 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui


class ArchitectureModuleSettings(BaseModel):
    """구조도 투영 상한(설치자 값)."""

    model_config = ConfigDict(extra="forbid")

    max_request_events: int = Field(
        title="단독 투영 이벤트 상한",
        description=(
            "이벤트를 본문으로 넘겨 그리는 요청(POST /architecture/project)이 받을 수 있는 "
            "최대 이벤트 수. 넘으면 그리지 않고 범위가 크다는 오류를 돌려준다."
        ),
        default=20_000,
        ge=0,
        json_schema_extra=x_ui(
            tier="advanced",
            unit="개",
            when="다른 도구에서 큰 이벤트 묶음을 넘겨 구조도를 그려야 할 때 늘리세요.",
        ),
    )
    max_scope_events: int = Field(
        title="범위 이벤트 상한",
        description=(
            "로그 범위(세션·실행)를 구조도로 그릴 때 셀 최대 이벤트 수. "
            "로그 연동이 이 값을 읽는다. "
            "넘으면 그리지 않고 필터를 좁히라고 안내한다."
        ),
        default=100_000,
        ge=0,
        json_schema_extra=x_ui(
            tier="advanced",
            unit="개",
            when="아주 긴 세션의 구조도가 상한 초과로 보이지 않을 때 늘리세요.",
        ),
    )


__all__ = ["ArchitectureModuleSettings"]
