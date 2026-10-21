"""실행 REST DTO: 실행 시작·이어 가기·포트 계산·답변 계획(design §5.2, §2R.6, §2R.10)."""

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr

from ._descriptors import BackendDescriptor
from ._interactions import InteractionGrant
from ._models import NodeRunStatus


class ResolvePortsRequest(ContractModel):
    """`POST /node-types/{id}/ports` 요청. 응답은 PortSpec."""

    config: JsonObject = Field(default_factory=dict)


class CreateRunRequest(ContractModel):
    """`POST /runs` 요청. 응답은 Run(202)."""

    graph_id: NonEmptyStr
    version_hash: str | None = Field(default=None, description="생략하면 현재 저장된 버전.")
    input: JsonObject = Field(
        default_factory=dict,
        description="그래프 입력 포트 이름 → 값. 입력 포트가 없으면 {}.",
    )
    origin: NonEmptyStr = Field(
        default="api", description="시작 경로. 알려진 값은 RUN_ORIGINS(확장 가능)."
    )
    project_id: str | None = Field(
        default=None,
        description=(
            "이 실행의 프로젝트 id(0.8.0). 생략 = 프로젝트 없음. 존재 확인은 연동 모듈이 한다."
        ),
    )


class EntrySlot(ContractModel):
    """팀 구성의 입구 하나(입구 연결의 도착 노드)."""

    edge_id: NonEmptyStr
    node_id: NonEmptyStr
    label: str | None = None


class AnswerSlot(ContractModel):
    """팀 구성의 답변 자리 하나(답변 연결). 속성은 엣지 타입 `reply_fields`로 config에서 읽는다."""

    edge_id: NonEmptyStr
    node_id: NonEmptyStr = Field(description="답변을 내는 노드(답변 연결의 출발 노드).")
    agent_id: str | None = None
    label: str | None = None
    order: int | None = None
    final: bool = True
    stream: bool = False


class TeamPlanSummary(ContractModel):
    """팀 구성 실행 계획 요약(`GET /graphs/{id}/plan`, 초안 `POST /graphs/plan`)."""

    entries: list[EntrySlot] = Field(default_factory=list)
    answers: list[AnswerSlot] = Field(default_factory=list)
    grants: dict[str, InteractionGrant] = Field(
        default_factory=dict, description="노드 id → 그 노드가 열 수 있는 상호작용."
    )


class ResumeNodeOption(ContractModel):
    """이어 갈 수 있는 끊긴 노드 하나."""

    node_id: NonEmptyStr
    label: str | None = None
    rerunnable: bool = Field(description="노드 타입 디스크립터의 `rerunnable`.")
    status: NodeRunStatus = Field(description="끊긴 실행에서의 마지막 노드 상태.")


class ResumeOptions(ContractModel):
    """`GET /runs/{id}/resume-options` 응답."""

    run_id: NonEmptyStr
    nodes: list[ResumeNodeOption] = Field(default_factory=list)


class ResumeRunRequest(ContractModel):
    """`POST /runs/{id}/resume` 요청. 응답은 새 `Run`(origin = resume, `resumed_from`)."""

    node_ids: list[NonEmptyStr] = Field(min_length=1, description="다시 실행할 노드 id.")


class UnresolvedBackendNode(ContractModel):
    """실행 백엔드가 정해지지 않은 노드 하나(사전 점검 결과)."""

    id: NonEmptyStr = Field(description="노드 id.")
    label: str = Field(
        default="", description="화면 이름(노드 label, 없으면 정의 이름). 문구는 이 값으로 부른다."
    )


class BackendUnresolvedDetails(ContractModel):
    """`backend.unresolved`(HTTP 422) 오류의 `error.details`(0.8.0).

    실행을 만들기 전에 백엔드를 쓰는 노드의 백엔드가 비었을 때 낸다. Run·턴 기록은 남지 않는다.
    해결 버튼은 `ErrorInfo.fix`에 있다.
    """

    nodes: list[UnresolvedBackendNode] = Field(default_factory=list)
    options: list[BackendDescriptor] = Field(
        default_factory=list, description="지금 고를 수 있는 백엔드(등록된 디스크립터)."
    )
