"""link-projects-sdd 설정(설치자 값, ``modules.options.link-projects-sdd``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui


class ProjectsSddSettings(BaseModel):
    """프로젝트 스펙 공간 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    reserved_dirs: list[str] = Field(
        title="가져오기·내보내기 금지 폴더",
        json_schema_extra=x_ui(tier="advanced"),
        default_factory=list,
        description=(
            "프로젝트 폴더 기준 상대 경로. 이 폴더 아래는 스펙 가져오기·내보내기·파일 목록에서 "
            "읽지도 쓰지도 않는다. 앱 구성 폴더는 적지 않아도 늘 막는다."
        ),
    )


__all__ = ["ProjectsSddSettings"]
