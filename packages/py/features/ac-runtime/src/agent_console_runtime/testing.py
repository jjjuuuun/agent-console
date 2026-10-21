"""테스트 도우미(공개, 운영 코드에서 쓰지 않는다).

- `InMemoryRecorder`(상호작용 저장 `MemoryInteractionWriter` 포함), `StepClock`,
  `SequentialIds`, `ManualClock`(가짜 시계 + 가짜 `sleep`, 시간 제한 테스트용):
  저장소 패키지 없이 엔진을 결정적으로 돌린다.
  운영용 저장소는 `agent_console_store`(SqliteStorage·InMemoryStorage)를 앱이 주입한다.
- 테스트 전용 노드·엣지 타입과 `make_harness()`: 엔진이 기본 제공 타입 없이 등록된 타입만으로
  동작함을 보이는 데 쓴다. 엔진 모듈은 이 모듈을 import하지 않는다.
  - 노드: `t.step`(설정으로 동작), `t.dyn`(동적 포트),
    `t.user`(실행 가능하지만 입구·흐름 입력이 없으면 스케줄되지 않는 자리),
    `t.res`(`executable=false`), `t.lead`(X12 위임 방식으로 대상 실행)
  - 엣지: `t.flow`·`t.err`·`t.broken`(flow), `t.entry`(entry), `t.exit`(exit), `t.tie`(none),
    `t.call`(none + invocation `t.inline`), `t.loop`(flow + 사이클 연결 `cycle`, design §5R.4),
    `t.invoke`(none + invocation `t.invoker`, design §5R.6)
  - 위임 방식(X12): `t.inline`(대상마다 하위 이벤트·답변을 내는 흉내), `t.invoker`(대상을
    `ctx.invoke_node`로 자기 NodeRun에서 실행, `register_invocation_types`)
  - 상호작용(X15): 종류 `t.ask`·`t.pick`(`ASK_KIND`·`PICK_KIND`),
    노드 `t.asker`(config로 요청을 연다). 엔진이 종류 이름을 모름을 보이는 데 쓴다.
  - 자식 Run(design §5R.7): 노드 `t.nest`(config `graph`를 `ctx.run_child`로 실행,
    `register_child_types`)
"""

from __future__ import annotations

import asyncio
import builtins
import copy
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import (
    Agent,
    CyclePolicy,
    DelegationStrategyDescriptor,
    EdgeInvocation,
    EdgeSpec,
    EdgeTypeDescriptor,
    Endpoint,
    ErrorInfo,
    Fix,
    Graph,
    Interaction,
    InteractionKindDescriptor,
    InteractionStatus,
    Issue,
    NodeRun,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    Run,
    RunEvent,
    RunEventBase,
    Usage,
)

from ._children import ChildRunResult
from ._context import NodeContext
from ._delegation import DelegationMember, DelegationPlan
from ._interactions import (
    InteractionClosedError,
    InteractionRequest,
    StaticInteractionKind,
)
from ._interfaces import (
    Activation,
    AgentRequest,
    AgentResult,
    NodeResult,
    NodeRunView,
    Reply,
    ValidationContext,
)
from ._registries import Registries
from ._runtime import GraphRuntime
from ._services import ServiceKey, Services

_UNFINISHED = frozenset({"queued", "running", "paused", "waiting"})


class SequentialIds:
    """`prefix-1`, `prefix-2`, … 를 내는 id 생성기."""

    def __init__(self, prefix: str = "id") -> None:
        self._prefix = prefix
        self._n = 0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            self._n += 1
            return f"{self._prefix}-{self._n}"


class StepClock:
    """호출할 때마다 `step`초씩 증가하는 시계(결정적 테스트)."""

    def __init__(self, start: float = 1_000.0, step: float = 1.0) -> None:
        self.now = start
        self.step = step
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            value = self.now
            self.now += self.step
            return value


class ManualClock:
    """손으로 움직이는 시계 + 그 시계를 따르는 `sleep`(시간 제한 테스트용).

    `GraphRuntime(clock=clock, sleep=clock.sleep)`로 넣고 `await clock.advance(초)`로 시간을 보낸다.
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start
        self._sleepers: list[tuple[float, asyncio.Future[None]]] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        """시계가 `delay`초 지날 때까지 기다린다."""
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._sleepers.append((self.now + delay, future))
        await future

    @property
    def sleepers(self) -> int:
        """아직 깨어나지 않은 sleep 수."""
        return sum(1 for _, f in self._sleepers if not f.done())

    async def advance(self, seconds: float) -> None:
        """시간을 보내고 기한이 된 sleep을 깨운 뒤 이벤트 루프에 차례를 넘긴다."""
        self.now += seconds
        due = [f for t, f in self._sleepers if t <= self.now and not f.done()]
        self._sleepers = [(t, f) for t, f in self._sleepers if not f.done() and f not in due]
        for future in due:
            future.set_result(None)
        for _ in range(5):
            await asyncio.sleep(0)


class MemoryRunWriter:
    def __init__(self, owner: InMemoryRecorder) -> None:
        self._o = owner

    def save(self, run: Run) -> None:
        with self._o.lock:
            self._o.run_docs[run.id] = run.model_copy(deep=True)

    def get(self, run_id: str) -> Run | None:
        with self._o.lock:
            return self._o.run_docs.get(run_id)

    def save_node_run(self, node_run: NodeRun) -> None:
        key = (node_run.node_id, node_run.attempt, node_run.iteration, node_run.call)
        with self._o.lock:
            self._o.node_run_docs.setdefault(node_run.run_id, {})[key] = node_run.model_copy(
                deep=True
            )

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        with self._o.lock:
            return list(self._o.node_run_docs.get(run_id, {}).values())

    def list(self, *, resumed_from: str | None = None) -> builtins.list[Run]:
        """Run 목록(생성 최신순). `resumed_from`이면 그 Run을 이어 간 Run만."""
        with self._o.lock:
            runs = [
                r
                for r in self._o.run_docs.values()
                if resumed_from is None or r.resumed_from == resumed_from
            ]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        ids: list[str] = []
        with self._o.lock:
            for run in list(self._o.run_docs.values()):
                if run.status in _UNFINISHED:
                    self._o.run_docs[run.id] = run.model_copy(
                        update={"status": "interrupted", "ended_at": ended_at, "error": error}
                    )
                    ids.append(run.id)
        return ids


class MemoryEventWriter:
    def __init__(self, owner: InMemoryRecorder) -> None:
        self._o = owner

    def append(self, event: RunEventBase) -> bool:
        return self.append_many([event]) == 1

    def append_many(self, events: Sequence[RunEventBase]) -> int:
        added = 0
        with self._o.lock:
            self._o.append_calls += 1
            for event in events:
                stored = RunEvent.model_validate(event.model_dump(by_alias=True))
                if stored.event_id in self._o.event_ids:
                    continue
                self._o.event_ids.add(stored.event_id)
                self._o.event_log.setdefault(stored.run_id, []).append(stored)
                added += 1
        return added

    def last_seq(self, run_id: str) -> int:
        with self._o.lock:
            log = self._o.event_log.get(run_id, [])
            return max((e.seq for e in log), default=0)

    def list(self, run_id: str) -> builtins.list[RunEvent]:
        with self._o.lock:
            return list(self._o.event_log.get(run_id, []))


class MemoryInteractionWriter:
    """`InteractionWriter`의 메모리 구현(`close`는 pending 조건부, 이미 닫혔으면
    `InteractionClosedError`)."""

    def __init__(self, owner: InMemoryRecorder) -> None:
        self._o = owner

    def save(self, interaction: Interaction) -> bool:
        with self._o.lock:
            existing = self._o.interaction_docs.get(interaction.id)
            if existing is not None and existing.status != "pending":
                return False
            self._o.interaction_docs[interaction.id] = interaction.model_copy(deep=True)
            return True

    def get(self, interaction_id: str) -> Interaction | None:
        with self._o.lock:
            found = self._o.interaction_docs.get(interaction_id)
            return None if found is None else found.model_copy(deep=True)

    def list(
        self,
        *,
        run_id: str | None = None,
        status: InteractionStatus | Iterable[InteractionStatus] | None = None,
    ) -> builtins.list[Interaction]:
        statuses = (
            None if status is None else ({status} if isinstance(status, str) else set(status))
        )
        with self._o.lock:
            rows = [
                i.model_copy(deep=True)
                for i in self._o.interaction_docs.values()
                if (run_id is None or i.run_id == run_id)
                and (statuses is None or i.status in statuses)
            ]
        return sorted(rows, key=lambda i: (i.created_at, i.id))

    def close(
        self,
        interaction_id: str,
        *,
        status: InteractionStatus,
        closed_at: float,
        response: dict[str, Any] | None = None,
        answered_by: str | None = None,
        close_reason: str | None = None,
    ) -> Interaction:
        if status == "pending":
            raise ValueError("닫힌 상태가 아닙니다")
        with self._o.lock:
            current = self._o.interaction_docs.get(interaction_id)
            if current is None:
                raise LookupError(interaction_id)
            if current.status != "pending":
                raise InteractionClosedError(current.model_copy(deep=True))
            closed = current.model_copy(
                update={
                    "status": status,
                    "closed_at": closed_at,
                    "response": copy.deepcopy(response)
                    if response is not None
                    else current.response,
                    "answered_by": answered_by,
                    "close_reason": close_reason,
                },
                deep=True,
            )
            self._o.interaction_docs[interaction_id] = closed
            return closed.model_copy(deep=True)

    def close_pending(
        self,
        *,
        status: InteractionStatus,
        closed_at: float,
        run_id: str | None = None,
        answered_by: str | None = "system",
        close_reason: str | None = None,
    ) -> builtins.list[Interaction]:
        if status not in ("expired", "cancelled"):
            raise ValueError("expired·cancelled만 됩니다")
        closed: list[Interaction] = []
        with self._o.lock:
            for item in self.list(run_id=run_id, status="pending"):
                closed.append(
                    self.close(
                        item.id,
                        status=status,
                        closed_at=closed_at,
                        answered_by=answered_by,
                        close_reason=close_reason,
                    )
                )
        return closed


class InMemoryRecorder:
    """`RunRecorder`의 최소 메모리 구현(테스트용). 저장 내용을 속성으로 들여다볼 수 있다."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.run_docs: dict[str, Run] = {}
        self.node_run_docs: dict[str, dict[tuple[str, int, int, int], NodeRun]] = {}
        self.event_log: dict[str, list[RunEvent]] = {}
        self.event_ids: set[str] = set()
        self.interaction_docs: dict[str, Interaction] = {}
        self.append_calls = 0
        self._runs = MemoryRunWriter(self)
        self._events = MemoryEventWriter(self)
        self._interactions = MemoryInteractionWriter(self)

    @property
    def runs(self) -> MemoryRunWriter:
        return self._runs

    @property
    def events(self) -> MemoryEventWriter:
        return self._events

    @property
    def interactions(self) -> MemoryInteractionWriter:
        return self._interactions


# ---------------------------------------------------------------- 테스트 전용 타입


@dataclass(frozen=True)
class NodeSeen:
    """`t.step` 노드 실행 한 번이 본 맥락(반복 테스트용)."""

    node_id: str
    iteration: int
    incoming: tuple[tuple[str, Any, bool], ...]
    """(엣지 id, 값, carried)."""
    previous_session_id: str | None


@dataclass
class Probe:
    """테스트 노드가 관찰 값을 남기는 곳(서비스로 주입)."""

    running: int = 0
    max_running: int = 0
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    cancel_callbacks: list[str] = field(default_factory=list)
    started: dict[str, asyncio.Event] = field(default_factory=dict)
    background: list[asyncio.Future[Any]] = field(default_factory=list)
    seen: list[NodeSeen] = field(default_factory=list)
    """`t.step` 실행마다 본 맥락(회차·엣지별 입력·직전 회차 세션)."""
    invocations: list[NodeRunView] = field(default_factory=list)
    """`t.invoker` 위임 방식이 받은 호출 결과(`ctx.invoke_node`)."""
    children: list[ChildRunResult] = field(default_factory=list)
    """`t.nest` 노드가 받은 자식 Run 결과(`ctx.run_child`)."""

    def started_event(self, node_id: str) -> asyncio.Event:
        return self.started.setdefault(node_id, asyncio.Event())


PROBE = ServiceKey[Probe]("test.probe")

_PORTS = PortSpec(
    inputs=[PortDef(name="in"), PortDef(name="in2")],
    outputs=[PortDef(name="out"), PortDef(name="alt")],
)


class StepNode:
    """config로 동작을 정하는 테스트 노드 `t.step`.

    config 키: per_iteration(list[dict], 회차마다 config에 덮어쓸 값 — 회차가 목록보다 크면 마지막),
    session(str, 결과 `backend_session_id`에 `"<session>-<회차>"`),
    outputs(dict, 기본 {"out": inputs}), fail(+ fix: 실패 `ErrorInfo.fix` 값), raise, skip, sleep,
    hang(취소 대기), name(선택 훅 `display_name`이 돌려줄 이름),
    stubborn(취소 무시하고 계속 잠), usage(dict), events(int, agent.text_delta 개수),
    secret(비밀 참조 → 해석 값을 이벤트에 넣음),
    leak(error|out: 해석 값을 결과에 넣음),
    forbidden(엔진 예약 이벤트 시도).
    """

    descriptor = NodeTypeDescriptor(
        id="t.step",
        title="테스트 단계",
        static_ports=_PORTS,
        config_schema={
            "type": "object",
            "properties": {"sleep": {"type": "number", "minimum": 0}},
        },
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _PORTS

    def actor_of(self, config: Mapping[str, Any]) -> str | None:
        """선택 훅(`NODE_ACTOR_HOOK`): config `actor`."""
        actor = config.get("actor")
        return str(actor) if actor else None

    def display_name(self, config: Mapping[str, Any], services: Any) -> str | None:
        """선택 훅(`NODE_NAME_HOOK`): config `name`."""
        name = config.get("name")
        return str(name) if name else None

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        if config.get("invalid"):
            return [Issue(severity="error", code="t.invalid", message="invalid", path="/invalid")]
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        cfg: Mapping[str, Any] = ctx.config
        per = cfg.get("per_iteration")
        if isinstance(per, list) and per:
            cfg = {**cfg, **per[min(ctx.iteration, len(per) - 1)]}
        probe = ctx.services.get(PROBE)
        if probe is not None:
            probe.seen.append(
                NodeSeen(
                    node_id=ctx.node.id,
                    iteration=ctx.iteration,
                    incoming=tuple((i.edge_id, i.value, i.carried) for i in ctx.incoming()),
                    previous_session_id=ctx.previous_session_id,
                )
            )
            probe.calls.append((ctx.node.id, dict(inputs)))
            probe.running += 1
            probe.max_running = max(probe.max_running, probe.running)
            probe.started_event(ctx.node.id).set()
        try:
            return await self._run(ctx, cfg, inputs, probe)
        finally:
            if probe is not None:
                probe.running -= 1

    async def _run(
        self,
        ctx: NodeContext,
        cfg: Mapping[str, Any],
        inputs: Mapping[str, Any],
        probe: Probe | None,
    ) -> NodeResult:
        for i in range(int(cfg.get("events", 0))):
            await ctx.emit("agent.text_delta", {"text": f"t{i}"})
        if "secret" in cfg:
            value = ctx.secrets.resolve(cfg["secret"])
            await ctx.emit("test.secret", {"value": value, "text": f"key={value}"})
            leak = cfg.get("leak")
            if leak == "error":
                return NodeResult(
                    status="failed",
                    error=ErrorInfo(code="t.leak", message=f"bad {value}", details={"k": value}),
                )
            if leak == "out":
                return NodeResult(status="succeeded", outputs={"out": f"val {value}"})
        if cfg.get("forbidden"):
            await ctx.emit("node.completed", {"status": "succeeded"})
        if cfg.get("sleep"):
            await asyncio.sleep(float(cfg["sleep"]))
        if cfg.get("hang"):
            if probe is not None:
                ctx.cancel.on_cancel(lambda: probe.cancel_callbacks.append(ctx.node.id))
            await ctx.cancel.wait()
            return NodeResult(status="failed", error=ErrorInfo(code="t", message="stopped"))
        if cfg.get("stubborn"):
            await asyncio.sleep(3600)
        if cfg.get("raise"):
            raise RuntimeError(str(cfg["raise"]))
        if cfg.get("fail"):
            error = ErrorInfo(code="t.fail", message="boom")
            if "fix" in cfg:
                error = error.model_copy(update={"fix": Fix.model_validate(cfg["fix"])})
            return NodeResult(status="failed", error=error)
        if cfg.get("skip"):
            return NodeResult(status="skipped")
        usage = Usage.model_validate(cfg["usage"]) if "usage" in cfg else None
        outputs = dict(cfg["outputs"]) if "outputs" in cfg else {"out": dict(inputs)}
        session = f"{cfg['session']}-{ctx.iteration}" if "session" in cfg else None
        return NodeResult(
            status="succeeded", outputs=outputs, usage=usage, backend_session_id=session
        )


class DynNode:
    """config.ports로 출력 포트가 정해지는 동적 포트 노드 `t.dyn`."""

    descriptor = NodeTypeDescriptor(id="t.dyn", title="동적", dynamic_ports=True)

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return PortSpec(
            inputs=[PortDef(name="in")],
            outputs=[PortDef(name=p) for p in config.get("ports", [])],
        )

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        chosen = str(ctx.config.get("choose", ""))
        return NodeResult(status="succeeded", outputs={chosen: inputs.get("in")})


class FlowEdge:
    """소스가 성공했고 소스 포트에 값이 있으면 통과하는 테스트 엣지 `t.flow`."""

    descriptor = EdgeTypeDescriptor(id="t.flow", title="흐름")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        return Activation(source.outputs[edge.source.port])


class LoopEdge(FlowEdge):
    """사이클 연결 `t.loop`: `t.flow`처럼 통과하고 디스크립터 `cycle`로 흐름 사이클을 닫는다.

    config `max_iterations`(엣지별 최대 반복). 기본 최대 반복은 3이다. 엔진은 이 이름을 모르고
    디스크립터 `cycle`만 본다(`descriptor` 사본으로 이름을 바꿔 등록해도 같다).
    """

    descriptor = EdgeTypeDescriptor(
        id="t.loop",
        title="되돌리기",
        cycle=CyclePolicy(max_iterations=3),
        config_schema={
            "type": "object",
            "properties": {"max_iterations": {"type": "integer", "minimum": 1}},
        },
    )


class ErrEdge:
    """소스가 실패하면 오류 정보를 전달하는 테스트 엣지 `t.err`."""

    descriptor = EdgeTypeDescriptor(id="t.err", title="오류")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "failed" or source.error is None:
            return None
        return Activation(source.error.model_dump(mode="json"))


class BrokenEdge:
    """항상 예외를 던지는 엣지 `t.broken`."""

    descriptor = EdgeTypeDescriptor(id="t.broken", title="고장")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        raise ValueError("edge bug")


class UserNode:
    """사용자 자리 흉내 `t.user`(포트 `says`·`hears`). 실행 가능하지만 입구·흐름 입력이 없으면
    스케줄되지 않는다. 흐름으로 들어오면 받은 값을 그대로 `says`로 낸다."""

    descriptor = NodeTypeDescriptor(
        id="t.user",
        title="테스트 사용자",
        role="t-person",
        static_ports=PortSpec(inputs=[PortDef(name="hears")], outputs=[PortDef(name="says")]),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return self.descriptor.static_ports or PortSpec()

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        probe = ctx.services.get(PROBE)
        if probe is not None:
            probe.calls.append((ctx.node.id, dict(inputs)))
        return NodeResult(status="succeeded", outputs={"says": inputs.get("hears")})


class InertNode:
    """실행하지 않는 노드 `t.res`(`executable=false`, 포트 `out`). 실행되면 실패한다."""

    descriptor = NodeTypeDescriptor(
        id="t.res",
        title="테스트 리소스",
        executable=False,
        static_ports=PortSpec(inputs=[PortDef(name="in")], outputs=[PortDef(name="out")]),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return self.descriptor.static_ports or PortSpec()

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        raise AssertionError("executable=false 노드가 실행됐다")


class EntryEdge:
    """입구 엣지 `t.entry`(scheduling=entry). config `key`가 있으면 Run 입력에서 그 키만 꺼낸다
    (없으면 이 경로는 죽는다). 없으면 Run 입력 전체를 넘긴다."""

    descriptor = EdgeTypeDescriptor(
        id="t.entry",
        title="입구",
        scheduling="entry",
        config_schema={"type": "object", "properties": {"key": {"type": "string"}}},
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        value = source.outputs.get(edge.source.port)
        key = edge.config.get("key")
        if key is None:
            return Activation(value)
        if not isinstance(value, Mapping) or key not in value:
            return None
        return Activation(value[key])


class ExitEdge:
    """답변 엣지 `t.exit`(scheduling=exit). 소스가 성공했고 포트에 값이 있으면 답변.

    config `label`·`order`·`final`은 `Reply`로 옮긴다.
    `raw: true`면 값을 그대로 넘긴다(엔진 변환 확인용).
    """

    descriptor = EdgeTypeDescriptor(id="t.exit", title="답변", scheduling="exit")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        value = source.outputs[edge.source.port]
        cfg = edge.config
        if cfg.get("raw"):
            return Activation(value)
        return Activation(
            Reply(
                text=str(value),
                label=cfg.get("label"),
                order=cfg.get("order"),
                final=bool(cfg.get("final", True)),
            )
        )


class TieEdge:
    """스케줄과 무관한 연결 `t.tie`(scheduling=none). 엔진은 `activates`를 부르지 않는다."""

    descriptor = EdgeTypeDescriptor(id="t.tie", title="묶음", scheduling="none")

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        raise AssertionError("scheduling=none 엣지가 평가됐다")


class CallEdge:
    """호출 연결 `t.call`(scheduling=none, invocation `t.inline`).

    대상은 위 노드 실행 안에서 돈다.
    """

    descriptor = EdgeTypeDescriptor(
        id="t.call",
        title="호출",
        scheduling="none",
        invocation=EdgeInvocation(strategy="t.inline"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        raise AssertionError("scheduling=none 엣지가 평가됐다")


class InlineStrategy:
    """테스트 위임 방식 `t.inline`(X12).

    대상마다 하위 이벤트(actor·하위 node_path)와 답변을 낸다.
    """

    descriptor = DelegationStrategyDescriptor(
        id="t.inline",
        title="테스트 위임",
        member_fields=["model"],
        max_depth=1,
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        if not plan.members:
            return [Issue(severity="error", code="t.no_members", message="대상 없음")]
        return []

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        parts: list[str] = []
        for member in plan.members:
            path = ctx.child_path(member.node_id)
            await ctx.emit(
                "agent.subagent_started",
                {"subagent_id": member.node_id, "name": member.node_id},
            )
            text = f"{member.node_id}:{plan.request.prompt}"
            await ctx.emit(
                "agent.message",
                {"role": "assistant", "text": text},
                actor=member.agent_id,
                node_path=path,
            )
            await ctx.emit_replies(member.node_id, {"out": text}, actor=member.agent_id)
            await ctx.emit(
                "agent.subagent_stopped",
                {"subagent_id": member.node_id, "name": member.node_id, "status": "completed"},
            )
            parts.append(text)
        return AgentResult(status="succeeded", text=" | ".join(parts))


class InvokeEdge:
    """독립 호출 연결 `t.invoke`(scheduling=none, invocation `t.invoker`, design §5R.6).

    대상은 위임자가 `ctx.invoke_node`로 부를 때 자기 NodeRun으로 돈다.
    """

    descriptor = EdgeTypeDescriptor(
        id="t.invoke",
        title="호출(자기 실행)",
        scheduling="none",
        invocation=EdgeInvocation(strategy="t.invoker"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        raise AssertionError("scheduling=none 엣지가 평가됐다")


class InvokeStrategy:
    """테스트 위임 방식 `t.invoker`(X12): 대상을 `ctx.invoke_node`로 실행한다.

    위임자 노드 config:
      - `calls`: 부를 대상 id 목록(같은 id 반복 가능). 기본 = 대상마다 한 번.
      - `parallel`: 참이면 동시에 부른다(기본은 순서대로).
      - `max_depth`: `invoke_node(max_depth=)`(기본 디스크립터 `max_depth` = 제한 없음).
    결과 텍스트 = 호출마다 `"<대상>#<call>:<상태>:<out 값>"`을 `" | "`로 이은 것. 대상이 실패해도
    위임자는 성공한다(결과에 남는다). 결과 목록은 probe `invocations`에도 남는다.
    """

    descriptor = DelegationStrategyDescriptor(
        id="t.invoker",
        title="테스트 호출 위임",
        member_fields=[],
        max_depth=None,
        composable=True,
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        return []

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        edges = {m.node_id: m.edge_id for m in plan.members}
        targets = [str(t) for t in ctx.config.get("calls") or list(edges)]
        raw_limit = ctx.config.get("max_depth", self.descriptor.max_depth)
        limit = int(raw_limit) if raw_limit is not None else None

        async def one(target: str) -> NodeRunView:
            return await ctx.invoke_node(
                target, {"in": plan.request.prompt}, by_edge=edges[target], max_depth=limit
            )

        if ctx.config.get("parallel"):
            views = list(await asyncio.gather(*(one(t) for t in targets)))
        else:
            views = [await one(t) for t in targets]
        probe = ctx.services.get(PROBE)
        if probe is not None:
            probe.invocations.extend(views)
        text = " | ".join(f"{v.node_id}#{v.call}:{v.status}:{v.outputs.get('out')}" for v in views)
        return AgentResult(status="succeeded", text=text)


class LeadNode:
    """위임자 흉내 `t.lead`. 나가는 엣지 중 디스크립터에 `invocation`이 있는 것의 대상을 모아
    그 위임 방식(X12)에 맡긴다. 대상 노드 config `actor`가 대상 에이전트 id다."""

    descriptor = NodeTypeDescriptor(id="t.lead", title="테스트 위임자", static_ports=_PORTS)

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _PORTS

    def actor_of(self, config: Mapping[str, Any]) -> str | None:
        return str(config.get("actor", "lead"))

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        members: list[DelegationMember] = []
        strategy_id: str | None = None
        nodes = {n.id: n for n in ctx.graph.nodes}
        for e in ctx.graph.edges:
            if e.source.node != ctx.node.id:
                continue
            invocation = ctx.registries.edge_types.get(e.kind).descriptor.invocation
            if invocation is None:
                continue
            strategy_id = str(e.config.get("strategy", invocation.strategy))
            target = nodes[e.target.node]
            members.append(
                DelegationMember(
                    node_id=target.id,
                    edge_id=e.id,
                    agent_id=target.config.get("actor"),
                    delegate_when=str(target.config.get("when", "")),
                )
            )
        agent = Agent(id=self.actor_of(ctx.config) or "lead", name="lead")
        request = AgentRequest(agent=agent, prompt=str(inputs.get("in", "")))
        if strategy_id is None:
            return NodeResult(status="succeeded", outputs={"out": request.prompt})
        strategy = ctx.registries.delegation_strategies.get(strategy_id)
        plan = DelegationPlan(
            strategy=strategy_id, delegator_node_id=ctx.node.id, request=request, members=members
        )
        issues = strategy.validate(plan)
        if any(i.severity == "error" for i in issues):
            return NodeResult(
                status="failed", error=ErrorInfo(code=issues[0].code, message=issues[0].message)
            )
        result = await strategy.run(plan, ctx)
        return NodeResult(status="succeeded", outputs={"out": result.text})


ASK_KIND = InteractionKindDescriptor(
    id="t.ask",
    title="테스트 질문",
    request_schema={"type": "object"},
    response_schema={
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    },
    free_text_path="/answer",
    expire_response={"answer": "(응답 없음)"},
)
"""테스트 상호작용 종류 `t.ask`(응답 `{answer: str}`, 만료 응답 있음)."""

PICK_KIND = InteractionKindDescriptor(id="t.pick", title="테스트 선택")
"""테스트 상호작용 종류 `t.pick`(기본 응답 스키마 없음 = 모두 허용, 만료 응답 없음)."""


class AskerNode:
    """config로 상호작용을 여는 테스트 노드 `t.asker`(엔진이 종류 이름을 모름을 보인다).

    config 키:
      - `asks`: 요청 목록. 항목은 `InteractionRequest` 필드(`kind` 기본 `t.ask`) + `child`(하위
        node_path 대상 id).
      - `parallel`: 참이면 요청을 동시에 연다(기본은 순서대로).
      - `background`: 참이면 요청을 뒤에서 열고 바로 끝난다(대기 중 노드 종료 흉내).
      - `secret`: 비밀 참조. 해석 값을 첫 요청 payload `secret`에 넣는다.
    출력 `out`: 결과 목록(`InteractionOutcome` dict).
    """

    descriptor = NodeTypeDescriptor(id="t.asker", title="테스트 질문자", static_ports=_PORTS)

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _PORTS

    def actor_of(self, config: Mapping[str, Any]) -> str | None:
        actor = config.get("actor")
        return str(actor) if actor else None

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        probe = ctx.services.get(PROBE)
        if probe is not None:
            probe.calls.append((ctx.node.id, dict(inputs)))
            probe.started_event(ctx.node.id).set()
        requests: list[InteractionRequest] = []
        for i, raw in enumerate(ctx.config.get("asks", [])):
            item = dict(raw)
            child = item.pop("child", None)
            item.setdefault("kind", ASK_KIND.id)
            if child is not None:
                item["node_path"] = ctx.child_path(str(child))
            if i == 0 and "secret" in ctx.config:
                payload = dict(item.get("payload", {}))
                payload["secret"] = ctx.secrets.resolve(str(ctx.config["secret"]))
                item["payload"] = payload
            requests.append(InteractionRequest.model_validate(item))
        if ctx.config.get("background"):
            tasks = [asyncio.ensure_future(ctx.request_input(r)) for r in requests]
            for _ in range(3):
                await asyncio.sleep(0)
            if probe is not None:
                probe.background.extend(tasks)
            return NodeResult(status="succeeded", outputs={"out": "left"})
        if ctx.config.get("parallel"):
            outcomes = await asyncio.gather(*(ctx.request_input(r) for r in requests))
        else:
            outcomes = [await ctx.request_input(r) for r in requests]
        return NodeResult(
            status="succeeded", outputs={"out": [o.model_dump(mode="json") for o in outcomes]}
        )


class NestNode:
    """자식 Run 흉내 `t.nest`(design §5R.7): config `graph`를 `ctx.run_child`로 실행한다.

    config 키: `graph`(계약 `Graph` 문서, 필수), `version`(`graph_version=`), `input_key`(입력 포트
    `in` 값에서 꺼낼 키, 생략 = `{"text": in 값}`), `actor`.
    출력 `out` = 자식 답변 텍스트를 `" | "`로 이은 것. 자식이 `completed`가 아니면 `failed`
    (오류 = 자식 오류). 사용량 = 자식 `totals`. 결과는 probe `children`에도 남는다.
    """

    descriptor = NodeTypeDescriptor(id="t.nest", title="테스트 중첩", static_ports=_PORTS)

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _PORTS

    def actor_of(self, config: Mapping[str, Any]) -> str | None:
        actor = config.get("actor")
        return str(actor) if actor else None

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        child_graph = Graph.model_validate(ctx.config["graph"])
        value = inputs.get("in")
        key = ctx.config.get("input_key")
        if key is not None and isinstance(value, Mapping):
            value = value.get(str(key))
        child_input = value if isinstance(value, dict) and key is None else {"text": value}
        result = await ctx.run_child(
            child_graph, child_input, graph_version=ctx.config.get("version")
        )
        probe = ctx.services.get(PROBE)
        if probe is not None:
            probe.children.append(result)
        text = " | ".join(r.text for r in result.replies)
        if result.status != "completed":
            return NodeResult(
                status="failed",
                error=result.error
                or ErrorInfo(code="t.child", message=f"자식 Run {result.status}"),
                outputs={"out": text},
                usage=result.totals,
            )
        return NodeResult(status="succeeded", outputs={"out": text}, usage=result.totals)


def register_child_types(registries: Registries) -> None:
    """자식 Run(`ctx.run_child`, design §5R.7) 테스트 노드 `t.nest`를 등록한다."""
    registries.node_types.register("t.nest", NestNode())


def register_interaction_types(registries: Registries) -> None:
    """테스트 상호작용 종류 `t.ask`·`t.pick`과 노드 `t.asker`를 등록한다."""
    registries.interaction_kinds.register(ASK_KIND.id, StaticInteractionKind(ASK_KIND))
    registries.interaction_kinds.register(PICK_KIND.id, StaticInteractionKind(PICK_KIND))
    registries.node_types.register("t.asker", AskerNode())


def register_scheduling_types(registries: Registries) -> None:
    """입구·답변·위임 테스트 타입을 아무 레지스트리 묶음에 등록한다(`load_plugins` 대상으로도 쓴다).

    노드 `t.user`·`t.res`·`t.lead`, 엣지 `t.entry`·`t.exit`·`t.tie`·`t.call`, 위임 방식 `t.inline`.
    실제 플러그인 타입으로 조립한 스택(서버 등)의 테스트에서 입구를 명시할 때 쓴다.
    """
    registries.node_types.register("t.user", UserNode())
    registries.node_types.register("t.res", InertNode())
    registries.node_types.register("t.lead", LeadNode())
    registries.edge_types.register("t.entry", EntryEdge())
    registries.edge_types.register("t.exit", ExitEdge())
    registries.edge_types.register("t.tie", TieEdge())
    registries.edge_types.register("t.call", CallEdge())
    registries.delegation_strategies.register("t.inline", InlineStrategy())


def register_invocation_types(registries: Registries) -> None:
    """호출 NodeRun(`ctx.invoke_node`, design §5R.6) 테스트 타입을 등록한다.

    엣지 `t.invoke`(invocation `t.invoker`)와 위임 방식 `t.invoker`. 위임자 노드는 `t.lead`.
    """
    registries.edge_types.register("t.invoke", InvokeEdge())
    registries.delegation_strategies.register("t.invoker", InvokeStrategy())


def make_registries() -> Registries:
    regs = Registries()
    regs.node_types.register("t.step", StepNode())
    regs.node_types.register("t.dyn", DynNode())
    regs.edge_types.register("t.flow", FlowEdge())
    regs.edge_types.register("t.loop", LoopEdge())
    regs.edge_types.register("t.err", ErrEdge())
    regs.edge_types.register("t.broken", BrokenEdge())
    register_scheduling_types(regs)
    register_interaction_types(regs)
    register_invocation_types(regs)
    register_child_types(regs)
    return regs


def node(node_id: str, type: str = "t.step", join: str | None = None, **config: Any) -> NodeSpec:
    return NodeSpec.model_validate({"id": node_id, "type": type, "config": config, "join": join})


USER_NODE = "you"
"""`graph(entries=…)`가 넣는 사용자 자리 노드 id."""


def edge(
    src: str,
    dst: str,
    *,
    kind: str = "t.flow",
    sp: str = "out",
    tp: str = "in",
    **config: Any,
) -> EdgeSpec:
    return EdgeSpec(
        id=f"{src}.{sp}->{dst}.{tp}",
        source=Endpoint(node=src, port=sp),
        target=Endpoint(node=dst, port=tp),
        kind=kind,
        config=config,
    )


def entry(dst: str, *, tp: str = "in", src: str = USER_NODE, **config: Any) -> EdgeSpec:
    """`src`(사용자 자리)의 `says` → `dst.tp` 입구 엣지(`t.entry`)."""
    return edge(src, dst, kind="t.entry", sp="says", tp=tp, **config)


def reply(src: str, *, sp: str = "out", dst: str = USER_NODE, **config: Any) -> EdgeSpec:
    """`src.sp` → `dst`(사용자 자리)의 `hears` 답변 엣지(`t.exit`)."""
    return edge(src, dst, kind="t.exit", sp=sp, tp="hears", **config)


def with_entries(graph: Graph, *entries: EdgeSpec) -> Graph:
    """그래프 사본에 입구 엣지(`entry(...)`)를 더한다.

    사용자 자리 `you`(`t.user`)가 없으면 넣는다.
    """
    nodes = list(graph.nodes)
    if all(n.id != USER_NODE for n in nodes):
        nodes.insert(0, node(USER_NODE, type="t.user"))
    return graph.model_copy(update={"nodes": nodes, "edges": [*entries, *graph.edges]})


def graph(
    nodes: list[NodeSpec],
    edges: list[EdgeSpec],
    gid: str = "g1",
    *,
    entries: Sequence[str] = (),
) -> Graph:
    """테스트 그래프.

    `entries`에 노드 id를 주면 사용자 자리 `you`와 그 노드들로 가는 입구 엣지를 넣는다
    (입구는 명시해야 한다. 엔진은 그래프 모양으로 입구를 추론하지 않는다)."""
    built = Graph(id=gid, name="test", nodes=nodes, edges=edges)
    return with_entries(built, *(entry(dst) for dst in entries)) if entries else built


class RecordingSink:
    """발행 시점에 그 이벤트가 이미 저장됐는지 기록하는 EventSink."""

    def __init__(self, recorder: InMemoryRecorder) -> None:
        self.recorder = recorder
        self.events: list[Any] = []
        self.stored_at_publish: list[bool] = []

    def publish(self, event: Any) -> None:
        self.events.append(event)
        self.stored_at_publish.append(event.event_id in self.recorder.event_ids)


@dataclass
class Harness:
    registries: Registries
    recorder: InMemoryRecorder
    sink: RecordingSink
    probe: Probe
    make: Callable[..., GraphRuntime]


def make_harness() -> Harness:
    """테스트 전용 타입을 등록한 레지스트리 + 메모리 recorder + 기록 sink + probe 묶음."""
    regs = make_registries()
    recorder = InMemoryRecorder()
    sink = RecordingSink(recorder)
    probe = Probe()

    def make(**kwargs: Any) -> GraphRuntime:
        kwargs.setdefault("clock", StepClock())
        kwargs.setdefault("ids", SequentialIds("e"))
        kwargs.setdefault("services", Services({PROBE: probe}))
        return GraphRuntime(regs, recorder, sink, **kwargs)

    return Harness(regs, recorder, sink, probe, make)


@dataclass(frozen=True)
class Builders:
    node: Callable[..., NodeSpec]
    edge: Callable[..., EdgeSpec]
    graph: Callable[..., Graph]
    probe_key: ServiceKey[Probe]
    entry: Callable[..., EdgeSpec] = entry
    reply: Callable[..., EdgeSpec] = reply


BUILDERS = Builders(node=node, edge=edge, graph=graph, probe_key=PROBE)
"""테스트 그래프 작성 도우미 묶음."""
