"""RunEvent: 실시간 스트림과 실행 로그 저장의 단일 형식(design §5.6).

- `RunEvent`: 일반 형태(`type`은 임의 문자열, `payload`는 객체). 전송·저장은 이 형태다.
  알 수 없는 type은 화면이 일반 행으로 표시한다(확장 가능).
- `KnownRunEvent`: 알려진 type별로 payload가 정해진 판별 유니온. `parse_run_event()`가 고른다.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, RootModel

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import Endpoint, ErrorInfo, Usage

from ._conditions import ConditionOutcome
from ._interactions import Interaction
from ._models import NodeRunStatus, RunStatus, WaitInfo

RUN_EVENT_SCHEMA_VERSION = 1


class RunEventBase(ContractModel):
    """RunEvent 공통 머리. `seq`는 Run 안에서 1부터 단조 증가(재접속 `since_seq` 기준)."""

    schema_version: int = RUN_EVENT_SCHEMA_VERSION
    event_id: NonEmptyStr
    run_id: NonEmptyStr
    seq: int = Field(ge=1)
    ts: float = Field(description="Unix epoch 초.")
    node_path: list[str] = Field(
        description="이벤트가 속한 노드 경로. Run 수준은 [], 하위 그래프는 [부모노드, 자식노드]."
    )
    attempt: int | None = Field(default=None, ge=1, description="노드 이벤트의 시도 번호.")
    actor: str | None = Field(
        default=None,
        description="이벤트를 낸 에이전트 정의 id. 위임받은 대상이면 대상 에이전트.",
    )
    evidence: str = Field(default="observed", description="observed | inferred 등(확장 가능).")
    raw: Any = Field(default=None, description="공급자 원시 메시지(크기 제한·비밀 제거 후).")


class RunEvent(RunEventBase):
    """일반 RunEvent. 모든 이벤트가 이 형태로 직렬화·저장된다."""

    type: NonEmptyStr
    payload: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------- payloads


class RunStatusPayload(ContractModel):
    """`run.*` 이벤트 payload."""

    status: RunStatus
    error: ErrorInfo | None = None
    totals: Usage | None = None
    duration_ms: int | None = None


class NodeStatusPayload(ContractModel):
    """`node.*` 이벤트 payload. waiting이면 `wait`, 종료면 usage·duration_ms·error."""

    status: NodeRunStatus
    node_type: str | None = None
    iteration: int | None = None
    call: int | None = Field(
        default=None, ge=0, description="호출 회차(위임자가 부른 NodeRun이면)."
    )
    outputs_preview: str | None = None
    usage: Usage | None = None
    duration_ms: int | None = None
    error: ErrorInfo | None = None
    wait: WaitInfo | None = None
    waited_ms: int | None = Field(default=None, description="node.resumed: 대기한 시간(ms).")
    reason: str | None = Field(
        default=None,
        description="node.skipped 등의 사유(열린 문자열, 예: 이어 가기의 상류 `resumed`).",
    )


class EdgeTraversedPayload(ContractModel):
    """`edge.traversed` payload."""

    edge_id: NonEmptyStr
    source: Endpoint
    target: Endpoint
    value_preview: str | None = None
    kind: str | None = Field(default=None, description="연결 종류 id(엣지 kind). 모르면 null.")
    condition: ConditionOutcome | None = Field(
        default=None, description="조건 연결이면 판정 근거. 없으면 null."
    )


class EdgeSkippedPayload(ContractModel):
    """`edge.skipped` payload: 연결이 지나가지 않았다(조건 거짓·반복 한도 등)."""

    edge_id: NonEmptyStr
    source: Endpoint
    target: Endpoint
    kind: str | None = Field(default=None, description="연결 종류 id(엣지 kind). 모르면 null.")
    reason: str | None = Field(
        default=None, description="지나가지 않은 사유(열린 문자열, 예: condition_false)."
    )
    condition: ConditionOutcome | None = Field(
        default=None, description="조건 연결이면 판정 근거. 없으면 null."
    )


class LoopIterationPayload(ContractModel):
    """`loop.iteration` payload: 사이클 연결이 반복 영역을 다시 열었다."""

    edge_id: NonEmptyStr = Field(description="지나간 사이클 연결 id.")
    iteration: int = Field(ge=1, description="새로 연 회차(첫 반복이 1).")
    nodes: list[str] = Field(default_factory=list, description="다시 연 반복 영역의 노드 id.")


class LoopExhaustedPayload(ContractModel):
    """`loop.exhausted` payload: 반복 한도에 닿아 사이클 연결이 더 지나가지 않는다."""

    edge_id: NonEmptyStr
    iteration: int = Field(ge=0, description="한도에 닿은 때의 회차.")
    max_iterations: int | None = Field(default=None, ge=1, description="적용한 한도.")


class RunChildStartedPayload(ContractModel):
    """`run.child_started` payload: 노드가 자식 Run(중첩 팀)을 시작했다.

    이 이벤트의 `status` 필드는 없다: 부모 Run 상태가 아니다(부모 상태는 `run.<상태>` 이벤트만).
    """

    child_run_id: NonEmptyStr
    node_id: NonEmptyStr = Field(description="자식 Run을 만든 부모 그래프의 노드 id.")
    graph_id: str | None = Field(default=None, description="자식 팀 구성 id.")


class RunChildFinishedPayload(ContractModel):
    """`run.child_finished` payload: 자식 Run이 끝났다. `status`는 **자식** Run 상태다."""

    child_run_id: NonEmptyStr
    node_id: NonEmptyStr
    status: RunStatus = Field(description="자식 Run의 최종 상태(부모 Run 상태가 아님).")


class AgentSessionStartedPayload(ContractModel):
    """`agent.session_started` payload."""

    session_id: NonEmptyStr
    backend: NonEmptyStr
    model: str | None = None


class AgentTextDeltaPayload(ContractModel):
    """`agent.text_delta` payload. 출력 패널이 누적한다."""

    text: str
    message_id: str | None = None


class AgentMessagePayload(ContractModel):
    """`agent.message` payload(완성된 메시지)."""

    role: NonEmptyStr
    text: str
    message_id: str | None = None
    structured: Any = None


class AgentToolCallPayload(ContractModel):
    """`agent.tool_call` payload."""

    tool_use_id: NonEmptyStr
    name: NonEmptyStr
    input: Any = None


class AgentToolResultPayload(ContractModel):
    """`agent.tool_result` payload."""

    tool_use_id: NonEmptyStr
    is_error: bool = False
    output_preview: str = ""


class AgentSubagentPayload(ContractModel):
    """`agent.subagent_started|stopped` payload.

    `name`은 위임 대상 노드 id. 종료 이벤트의 `usage`는 백엔드가 주는 만큼만(예: 총 토큰만).
    """

    subagent_id: NonEmptyStr
    name: str | None = None
    tool_use_id: str | None = Field(default=None, description="위임 도구 호출 id(부모 연결 키).")
    task_type: str | None = None
    task_preview: str | None = None
    status: str | None = Field(default=None, description="종료 상태 문자열(백엔드가 줌).")
    usage: Usage | None = None
    tool_uses: int | None = Field(default=None, ge=0)
    duration_ms: int | None = None
    result_preview: str | None = None


class AgentUsagePayload(ContractModel):
    """`agent.usage` payload. `usage`는 이 노드 시도(attempt)의 **누적값**이다(더하지 말고 교체)."""

    usage: Usage
    model: str | None = None


class RunReplyPayload(ContractModel):
    """`run.reply` payload: 답변 연결(`scheduling = exit`)의 출발 노드가 낸 답변."""

    edge_id: NonEmptyStr
    node_id: NonEmptyStr
    label: str | None = None
    order: int | None = None
    final: bool = True
    text: str


class UsageRateLimitPayload(ContractModel):
    """`usage.rate_limit` payload. 창 id·상태는 공급자 문자열 그대로다."""

    window: NonEmptyStr = Field(description="창 id(고정 목록 아님).")
    status: str | None = None
    utilization: float | None = Field(default=None, ge=0, description="사용률(0~1).")
    resets_at: float | None = Field(default=None, description="Unix epoch 초.")
    overage_status: str | None = None


class InteractionRequestedPayload(ContractModel):
    """`interaction.requested` payload."""

    interaction: Interaction


class InteractionAnsweredPayload(ContractModel):
    """`interaction.answered` payload. 응답 원문 대신 미리보기만 싣는다."""

    interaction_id: NonEmptyStr
    kind: NonEmptyStr
    answered_by: str | None = None
    response_preview: str | None = None


class InteractionClosedPayload(ContractModel):
    """`interaction.closed` payload(응답 없이 닫힘)."""

    interaction_id: NonEmptyStr
    kind: NonEmptyStr
    status: Literal["expired", "cancelled"]
    reason: str | None = None


class LogWarningPayload(ContractModel):
    """`log.warning` payload."""

    message: str
    details: JsonObject = Field(default_factory=dict)


# ---------------------------------------------------------------- typed events


class RunLifecycleEvent(RunEventBase):
    type: Literal[
        "run.created",
        "run.started",
        "run.paused",
        "run.resumed",
        "run.waiting",
        "run.completed",
        "run.failed",
        "run.cancelled",
        "run.interrupted",
    ]
    payload: RunStatusPayload


class NodeStatusEvent(RunEventBase):
    type: Literal[
        "node.queued",
        "node.started",
        "node.waiting",
        "node.resumed",
        "node.completed",
        "node.failed",
        "node.skipped",
        "node.cancelled",
    ]
    payload: NodeStatusPayload


class EdgeTraversedEvent(RunEventBase):
    type: Literal["edge.traversed"]
    payload: EdgeTraversedPayload


class EdgeSkippedEvent(RunEventBase):
    type: Literal["edge.skipped"]
    payload: EdgeSkippedPayload


class LoopIterationEvent(RunEventBase):
    type: Literal["loop.iteration"]
    payload: LoopIterationPayload


class LoopExhaustedEvent(RunEventBase):
    type: Literal["loop.exhausted"]
    payload: LoopExhaustedPayload


class RunChildStartedEvent(RunEventBase):
    type: Literal["run.child_started"]
    payload: RunChildStartedPayload


class RunChildFinishedEvent(RunEventBase):
    type: Literal["run.child_finished"]
    payload: RunChildFinishedPayload


class AgentSessionStartedEvent(RunEventBase):
    type: Literal["agent.session_started"]
    payload: AgentSessionStartedPayload


class AgentTextDeltaEvent(RunEventBase):
    type: Literal["agent.text_delta"]
    payload: AgentTextDeltaPayload


class AgentMessageEvent(RunEventBase):
    type: Literal["agent.message"]
    payload: AgentMessagePayload


class AgentToolCallEvent(RunEventBase):
    type: Literal["agent.tool_call"]
    payload: AgentToolCallPayload


class AgentToolResultEvent(RunEventBase):
    type: Literal["agent.tool_result"]
    payload: AgentToolResultPayload


class AgentSubagentEvent(RunEventBase):
    type: Literal["agent.subagent_started", "agent.subagent_stopped"]
    payload: AgentSubagentPayload


class AgentUsageEvent(RunEventBase):
    type: Literal["agent.usage"]
    payload: AgentUsagePayload


class LogWarningEvent(RunEventBase):
    type: Literal["log.warning"]
    payload: LogWarningPayload


class RunReplyEvent(RunEventBase):
    type: Literal["run.reply"]
    payload: RunReplyPayload


class UsageRateLimitEvent(RunEventBase):
    type: Literal["usage.rate_limit"]
    payload: UsageRateLimitPayload


class InteractionRequestedEvent(RunEventBase):
    type: Literal["interaction.requested"]
    payload: InteractionRequestedPayload


class InteractionAnsweredEvent(RunEventBase):
    type: Literal["interaction.answered"]
    payload: InteractionAnsweredPayload


class InteractionClosedEvent(RunEventBase):
    type: Literal["interaction.closed"]
    payload: InteractionClosedPayload


_KNOWN_EVENT_CLASSES: tuple[type[RunEventBase], ...] = (
    RunLifecycleEvent,
    NodeStatusEvent,
    EdgeTraversedEvent,
    AgentSessionStartedEvent,
    AgentTextDeltaEvent,
    AgentMessageEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentSubagentEvent,
    AgentUsageEvent,
    LogWarningEvent,
    RunReplyEvent,
    UsageRateLimitEvent,
    InteractionRequestedEvent,
    InteractionAnsweredEvent,
    InteractionClosedEvent,
    EdgeSkippedEvent,
    LoopIterationEvent,
    LoopExhaustedEvent,
    RunChildStartedEvent,
    RunChildFinishedEvent,
)

type AnyKnownRunEvent = Annotated[
    RunLifecycleEvent
    | NodeStatusEvent
    | EdgeTraversedEvent
    | AgentSessionStartedEvent
    | AgentTextDeltaEvent
    | AgentMessageEvent
    | AgentToolCallEvent
    | AgentToolResultEvent
    | AgentSubagentEvent
    | AgentUsageEvent
    | LogWarningEvent
    | RunReplyEvent
    | UsageRateLimitEvent
    | InteractionRequestedEvent
    | InteractionAnsweredEvent
    | InteractionClosedEvent
    | EdgeSkippedEvent
    | LoopIterationEvent
    | LoopExhaustedEvent
    | RunChildStartedEvent
    | RunChildFinishedEvent,
    Field(discriminator="type"),
]


class KnownRunEvent(RootModel[AnyKnownRunEvent]):
    """알려진 RunEvent 판별 유니온(`type`으로 구분)."""


def _literal_values(cls: type[RunEventBase]) -> tuple[str, ...]:
    annotation = cls.model_fields["type"].annotation
    return tuple(getattr(annotation, "__args__", ()))


KNOWN_RUN_EVENT_TYPES: tuple[str, ...] = tuple(
    value for cls in _KNOWN_EVENT_CLASSES for value in _literal_values(cls)
)
"""payload 형식이 계약에 정해진 이벤트 type 목록. 이 밖의 type도 허용된다."""


def parse_run_event(data: RunEvent | dict[str, Any]) -> AnyKnownRunEvent | RunEvent:
    """이벤트를 알려진 타입이면 타입별 모델로, 아니면 일반 `RunEvent`로 검증해 돌려준다.

    알려진 type인데 payload가 형식에 맞지 않으면 `pydantic.ValidationError`를 낸다.
    """
    raw = data.model_dump(by_alias=True) if isinstance(data, RunEvent) else data
    if raw.get("type") in KNOWN_RUN_EVENT_TYPES:
        return KnownRunEvent.model_validate(raw).root
    return RunEvent.model_validate(raw)
