"""link-projects-records 설정(설치자 값, ``modules.options.link-projects-records``)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

from .sessions import SessionArchiveSettings


class ProjectsRecordsSettings(BaseModel):
    """프로젝트 기록 DB 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    space_prefix: str = Field(
        title="공간 이름 접두",
        json_schema_extra=x_ui(tier="advanced"),
        default="project:",
        description="기록 공간 이름에서 떼어 낼 접두. 나머지가 프로젝트 등록 id다.",
    )
    max_open_spaces: int = Field(
        title="동시에 열어 둘 프로젝트 수",
        json_schema_extra=x_ui(tier="advanced"),
        default=8,
        ge=1,
        description="한 번에 열어 두는 프로젝트 기록 DB 개수. 넘으면 오래 안 쓴 것부터 닫는다.",
    )
    idle_close_seconds: float = Field(
        title="안 쓰면 닫기(초)",
        json_schema_extra=x_ui(tier="advanced"),
        default=300.0,
        ge=0,
        description="이 시간 동안 쓰지 않은 프로젝트 기록 DB의 연결을 닫는다. 0이면 닫지 않는다.",
    )
    busy_timeout_ms: int = Field(
        title="잠금 대기 시간(밀리초)",
        json_schema_extra=x_ui(tier="advanced"),
        default=5000,
        ge=0,
        description="다른 앱이 같은 기록 DB를 쓰고 있을 때 잠금이 풀리길 기다리는 시간.",
    )
    backups_keep: int = Field(
        title="올리기 전 백업 보관 개수",
        json_schema_extra=x_ui(tier="advanced"),
        default=3,
        ge=1,
        description="기록 DB를 새 버전으로 올리기 전에 만든 백업을 몇 개까지 남길지.",
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
    session_archive: SessionArchiveSettings = Field(
        default_factory=SessionArchiveSettings,
        title="대화 원본 보관",
        json_schema_extra=x_ui(tier="advanced"),
        description=(
            "다른 앱에서도 대화를 이어 가도록 세션 원본을 프로젝트 폴더에 둡니다(기본 켬). 폴더를 "
            "공유하면 대화 원본도 함께 공유됩니다."
        ),
    )
    spool_dir: str = Field(
        title="대기 파일 폴더 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default="records-spool",
        min_length=1,
        description="폴더가 사라져 못 쓴 기록을 임시로 적어 두는, 앱 상태 폴더 안 폴더 이름.",
    )


__all__ = ["ProjectsRecordsSettings"]
