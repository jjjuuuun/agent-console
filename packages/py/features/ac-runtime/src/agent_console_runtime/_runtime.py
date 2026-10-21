"""토큰 기반 그래프 스케줄러(design §4.2~§4.5, §R3.1, §5R.4). 특정 노드·엣지 타입을 모른다.

엣지는 디스크립터 `scheduling`으로만 구분한다: `entry`(입구, Run 입력 주입) · `flow`(토큰 흐름) ·
`exit`(답변 발행) · `none`(스케줄과 무관). 노드는 `executable`과 들어오는 `entry`·`flow` 엣지 유무로
스케줄 대상을 정한다. 입구는 `entry` 엣지로 명시된 것뿐이며 그래프 모양으로 추론하지 않는다.

반복(design §5R.4): 디스크립터 `cycle`이 있는 흐름 엣지(사이클 연결)가 지나가면 그 반복 영역
(`ac-graph.loop_regions`)의 노드를 새 회차(`NodeRun.iteration` + 1)로 다시 연다. 연결 이름은 모른다.

호출: 노드가 실행 안에서 `ctx.invoke_node`로 `invocation` 연결의 대상을 부르면 대상은
자기 NodeRun(`call`·`invoked_by`)으로 돈다. 같은 대상은 직렬, 기다리는 위임자는 슬롯을 내놓는다.

자식 Run(design §5R.7): 노드가 `ctx.run_child`로 다른 그래프를 실행하면 같은 런타임에서 자식
Run(`parent_run_id`·`parent_node_id`·`root_run_id`)이 돈다. 기다리는 노드는 슬롯을 내놓고, 자식이
상호작용만 기다리면 부모도 `waiting`, 부모 취소·끊김은 자식에 전파된다.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import inspect
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol

from agent_console_contracts import (
    ConditionOutcome,
    DelegationSettings,
    EdgeSpec,
    EdgeTraversedPayload,
    EdgeTypeDescriptor,
    ErrorCodes,
    ErrorInfo,
    FlowSettings,
    Graph,
    Interaction,
    InteractionGrant,
    InteractionSettings,
    Issue,
    JoinRule,
    KnownIssueCodes,
    LogWarningPayload,
    LoopExhaustedPayload,
    LoopIterationPayload,
    NodeRun,
    NodeRunStatus,
    NodeSpec,
    NodeStatusPayload,
    Run,
    RunChildFinishedPayload,
    RunChildStartedPayload,
    RunEvent,
    RunReplyPayload,
    RunStatus,
    RunStatusPayload,
    Usage,
    WaitInfo,
)
from agent_console_graph import (
    LoopRegion,
    ScheduleView,
    effective_max_iterations,
    graph_hash,
    loop_regions,
    schedule_view,
)

from ._cancel import CancelToken
from ._children import ChildRunPreparation, ChildRunPreparer, ChildRunRequest, ChildRunResult
from ._context import ChildRunner, NodeContext, NodeInvoker, RequestOpener
from ._interactions import (
    InteractionClosedError,
    InteractionCloseReasons,
    InteractionOutcome,
    InteractionRequest,
    UnknownInteractionError,
)
from ._interfaces import (
    Clock,
    EventSink,
    IdFactory,
    Incoming,
    NodeResult,
    NodeRunView,
    NodeType,
    RunRecorder,
    node_actor,
    node_display_name,
)
from ._journal import RunJournal
from ._registries import Registries
from ._replies import activate_edge, emit_replies
from ._secrets import SecretResolver
from ._services import ServiceKey, Services
from ._usage import DEFAULT_PREVIEW_CHARS, preview, sum_usage
from ._validation import (
    GraphValidationError,
    edge_type_descriptors,
    node_type_descriptors,
    validate_graph_with,
)
from ._waits import InteractionBroker, Sleep, WaitPolicy

_log = logging.getLogger(__name__)


class RuntimeErrorCodes:
    """엔진이 쓰는 `ErrorInfo.code` 값."""

    NODE_FAILED: Final = "node_failed"
    """처리되지 않은 노드 실패로 Run이 실패했다(`details.node_id`, `details.error`)."""
    NODE_EXCEPTION: Final = "node_exception"
    """노드 `execute`가 예외를 던졌다."""
    INVALID_RESULT: Final = "invalid_node_result"
    """노드가 `NodeResult`가 아닌 값을 돌려줬다."""
    CANCELLED: Final = "cancelled"
    """취소로 끝났다."""
    INTERRUPTED: Final = "interrupted"
    """서버 재시작 등으로 실행이 끊겼다."""
    INTERNAL: Final = "internal"
    """엔진 내부 오류."""
    MAX_NODE_RUNS_EXCEEDED: Final = KnownIssueCodes.FLOW_MAX_NODE_RUNS_EXCEEDED
    """노드 실행 수가 `flow.max_node_runs`를 넘어 Run이 실패했다(`details.limit`, §5R.4 5)."""
    DELEGATION_DEPTH_EXCEEDED: Final = KnownIssueCodes.DELEGATION_DEPTH_EXCEEDED
    """`ctx.invoke_node`: 위임 깊이가 한도를 넘어 대상을 실행하지 않았다(`details.depth`·
    `details.max_depth`, design §5R.6)."""
    DELEGATION_CYCLE: Final = "delegation.cycle"
    """`ctx.invoke_node`: 대상이 이미 위임 경로에 있어 실행하지 않았다(`details.path`)."""
    CHILD_NESTING_EXCEEDED: Final = KnownIssueCodes.TEAM_NESTING_EXCEEDED
    """`ctx.run_child`: 중첩 깊이가 `delegation.max_nesting`을 넘어 자식 Run을 만들지 않았다
    (`details.depth`·`details.limit`, design §5R.7)."""
    CHILD_RECURSIVE: Final = KnownIssueCodes.TEAM_RECURSIVE
    """`ctx.run_child`: 자식 그래프가 이미 Run 경로에 있어 만들지 않았다(`details.path` =
    그래프 id 경로)."""
    CHILD_INVALID: Final = ErrorCodes.VALIDATION_FAILED
    """`ctx.run_child`: 준비·검증이 실행을 막았다(`details.issues`)."""


class RuntimeIssueCodes:
    """엔진이 실행 전에 내는 `Issue.code` 값(`GraphValidationError.issues`)."""

    NO_ENTRY: Final = "no_entry"
    """실행 가능한 노드로 들어가는 `scheduling = entry` 엣지가 없다(Run을 만들지 않음)."""
    SEED_NOT_SCHEDULED: Final = "seed_not_scheduled"
    """`start(seed=)`의 노드가 이 그래프에서 스케줄되는 노드가 아니다(Run을 만들지 않음)."""


class SkipReasons:
    """엔진이 `node.skipped` payload `reason`에 남기는 값(열린 문자열)."""

    RESUMED: Final = "resumed"
    """이어 가기(`start(seed=)`)에서 시작 노드의 상류라 다시 실행하지 않았다."""


class NoEntryError(GraphValidationError):
    """입구(`scheduling = entry` 엣지가 들어오는 실행 가능 노드)가 없어 Run을 만들지 않았다."""

    def __init__(self) -> None:
        super().__init__(
            [
                Issue(
                    severity="error",
                    code=RuntimeIssueCodes.NO_ENTRY,
                    message="입구 연결(scheduling=entry)이 없어 실행할 수 없습니다",
                )
            ]
        )


type _EdgeState = Literal["open", "passed", "dead"]

_NODE_EVENT: Final[dict[str, str]] = {
    "queued": "node.queued",
    "running": "node.started",
    "succeeded": "node.completed",
    "failed": "node.failed",
    "skipped": "node.skipped",
    "waiting": "node.waiting",
    "cancelled": "node.cancelled",
}


def _default_ids() -> str:
    return uuid.uuid4().hex


@dataclass
class _NodeState:
    spec: NodeSpec
    impl: NodeType
    join: JoinRule
    incoming: tuple[str, ...]
    outgoing: tuple[str, ...]
    exits: tuple[str, ...]
    actor: str | None
    status: NodeRunStatus = "pending"
    inputs: dict[str, Any] = field(default_factory=dict)
    received: tuple[Incoming, ...] = ()
    started_at: float | None = None
    result: NodeResult | None = None
    handled: bool = False
    holding: bool = False
    """동시 실행 슬롯을 잡고 있는지."""
    live_wait: bool = False
    """열린 상호작용을 기다리는 중인지(live wait). parked wait(`NodeResult(waiting)`)와 구분."""
    finished: bool = False
    """`execute`가 끝났는지(이후 요청은 열 수 없고 슬롯을 다시 잡지 않는다)."""
    iteration: int = 0
    """지금 회차(반복 영역이 다시 열릴 때마다 1씩 는다, design §5R.4)."""
    previous_session_id: str | None = None
    """직전 회차 결과의 백엔드 세션 id(`ctx.previous_session_id`)."""
    path: tuple[str, ...] = ()
    """이벤트 `node_path`. 스케줄 실행은 `(node_id,)`, 호출 실행은 `(...위임자 경로, node_id)`."""
    key: Hashable = ""
    """상호작용 대기 키(스케줄 실행은 노드 id, 호출 실행은 `("call", node_id, call)`)."""
    call: int = 0
    """호출 회차. 스케줄 실행은 0."""
    invoked_by: tuple[str, ...] | None = None
    """호출 실행이면 위임자 노드 경로."""
    inflight: list[str] = field(default_factory=list)
    """이 실행이 지금 `invoke_node`로 부르고 있는(또는 차례를 기다리는) 대상 노드 id."""
    closed: bool = False
    """호출 실행의 마지막 상태를 기록했는지(취소 정리가 두 번 기록하지 않게)."""
    children: list[_Execution] = field(default_factory=list)
    """이 실행이 지금 `run_child`로 기다리는 자식 Run 실행."""


@dataclass
class _Child:
    """부모 Run이 기다리는 자식 Run 하나."""

    execution: _Execution
    task: asyncio.Task[Run]
    caller: _NodeState
    reported: bool = False
    """`run.child_finished`를 냈는지."""


@dataclass(frozen=True)
class _Loop:
    """사이클 연결 하나와 그 반복 영역(스케줄 대상 노드만)."""

    edge_id: str
    entry: str
    exit: str
    nodes: tuple[str, ...]
    members: frozenset[str]
    limit: int | None
    """유효 최대 반복. None = 쓸 수 있는 값이 없다(다시 열지 않는다)."""


@dataclass(frozen=True)
class _Settings:
    registries: Registries
    recorder: RunRecorder
    sink: EventSink | None
    clock: Clock
    ids: IdFactory
    secrets: SecretResolver
    semaphore: asyncio.Semaphore | None
    cancel_grace: float
    preview_chars: int
    sleep: Sleep
    interaction_settings: InteractionSettings | None
    flow_settings: FlowSettings | None
    delegation_settings: DelegationSettings | None


@dataclass(frozen=True)
class _Plan:
    """Run 시작 전에 계산하는 실행 계획(노드 구현 조회 + 스케줄 관점 요약)."""

    impls: Mapping[str, NodeType]
    view: ScheduleView
    regions: Mapping[str, LoopRegion]
    cycle_types: Mapping[str, EdgeTypeDescriptor]
    """사이클 연결 id → 그 연결 종류 디스크립터(최대 반복 계산용)."""


def _plan(registries: Registries, graph: Graph) -> _Plan:
    """노드 구현을 찾고 스케줄 관점을 계산한다.

    Raises:
        UnknownExtensionError: 등록되지 않은 노드 타입.
    """
    impls: dict[str, NodeType] = {}
    for spec in graph.nodes:
        impls.setdefault(spec.id, registries.node_types.get(spec.type, spec.type_version))
    edge_types = edge_type_descriptors(registries)
    view = schedule_view(graph, node_type_descriptors(registries), edge_types)
    regions = loop_regions(graph, edge_types)
    kinds = {e.id: e.kind for e in reversed(graph.edges)}
    cycle_types = {
        edge_id: registries.edge_types.get(kinds[edge_id]).descriptor for edge_id in regions
    }
    return _Plan(impls=impls, view=view, regions=regions, cycle_types=cycle_types)


class _ChildSpawner(Protocol):
    """자식 Run을 만드는 쪽(`GraphRuntime`). 실행 하나가 런타임 전체를 알지 않게 좁힌다."""

    async def spawn_child(
        self, parent: _Execution, request: ChildRunRequest
    ) -> tuple[_Execution, asyncio.Task[Run]]: ...


class _Execution:
    """Run 하나의 실행 상태와 스케줄링 루프."""

    def __init__(
        self,
        settings: _Settings,
        run: Run,
        graph: Graph,
        services: Services,
        plan: _Plan,
        policy: WaitPolicy,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        spawner: _ChildSpawner | None = None,
        ancestors: tuple[Run, ...] = (),
        conversation_id: str | None = None,
        run_context: Mapping[str, Any] | None = None,
        start_warnings: Sequence[Issue] = (),
    ) -> None:
        self.s = settings
        # `run.started` payload에 더할 Run 맥락(예: 유효 작업 폴더 `cwd`). 엔진은 뜻을 모른다.
        # 자식 Run은 준비자가 다른 값을 주지 않으면 이것을 물려받는다.
        self.run_context: dict[str, Any] = dict(run_context or {})
        # `run.started` 뒤에 낼 실행 수준 경고(`log.warning`, 예: 준비 중 알게 된 문제).
        self.start_warnings: tuple[Issue, ...] = tuple(start_warnings)
        # 자식 Run(design §5R.7): 만드는 쪽(런타임), 루트부터 부모까지의 Run,
        # 상태가 바뀔 때 알릴 곳(부모 Run).
        self.spawner = spawner
        self.ancestors = ancestors
        self.on_status: Callable[[], None] | None = None
        self.children: dict[str, _Child] = {}
        # 이 Run이 낸 답변(`run.reply` payload, 비밀을 가린 값). 자식 Run 결과로 돌려준다.
        self.replies: list[RunReplyPayload] = []
        # 이어 가기: 노드 id → 저장된 입력. None이면 평소처럼 입구 엣지로 시작한다(§2R.10).
        self.seed = {k: dict(v) for k, v in seed.items()} if seed is not None else None
        self.run = run
        # 종료 처리 중(`_finalize`) 바깥에 보일 Run: 최종 상태를 메모리에 정한 뒤 기록이 모두
        # 저장·발행될 때까지 직전 상태를 보인다(5.2R.39 — 종료 상태가 보이면 답변 등 그 Run의
        # 이벤트는 이미 저장소·구독자에 있다). None이면 `run`을 그대로 보인다.
        self.held_run: Run | None = None
        self.graph = graph
        self.services = services
        self.view = plan.view
        self.token = CancelToken()
        # 끊김(서버 종료) 메시지. None이 아니면 취소 대신 `interrupted`로 정리한다(§R14.5).
        self.interrupted: str | None = None
        self.journal = RunJournal(
            run.id,
            settings.recorder,
            settings.sink,
            clock=settings.clock,
            ids=settings.ids,
            redact=settings.secrets.redact,
            observe=self._observe,
        )
        self.edges: dict[str, EdgeSpec] = {}
        for edge in graph.edges:
            self.edges.setdefault(edge.id, edge)
        self.edge_order = {edge_id: i for i, edge_id in enumerate(self.edges)}
        self.order = {n.id: i for i, n in enumerate(graph.nodes)}
        self.specs: dict[str, NodeSpec] = {}
        for spec in graph.nodes:
            self.specs.setdefault(spec.id, spec)
        scheduled = set(plan.view.scheduled)
        # 스케줄 대상만 상태를 가진다. 입구 없는 노드·호출 대상·실행하지 않는 노드는 NodeRun이 없다.
        self.nodes: dict[str, _NodeState] = {}
        for node_id in plan.view.scheduled:
            spec = self.specs[node_id]
            impl = plan.impls[node_id]
            self.nodes[node_id] = _NodeState(
                spec=spec,
                impl=impl,
                join=spec.join or impl.descriptor.join,
                incoming=plan.view.incoming[node_id],
                outgoing=tuple(
                    e for e in plan.view.outgoing[node_id] if self.edges[e].target.node in scheduled
                ),
                exits=plan.view.exits[node_id],
                actor=node_actor(impl, spec.config),
                path=(node_id,),
                key=node_id,
            )
        self.edge_state: dict[str, _EdgeState] = {
            e: "open" for state in self.nodes.values() for e in state.incoming
        }
        self.edge_values: dict[str, Any] = {}
        flow = settings.flow_settings or FlowSettings()
        self.max_node_runs = flow.max_node_runs
        self.node_run_count = 0
        # 안전 한도를 넘었으면 그 오류(Run failed). 취소 토큰으로 실행을 멈춘다.
        self.limit_error: ErrorInfo | None = None
        self._init_loops(plan, flow)
        self._init_calls(plan)
        self.ready: deque[str] = deque()
        self.running: dict[asyncio.Task[NodeResult | None], str] = {}
        self.policy = policy
        self.broker = InteractionBroker(
            self,
            journal=self.journal,
            recorder=settings.recorder,
            registries=settings.registries,
            token=self.token,
            clock=settings.clock,
            ids=settings.ids,
            sleep=settings.sleep,
            policy=policy,
            preview_chars=settings.preview_chars,
            conversation_id=conversation_id,
        )

    def _observe(self, event: RunEvent) -> None:
        if event.type == "run.reply":
            self.replies.append(RunReplyPayload.model_validate(event.payload))

    def _init_loops(self, plan: _Plan, flow: FlowSettings) -> None:
        """사이클 연결·반복 영역 상태를 만든다(design §5R.4).

        영역의 출발·도착 노드가 스케줄 대상인 사이클 연결만 반복으로 다룬다. 사이클 연결은 첫 회차의
        join 계산에서 빠지도록 처음에 dead다(지나갈 때 passed가 된다).
        """
        self.loops: dict[str, _Loop] = {}
        for edge_id, region in plan.regions.items():
            exit_state = self.nodes.get(region.exit)
            if region.entry not in self.nodes or exit_state is None:
                continue
            if edge_id not in exit_state.outgoing:
                continue
            limit = effective_max_iterations(
                self.edges[edge_id], plan.cycle_types[edge_id], flow.max_iterations
            )
            nodes = tuple(n for n in region.nodes if n in self.nodes)
            self.loops[edge_id] = _Loop(
                edge_id=edge_id,
                entry=region.entry,
                exit=region.exit,
                nodes=nodes,
                members=frozenset(nodes),
                limit=limit if limit is not None and limit >= 1 else None,
            )
        # 사이클 연결이 지금 회차에서 영역을 다시 열었던 횟수(바깥 영역이 다시 열리면 0으로).
        self.loop_count: dict[str, int] = dict.fromkeys(self.loops, 0)
        # 아직 다시 열릴 수 있는 반복(출발 노드가 이번 회차에서 연결을 아직 평가하지 않음).
        self.loop_live: set[str] = set(self.loops)
        # 영역이 조용해지기를 기다리는 다시 열기(사이클 연결 id → 넘길 값).
        self.deferred: dict[str, Any] = {}
        for edge_id in self.loops:
            self.edge_state[edge_id] = "dead"
        # 영역 밖으로 나가는 흐름 연결 → 그 연결을 붙잡는 반복(출발 노드는 영역 안, 도착은 밖).
        self.exit_loops: dict[str, tuple[str, ...]] = {}
        for state in self.nodes.values():
            for edge_id in state.outgoing:
                if edge_id in self.loops:
                    continue
                target = self.edges[edge_id].target.node
                holders = tuple(
                    lid
                    for lid, loop in self.loops.items()
                    if state.spec.id in loop.members and target not in loop.members
                )
                if holders:
                    self.exit_loops[edge_id] = holders
        # 영역이 다시 열릴 수 있어 dead를 미룬 연결(상태는 open으로 남는다).
        self.held: set[str] = set()
        # 도착 노드의 이전 회차 전에 지나가 남아 있는 값(`Incoming.carried`).
        self.carried: set[str] = set()
        # 다시 열기 전 회차들의 사용량과 처리되지 않은 실패(node_id, iteration, error).
        self.past_usage: list[Usage] = []
        self.past_failures: list[tuple[str, int, ErrorInfo | None]] = []

    def _init_calls(self, plan: _Plan) -> None:
        """호출 실행(`ctx.invoke_node`, design §5R.6) 상태를 만든다."""
        self.impls = plan.impls
        delegation = self.s.delegation_settings
        self.max_delegation_depth = delegation.max_depth if delegation is not None else None
        # 대상 노드 id → 직렬 잠금 / 다음 호출 회차 / 직전 호출의 백엔드 세션 id.
        self.call_locks: dict[str, asyncio.Lock] = {}
        self.call_count: dict[str, int] = {}
        self.call_sessions: dict[str, str] = {}
        # 진행 중인 호출 실행(대상 노드 id → 상태, 대기 키 → 상태). 같은 대상은 하나뿐이다.
        self.active_calls: dict[str, _NodeState] = {}
        self.call_states: dict[Hashable, _NodeState] = {}
        # 끝난 호출 실행의 사용량(Run totals에 더한다).
        self.call_usage: list[Usage] = []

    # ------------------------------------------------------------ 기록 도우미

    def _save_run(self) -> None:
        run = self.run
        runs = self.s.recorder.runs
        self.journal.save(runs.save, run)

    def _run_event(
        self,
        type: str,
        duration_ms: int | None = None,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = RunStatusPayload(
            status=self.run.status,
            error=self.run.error,
            totals=self.run.totals,
            duration_ms=duration_ms,
        ).model_dump(mode="json", by_alias=True)
        if context:
            # 열린 payload: 상태 필드는 덮어쓰지 않는다.
            payload = {**{k: v for k, v in context.items() if k not in payload}, **payload}
        self.journal.event(type, payload)

    def _start_warnings(self) -> None:
        for issue in self.start_warnings:
            self.journal.event(
                "log.warning",
                LogWarningPayload(
                    message=issue.message,
                    details={"code": issue.code, **(issue.details or {})},
                ),
            )

    def _node_record(
        self,
        state: _NodeState,
        status: NodeRunStatus,
        *,
        ended_at: float | None = None,
        error: ErrorInfo | None = None,
        wait: WaitInfo | None = None,
        event: str | None = None,
        waited_ms: int | None = None,
        reason: str | None = None,
    ) -> None:
        state.status = status
        result = state.result
        duration_ms = (
            round((ended_at - state.started_at) * 1000)
            if ended_at is not None and state.started_at is not None
            else None
        )
        outputs = dict(result.outputs) if result is not None and status != "cancelled" else {}
        usage = result.usage if result is not None else None
        invoked = state.invoked_by is not None
        record = NodeRun(
            run_id=self.run.id,
            node_id=state.spec.id,
            status=status,
            node_type=state.spec.type,
            iteration=state.iteration,
            call=state.call,
            invoked_by=list(state.invoked_by) if state.invoked_by is not None else None,
            inputs=dict(state.inputs),
            outputs=outputs,
            error=error,
            usage=usage,
            started_at=state.started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            backend_session_id=result.backend_session_id if result is not None else None,
        )
        runs = self.s.recorder.runs
        self.journal.save(runs.save_node_run, record)
        self.journal.event(
            event or _NODE_EVENT[status],
            NodeStatusPayload(
                status=status,
                node_type=state.spec.type,
                iteration=state.iteration,
                call=state.call if invoked else None,
                outputs_preview=preview(outputs, self.s.preview_chars) if outputs else None,
                usage=usage,
                duration_ms=duration_ms,
                error=error,
                wait=wait,
                waited_ms=waited_ms,
                reason=reason,
            ),
            node_path=_path(state),
            attempt=1,
            actor=state.actor,
        )

    # ------------------------------------------------------------ 상호작용 대기(WaitHost)

    def _waiter(self, key: Hashable) -> _NodeState | None:
        """대기 키의 실행 상태(스케줄 노드면 노드 id, 호출 실행이면 호출 키)."""
        if isinstance(key, str):
            return self.nodes.get(key)
        return self.call_states.get(key)

    def node_open(self, key: Hashable) -> bool:
        state = self._waiter(key)
        return state is not None and state.status in ("running", "waiting") and not state.finished

    def node_label(self, node_id: str) -> str:
        state = self.nodes.get(node_id)
        spec = (
            state.spec
            if state is not None
            else next((n for n in self.graph.nodes if n.id == node_id), None)
        )
        return (spec.label if spec is not None else None) or node_id

    def node_waiting(self, key: Hashable, wait: WaitInfo) -> None:
        state = self._waiter(key)
        if state is None:
            return
        self._release(state)
        state.live_wait = True
        self._node_record(state, "waiting", wait=wait)
        self._sync_run_status()

    async def node_resuming(self, key: Hashable, waited_ms: int) -> None:
        state = self._waiter(key)
        if state is None:
            return
        # 부르고 있는 대상·자식 Run이 있으면 슬롯은 그것이 끝날 때 다시 잡는다(`_reclaim`).
        semaphore = self.s.semaphore if not _delegating(state) else None
        if semaphore is not None:
            await semaphore.acquire()
        if state.finished or self.token.cancelled:
            if semaphore is not None:
                semaphore.release()
            return
        state.holding = semaphore is not None
        state.live_wait = False
        self._node_record(state, "running", event="node.resumed", waited_ms=waited_ms)
        self._sync_run_status()

    def _release(self, state: _NodeState) -> None:
        if state.holding and self.s.semaphore is not None:
            self.s.semaphore.release()
        state.holding = False

    def _sync_run_status(self) -> None:
        """Run running ⇄ waiting: 실행 중·대기열 노드가 없고 live wait 노드가 있으면 waiting.

        호출 실행도 센다. 부른 대상이 모두 기다리기만 하는 위임자는 실행 중으로 보지
        않는다(`_blocked`).
        """
        if self.token.cancelled or self.run.status not in ("running", "waiting"):
            return
        states = [*self.nodes.values(), *self.active_calls.values()]
        busy = bool(self.ready) or any(
            s.status in ("queued", "running") and not self._blocked(s) for s in states
        )
        # 자식 Run이 상호작용만 기다리는 노드도 대기로 센다(그 상호작용은 자식 Run에 있다).
        waiting = any(s.live_wait or (s.children and self._blocked(s)) for s in states)
        target: RunStatus = "waiting" if waiting and not busy else "running"
        if target == self.run.status:
            return
        self.run = self.run.model_copy(update={"status": target})
        self._save_run()
        self._run_event("run.waiting" if target == "waiting" else "run.resumed")
        if self.on_status is not None:
            self.on_status()  # 부모 Run이 이 자식을 기다리는 노드의 처지를 다시 본다

    def _blocked(self, state: _NodeState) -> bool:
        """실행이 상호작용만 기다리는지: live wait이거나, 부르는 대상·기다리는 자식 Run이 모두
        그런 상태다."""
        if state.live_wait:
            return True
        if state.status != "running" or not _delegating(state):
            return False
        return all(self._target_blocked(target) for target in state.inflight) and all(
            child.run.status == "waiting" for child in state.children
        )

    def _target_blocked(self, node_id: str) -> bool:
        # 차례를 기다리는 호출은 지금 그 대상을 실행 중인 호출과 같은 처지다(직렬).
        active = self.active_calls.get(node_id)
        return active is not None and self._blocked(active)

    def _opener(self, state: _NodeState) -> RequestOpener:
        """`NodeContext.request_input`의 연결 지점(실행 하나의 대기 키로 묶는다)."""

        async def open_request(ctx: NodeContext, req: InteractionRequest) -> InteractionOutcome:
            return await self.broker.request(
                ctx.node.id,
                req,
                node_path=ctx.node_path,
                actor=ctx.actor,
                attempt=ctx.attempt,
                key=state.key,
            )

        return open_request

    def _invoker(self, state: _NodeState) -> NodeInvoker:
        """`NodeContext.invoke_node`의 연결 지점(부르는 쪽 실행 상태를 묶는다)."""

        async def invoke(
            ctx: NodeContext,
            node_id: str,
            inputs: Mapping[str, Any],
            *,
            by_edge: str,
            max_depth: int | None,
        ) -> NodeRunView:
            return await self._invoke(state, node_id, inputs, by_edge=by_edge, max_depth=max_depth)

        return invoke

    def _child_runner(self, state: _NodeState) -> ChildRunner:
        """`NodeContext.run_child`의 연결 지점(부르는 쪽 실행 상태를 묶는다)."""

        async def run_child(
            ctx: NodeContext,
            graph: Graph,
            input: Mapping[str, Any] | None,
            *,
            graph_version: str | None,
            services: Mapping[ServiceKey[Any], Any] | None,
        ) -> ChildRunResult:
            return await self._run_child(
                state, graph, input, graph_version=graph_version, services=services
            )

        return run_child

    def _context(self, state: _NodeState) -> NodeContext:
        return NodeContext(
            run=self.run,
            graph=self.graph,
            node=state.spec,
            attempt=1,
            iteration=state.iteration,
            registries=self.s.registries,
            services=self.services,
            secrets=self.s.secrets,
            cancel=self.token,
            clock=self.s.clock,
            journal=self.journal,
            actor=state.actor,
            interaction_grant=self.policy.grants.get(state.spec.id),
            open_request=self._opener(state),
            incoming=state.received,
            previous_session_id=state.previous_session_id,
            node_path=_path(state),
            call=state.call,
            invoked_by=state.invoked_by,
            invoke=self._invoker(state),
            run_child=self._child_runner(state),
        )

    # ------------------------------------------------------------ 실행

    async def announce(self) -> None:
        """Run을 queued로 저장하고 `run.created`를 낸다(저장 완료까지 기다린다)."""
        self._save_run()
        self._run_event("run.created")
        await self.journal.flush()

    async def execute(self) -> Run:
        try:
            try:
                await self._main()
            except asyncio.CancelledError:
                # 바깥 태스크 취소(종료 등): 정리 후 다시 던진다.
                self.token.cancel("shutdown")
                await self._close_requests()
                await self._cancel_running(grace=0)
                await self._finalize()
                raise
            except Exception as exc:
                _log.exception("Run %s 실행 중 엔진 오류", self.run.id)
                self.token.cancel("internal")
                await self.broker.close_all()
                await self._cancel_running(grace=0)
                await self._finalize(
                    internal=ErrorInfo(
                        code=RuntimeErrorCodes.INTERNAL, message=f"{type(exc).__name__}: {exc}"
                    )
                )
        finally:
            await self.journal.close()
        return self.run

    async def _main(self) -> None:
        self.run = self.run.model_copy(update={"status": "running", "started_at": self.s.clock()})
        self._save_run()
        self._run_event("run.started", context=self.run_context)
        self._start_warnings()
        if self.seed is None:
            self._open_entries()
        else:
            self._open_seed(self.seed)
        self._evaluate(list(self.nodes))

        cancel_wait = asyncio.ensure_future(self.token.wait())
        try:
            while not self.token.cancelled:
                while self.ready:
                    node_id = self.ready.popleft()
                    task = asyncio.create_task(self._run_node(node_id), name=f"node:{node_id}")
                    self.running[task] = node_id
                if not self.running:
                    if self._unstall():
                        continue
                    break
                done, _ = await asyncio.wait(
                    {*self.running, cancel_wait}, return_when=asyncio.FIRST_COMPLETED
                )
                finished = sorted(
                    (t for t in done if t is not cancel_wait),
                    key=lambda t: self.order[self.running[t]],
                )
                if self._cancel_requested():
                    break
                for task in finished:
                    node_id = self.running.pop(task)
                    result = task.result()
                    if result is not None:
                        self._complete(node_id, result)
                self._run_deferred()
                self._sync_run_status()
        finally:
            cancel_wait.cancel()
        if self.token.cancelled:
            # 열린 요청을 먼저 닫아 기다리던 노드가 취소 결과를 받고 스스로 정리할 수 있게 한다.
            await self._close_requests()
            await self._cancel_running(grace=self.s.cancel_grace)
        await self._finalize()

    def _open_entries(self) -> None:
        """입구 엣지를 평가해 Run 입력을 넣고, 스케줄되지 않는 노드에서 오는 흐름 엣지는 죽인다.

        입구 엣지의 소스는 `{소스 포트: Run 입력}`을 출력으로 가진 성공 결과로 보인다.
        """
        for state in self.nodes.values():
            for edge_id in state.incoming:
                edge = self.edges[edge_id]
                source = edge.source
                if self.view.scheduling[edge_id] == "entry":
                    view = NodeRunView(
                        node_id=source.node,
                        node_type=self.specs[source.node].type,
                        status="succeeded",
                        outputs=MappingProxyType({source.port: dict(self.run.input)}),
                    )
                    activation = activate_edge(
                        self.journal, self.s.registries, edge, view, node_path=[], attempt=None
                    )
                    if activation is None:
                        self.edge_state[edge_id] = "dead"
                    else:
                        self.edge_state[edge_id] = "passed"
                        self.edge_values[edge_id] = activation.value
                elif source.node not in self.nodes:
                    self.edge_state[edge_id] = "dead"

    def _open_seed(self, seed: Mapping[str, dict[str, Any]]) -> None:
        """이어 가기 시작: 입구 주입 없이 seed 노드를 저장된 입력으로 활성화한다(§2R.10).

        seed 노드의 상류(흐름 엣지를 거슬러 닿는 스케줄 노드, seed 자신 제외)는 실행하지 않고
        `skipped`(reason `resumed`)로 남긴다. 입구 엣지와 상류에서 나가는 엣지는 죽인다. 나머지
        노드는 평소 규칙(join·dead-path)을 따른다.
        """
        upstream: set[str] = set()
        work = deque(seed)
        while work:
            for edge_id in self.nodes[work.popleft()].incoming:
                if edge_id in self.loops:  # 되돌아오는 연결은 상류가 아니다
                    continue
                source = self.edges[edge_id].source.node
                if source in self.nodes and source not in seed and source not in upstream:
                    upstream.add(source)
                    work.append(source)
        for state in self.nodes.values():
            for edge_id in state.incoming:
                source = self.edges[edge_id].source.node
                if (
                    self.view.scheduling[edge_id] == "entry"
                    or source not in self.nodes
                    or source in upstream
                ):
                    self.edge_state[edge_id] = "dead"
        now = self.s.clock()
        for state in self._in_order():
            if state.spec.id in upstream:
                self._node_record(state, "skipped", ended_at=now, reason=SkipReasons.RESUMED)
        for state in self._in_order():
            if state.spec.id in seed:
                self._activate(state.spec.id, dict(seed[state.spec.id]))

    def _activate(
        self, node_id: str, inputs: dict[str, Any], received: tuple[Incoming, ...] = ()
    ) -> None:
        if not self._take_node_run():
            return
        state = self.nodes[node_id]
        state.inputs = inputs
        state.received = received
        self._node_record(state, "queued")
        self.ready.append(node_id)

    def _take_node_run(self) -> bool:
        """노드 실행 하나를 센다. `flow.max_node_runs`를 넘으면 Run을 실패로 멈추고 False.

        반복·호출을 포함한 이 Run의 모든 노드 실행이 대상이다(design §5R.4 5).
        """
        if self.limit_error is not None:
            return False
        limit = self.max_node_runs
        if limit is not None and self.node_run_count >= limit:
            self.limit_error = ErrorInfo(
                code=RuntimeErrorCodes.MAX_NODE_RUNS_EXCEEDED,
                message=f"노드 실행 수가 한도({limit})를 넘어 실행을 멈췄습니다",
                details={"limit": limit},
            )
            self.token.cancel(RuntimeErrorCodes.MAX_NODE_RUNS_EXCEEDED)
            return False
        self.node_run_count += 1
        return True

    def _cancel_requested(self) -> bool:
        # 메서드로 감싸 await 뒤 재확인이 타입 좁히기에 막히지 않게 한다.
        return self.token.cancelled

    async def _run_node(self, node_id: str) -> NodeResult | None:
        """노드 하나를 실행한다. 슬롯은 직접 잡고 놓는다(live wait 동안 반납·재획득, §R14.5)."""
        state = self.nodes[node_id]
        semaphore = self.s.semaphore
        if semaphore is not None:
            await semaphore.acquire()
            state.holding = True
        try:
            if self.token.cancelled:
                return None
            state.started_at = self.s.clock()
            self._node_record(state, "running")
            ctx = self._context(state)
            result: object
            try:
                returned: object = await state.impl.execute(
                    ctx, MappingProxyType(dict(state.inputs))
                )
                result = returned
            except Exception as exc:
                result = NodeResult(
                    status="failed",
                    error=ErrorInfo(
                        code=RuntimeErrorCodes.NODE_EXCEPTION,
                        message=self.s.secrets.redact(f"{type(exc).__name__}: {exc}"),
                    ),
                )
            # 대기 중에 끝났으면 남은 요청을 node_finished로 닫는다(이후 슬롯을 다시 잡지 않음).
            state.finished = True
            self._release(state)
            await self.broker.close_node(state.key)
            state.live_wait = False
            if not isinstance(result, NodeResult):
                return NodeResult(
                    status="failed",
                    error=ErrorInfo(
                        code=RuntimeErrorCodes.INVALID_RESULT,
                        message=f"노드가 NodeResult 대신 {type(result).__name__}를 돌려줬습니다",
                    ),
                )
            return result
        finally:
            state.finished = True
            self._release(state)

    def _complete(self, node_id: str, result: NodeResult) -> None:
        state = self.nodes[node_id]
        state.result = result
        error = result.error
        if result.status == "failed" and error is None:
            error = ErrorInfo(code=RuntimeErrorCodes.NODE_FAILED, message="노드 실패")
        self._node_record(
            state,
            result.status,
            ended_at=None if result.status == "waiting" else self.s.clock(),
            error=error,
            wait=result.wait,
        )
        if result.status in ("succeeded", "failed"):
            view = NodeRunView(
                node_id=node_id,
                node_type=state.spec.type,
                status=result.status,
                outputs=MappingProxyType(dict(result.outputs)),
                error=error,
                iteration=state.iteration,
                structured=result.structured,
            )
            emit_replies(
                self.journal,
                self.s.registries,
                [self.edges[e] for e in state.exits],
                view,
                node_path=[node_id],
                attempt=1,
                actor=state.actor,
            )
            self._propagate(state, view)
        elif result.status == "skipped":
            self._kill_outgoing(state)

    def _propagate(self, state: _NodeState, view: NodeRunView) -> None:
        targets: list[str] = []
        reopen: list[tuple[str, Any]] = []
        ended: list[str] = []
        for edge_id in state.outgoing:
            edge = self.edges[edge_id]
            activation = activate_edge(
                self.journal,
                self.s.registries,
                edge,
                view,
                node_path=[state.spec.id],
                attempt=1,
            )
            loop = self.loops.get(edge_id)
            if loop is not None:
                if activation is not None and self._may_reopen(loop):
                    if view.status == "failed":
                        state.handled = True
                    self._traversed(edge, activation.value, activation.condition)
                    reopen.append((edge_id, activation.value))
                else:
                    if activation is not None:
                        self._exhausted(loop)
                    ended.append(edge_id)
                continue
            if activation is None:
                if self._settle_dead(edge_id):
                    targets.append(edge.target.node)
                continue
            self.edge_state[edge_id] = "passed"
            self.edge_values[edge_id] = activation.value
            self.held.discard(edge_id)
            self.carried.discard(edge_id)
            if view.status == "failed":
                state.handled = True
            self._traversed(edge, activation.value, activation.condition)
            targets.append(edge.target.node)
        self._evaluate(targets)
        # 반복을 닫는 것은 다른 나가는 연결을 다 평가한 뒤다(이번 회차에 지나간 연결을 놓지 않게).
        for edge_id in ended:
            self._end_loop(edge_id)
        for edge_id, value in reopen:
            self.deferred[edge_id] = value
        if reopen:
            self._run_deferred()

    def _traversed(
        self, edge: EdgeSpec, value: Any, condition: ConditionOutcome | None = None
    ) -> None:
        self.journal.event(
            "edge.traversed",
            EdgeTraversedPayload(
                edge_id=edge.id,
                source=edge.source,
                target=edge.target,
                value_preview=preview(value, self.s.preview_chars),
                kind=edge.kind,
                condition=condition,
            ),
        )

    def _settle_dead(self, edge_id: str) -> bool:
        """지나가지 않은 흐름 연결을 정리한다. 도착 노드를 다시 평가해야 하면 참.

        - 이전 회차에 이미 지나간 연결(영역 밖으로 나가는 연결)은 되돌리지 않는다.
        - 출발 노드의 반복 영역이 아직 다시 열릴 수 있으면 dead를 미룬다(다음 회차에 지날 수 있다).
        """
        if self.edge_state.get(edge_id) == "passed":
            return False
        if any(lid in self.loop_live for lid in self.exit_loops.get(edge_id, ())):
            self.held.add(edge_id)
            return False
        self.edge_state[edge_id] = "dead"
        return True

    def _dead_outgoing(self, state: _NodeState) -> list[str]:
        """노드가 skipped일 때 나가는 연결을 모두 막는다. 다시 평가할 도착 노드를 돌려준다."""
        targets: list[str] = []
        for edge_id in state.outgoing:
            if edge_id not in self.loops and self._settle_dead(edge_id):
                targets.append(self.edges[edge_id].target.node)
        for edge_id in state.outgoing:
            if edge_id in self.loops:
                self._end_loop(edge_id)
        return targets

    def _kill_outgoing(self, state: _NodeState) -> None:
        self._evaluate(self._dead_outgoing(state))

    def _evaluate(self, node_ids: list[str]) -> None:
        """대기 중인 노드의 join을 평가해 활성화하거나 dead-path로 skipped 처리한다."""
        work = deque(node_ids)
        while work:
            state = self.nodes.get(work.popleft())
            if state is None or state.status != "pending":
                continue
            passed = [e for e in state.incoming if self.edge_state[e] == "passed"]
            still_open = any(self.edge_state[e] == "open" for e in state.incoming)
            if passed and (state.join == "any" or not still_open):
                inputs: dict[str, Any] = {}
                # 포트마다 첫 값: 이번 회차에 도착한 값이 남아 있던 값보다 먼저다(안정 정렬).
                for edge_id in sorted(passed, key=lambda e: e in self.carried):
                    inputs.setdefault(self.edges[edge_id].target.port, self.edge_values[edge_id])
                received = tuple(
                    Incoming(
                        port=edge.target.port,
                        edge_id=edge.id,
                        source_node=edge.source.node,
                        source_port=edge.source.port,
                        value=self.edge_values[edge.id],
                        carried=edge.id in self.carried,
                    )
                    for edge in (self.edges[e] for e in passed)
                )
                self._activate(state.spec.id, inputs, received)
            elif not passed and not still_open:
                self._node_record(state, "skipped", ended_at=self.s.clock())
                work.extend(self._dead_outgoing(state))

    # ------------------------------------------------------------ 반복(design §5R.4)

    def _may_reopen(self, loop: _Loop) -> bool:
        return loop.limit is not None and self.loop_count[loop.edge_id] < loop.limit

    def _exhausted(self, loop: _Loop) -> None:
        self.journal.event(
            "loop.exhausted",
            LoopExhaustedPayload(
                edge_id=loop.edge_id,
                iteration=self.loop_count[loop.edge_id],
                max_iterations=loop.limit,
            ),
        )

    def _end_loop(self, edge_id: str) -> None:
        """사이클 연결이 이번 회차에서 다시 열지 않는다: 연결을 막고 붙잡아 둔 연결을 놓는다."""
        self.edge_state[edge_id] = "dead"
        self.loop_live.discard(edge_id)
        self.deferred.pop(edge_id, None)
        released = [
            e
            for e in self.held
            if not any(lid in self.loop_live for lid in self.exit_loops.get(e, ()))
        ]
        targets: list[str] = []
        for held in sorted(released, key=self._edge_rank):
            self.held.discard(held)
            self.edge_state[held] = "dead"
            targets.append(self.edges[held].target.node)
        if targets:
            self._evaluate(targets)

    def _edge_rank(self, edge_id: str) -> int:
        return self.edge_order[edge_id]

    def _quiet(self, node_id: str) -> bool:
        """노드가 대기열·실행 중·live wait가 아니면 참(parked wait는 끝난 것으로 본다)."""
        state = self.nodes[node_id]
        return (
            state.status not in ("queued", "running")
            and not state.live_wait
            and node_id not in self.ready
        )

    def _run_deferred(self) -> None:
        """미뤄 둔 다시 열기 중 영역이 조용해진 것을 연다(사이클 연결 순서)."""
        for edge_id in [e for e in self.loops if e in self.deferred]:
            if self.limit_error is not None or self.token.cancelled:
                return
            loop = self.loops[edge_id]
            if edge_id not in self.deferred or not all(self._quiet(n) for n in loop.nodes):
                continue
            self._reopen(loop, self.deferred.pop(edge_id))

    def _reopen(self, loop: _Loop, value: Any) -> None:
        """반복 영역을 새 회차로 다시 연다(design §5R.4 2).

        영역 노드는 새 NodeRun(회차 + 1)으로 pending, 영역 안 흐름 연결은 open, 안쪽 사이클 연결은
        dead + 횟수 0, 도착 노드에는 사이클 연결 값이 들어간다. 영역 밖에서 들어와 지나간 값은
        남긴다(`carried`).
        """
        lid = loop.edge_id
        count = self.loop_count[lid] + 1
        self.loop_count[lid] = count
        for other in self.loops.values():
            if other.edge_id != lid and {other.entry, other.exit} <= loop.members:
                self.loop_count[other.edge_id] = 0
                self.loop_live.add(other.edge_id)
                self.deferred.pop(other.edge_id, None)
        for node_id in loop.nodes:
            self._reset_node(self.nodes[node_id])
        for node_id in loop.nodes:
            for edge_id in self.nodes[node_id].incoming:
                source = self.edges[edge_id].source.node
                if edge_id == lid:
                    self.edge_state[edge_id] = "passed"
                    self.edge_values[edge_id] = value
                    self.carried.discard(edge_id)
                elif source in loop.members:
                    self.held.discard(edge_id)
                    self.carried.discard(edge_id)
                    self.edge_values.pop(edge_id, None)
                    self.edge_state[edge_id] = "dead" if edge_id in self.loops else "open"
                elif self.edge_state.get(edge_id) == "passed":
                    self.carried.add(edge_id)
        # 회차 = 도착 노드의 새 NodeRun 회차(화면 "n회차 시작" 링크, screen-delegation D1).
        # 도착 노드가 아직 실행된 적 없으면(영역 밖 입력으로 출발 노드만 돈 경우) 이 연결이 연 횟수.
        opened = self.nodes[loop.entry].iteration or count
        self.journal.event(
            "loop.iteration",
            LoopIterationPayload(edge_id=lid, iteration=opened, nodes=list(loop.nodes)),
        )
        self._evaluate(list(loop.nodes))

    def _reset_node(self, state: _NodeState) -> None:
        """노드를 다음 회차의 pending으로 되돌린다. 이번 회차 기록이 있으면 회차를 올린다."""
        if state.status != "pending":
            result = state.result
            if result is not None:
                if result.usage is not None:
                    self.past_usage.append(result.usage)
                if result.backend_session_id:
                    state.previous_session_id = result.backend_session_id
            if state.status == "failed" and not state.handled:
                error = result.error if result is not None else None
                self.past_failures.append((state.spec.id, state.iteration, error))
            state.iteration += 1
        state.status = "pending"
        state.inputs = {}
        state.received = ()
        state.started_at = None
        state.result = None
        state.handled = False
        state.finished = False
        state.live_wait = False

    def _unstall(self) -> bool:
        """실행할 노드가 없을 때 남은 반복을 정리한다. 새로 준비된 노드가 생기면 참.

        미뤄 둔 다시 열기를 먼저 열고, 그래도 없으면 다시 열릴 수 없는 반복을 모두 닫아 붙잡아 둔
        연결을 놓는다(join `all` 노드가 그 결과로 준비될 수 있다).
        """
        if self.token.cancelled:
            return False
        self._run_deferred()
        if not self.ready:
            for edge_id in [e for e in self.loops if e in self.loop_live]:
                self._end_loop(edge_id)
        return bool(self.ready)

    # ------------------------------------------------------------ 호출(design §5R.6)

    async def _invoke(
        self,
        caller: _NodeState,
        node_id: str,
        inputs: Mapping[str, Any],
        *,
        by_edge: str,
        max_depth: int | None,
    ) -> NodeRunView:
        """`ctx.invoke_node`: 대상을 자기 NodeRun으로 실행한다(같은 대상은 직렬)."""
        spec, impl = self._invocation_target(caller, node_id, by_edge)
        path = (*_path(caller), node_id)
        refused = self._refuse_call(caller, spec, path, max_depth)
        if refused is not None:
            return refused
        # 기다리는 동안 슬롯을 내놓는다(대상이 슬롯을 얻어야 하므로, max_concurrency=1에서도).
        caller.inflight.append(node_id)
        self._release(caller)
        self._sync_run_status()
        try:
            lock = self.call_locks.setdefault(node_id, asyncio.Lock())
            async with lock:
                return await self._run_call(caller, spec, impl, path, by_edge, inputs)
        finally:
            caller.inflight.remove(node_id)
            self._sync_run_status()
            await self._reclaim(caller)

    def _invocation_target(
        self, caller: _NodeState, node_id: str, by_edge: str
    ) -> tuple[NodeSpec, NodeType]:
        """`by_edge`가 부르는 쪽에서 `node_id`로 가는 `invocation` 연결인지 확인한다.

        Raises:
            ValueError: 그런 연결이 아니거나 대상을 실행할 수 없다.
        """
        edge = self.edges.get(by_edge)
        if edge is None or edge.source.node != caller.spec.id or edge.target.node != node_id:
            raise ValueError(
                f"연결 {by_edge!r}는 노드 {caller.spec.id!r}에서 {node_id!r}로 가는 연결이 아닙니다"
            )
        descriptor: EdgeTypeDescriptor | None
        try:
            descriptor = self.s.registries.edge_types.get(edge.kind).descriptor
        except Exception:
            descriptor = None
        if descriptor is None or descriptor.invocation is None:
            raise ValueError(f"연결 {by_edge!r}는 호출(invocation) 연결이 아닙니다")
        spec = self.specs.get(node_id)
        impl = self.impls.get(node_id)
        if spec is None or impl is None or node_id not in self.view.executable:
            raise ValueError(f"노드 {node_id!r}는 실행할 수 있는 노드가 아닙니다")
        return spec, impl

    def _node_name(self, node_id: str) -> str:
        """사용자 문구의 노드 이름(`node_display_name`: label → 노드 타입 훅 → 타입 title)."""
        spec = self.specs.get(node_id)
        if spec is None:
            return "알 수 없는 노드"
        return node_display_name(spec, self.impls.get(node_id), self.services)

    def _failure_summary(self, node_id: str, cause: ErrorInfo | None) -> ErrorInfo:
        """Run 실패 요약: 노드를 이름으로 부르고(id는 `details`) 원인의 해결 버튼을 잇는다."""
        name = self._node_name(node_id)
        if cause is None:
            message = f"'{name}' 노드가 실패했습니다"
        elif f"'{name}'" in cause.message:
            message = cause.message  # 원인 문구가 이미 노드를 이름으로 부른다
        else:
            message = f"'{name}' 실패: {cause.message}"
        error = ErrorInfo(
            code=RuntimeErrorCodes.NODE_FAILED,
            message=message,
            details={
                "node_id": node_id,
                "node_name": name,
                "error": cause.model_dump(mode="json") if cause is not None else None,
            },
        )
        if cause is not None and cause.fix is not None:
            error = error.model_copy(update={"fix": cause.fix})
        return error

    def _refuse_call(
        self,
        caller: _NodeState,
        spec: NodeSpec,
        path: tuple[str, ...],
        max_depth: int | None,
    ) -> NodeRunView | None:
        """깊이 한도·위임 순환이면 실행하지 않고 실패 결과(+ `log.warning`)를 돌려준다."""
        depth = len(path) - 1
        limits = [v for v in (max_depth, self.max_delegation_depth) if v is not None]
        limit = min(limits) if limits else None
        error: ErrorInfo | None = None
        if spec.id in path[:-1]:
            error = ErrorInfo(
                code=RuntimeErrorCodes.DELEGATION_CYCLE,
                message=(
                    f"'{self._node_name(spec.id)}'은(는) 이미 위임 경로에 있어 "
                    "다시 부를 수 없습니다"
                ),
                details={"path": list(path), "node_id": spec.id},
            )
        elif limit is not None and depth > limit:
            error = ErrorInfo(
                code=RuntimeErrorCodes.DELEGATION_DEPTH_EXCEEDED,
                message=(
                    f"위임 깊이 {depth}가 한도({limit})를 넘어 "
                    f"'{self._node_name(spec.id)}'을(를) 부르지 않았습니다"
                ),
                details={"depth": depth, "max_depth": limit, "node_id": spec.id},
            )
        if error is None:
            return None
        self.journal.event(
            "log.warning",
            LogWarningPayload(
                message=error.message, details={"code": error.code, **(error.details or {})}
            ),
            node_path=list(path),
            attempt=1,
            actor=caller.actor,
        )
        return NodeRunView(
            node_id=spec.id,
            node_type=spec.type,
            status="failed",
            error=error,
            iteration=caller.iteration,
        )

    async def _reclaim(self, caller: _NodeState) -> None:
        """부르던 대상·자식 Run이 모두 끝나면 부른 쪽 슬롯을 다시 잡는다.

        live wait 중이면 재개(`node_resuming`)가 잡는다.
        """
        semaphore = self.s.semaphore
        if (
            semaphore is None
            or _delegating(caller)
            or caller.live_wait
            or caller.finished
            or caller.holding
            or self.token.cancelled
        ):
            return
        await semaphore.acquire()
        if _delegating(caller) or caller.live_wait or caller.finished or caller.holding:
            semaphore.release()
            return
        caller.holding = True

    async def _run_call(
        self,
        caller: _NodeState,
        spec: NodeSpec,
        impl: NodeType,
        path: tuple[str, ...],
        by_edge: str,
        inputs: Mapping[str, Any],
    ) -> NodeRunView:
        """차례가 온 호출 하나: NodeRun을 만들고 실행한다(직렬 잠금 안)."""
        node_id = spec.id
        if self.token.cancelled or not self._take_node_run():
            return NodeRunView(
                node_id=node_id,
                node_type=spec.type,
                status="cancelled",
                error=self._stop_error(),
                iteration=caller.iteration,
            )
        # 스케줄되기도 하는 노드면 스케줄 실행이 call 0을 쓰므로 1부터 센다(NodeRun 키 충돌 방지).
        call = self.call_count.get(node_id, 1 if node_id in self.nodes else 0)
        self.call_count[node_id] = call + 1
        key: Hashable = ("call", node_id, call)
        edge = self.edges[by_edge]
        state = _NodeState(
            spec=spec,
            impl=impl,
            join=spec.join or impl.descriptor.join,
            incoming=(),
            outgoing=(),
            exits=self.view.exits.get(node_id, ()),
            actor=node_actor(impl, spec.config),
            iteration=caller.iteration,
            previous_session_id=self.call_sessions.get(node_id),
            path=path,
            key=key,
            call=call,
            invoked_by=_path_tuple(caller),
        )
        state.inputs = dict(inputs)
        state.received = tuple(
            Incoming(
                port=port,
                edge_id=by_edge,
                source_node=caller.spec.id,
                source_port=edge.source.port,
                value=value,
            )
            for port, value in inputs.items()
        )
        self.call_states[key] = state
        self.active_calls[node_id] = state
        try:
            self._node_record(state, "queued")
            return await self._execute_call(state)
        finally:
            self.call_states.pop(key, None)
            self.active_calls.pop(node_id, None)

    async def _execute_call(self, state: _NodeState) -> NodeRunView:
        semaphore = self.s.semaphore
        try:
            if semaphore is not None:
                await semaphore.acquire()
                state.holding = True
            if self.token.cancelled:
                return self._cancel_call(state)
            state.started_at = self.s.clock()
            self._node_record(state, "running")
            self._sync_run_status()
            result: object
            try:
                returned: object = await state.impl.execute(
                    self._context(state), MappingProxyType(dict(state.inputs))
                )
                result = returned  # 노드는 타입을 어길 수 있다(사용자 플러그인)
            except Exception as exc:
                result = NodeResult(
                    status="failed",
                    error=ErrorInfo(
                        code=RuntimeErrorCodes.NODE_EXCEPTION,
                        message=self.s.secrets.redact(f"{type(exc).__name__}: {exc}"),
                    ),
                )
            state.finished = True
            self._release(state)
            await self.broker.close_node(state.key)
            state.live_wait = False
            if self._cancel_requested():
                return self._cancel_call(state)
            if not isinstance(result, NodeResult):
                result = NodeResult(
                    status="failed",
                    error=ErrorInfo(
                        code=RuntimeErrorCodes.INVALID_RESULT,
                        message=f"노드가 NodeResult 대신 {type(result).__name__}를 돌려줬습니다",
                    ),
                )
            return self._finish_call(state, result)
        except asyncio.CancelledError:
            self._cancel_call(state)
            raise
        finally:
            state.finished = True
            self._release(state)

    def _cancel_call(self, state: _NodeState) -> NodeRunView:
        """호출 실행을 취소로 기록한다(한 번만)."""
        error = self._stop_error()
        if not state.closed:
            state.closed = True
            state.live_wait = False
            self._node_record(state, "cancelled", ended_at=self.s.clock(), error=error)
        return NodeRunView(
            node_id=state.spec.id,
            node_type=state.spec.type,
            status="cancelled",
            error=error,
            iteration=state.iteration,
            call=state.call,
        )

    def _finish_call(self, state: _NodeState, result: NodeResult) -> NodeRunView:
        """호출 실행 결과를 기록하고 답변 연결을 평가한다. 실패는 Run 실패로 세지 않는다."""
        state.closed = True
        state.result = result
        error = result.error
        if result.status == "failed" and error is None:
            error = ErrorInfo(code=RuntimeErrorCodes.NODE_FAILED, message="노드 실패")
        self._node_record(
            state,
            result.status,
            ended_at=None if result.status == "waiting" else self.s.clock(),
            error=error,
            wait=result.wait,
        )
        if result.usage is not None:
            self.call_usage.append(result.usage)
        if result.backend_session_id:
            self.call_sessions[state.spec.id] = result.backend_session_id
        view = NodeRunView(
            node_id=state.spec.id,
            node_type=state.spec.type,
            status=result.status,
            outputs=MappingProxyType(dict(result.outputs)),
            error=error,
            iteration=state.iteration,
            structured=result.structured,
            call=state.call,
        )
        if result.status in ("succeeded", "failed"):
            emit_replies(
                self.journal,
                self.s.registries,
                [self.edges[e] for e in state.exits],
                view,
                node_path=_path(state),
                attempt=1,
                actor=state.actor,
            )
        return view

    # ------------------------------------------------------------ 자식 Run(design §5R.7)

    async def _run_child(
        self,
        caller: _NodeState,
        graph: Graph,
        input: Mapping[str, Any] | None,
        *,
        graph_version: str | None,
        services: Mapping[ServiceKey[Any], Any] | None,
    ) -> ChildRunResult:
        """`ctx.run_child`: 자식 Run을 만들어 끝날 때까지 기다린다."""
        if self.spawner is None:
            raise RuntimeError("이 실행은 자식 Run을 만들 수 없습니다(런타임 없이 만든 실행)")
        if graph_version is not None and graph_hash(graph) != graph_version:
            raise ValueError(
                f"그래프 {graph.id!r}의 버전이 {graph_version!r}가 아닙니다"
                f"(해시 {graph_hash(graph)!r})"
            )
        frozen = graph.model_copy(deep=True)
        if self.token.cancelled:
            return ChildRunResult(run_id=None, status="cancelled", error=self._stop_error())
        refused = self._refuse_child(caller, frozen)
        if refused is not None:
            return refused
        base = self.services
        for key, value in (services or {}).items():
            base = base.with_(key, value)
        request = ChildRunRequest(
            graph=frozen,
            input=dict(input or {}),
            parent=self.run,
            node_id=caller.spec.id,
            node_path=_path_tuple(caller),
            ancestors=(*self.ancestors, self.run),
            services=base,
        )
        try:
            child, task = await self.spawner.spawn_child(self, request)
        except GraphValidationError as exc:
            return self._child_refused(
                caller,
                ErrorInfo(
                    code=RuntimeErrorCodes.CHILD_INVALID,
                    message=f"자식 팀 구성 {frozen.id!r}을 실행할 수 없습니다",
                    details={"issues": [i.model_dump(mode="json") for i in exc.issues]},
                ),
            )
        entry = _Child(execution=child, task=task, caller=caller)
        self.children[child.run.id] = entry
        caller.children.append(child)
        child.on_status = self._sync_run_status
        # 기다리는 동안 슬롯을 내놓는다(자식 노드가 같은 세마포어를 쓰므로,
        # max_concurrency=1에서도 교착이 없게).
        self._release(caller)
        self.journal.event(
            "run.child_started",
            RunChildStartedPayload(
                child_run_id=child.run.id, node_id=caller.spec.id, graph_id=frozen.id
            ),
            node_path=_path(caller),
            attempt=1,
            actor=caller.actor,
        )
        self._sync_run_status()
        try:
            stop = asyncio.ensure_future(self.token.wait())
            try:
                await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                stop.cancel()
            if not task.done():
                self._stop_child(entry)
                await asyncio.wait({task})
            return self._child_finished(entry)
        except asyncio.CancelledError:
            self._stop_child(entry)  # 정리는 `_cancel_running`이 기다려 마친다
            raise
        finally:
            caller.children.remove(child)
            child.on_status = None
            self._sync_run_status()
            await self._reclaim(caller)

    def _refuse_child(self, caller: _NodeState, graph: Graph) -> ChildRunResult | None:
        """중첩 깊이 한도·그래프 순환이면 자식 Run을 만들지 않고 실패 결과를 돌려준다."""
        lineage = (*self.ancestors, self.run)
        graph_ids = [r.graph_id for r in lineage]
        depth = len(lineage)
        settings = self.s.delegation_settings or DelegationSettings()
        limit = settings.max_nesting
        if graph.id in graph_ids:
            return self._child_refused(
                caller,
                ErrorInfo(
                    code=RuntimeErrorCodes.CHILD_RECURSIVE,
                    message=f"팀 구성 {graph.id!r}이 이미 실행 경로에 있어 다시 넣을 수 없습니다",
                    details={"path": [*graph_ids, graph.id]},
                ),
            )
        if limit is not None and depth > limit:
            return self._child_refused(
                caller,
                ErrorInfo(
                    code=RuntimeErrorCodes.CHILD_NESTING_EXCEEDED,
                    message=(
                        f"팀 중첩 깊이 {depth}가 한도({limit})를 넘어 "
                        f"{graph.id!r}을 실행하지 않았습니다"
                    ),
                    details={"depth": depth, "limit": limit},
                ),
            )
        return None

    def _child_refused(self, caller: _NodeState, error: ErrorInfo) -> ChildRunResult:
        self.journal.event(
            "log.warning",
            LogWarningPayload(
                message=error.message, details={"code": error.code, **(error.details or {})}
            ),
            node_path=_path(caller),
            attempt=1,
            actor=caller.actor,
        )
        return ChildRunResult(run_id=None, status="failed", error=error)

    def _stop_child(self, entry: _Child) -> None:
        """부모가 취소·끊기면 자식도 같은 방식으로 멈춘다."""
        if self.interrupted is not None:
            entry.execution.interrupt(self.interrupted)
        else:
            entry.execution.token.cancel(self.token.reason or "cancelled")

    def _child_finished(self, entry: _Child) -> ChildRunResult:
        """끝난 자식 Run의 결과를 만들고 `run.child_finished`를 낸다(한 번만)."""
        child = entry.execution
        run = child.run
        status: RunStatus = run.status
        error = run.error
        task = entry.task
        failure = None if task.cancelled() else task.exception()
        if failure is not None or status in ("queued", "running"):
            # 기록 실패 등으로 마지막 상태를 남기지 못했다.
            status = "failed"
            error = ErrorInfo(
                code=RuntimeErrorCodes.INTERNAL,
                message=self.s.secrets.redact(
                    f"{type(failure).__name__}: {failure}"
                    if failure is not None
                    else "자식 Run이 끝나지 않았습니다"
                ),
            )
        if not entry.reported:
            entry.reported = True
            self.children.pop(run.id, None)
            self.journal.event(
                "run.child_finished",
                RunChildFinishedPayload(
                    child_run_id=run.id, node_id=entry.caller.spec.id, status=status
                ),
                node_path=_path(entry.caller),
                attempt=1,
                actor=entry.caller.actor,
            )
        return ChildRunResult(
            run_id=run.id,
            status=status,
            replies=tuple(child.replies),
            totals=run.totals,
            error=error,
        )

    async def _close_children(self, *, grace: float) -> None:
        """끝나지 않은 자식 Run을 멈추고 끝나기를 기다려 `run.child_finished`를 낸다."""
        entries = list(self.children.values())
        if not entries:
            return
        for entry in entries:
            self._stop_child(entry)
        tasks = {entry.task for entry in entries}
        # 자식은 자기 취소 유예 뒤 노드 태스크를 끊으므로 끝난다. 0이면(강제 정리) 끝까지 기다린다.
        _, pending = await asyncio.wait(tasks, timeout=grace if grace > 0 else None)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending)
        for entry in entries:
            self._child_finished(entry)

    async def _cancel_running(self, *, grace: float) -> None:
        tasks = list(self.running)
        if tasks:
            pending: set[asyncio.Task[NodeResult | None]] = set(tasks)
            if grace > 0:
                _, pending = await asyncio.wait(tasks, timeout=grace)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.running.clear()
        self.ready.clear()
        error = self._stop_error()
        now = self.s.clock()
        for state in self._in_order():
            live = state.status == "waiting" and not _parked(state)
            if state.status in ("queued", "running") or live or state.live_wait:
                state.live_wait = False
                self._node_record(state, "cancelled", ended_at=now, error=error)
        # 부른 쪽 태스크와 함께 끝나지 않은 호출 실행(백엔드가 따로 돌린 핸들러 등)도 정리한다.
        for state in list(self.active_calls.values()):
            self._cancel_call(state)
        # 노드 태스크와 함께 끝나지 않은 자식 Run도 멈추고 기다린다(부모 종료 이벤트보다 먼저).
        await self._close_children(grace=max(grace, self.s.cancel_grace))

    def interrupt(self, message: str) -> bool:
        """서버 종료 등으로 실행을 끊는다. 취소와 같게 멈추되 결과는 재시작 복구와 같다.

        Run `interrupted`, 끝나지 않은 노드 `cancelled`(error.code `interrupted`), 열린 요청
        `expired`(close_reason `interrupted`). 이미 취소 요청된 Run이면 아무것도 바꾸지 않는다.
        """
        if self.token.cancelled:
            return False
        self.interrupted = message
        return self.token.cancel(RuntimeErrorCodes.INTERRUPTED)

    def _stop_error(self) -> ErrorInfo:
        if self.limit_error is not None:
            return self.limit_error
        if self.interrupted is not None:
            return ErrorInfo(code=RuntimeErrorCodes.INTERRUPTED, message=self.interrupted)
        return ErrorInfo(code=RuntimeErrorCodes.CANCELLED, message=self.token.reason or "cancelled")

    async def _close_requests(self) -> None:
        if self.interrupted is not None:
            await self.broker.close_all(InteractionCloseReasons.INTERRUPTED, status="expired")
        else:
            await self.broker.close_all()

    def _in_order(self) -> list[_NodeState]:
        return sorted(self.nodes.values(), key=lambda s: self.order[s.spec.id])

    async def _finalize(self, internal: ErrorInfo | None = None) -> None:
        # 남은 요청(엔진 오류 등)을 닫고 타이머·뒤 작업을 정리한다.
        await self._close_requests()
        # 노드가 기다리지 않고 남긴 자식 Run도 멈춘다(부모가 끝난 뒤 자식이 돌지 않게).
        await self._close_children(grace=self.s.cancel_grace)
        await self.broker.drain()
        states = self._in_order()
        # Run waiting = parked wait(`NodeResult(waiting)`)만. live wait 노드는 여기 오기 전에
        # 끝났거나 취소로 정리된다(§R14.5: 종료 판정은 바뀌지 않는다).
        waiting = any(s.status == "waiting" and _parked(s) for s in states)
        if not waiting or self.token.cancelled:
            now = self.s.clock()
            for state in states:
                if state.status == "pending":
                    self._node_record(state, "skipped", ended_at=now)

        failed = sorted(
            [*self.past_failures]
            + [
                (s.spec.id, s.iteration, s.result.error if s.result is not None else None)
                for s in states
                if s.status == "failed" and not s.handled
            ],
            key=lambda f: (self.order[f[0]], f[1]),
        )
        status: RunStatus
        error: ErrorInfo | None = None
        if internal is not None:
            status, error = "failed", internal
        elif self.limit_error is not None:
            status, error = "failed", self.limit_error
        elif self.interrupted is not None:
            status, error = "interrupted", self._stop_error()
        elif self.token.cancelled:
            status, error = "cancelled", self._stop_error()
        elif failed:
            node_id, _, cause = failed[0]
            status = "failed"
            error = self._failure_summary(node_id, cause)
        elif waiting:
            status = "waiting"
        else:
            status = "completed"

        totals = sum_usage(
            [
                *self.past_usage,
                *self.call_usage,
                *(s.result.usage for s in states if s.result is not None),
            ]
        )
        ended_at = None if status == "waiting" else self.s.clock()
        started = self.run.started_at
        duration_ms = (
            round((ended_at - started) * 1000)
            if ended_at is not None and started is not None
            else None
        )
        # 반환·공개되는 최종 Run도 저장본과 같게 비밀을 가린다.
        # 순서(5.2R.39): 최종 Run 저장 → `run.<상태>` 이벤트 저장·발행 → 바깥에 최종 상태 공개.
        # 기록 줄은 들어온 순서대로 처리하므로 flush가 끝나면 앞서 낸 답변(`run.reply`)·세션
        # 이벤트도 모두 저장·발행된 뒤다. 그 전까지 손잡이(`RunHandle.run`)는 직전 상태를 보인다.
        self.held_run = self.run
        self.run = self.journal.redact_model(
            self.run.model_copy(
                update={"status": status, "ended_at": ended_at, "error": error, "totals": totals}
            )
        )
        try:
            self._save_run()
            self._run_event(f"run.{status}", duration_ms)
            await self.journal.flush()
        finally:
            self.held_run = None


def _seed_name(graph: Graph, plan: _Plan, node_id: str) -> str:
    """seed 검사 문구의 노드 이름(그래프에 없는 노드면 "고른 노드")."""
    spec = next((n for n in graph.nodes if n.id == node_id), None)
    return node_display_name(spec, plan.impls.get(node_id)) if spec is not None else "고른 노드"


def _check_seed(graph: Graph, plan: _Plan, seed: Mapping[str, Mapping[str, Any]]) -> None:
    """seed가 비어 있지 않고 모든 노드가 스케줄 대상인지 확인한다."""
    scheduled = set(plan.view.scheduled)
    bad = [node_id for node_id in seed if node_id not in scheduled]
    if not seed or bad:
        raise GraphValidationError(
            [
                Issue(
                    severity="error",
                    code=RuntimeIssueCodes.SEED_NOT_SCHEDULED,
                    message=(
                        f"'{_seed_name(graph, plan, node_id)}'은(는) 이 팀 구성에서 "
                        "실행되는 노드가 아니라 여기서부터 다시 실행할 수 없습니다"
                    ),
                    node_id=node_id,
                )
                for node_id in bad
            ]
            or [
                Issue(
                    severity="error",
                    code=RuntimeIssueCodes.SEED_NOT_SCHEDULED,
                    message="다시 실행할 노드가 없습니다",
                )
            ]
        )


def _path(state: _NodeState) -> list[str]:
    """실행 상태의 이벤트 `node_path`."""
    return list(_path_tuple(state))


def _path_tuple(state: _NodeState) -> tuple[str, ...]:
    return state.path or (state.spec.id,)


def _delegating(state: _NodeState) -> bool:
    """실행이 부른 대상이나 자식 Run을 기다리는 중인지(그동안 슬롯을 내놓는다)."""
    return bool(state.inflight or state.children)


def _parked(state: _NodeState) -> bool:
    """노드가 `NodeResult(waiting)`을 돌려주고 끝난 parked wait인지(live wait와 구분)."""
    return state.result is not None and state.result.status == "waiting"


class RunHandle:
    """시작된 Run 하나의 손잡이."""

    def __init__(self, execution: _Execution, task: asyncio.Task[Run]) -> None:
        self._execution = execution
        self._task = task

    @property
    def run_id(self) -> str:
        """Run id."""
        return self._execution.run.id

    @property
    def run(self) -> Run:
        """현재 Run 상태(메모리 사본).

        종료 상태(`completed`·`failed`·`cancelled`·`interrupted`·parked `waiting`)는 그 Run의
        기록(답변 등 모든 이벤트, 최종 Run, `run.<상태>` 이벤트)이 저장소에 저장되고 발행된 뒤에만
        보인다. 그 전에는 직전 상태(`running` 등)다.
        """
        held = self._execution.held_run
        return held if held is not None else self._execution.run

    def done(self) -> bool:
        """실행 태스크가 끝났으면 참."""
        return self._task.done()

    def cancel(self, reason: str = "cancelled") -> bool:
        """취소를 요청한다. 처음 요청이면 True."""
        return self._execution.token.cancel(reason)

    def interrupt(self, message: str = "서버가 종료되어 실행이 중단되었습니다") -> bool:
        """실행을 "끊김"으로 멈춘다(Run `interrupted`, 열린 요청 `expired`/`interrupted`).

        서버 정상 종료처럼 사용자가 취소하지 않았는데 실행이 멈출 때 쓴다(재시작 복구와 같은 결과).
        처음 요청이면 True, 이미 취소·끊김 요청됐으면 False.
        """
        return self._execution.interrupt(message)

    async def wait(self) -> Run:
        """Run이 끝날 때까지 기다려 최종 Run을 돌려준다(기다리는 쪽이 취소돼도 Run은 계속).

        Raises:
            RecorderError: 저장소 기록이 실패했을 때.
        """
        return await asyncio.shield(self._task)


class GraphRuntime:
    """그래프 실행 엔진. 레지스트리에 등록된 타입만으로 동작한다(특정 타입을 모른다).

    Args:
        registries: 노드·엣지 타입, 백엔드 등 레지스트리 묶음.
        recorder: 저장 묶음(`runs`, `events`, `interactions`). 동기 인터페이스이며 워커
            스레드에서 호출.
        event_sink: 저장이 끝난 이벤트를 발행할 곳(없으면 저장만).
        clock: 시각 함수(기본 `time.time`).
        ids: id 생성기(기본 uuid4 hex). Run id와 이벤트 id에 쓴다.
        services: 노드에 넘길 앱 서비스(기본 빈 묶음). `start(services=)`로 Run별 교체 가능.
        secrets: 비밀 해석기. 없으면 `registries.secret_providers`의 key 순서로 만든다.
        max_concurrency: 이 런타임 전체에서 동시에 실행할 노드 수 한도(None = 제한 없음).
        cancel_grace: 취소 후 실행 중 노드가 스스로 끝나기를 기다리는 초. 넘으면 태스크를 취소.
        preview_chars: 이벤트 미리보기 최대 길이.
        interaction_settings: 상호작용 대기 한도 기본값(앱 설정 `interaction.*`).
            `start(interaction_settings=)`가 Run마다 덮어쓴다.
        flow_settings: 반복·실행 한도 기본값(앱 설정 `flow.*`, design §5R.4). None이면 계약 기본값
            (`FlowSettings()`: 최대 반복은 연결 종류 기본값, 노드 실행 총 한도 200).
            `start(flow_settings=)`가 Run마다 덮어쓴다.
        sleep: 시간 제한 타이머가 쓰는 대기 함수(기본 `asyncio.sleep`, 테스트에서 가짜 시계와 함께).
        delegation_settings: 위임 설정 기본값(앱 설정 `delegation.*`). 엔진은 `max_depth`와
            `max_nesting`만 쓴다: `ctx.invoke_node`가 실행 중 위임 깊이를,
            `ctx.run_child`가 자식 Run 중첩 깊이를(design §5R.7) 확인한다.
            `start(delegation_settings=)`가 Run마다 덮어쓴다. None = 위임 깊이 설정 한도 없음
            (위임 방식이 준 한도만), 중첩 깊이는 계약 기본값(`DelegationSettings().max_nesting`).
        child_preparer: 자식 Run 준비자(`ChildRunPreparer`). 노드가 `ctx.run_child`로 자식 Run을
            만들 때 일반 Run과 같은 준비(검사·허용 상호작용·설정 층·서비스)를 하도록 앱이 준다.
            None이면 엔진 검증만 하고 서비스·설정은 부모 Run 값을 물려받는다.

    실행 중 상호작용(design §R14.5): 노드는 `ctx.request_input(...)`으로 요청을 열고 기다린다.
    앱은 `respond(...)`로 응답하고 `pending()`으로 대기 목록을 본다. 종류 이름은 모른다.
    """

    def __init__(
        self,
        registries: Registries,
        recorder: RunRecorder,
        event_sink: EventSink | None = None,
        *,
        clock: Clock = time.time,
        ids: IdFactory = _default_ids,
        services: Services | None = None,
        secrets: SecretResolver | None = None,
        max_concurrency: int | None = None,
        cancel_grace: float = 2.0,
        preview_chars: int = DEFAULT_PREVIEW_CHARS,
        interaction_settings: InteractionSettings | None = None,
        sleep: Sleep = asyncio.sleep,
        flow_settings: FlowSettings | None = None,
        delegation_settings: DelegationSettings | None = None,
        child_preparer: ChildRunPreparer | None = None,
    ) -> None:
        if max_concurrency is not None and max_concurrency < 1:
            raise ValueError("max_concurrency는 1 이상이어야 합니다")
        self.registries = registries
        self.recorder = recorder
        self.services = services or Services()
        self._settings = _Settings(
            registries=registries,
            recorder=recorder,
            sink=event_sink,
            clock=clock,
            ids=ids,
            secrets=secrets or SecretResolver(e.item for e in registries.secret_providers.list()),
            semaphore=asyncio.Semaphore(max_concurrency) if max_concurrency else None,
            cancel_grace=cancel_grace,
            preview_chars=preview_chars,
            sleep=sleep,
            interaction_settings=interaction_settings,
            flow_settings=flow_settings,
            delegation_settings=delegation_settings,
        )
        self.child_preparer = child_preparer
        """자식 Run 준비자(`ctx.run_child`, design §5R.7). 바꿔 끼울 수 있다(다음 자식부터 적용)."""
        self._active: dict[str, RunHandle] = {}

    def validate(self, graph: Graph, *, services: Services | None = None) -> list[Issue]:
        """등록된 타입 기준으로 그래프를 검증한다(`validate_graph_with`)."""
        return validate_graph_with(graph, self.registries, services=services or self.services)

    async def start(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = "api",
        run_id: str | None = None,
        conversation_id: str | None = None,
        parent_run_id: str | None = None,
        parent_node_id: str | None = None,
        services: Services | None = None,
        validate: bool = True,
        interaction_grants: Mapping[str, InteractionGrant] | None = None,
        interaction_settings: InteractionSettings | None = None,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        resumed_from: str | None = None,
        flow_settings: FlowSettings | None = None,
        delegation_settings: DelegationSettings | None = None,
        project_id: str | None = None,
        run_context: Mapping[str, Any] | None = None,
        start_warnings: Sequence[Issue] = (),
    ) -> RunHandle:
        """Run을 만들고(`run.created` 저장 완료 후) 백그라운드에서 실행을 시작한다.

        그래프는 깊은 복사해 고정하고 `Run.graph_version = graph_hash(graph)`로 기록한다.

        입구는 `scheduling = entry` 엣지가 들어오는 실행 가능 노드뿐이다
        (그래프 모양으로 추론하지 않음).
        입구 엣지 값이 그 노드의 입력 포트로 들어가고, `entry`·`flow` 엣지가 들어오지 않는 노드와
        `executable = false` 노드는 스케줄하지 않는다(NodeRun 없음).

        Args:
            conversation_id: Run 메타 `Run.conversation_id`(채팅 대화의 한 턴이면 그 대화 id).
                엔진은 의미를 모르고 기록·복사만 한다(이 Run의 상호작용에도 같은 값이 들어간다).
            interaction_grants: 노드 id → 그 노드가 열 수 있는 상호작용(`ac-teams` 계산 결과).
                엔진은 시간 제한 기본값으로만 쓰고 종류를 강제하지 않는다(`ctx.interaction_grant`).
            interaction_settings: 이 Run의 상호작용 대기 설정(팀 구성 → 공통으로 해석된 값).
                None이면 런타임 기본값.
            seed: 이어 가기(§2R.10). 노드 id → 그 노드의 입력(포트 → 값). 주면 입구 주입을 하지
                않고 이 노드들을 그 입력으로 시작한다. 상류 노드는 `skipped`(reason `resumed`).
                노드가 다시 실행해도 되는지(`rerunnable`)는 호출자가 검사한다(엔진은 모른다).
            resumed_from: Run 메타 `Run.resumed_from`(이어 간 원래 Run id). 기록만 한다.
            flow_settings: 이 Run의 반복·실행 한도(팀 구성 → 공통으로 해석된 `flow`, design §5R.4).
                None이면 런타임 기본값. 사이클 연결의 최대 반복은 엣지 config `max_iterations` →
                이 값의 `max_iterations` → 연결 종류 디스크립터 `cycle.max_iterations` 순이다.
                노드 실행 수가 `max_node_runs`를 넘으면 Run은 `failed`
                (`flow.max_node_runs_exceeded`)다. 호출 실행(`ctx.invoke_node`)도 센다.
            delegation_settings: 이 Run의 위임 설정(팀 구성 → 공통으로 해석된 `delegation`).
                None이면 런타임 기본값. `max_depth`가 `ctx.invoke_node`의 실행 중 깊이 한도다.
            project_id: Run 메타 `Run.project_id`(불투명 문자열, 5.2R.32). 기록·복사만 하고 자식
                Run은 부모 값을 받는다.
            run_context: `run.started` payload에 더할 값(예: 유효 작업 폴더 `cwd`, 5.2R.34). 엔진은
                뜻을 모르고 싣기만 한다. 상태 필드(`status` 등)와 같은 키는 무시한다. 자식 Run은
                준비자가 다른 값을 주지 않으면 같은 값을 받는다.
            start_warnings: `run.started` 뒤에 `log.warning`으로 낼 실행 수준 경고(예: 준비 중
                알게 된 문제). `details`에 `code`를 더한다.

        Raises:
            GraphValidationError: `validate`가 참이고 error 이슈가 있을 때(Run을 만들지 않음).
            NoEntryError: 입구가 없을 때(`validate`와 무관, seed가 없을 때만, Run을 만들지 않음).
            GraphValidationError: seed 노드가 스케줄 대상이 아닐 때(`seed_not_scheduled`).
            UnknownExtensionError: 등록되지 않은 노드 타입(검증을 끈 경우).
            ValueError: 같은 `run_id`가 이미 실행 중일 때.
        """
        frozen = graph.model_copy(deep=True)
        svc = services or self.services
        if validate:
            issues = self.validate(frozen, services=svc)
            if any(i.severity == "error" for i in issues):
                raise GraphValidationError(issues)
        plan = _plan(self.registries, frozen)
        if seed is not None:
            _check_seed(frozen, plan, seed)
        elif not plan.view.entry_nodes:
            raise NoEntryError()
        rid = run_id or self._settings.ids()
        if rid in self._active:
            raise ValueError(f"Run {rid!r}가 이미 실행 중입니다")
        run = Run(
            id=rid,
            graph_id=frozen.id,
            graph_version=graph_hash(frozen),
            status="queued",
            input=dict(input or {}),
            origin=origin,
            conversation_id=conversation_id,
            parent_run_id=parent_run_id,
            parent_node_id=parent_node_id,
            resumed_from=resumed_from,
            project_id=project_id,
            created_at=self._settings.clock(),
        )
        policy = WaitPolicy(
            grants=dict(interaction_grants or {}),
            settings=interaction_settings or self._settings.interaction_settings,
        )
        settings = self._settings
        if flow_settings is not None:
            settings = dataclasses.replace(settings, flow_settings=flow_settings)
        if delegation_settings is not None:
            settings = dataclasses.replace(settings, delegation_settings=delegation_settings)
        execution = _Execution(
            settings,
            run,
            frozen,
            svc,
            plan,
            policy,
            seed,
            spawner=self,
            conversation_id=conversation_id,
            run_context=run_context,
            start_warnings=start_warnings,
        )
        return await self._launch(execution)

    async def _launch(self, execution: _Execution) -> RunHandle:
        """실행을 알리고(`run.created` 저장 완료까지) 백그라운드 태스크로 시작해 등록한다."""
        rid = execution.run.id
        try:
            await execution.announce()
        except BaseException:
            with contextlib.suppress(Exception):
                await execution.journal.close()
            raise
        task = asyncio.create_task(execution.execute(), name=f"run:{rid}")
        handle = RunHandle(execution, task)
        self._active[rid] = handle
        task.add_done_callback(lambda t: self._on_run_done(rid, t))
        return handle

    async def spawn_child(
        self, parent: _Execution, request: ChildRunRequest
    ) -> tuple[_Execution, asyncio.Task[Run]]:
        """자식 Run을 준비·검증하고 시작한다(`ctx.run_child`의 엔진 쪽, design §5R.7).

        준비자가 없거나 값을 주지 않으면 부모 Run의 서비스·설정을 물려받는다. 자식 Run은 이
        런타임에 등록되어 `get`·`cancel`·`respond`·`pending`·`shutdown`이 그대로 다룬다.

        Raises:
            GraphValidationError: 준비자가 막았거나 검증 오류·입구 없음(Run을 만들지 않음).
        """
        prep = ChildRunPreparation()
        preparer = self.child_preparer
        if preparer is not None:
            made = preparer(request)
            prep = await made if inspect.isawaitable(made) else made
        graph = request.graph
        services = prep.services if prep.services is not None else request.services
        if not prep.checked:
            issues = self.validate(graph, services=services)
            if any(i.severity == "error" for i in issues):
                raise GraphValidationError(issues)
        plan = _plan(self.registries, graph)
        if not plan.view.entry_nodes:
            raise NoEntryError()
        parent_run = parent.run
        root = request.ancestors[0] if request.ancestors else parent_run
        run = Run(
            id=self._settings.ids(),
            graph_id=graph.id,
            graph_version=graph_hash(graph),
            status="queued",
            input=dict(request.input),
            origin=parent_run.origin,
            parent_run_id=parent_run.id,
            parent_node_id=request.node_id,
            root_run_id=parent_run.root_run_id or parent_run.id,
            project_id=parent_run.project_id,
            created_at=self._settings.clock(),
        )
        policy = WaitPolicy(
            grants=dict(prep.interaction_grants or {}),
            settings=prep.interaction_settings or parent.policy.settings,
        )
        settings = parent.s
        if prep.flow_settings is not None:
            settings = dataclasses.replace(settings, flow_settings=prep.flow_settings)
        if prep.delegation_settings is not None:
            settings = dataclasses.replace(settings, delegation_settings=prep.delegation_settings)
        execution = _Execution(
            settings,
            run,
            graph,
            services,
            plan,
            policy,
            spawner=self,
            ancestors=request.ancestors,
            conversation_id=root.conversation_id,
            run_context=prep.run_context if prep.run_context is not None else parent.run_context,
        )
        handle = await self._launch(execution)
        return execution, handle._task

    async def run(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> Run:
        """`start` 후 끝날 때까지 기다린다. 옵션은 `start`와 같다."""
        handle = await self.start(graph, input, **options)
        return await handle.wait()

    def _on_run_done(self, run_id: str, task: asyncio.Task[Run]) -> None:
        self._active.pop(run_id, None)
        # 아무도 wait()하지 않아도 "Task exception was never retrieved"가 나지 않게 회수한다.
        if not task.cancelled() and (exc := task.exception()) is not None:
            _log.error("Run %s 기록 실패로 종료: %r", run_id, exc)

    def get(self, run_id: str) -> RunHandle | None:
        """실행 중인 Run의 손잡이(끝났으면 None)."""
        return self._active.get(run_id)

    def active_run_ids(self) -> list[str]:
        """실행 중인 Run id 목록."""
        return list(self._active)

    async def respond(
        self,
        run_id: str,
        interaction_id: str,
        response: Mapping[str, Any],
        *,
        by: str = "user",
    ) -> Interaction:
        """열린 상호작용에 응답한다. 응답은 그 요청의 `response_schema`로 검증한다.

        동시에 여러 응답이 오면 먼저 닫은 하나만 성공한다. 기다리던 노드는 슬롯을 다시 얻은 뒤
        이어서 실행된다(이 호출은 그것을 기다리지 않는다).

        Returns:
            닫힌 상호작용(비밀을 가린 저장본).

        Raises:
            UnknownInteractionError: 그 Run에 그런 상호작용이 없다.
            InteractionClosedError: 이미 닫혔다(실행이 끝났거나 다른 응답이 먼저 닫음).
            ResponseValidationError: 응답이 스키마에 맞지 않는다(`issues`).
            RecorderError: 저장소 기록 실패.
        """
        handle = self._active.get(run_id)
        if handle is not None and handle._execution.broker.knows(interaction_id):
            return await handle._execution.broker.respond(interaction_id, response, by=by)
        stored = await asyncio.to_thread(self.recorder.interactions.get, interaction_id)
        if stored is None or stored.run_id != run_id:
            raise UnknownInteractionError(run_id, interaction_id)
        # 이 프로세스에서 기다리는 노드가 없다(끝난 실행이거나 재시작 전 요청): 응답할 수 없다.
        raise InteractionClosedError(stored)

    def pending(self, *, run_id: str | None = None) -> list[Interaction]:
        """이 런타임에서 열려 있는 상호작용(비밀을 가린 저장본, `created_at` 순).

        `run_id`를 주면 그 Run만. 재시작 전 요청은 `recover_unfinished_runs`가 닫으므로 없다.
        """
        handles: Sequence[RunHandle]
        if run_id is not None:
            handle = self._active.get(run_id)
            handles = [handle] if handle is not None else []
        else:
            handles = list(self._active.values())
        found = [i for h in handles for i in h._execution.broker.pending()]
        return sorted(found, key=lambda i: (i.created_at, i.id))

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        """실행 중인 Run을 취소한다. 실행 중이 아니거나 이미 취소 요청됐으면 False."""
        handle = self._active.get(run_id)
        return handle.cancel(reason) if handle is not None else False

    async def shutdown(
        self,
        reason: str = "shutdown",
        *,
        timeout: float | None = None,
        interrupt: bool = False,
    ) -> bool:
        """실행 중인 모든 Run을 멈추고 끝날 때까지 기다린다.

        Args:
            reason: 취소 사유(`interrupt`면 끊김 메시지).
            interrupt: 참이면 취소 대신 "끊김"으로 정리한다. Run `interrupted`, 열린 요청
                `expired`(close_reason `interrupted`) — 서버 재시작 복구
                (`recover_unfinished_runs`)와 같은 결과라 정상 종료와 비정상 종료가
                같게 보인다(§R14.5).
            timeout: 협조적 취소를 기다릴 최대 초. 넘으면 남은 Run 태스크를 asyncio 취소하고
                그 정리(열린 요청 닫기·최종 기록)가 끝날 때까지 기다린다. None = 무기한.

        Returns:
            시간 안에 모두 스스로 끝났으면 True(강제 취소한 Run이 있으면 False).
        """
        handles = list(self._active.values())
        for handle in handles:
            if interrupt:
                handle.interrupt(reason)
            else:
                handle.cancel(reason)
        tasks = [h._task for h in handles]
        if not tasks:
            return True
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return not pending
