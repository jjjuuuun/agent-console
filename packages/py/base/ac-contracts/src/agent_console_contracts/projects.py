"""계약 하위 모듈 `projects`: 프로젝트 정의와 그 REST DTO(design §UX-P, 0.8.0에서 1.0.0으로 시작).

프로젝트 = 사용자가 만든 이름 붙은 작업 단위. 정의를 정리·거르는 단위이고 실행의 기본 맥락(작업
폴더·설정 층)이다. 보안 격리 단위는 아니다. 프로젝트 목록·속성은 전부 사용자 데이터이며 코드에
프로젝트가 없다(0개가 기본).

정의(에이전트·팀 구성·리소스)의 범위는 각 정의의 `project` 필드다(생략 = 공용). 새 정의 범위
설정 `ProjectPreferences`는 공통 설정의 섹션이라 `definitions`에 있다(이 모듈이 `definitions`를
쓰므로 반대 방향 import를 피함). 편의를 위해 여기서도 다시 내보낸다.

의존: `common`, `definitions`. 실행·대화의 `project_id`는 `runs`·`chat`의 불투명 문자열이다.
"""

from typing import Literal

from pydantic import ConfigDict, Field

from ._base import ContractModel, DefinitionModel, JsonObject, NonEmptyStr, Slug
from .common import x_ui
from .definitions import AgentSettings, DefinitionScope, Issue, ProjectPreferences

type ProjectDeleteMode = Literal["move_to_shared", "delete_definitions"]
"""프로젝트 삭제 때 그 프로젝트 정의 처리. move_to_shared = 공용으로 옮기고 삭제
(기본), delete_definitions = 정의도 함께 삭제. 실행·대화의 `project_id`는 어느 쪽이든
그대로 남는다."""


class _ProjectFields(DefinitionModel):
    """프로젝트의 사용자 필드(만들기·정의 공통)."""

    name: NonEmptyStr = Field(
        title="이름",
        description="프로젝트를 부르는 이름입니다. 위쪽 프로젝트 고르기에 보입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="프로젝트 고르기 목록에서 알아보기 쉬운 이름으로 바꾸고 싶을 때 바꾸세요.",
            example="결제 서비스",
        ),
    )
    description: str = Field(
        default="",
        title="설명",
        description="이 프로젝트가 무엇인지 적습니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 프로젝트가 무엇인지 함께 쓰는 사람에게 알리고 싶을 때 적으세요.",
            example="결제 API와 관리 화면",
        ),
    )
    working_directory: str | None = Field(
        default=None,
        title="작업 폴더",
        description="이 프로젝트에서 실행하는 에이전트의 작업 폴더. 비우면 서버 설정의 작업 폴더.",
        json_schema_extra=x_ui(
            tier="basic",
            when="이 프로젝트의 에이전트를 특정 저장소에서 일하게 하고 싶을 때 정하세요.",
            example="/home/me/projects/app",
        ),
    )
    log_projects: list[str] = Field(
        default_factory=list,
        title="연결한 로그 묶음",
        description="이 프로젝트로 볼 로그 묶음입니다. 비우면 로그를 거르지 않습니다.",
        json_schema_extra={
            "default": [],
            **x_ui(
                tier="advanced",
                when="이 프로젝트를 고르면 관련 로그만 보이게 하고 싶을 때 고르세요.",
            ),
        },
    )
    settings: AgentSettings | None = Field(
        default=None,
        title="프로젝트 층 설정",
        description="이 프로젝트의 에이전트 설정입니다. 비운 항목은 공통 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="이 프로젝트에서만 모델·지침을 다르게 하고 싶을 때 바꾸세요."
        ),
    )
    labels: list[str] = Field(
        default_factory=list,
        title="라벨",
        description="찾기·거르기에 쓰는 꼬리표입니다.",
        json_schema_extra={"default": [], **x_ui(tier="advanced")},
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="기타 속성",
        description="다른 도구가 읽는 자유 속성입니다. 보통은 비워 둡니다.",
        json_schema_extra={"default": {}, **x_ui(tier="advanced")},
    )


class Project(_ProjectFields):
    """프로젝트입니다. 작업 폴더와 연결한 로그, 그 프로젝트에서 쓸 설정을 묶습니다."""

    # 프로젝트 정의(`<workspace>/projects/<id>.yaml`, 정의 종류 `project`).

    model_config = ConfigDict(title="프로젝트")

    kind: Literal["project"] = "project"
    id: Slug = Field(
        title="id",
        description="가리킬 때 쓰는 고유 이름입니다. 파일 이름으로도 씁니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    schema_version: int = Field(
        default=1,
        title="형식 버전",
        description="파일 형식 번호입니다. 직접 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class ProjectCreate(_ProjectFields):
    """새 프로젝트를 만들 때 적는 값입니다."""

    # `POST /projects` 요청. 응답은 `Project`(201).

    model_config = ConfigDict(title="프로젝트 만들기")

    id: Slug = Field(
        title="id",
        description=(
            "새 프로젝트의 고유 이름입니다. 영문·숫자·-·_만 쓰며 이미 있는 이름은 못 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="만들 때 한 번 정하며, 파일 이름으로 쓰기 좋은 짧은 영문으로 적으세요.",
            example="payments",
        ),
    )


class ProjectUpdate(ContractModel):
    """`PUT /projects/{id}` 요청. 생략한 필드는 그대로 둔다.

    `working_directory`·`settings`의 null은 값을 지운다(상속으로 되돌림).
    `name`의 null은 생략과 같다.
    """

    name: NonEmptyStr | None = None
    description: str | None = None
    working_directory: str | None = None
    log_projects: list[str] | None = None
    settings: AgentSettings | None = None
    labels: list[str] | None = None
    attributes: JsonObject | None = None


class DefinitionKey(ContractModel):
    """정의 하나를 가리키는 키(종류 이름 + id). 표시 이름은 선택."""

    kind: NonEmptyStr = Field(description="정의 종류 이름(예: agent, graph, resource).")
    id: NonEmptyStr
    name: str = ""


class DefinitionMove(DefinitionKey):
    """정의 하나의 범위 바꾸기(필드 `project` 하나를 고쳐 저장). null = 공용."""

    from_: str | None = Field(default=None, alias="from", description="지금 범위(null = 공용).")
    to: str | None = Field(default=None, description="옮길 범위(null = 공용).")
    required: bool = Field(
        default=False,
        description="옮기려는 그 정의면 true. false는 참조 때문에 함께 옮기기를 권하는 정의.",
    )


class MovePlanRequest(ContractModel):
    """`POST /projects/move-plan` 요청: 정의 하나를 `to` 범위로 옮길 때의 계획을 계산한다."""

    kind: NonEmptyStr
    id: NonEmptyStr
    to: Slug | None = Field(default=None, description="옮길 프로젝트 id. null = 공용으로.")


class MovePlan(ContractModel):
    """옮기기 계획(순수 함수 `move_plan`의 결과). 저장하지 않는다.

    P 전용 → 공용: `moves`에 그 정의가 쓰는 P 전용 정의(참조 닫힘)가 함께 들어간다(기본 선택).
    공용 → P 전용: 그 정의를 쓰는 다른 프로젝트·공용 정의는 `warnings`로 알린다(막지 않음).
    """

    target: DefinitionKey = Field(description="옮기려는 정의.")
    to: str | None = Field(default=None, description="옮길 범위(null = 공용).")
    moves: list[DefinitionMove] = Field(default_factory=list)
    warnings: list[Issue] = Field(
        default_factory=list,
        description="옮긴 뒤 생길 범위 경고(project.shared_uses_project 등)나 검사 못 함 정보.",
    )


class DeletePlan(ContractModel):
    """`POST /projects/{id}/delete-plan` 응답: 삭제하면 무엇이 바뀌는지(저장하지 않음).

    삭제는 `DELETE /projects/{id}?mode=<ProjectDeleteMode>`(생략 = `default_mode`)로 한다.
    """

    project_id: NonEmptyStr
    definitions: list[DefinitionKey] = Field(
        default_factory=list, description="이 프로젝트 전용 정의(공용으로 옮기거나 함께 삭제)."
    )
    default_mode: ProjectDeleteMode = "move_to_shared"
    warnings: list[Issue] = Field(default_factory=list)


__all__ = [
    "DefinitionKey",
    "DefinitionMove",
    "DefinitionScope",
    "DeletePlan",
    "MovePlan",
    "MovePlanRequest",
    "Project",
    "ProjectCreate",
    "ProjectDeleteMode",
    "ProjectPreferences",
    "ProjectUpdate",
]
