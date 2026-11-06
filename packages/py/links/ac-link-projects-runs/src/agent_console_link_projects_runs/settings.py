"""link-projects-runs 설정(설치자 값, ``modules.options.link-projects-runs``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import x_ui

from .scope import DEFAULT_LAYER_ID, DEFAULT_LAYER_LABEL, DEFAULT_UNKNOWN_MESSAGE


class ProjectsRunsSettings(BaseModel):
    """프로젝트·실행 연동 설정."""

    model_config = ConfigDict(extra="forbid")

    layer_id: str = Field(
        title="프로젝트 설정 id",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_LAYER_ID,
        min_length=1,
        description="실행 설정의 출처 표시에 쓰는 프로젝트 설정 id. 다른 설정 id와 겹치면 안 된다.",
    )
    layer_label: str = Field(
        title="프로젝트 설정 이름",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_LAYER_LABEL,
        description="실행 설정 출처에 보이는 프로젝트 설정 이름.",
    )
    unknown_message: str = Field(
        title="프로젝트 없음 경고",
        json_schema_extra=x_ui(tier="advanced"),
        default=DEFAULT_UNKNOWN_MESSAGE,
        description=(
            "실행의 프로젝트를 찾지 못했을 때 경고 문구($project 자리 채움). 실행은 계속한다."
        ),
    )
    require_project: bool = Field(
        title="프로젝트 없이 실행 막기",
        json_schema_extra=x_ui(tier="advanced"),
        # 기본 거짓(임시, 5.7R.33g 결정): 웹 실행 시작이 아직 project_id를 보내지 않는다(33o·33v).
        # 웹이 보내게 되면 기본을 참으로 바꾼다(design §PI.4.5 규칙 1).
        default=False,
        description=(
            "켜면 프로젝트를 고르지 않은 실행·대화를 시작하지 않는다(실행은 프로젝트 폴더에서만). "
            "끄면 프로젝트 없는 실행은 서버 작업 폴더에서 돈다."
        ),
    )


__all__ = ["ProjectsRunsSettings"]
