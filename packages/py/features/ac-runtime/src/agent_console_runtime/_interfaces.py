"""확장 인터페이스(design §3.3, §R3).

X1 NodeType, X2 EdgeType, X3 ExecutionBackend, X10 SecretProvider,
그리고 엔진이 주입받는 RunRecorder(저장)·EventSink(발행)·Clock·IdFactory.

X12 위임 방식(`DelegationStrategy`)은 `_delegation.py`에 있다."""

from __future__ import annotations

import builtins
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import (
    Agent,
    BackendDescriptor,
    ConditionOutcome,
    EdgeSpec,
    EdgeTypeDescriptor,
    ErrorInfo,
    Graph,
    InteractionGrant,
    Issue,
    Limits,
    LogWarningPayload,
    ModelInfo,
    NodeRun,
    NodeRunStatus,
    NodeSpec,
    NodeTypeDescriptor,
    PortSpec,
    ResourceBundle,
    Run,
    RunEvent,
    RunEventBase,
    Usage,
    WaitInfo,
)

from ._host_tools import HostTool
from ._interactions import InteractionWriter

if TYPE_CHECKING:
    from ._cancel import CancelToken
    from ._context import NodeContext
    from ._registries import Registries
    from ._secrets import SecretResolver
    from ._services import Services

_log = logging.getLogger(__name__)

type Clock = Callable[[], float]
"""현재 시각(Unix epoch 초)을 돌려주는 함수. 기본 `time.time`."""

type IdFactory = Callable[[], str]
"""고유 id 생성기(Run id, 이벤트 id). 기본 uuid4 hex."""


# ---------------------------------------------------------------- X1 노드 타입


class NodeResult(BaseModel):
    """노드 1회 실행 결과.

    - `outputs`: 포트 이름 → 값. **값이 있는 포트만 방출**된 것으로 본다(나가는 엣지 판단 근거).
      값은 JSON 호환이어야 한다(NodeRun으로 저장된다).
    - `status="waiting"`이면 `wait`(Phase 4 승인 등). Phase 1 엔진은 waiting 노드를 재개하지 않는다.
    - `structured`: 선택. 노드의 구조화 결과(예: 백엔드 `AgentResult.structured`). 저장하지 않고
      나가는 엣지 타입이 `NodeRunView.structured`로 본다(조건 연결 `/structured/...`, design §5R.5).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: Literal["succeeded", "failed", "waiting", "skipped"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: ErrorInfo | None = None
    wait: WaitInfo | None = None
    usage: Usage | None = None
    backend_session_id: str | None = None
    structured: Any = None


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """`NodeType.validate`에 주는 검증 맥락(스키마 외 의미 검증용: 참조 존재 등)."""

    graph: Graph
    node: NodeSpec
    registries: Registries
    services: Services


@runtime_checkable
class NodeType(Protocol):
    """노드 타입(X1). 엔진은 이 인터페이스만 알고 구체 타입은 레지스트리에서 찾는다.

    - `resolve_ports(config)`: `descriptor.dynamic_ports`가 참일 때 실제 포트.
      고정 포트 타입은 `descriptor.static_ports`를 돌려주면 된다.
    - `validate(config, ctx)`: config 스키마 검증 뒤 호출되는 의미 검증.
      이슈의 `path`는 config 기준.
    - `execute(ctx, inputs)`: 입력 포트 이름 → 값을 받아 결과를 돌려준다. 예외는 엔진이
      `failed`로 바꾼다. 취소는 `ctx.cancel`을 확인한다.
    """

    descriptor: NodeTypeDescriptor

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec: ...

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]: ...

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult: ...


NODE_ACTOR_HOOK = "actor_of"
"""`NodeType`의 선택 훅 이름: `actor_of(config) -> str | None`.

이 노드 자리에서 일하는 에이전트 정의 id(이벤트 머리 `actor`, design §R3.4)를 돌려준다.
엔진은 config 키를 모르므로 노드 타입이 알려 준다.
훅이 없거나 None이면 그 노드의 이벤트에 actor가 없다."""


def node_actor(impl: object, config: Mapping[str, Any]) -> str | None:
    """노드 타입 구현의 `actor_of(config)` 훅을 부른다(없거나 실패하면 None, 실패는 로그만)."""
    hook = getattr(impl, NODE_ACTOR_HOOK, None)
    if not callable(hook):
        return None
    try:
        value = hook(config)
    except Exception:
        _log.exception("노드 타입 actor 훅 실패")
        return None
    return value if isinstance(value, str) and value else None


NODE_NAME_HOOK = "display_name"
"""`NodeType`의 선택 훅 이름: `display_name(config, services) -> str | None`.

노드에 `label`이 없을 때 사용자 문구(실행 실패 요약 등)에 쓸 이름을 돌려준다(예: 묶인 에이전트
정의의 이름). 엔진은 정의를 모르므로 노드 타입이 알려 준다. 없거나 None이면 노드 타입 `title`."""


def node_display_name(spec: Any, impl: object | None, services: Any = None) -> str:
    """사용자 문구에 쓸 노드 이름: `label` → 노드 타입 `display_name` 훅 → 노드 타입 `title`.

    노드 id는 문구에 쓰지 않는다(id는 `details`에 둔다). 훅 실패는 로그만 남긴다.

    Args:
        spec: 노드(`NodeSpec`).
        impl: 노드 타입 구현(모르면 None).
        services: 훅에 넘길 앱 서비스(`Services`).
    """
    label = getattr(spec, "label", None)
    if isinstance(label, str) and label:
        return label
    hook = getattr(impl, NODE_NAME_HOOK, None)
    if callable(hook):
        try:
            value = hook(getattr(spec, "config", {}), services)
        except Exception:
            _log.exception("노드 타입 이름 훅 실패")
            value = None
        if isinstance(value, str) and value:
            return value
    descriptor = getattr(impl, "descriptor", None)
    title = getattr(descriptor, "title", None)
    if isinstance(title, str) and title:
        return title
    return str(getattr(spec, "type", "") or "노드")


# ---------------------------------------------------------------- X2 엣지 타입


@dataclass(frozen=True, slots=True)
class NodeRunView:
    """엣지 타입이 보는 소스 노드 결과(읽기 전용).

    `iteration`은 그 NodeRun의 반복 회차(0부터, design §5R.4). 조건 연결이 회차를 볼 때 쓴다.
    `structured`는 노드 결과의 구조화 값(`NodeResult.structured`, 없으면 None, design §5R.5).
    `call`은 호출 회차(위임자가 `ctx.invoke_node`로 부른 NodeRun이면 그 순번, 스케줄 실행은 0,
    design §5R.6).
    """

    node_id: str
    node_type: str
    status: NodeRunStatus
    outputs: Mapping[str, Any] = field(default_factory=dict)
    error: ErrorInfo | None = None
    iteration: int = 0
    structured: Any = None
    call: int = 0


@dataclass(frozen=True, slots=True)
class Incoming:
    """노드 입력 포트로 들어온 값 하나(통과한 엣지 하나, design §4.3·§R3.2-4).

    같은 포트로 여러 엣지가 들어오면(join `all` 합류 등) 노드는 `ctx.incoming(port)`로 엣지별 값을
    모두 받는다. `execute`의 `inputs`는 호환을 위해 포트마다 첫 값만 담는다.

    Attributes:
        port: 받은 입력 포트 이름.
        edge_id: 통과한 엣지 id.
        source_node: 보낸 노드 id(입구 엣지면 입구 엣지의 출발 노드).
        source_port: 보낸 포트 이름.
        value: 엣지 타입이 넘긴 값(메모리 원본, 가리지 않음).
        carried: 반복 회차(design §5R.4)에서 이 노드의 이전 회차 전에 도착해 남아 있는 값이면 참
            (반복 영역 밖에서 한 번 들어온 값). 이번 회차에 새로 도착한 값은 거짓. 같은 포트의
            `inputs` 첫 값은 새로 도착한 값이 먼저다.
    """

    port: str
    edge_id: str
    source_node: str
    source_port: str
    value: Any = None
    carried: bool = False


@dataclass(frozen=True, slots=True)
class Activation:
    """엣지 통과. `value`가 타깃 입력 포트로 전달된다.

    `scheduling = exit`(답변) 엣지에서는 `value`가 답변이 된다. `Reply`면 그 필드를 쓰고,
    문자열이면 그대로, 그 밖의 값은 JSON 문자열로 바꾼다(라벨 없음, final=True).

    - `condition`: 선택. 통과 판정 근거(조건 연결 등, design §5R.5). 엔진이 `edge.traversed`
      payload `condition`에 싣는다.
    - `warnings`: 선택. 엔진이 `log.warning` 이벤트로 낸다(`details`에 `edge_id`·`kind`를 더함).
    """

    value: Any = None
    condition: ConditionOutcome | None = None
    warnings: tuple[LogWarningPayload, ...] = ()


@dataclass(frozen=True, slots=True)
class Blocked:
    """엣지가 판정 결과 지나가지 않는다(dead-path, None과 같음) + 사유·근거.

    엔진은 `edge.skipped{reason, condition}` 이벤트를 내고 None처럼 다룬다(design §5R.5).
    `reason`은 열린 문자열(예: `condition_false`). `warnings`는 `Activation.warnings`와 같다.
    """

    reason: str | None = None
    condition: ConditionOutcome | None = None
    warnings: tuple[LogWarningPayload, ...] = ()


@dataclass(frozen=True, slots=True)
class Reply:
    """답변 엣지(`scheduling = exit`)가 `Activation.value`로 돌려주는 답변 하나.

    `run.reply` payload가 된다.

    라벨·순서·최종 여부는 엣지 config의 의미이므로 엣지 타입이 채운다(엔진은 config 키를 모른다).
    """

    text: str
    label: str | None = None
    order: int | None = None
    final: bool = True


@runtime_checkable
class EdgeType(Protocol):
    """엣지 타입(X2). 엔진은 디스크립터 `scheduling`에 따라 `activates`를 부른다(design §R3.1).

    - `flow`: 소스 노드가 끝나면(succeeded·failed) 부른다.
      `Activation`이면 통과(타깃 입력 포트에 값), None이면 이 경로는 죽는다(dead-path).
      `Blocked`도 dead-path이며 엔진이 사유·근거를 `edge.skipped`로 남긴다.
    - `entry`: Run 시작 때 부른다. 소스는 Run 입력을 그 엣지의 소스 포트 값으로 가진 가상 결과
      (`status="succeeded"`, `outputs={source.port: Run 입력 dict}`)다.
      통과하면 타깃 노드(입구)에 값이 들어간다.
    - `exit`: 소스 노드가 끝나면 부른다. 통과하면 그 값이 답변(`run.reply`)이 된다(`Reply` 참고).
    - `none`: 부르지 않는다(위임·리소스·상호작용 허용 등 노드가 해석하는 연결).
    """

    descriptor: EdgeTypeDescriptor

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | Blocked | None: ...


@dataclass(frozen=True, slots=True)
class EdgeValidationContext:
    """`EdgeValidator.validate_edge`에 주는 검증 맥락."""

    graph: Graph
    edge: EdgeSpec
    registries: Registries
    services: Services


@runtime_checkable
class EdgeValidator(Protocol):
    """선택 능력(X2): 엣지 config의 의미 검증(스키마 검사 뒤, 저장 전 검사, design §5R.8).

    이슈의 `path`는 엣지 config 기준이다. `edge_id`를 비우면 엔진이 채운다. config가 스키마에
    맞지 않을 수도 있으므로(스키마 이슈는 따로 난다) 해석에 실패하면 빈 목록을 돌려준다.
    """

    def validate_edge(self, edge: EdgeSpec, ctx: EdgeValidationContext) -> list[Issue]: ...


# ---------------------------------------------------------------- X3 실행 백엔드


class SessionRef(BaseModel):
    """백엔드 세션 참조(맥락 이어 쓰기·resume, R4.6)."""

    backend: str
    session_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class SubagentSpec(BaseModel):
    """한 세션 안에서 위임자가 부를 수 있는 하위 에이전트 하나(design §R3.3, X12 `sdk-subagents`).

    백엔드는 `capabilities.subagents`가 참일 때만 이 목록을 실행한다. 하위 에이전트가 낸 이벤트는
    `node_path=[위임자 노드, name]`, `actor=actor`로 귀속한다.
    """

    name: str = Field(description="위임 대상 노드 id(세션 안 하위 에이전트 이름).")
    description: str = Field(default="", description="언제 맡길지(위임자 모델이 보고 판단).")
    prompt: str = Field(default="", description="하위 에이전트 시스템 프롬프트.")
    actor: str | None = Field(default=None, description="대상 에이전트 정의 id.")
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    model: str | None = None
    bundle: ResourceBundle | None = Field(
        default=None, description="대상 노드의 실행 묶음(받을 수 있는 칸만 백엔드가 쓴다)."
    )
    options: dict[str, Any] = Field(default_factory=dict, description="백엔드별 추가 필드.")


class AgentRequest(BaseModel):
    """백엔드 실행 요청. `agent`는 비밀 참조(`secret://…`)가 해석된 상태로 넘긴다.

    - `subagents`: 같은 세션에서 위임자가 부를 하위 에이전트(위임 방식이 채운다, 비면 위임 없음).
    - `bundle`: 이 노드의 실행 묶음(design §R12.4).
      백엔드는 `capabilities.resource_slots`의 칸만 쓴다.
    - `interactions`: 이 노드가 열 수 있는 상호작용. None이면 열지 않는다.
    - `run_folder`: 이 노드 실행의 파일 폴더(`<Run 파일 루트>/<run>/<노드>`, 만들지 않은 경로일 수
      있다). 백엔드가 실행 산출물(예: hook probe 기록 `hook-probe/`)을 쓰는 곳이다. None이면 쓸 곳이
      없다(그 기능만 꺼진다).
    - `run_context`: 산출물에 붙일 실행 맥락(`run_id`·`node_path`="a/b" 등 문자열). 비면 없음.
    - `host_tools`: 모델에게 줄 플랫폼 도구(`HostTool`, design §5R.6). 위임 방식이 채우고
      `capabilities.host_tools`를 선언한 백엔드가 호출마다 `handler`를 부른다. 런타임 전용이라
      `model_dump`에 나오지 않는다. 능력이 없는 백엔드는 무시한다(검증이 먼저 막는다).
    """

    agent: Agent
    prompt: str
    attachments: list[Any] = Field(default_factory=list)
    cwd: str | None = None
    limits: Limits | None = None
    session: SessionRef | None = None
    subagents: list[SubagentSpec] = Field(default_factory=list)
    bundle: ResourceBundle | None = None
    interactions: InteractionGrant | None = None
    observe: dict[str, Any] = Field(default_factory=dict, description="수집기(X7) 옵션.")
    options: dict[str, Any] = Field(default_factory=dict, description="노드가 주는 추가 옵션.")
    run_folder: str | None = Field(
        default=None, description="이 노드 실행의 파일 폴더(실행 산출물을 쓰는 곳)."
    )
    run_context: dict[str, str] = Field(
        default_factory=dict, description="산출물에 붙일 실행 맥락(run_id·node_path 등)."
    )
    host_tools: list[HostTool] = Field(
        default_factory=list,
        exclude=True,
        description="플랫폼 도구(런타임 전용, 직렬화하지 않는다). capabilities.host_tools인 "
        "백엔드만 쓴다.",
    )


class AgentResult(BaseModel):
    """백엔드 실행 결과."""

    status: Literal["succeeded", "failed", "cancelled"]
    text: str = ""
    structured: Any = None
    usage: Usage = Field(default_factory=Usage)
    session: SessionRef | None = None
    error: ErrorInfo | None = None


@runtime_checkable
class SubagentResultListener(Protocol):
    """선택 sink 능력: 서브에이전트 호출 하나가 끝날 때마다 결과(위임 도구 결과 전체)를 받는다.

    위임 방식(X12, 예: `sdk-subagents`)이 sink를 감싸 이 메서드로 대상 노드의 답변
    (`ctx.emit_replies`)을 낸다. 백엔드는 노드 포트 이름을 모르므로 답변을 직접 내지 않고,
    sink가 이 프로토콜을 만족할 때만(`isinstance(sink, SubagentResultListener)`) 알린다.
    알림 예외는 백엔드가 `log.warning`으로 바꾼다.

    Args:
        name: 대상 이름(`SubagentSpec.name` = 대상 노드 id).
        text: 결과 텍스트.
        status: `succeeded` | `failed`.
        actor: 대상 에이전트 정의 id(`SubagentSpec.actor`).
        tool_use_id: 위임 도구 호출 id.
    """

    async def on_subagent_result(
        self, name: str, *, text: str, status: str, actor: str | None, tool_use_id: str
    ) -> None: ...


class BackendEventSink(Protocol):
    """백엔드가 공급자 독립 이벤트(`agent.*`, `hook.*`, `mcp.*`)를 내보내는 곳.

    `NodeContext`가 이 프로토콜을 만족하므로 노드는 `backend.run(req, ctx, ctx.cancel)`로 넘긴다.
    머리 필드(run_id·seq·ts·attempt)는 엔진이 채운다.
    `actor`·`node_path`를 생략하면 그 노드의 값이고,
    하위 에이전트 이벤트는 `actor=대상 에이전트`, `node_path=child_path(대상 노드)`로 낸다.
    """

    def child_path(self, node_id: str) -> list[str]:
        """이 노드 실행 안에서 부른 대상 노드의 `node_path`(`[위임자 경로…, node_id]`, §R3.4).

        백엔드가 같은 세션 안의 서브에이전트 이벤트를 대상 노드에 귀속할 때 쓴다.
        """
        ...

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        raw: Any = None,
        evidence: str = "observed",
        actor: str | None = None,
        node_path: Sequence[str] | None = None,
    ) -> RunEvent: ...


@runtime_checkable
class ExecutionBackend(Protocol):
    """실행 백엔드 어댑터(X3)."""

    descriptor: BackendDescriptor

    async def list_models(self) -> list[ModelInfo]: ...

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult: ...


BACKEND_OPTIONS_HOOK = "from_options"
"""`ConfigurableBackend`의 생성 훅 이름(앱이 duck typing으로 찾는다)."""

BACKEND_HOST_PARAM = "host"
"""`from_options` 훅이 이 이름의 키워드 인자를 받으면 앱이 `BackendHostContext`를 넘긴다(선택)."""


@dataclass(frozen=True)
class BackendHostContext:
    """앱이 백엔드 설정 훅에 넘기는 호스트 정보(선택, 5.7R.30·5.7R.30b).

    키 해석은 백엔드가 한다. 앱은 값만 채운다. 팀 모드(사람별 자격)처럼 범위가 넓어지면 이
    자리에 필드를 더한다.

    Attributes:
        workspace_dir: 앱 workspace(앱 데이터 폴더, 서버 ``--workspace``) 절대 경로. 백엔드가 앱이
            관리하는 상대 경로(예: 앱 하나에 하나인 구독 자격 폴더)를 푸는 기준. 프로젝트(작업)
            폴더가 아니다 — 앱은 등록만으로 프로젝트 폴더에 쓰지 않는다. 모르면 None.
    """

    workspace_dir: Path | None = None


def accepts_host_context(hook: Callable[..., Any]) -> bool:
    """`from_options` 훅이 `host` 키워드 인자를 받는지(받는 훅에만 `BackendHostContext`를 넘긴다).

    >>> def old(options, *, secrets, environ): ...
    >>> def new(options, *, secrets, environ, host=None): ...
    >>> accepts_host_context(old), accepts_host_context(new)
    (False, True)
    """
    try:
        params = inspect.signature(hook).parameters
    except (TypeError, ValueError):
        return False
    param = params.get(BACKEND_HOST_PARAM)
    if param is not None:
        return param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)
    return any(p.kind is p.VAR_KEYWORD for p in params.values())


@runtime_checkable
class ConfigurableBackend(Protocol):
    """설치자 설정(앱 설정의 `backends.<id>`)으로 다시 만들 수 있는 백엔드(X3 선택 훅).

    entry point는 인자 없이 만들어지므로, 생성 인자(모델 목록·환경 정책 등)가 필요한 백엔드는
    이 classmethod를 구현한다. 앱은 레지스트리에 등록된 백엔드에 이 훅이 있으면 호출해 교체할 뿐,
    설정 키의 의미는 모른다(키 해석은 각 백엔드 패키지 안에 있다).
    """

    @classmethod
    def from_options(
        cls,
        options: Mapping[str, Any],
        *,
        secrets: SecretResolver,
        environ: Mapping[str, str],
    ) -> ExecutionBackend:
        """설정 값으로 백엔드를 만든다.

        Args:
            options: 설정의 `backends.<id>` 값(없으면 빈 dict).
            secrets: 공용 비밀 해석기(원시 메시지 가리기 등).
            environ: 하위 프로세스 등에 쓸 환경(주입).

        Raises:
            ValueError: 모르는 키나 잘못된 값(메시지에 값 자체는 넣지 않는다).
        """
        ...


# ---------------------------------------------------------------- X10 비밀 값 공급자


@runtime_checkable
class SecretProvider(Protocol):
    """비밀 값 공급자(X10). 이름에 해당하는 값이 없으면 None."""

    def get_secret(self, name: str) -> str | None: ...


# ---------------------------------------------------------------- 저장·발행 (주입)


class RunWriter(Protocol):
    """Run·NodeRun 기록. `agent_console_store`의 `RunRepository`가 구조적으로 만족한다."""

    def save(self, run: Run) -> None: ...

    def save_node_run(self, node_run: NodeRun) -> None: ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]: ...


class EventWriter(Protocol):
    """RunEvent 기록. 같은 `event_id` 재적재는 False(멱등). `EventRepository`가 만족한다."""

    def append(self, event: RunEventBase) -> bool: ...

    def append_many(self, events: Sequence[RunEventBase]) -> int: ...

    def last_seq(self, run_id: str) -> int: ...


class RunRecorder(Protocol):
    """엔진이 쓰는 저장 묶음(동기). `agent_console_store`의 `SqliteStorage`·`InMemoryStorage`가
    구조적 타이핑으로 만족한다(runtime은 store를 import하지 않는다).

    엔진은 Run마다 기록 작업을 한 줄로 세워 워커 스레드에서 호출하고, 연속된 이벤트는
    `append_many` 한 번으로 묶는다. 상호작용(design §R14)은 `interactions`에 저장한다.
    """

    @property
    def runs(self) -> RunWriter: ...

    @property
    def events(self) -> EventWriter: ...

    @property
    def interactions(self) -> InteractionWriter: ...


class EventSink(Protocol):
    """저장이 끝난 이벤트를 발행하는 곳(이벤트 버스·WS 팬아웃). 막히지 않아야 한다."""

    def publish(self, event: RunEvent) -> None: ...
