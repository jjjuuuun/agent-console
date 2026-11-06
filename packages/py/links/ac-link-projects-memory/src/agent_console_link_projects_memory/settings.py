"""link-projects-memory 설정(설치자 값, ``modules.options.link-projects-memory``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui


class ProjectsMemorySettings(BaseModel):
    """프로젝트 메모리 DB 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    max_open_spaces: int = Field(
        title="동시에 열어 둘 프로젝트 수",
        json_schema_extra=x_ui(tier="advanced"),
        default=8,
        ge=1,
        description="한 번에 열어 두는 프로젝트 메모리 DB 개수. 넘으면 오래 안 쓴 것부터 닫는다.",
    )
    idle_close_seconds: float = Field(
        title="안 쓰면 닫기(초)",
        json_schema_extra=x_ui(tier="advanced"),
        default=300.0,
        ge=0,
        description="이 시간 동안 쓰지 않은 프로젝트 메모리 DB의 연결을 닫는다. 0이면 닫지 않는다.",
    )
    busy_timeout_seconds: float = Field(
        title="잠금 대기 시간(초)",
        json_schema_extra=x_ui(tier="advanced"),
        default=10.0,
        ge=0,
        description="다른 앱이 같은 메모리 DB를 쓰고 있을 때 잠금이 풀리길 기다리는 시간.",
    )
    full_text_search: bool = Field(
        title="전문 검색 쓰기",
        json_schema_extra=x_ui(tier="advanced"),
        default=True,
        description="끄면 프로젝트 메모리 검색이 단순 포함 검색이 된다.",
    )
    journal: Literal["auto", "WAL", "DELETE"] = Field(
        title="저널 방식",
        json_schema_extra=x_ui(
            tier="advanced",
            enum_labels={
                "auto": "자동",
                "WAL": "WAL(기본)",
                "DELETE": "DELETE(네트워크 드라이브용)",
            },
        ),
        default="auto",
        description="auto는 네트워크 드라이브로 보이면 DELETE, 아니면 WAL을 쓴다.",
    )
    migration_scope: str = Field(
        title="메모리 DB 계보 범위",
        json_schema_extra=x_ui(tier="advanced"),
        default="memory",
        min_length=1,
        description=(
            "프로젝트 메모리 DB에 올릴 계보를 고르는 범위 이름. 켜진 모듈 중 이 범위를 선언한 "
            "계보만 올린다."
        ),
    )
    context_field: str = Field(
        title="폴더 id를 넣을 맥락 필드",
        json_schema_extra=x_ui(tier="advanced"),
        default="project_id",
        min_length=1,
        description=(
            "프로젝트 실행의 메모리 범위 id를 풀 때 폴더 id(매니페스트 id)를 넣을 접근 맥락 필드. "
            "다른 앱에서 등록 id가 달라도 같은 범위가 된다."
        ),
    )


__all__ = ["ProjectsMemorySettings"]
