"""ac-nodes-core 에이전트 도구 공급자(X30, 5.7R.12, design §5.7R.3).

fake 백엔드 규칙 `host_tool_calls`로 모델의 도구 호출을 흉내 낸다. 공급자는 테스트 공급자
`EchoToolProvider`와 이 파일의 임의 공급자만 쓴다(특정 기능을 모른다).
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    BackendCapabilities,
    BackendDescriptor,
    EdgeSpec,
    Graph,
    Issue,
    ModelInfo,
    NodeSpec,
    Resource,
    ResourceBundle,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    TEAM_LOOKUP,
    TOOL_PROVIDERS,
    WORKSPACE_SETTINGS,
    ToolProvider,
    ToolProviderCodes,
    ToolProvision,
    ToolProvisionContext,
    drop_taken,
    provide_tools,
)
from agent_console_nodes_core.testing import EchoToolProvider
from agent_console_resources import (
    SLOT_UNSUPPORTED,
    InMemoryResources,
    declarative_type_from_data,
)
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    INTERACTION_KINDS_GROUP,
    NODE_TYPES_GROUP,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    GraphRuntime,
    HostTool,
    HostToolResult,
    Registries,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

DISTS = ("agent-console-nodes-core", "agent-console-delegation-host")
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}})
SLOT = "t.notes-slot"


@dataclass
class Recording:
    """fake 백엔드를 감싸 요청을 기록한다. `host_tools`를 끄면 능력 없는 백엔드 흉내."""

    inner: FakeBackend
    backend_id: str
    host_tools: bool = True
    requests: list[AgentRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        caps = self.inner.descriptor.capabilities.model_copy(update={"host_tools": self.host_tools})
        self.descriptor: BackendDescriptor = self.inner.descriptor.model_copy(
            update={"id": self.backend_id, "capabilities": caps}
        )

    async def list_models(self) -> list[ModelInfo]:
        return await self.inner.list_models()

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        return await self.inner.run(req, sink, cancel)


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    backends: dict[str, Recording]
    services: dict[Any, Any]

    async def run(self, graph: Graph, text: str) -> Run:
        runtime = GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds("e"),
            services=Services(self.services),
        )
        return await runtime.run(graph, {"text": text})

    def events(self, run: Run, type: str | None = None) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if type is None or e.type == type]

    def warnings(self, run: Run) -> list[dict[str, Any]]:
        return [dict(e.payload["details"]) for e in self.events(run, "log.warning")]

    def requests_of(self, agent_id: str) -> list[AgentRequest]:
        return [r for b in self.backends.values() for r in b.requests if r.agent.id == agent_id]

    def output(self, run: Run, node_id: str) -> Any:
        found = [nr for nr in self.recorder.runs.list_node_runs(run.id) if nr.node_id == node_id]
        return found[0].outputs.get("out")


def make_stack(*agents: Agent, providers: list[Any] | None = None) -> Stack:
    regs = Registries()
    eps = [
        ep
        for dist in DISTS
        for ep in importlib.metadata.distribution(dist).entry_points
        if ep.group in GROUPS
    ]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    backends = {
        "fake-agent": Recording(
            FakeBackend(ids=SequentialIds("s"), clock=StepClock()), "fake-agent"
        ),
        "plain": Recording(
            FakeBackend(ids=SequentialIds("p"), clock=StepClock()), "plain", host_tools=False
        ),
    }
    for key, backend in backends.items():
        regs.backends.register(key, backend)
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {AGENT_LOOKUP: found.get, WORKSPACE_SETTINGS: WORKSPACE}
    if providers is not None:
        services[TOOL_PROVIDERS] = providers
    return Stack(regs, InMemoryRecorder(), backends, services)


def agent(agent_id: str, response: str = "$agent_id:$prompt", **rule: Any) -> Agent:
    return Agent.model_validate(
        {
            "id": agent_id,
            "name": agent_id,
            "backend_options": {"default": {"response": response, **rule}},
        }
    )


def calls(*items: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {"host_tool_calls": [{"tool": t, "input": i, "append": False} for t, i in items]}


def n(node_id: str, ref: str | None = None, *, type: str = "agent", **config: Any) -> NodeSpec:
    cfg = dict(config)
    if type == "agent":
        cfg["agent_ref"] = ref or node_id
    return NodeSpec.model_validate({"id": node_id, "type": type, "label": node_id, "config": cfg})


def e(eid: str, src: str, sp: str, dst: str, tp: str, kind: str, **config: Any) -> EdgeSpec:
    return EdgeSpec.model_validate(
        {
            "id": eid,
            "source": {"node": src, "port": sp},
            "target": {"node": dst, "port": tp},
            "kind": kind,
            "config": config,
        }
    )


def team(nodes: list[NodeSpec], edges: list[EdgeSpec], graph_id: str = "team") -> Graph:
    return Graph.model_validate(
        {
            "id": graph_id,
            "name": graph_id,
            "nodes": [{"id": "you", "type": "user", "label": "나"}]
            + [x.model_dump() for x in nodes],
            "edges": [x.model_dump() for x in edges],
        }
    )


def solo(node_id: str = "lead", graph_id: str = "team", **config: Any) -> Graph:
    return team(
        [n(node_id, **config)],
        [
            e("m", "you", "says", node_id, "in", "message"),
            e("r", node_id, "out", "you", "hears", "reply"),
        ],
        graph_id,
    )


def dele(src: str, dst: str, kind: str = "delegate") -> EdgeSpec:
    return e(f"{src}->{dst}", src, "delegates", dst, "delegated", kind)


class Boom:
    """늘 실패하는 공급자(예외 메시지에 비밀 흉내)."""

    id = "t.boom"

    def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
        raise RuntimeError("secret-value-123")


class Wrong:
    id = "t.wrong"

    def provide(self, ctx: ToolProvisionContext) -> Any:
        return {"host_tools": []}


# ---------------------------------------------------------------- 단위


def _ctx(bundle: ResourceBundle | None = None) -> ToolProvisionContext:
    async def emit(type: str, payload: Any) -> None:
        return None

    return ToolProvisionContext(
        run_id="r",
        root_run_id="r",
        graph_id="g",
        node_id="a",
        node_path=("a",),
        agent_id="a",
        call=0,
        iteration=0,
        bundle=bundle or ResourceBundle(),
        backend_capabilities=BackendCapabilities(),
        emit=emit,
        cancel=CancelToken(),
    )


def test_echo_provider_satisfies_protocol() -> None:
    assert isinstance(EchoToolProvider(), ToolProvider)


def test_provide_tools_isolates_failures_and_dedupes() -> None:
    a = EchoToolProvider("t.a", tool_name="same")
    b = EchoToolProvider("t.b", tool_name="same")
    c = EchoToolProvider("t.c", tool_name="other")
    got = provide_tools([Boom(), a, Wrong(), b, c], _ctx())
    assert [t.name for t in got.host_tools] == ["same", "other"]
    codes = [(i.code, i.details.get("provider")) for i in got.warnings]
    assert codes == [
        (ToolProviderCodes.PROVIDER_FAILED, "t.boom"),
        (ToolProviderCodes.PROVIDER_FAILED, "t.wrong"),
        (ToolProviderCodes.DUPLICATE_NAME, "t.b"),
    ]
    # 예외 메시지(비밀이 섞일 수 있음)는 싣지 않는다
    assert "secret-value-123" not in repr(got.warnings)


def test_provide_tools_collects_consumed_slots_and_provider_warnings() -> None:
    class Warns:
        id = "t.warns"

        def provide(self, ctx: ToolProvisionContext) -> ToolProvision:
            return ToolProvision(
                consumed_slots=frozenset({"x"}),
                warnings=(Issue(severity="warning", code="t.note", message="m"),),
            )

    echo = EchoToolProvider("t.echo", slot="y")
    bundle = ResourceBundle(slots={"y": [{"prefix": ">"}]})
    got = provide_tools([Warns(), echo], _ctx(bundle))
    assert got.consumed_slots == {"x", "y"}
    assert [(i.code, i.details["provider"]) for i in got.warnings] == [("t.note", "t.warns")]
    # 칸이 없으면 도구도 없다
    assert provide_tools([echo], _ctx()).host_tools == ()


def test_drop_taken_keeps_order() -> None:
    tools = [
        HostTool(n, "", {"type": "object"}, handler=_noop) for n in ("delegate", "x", "x", "y")
    ]
    kept, issues = drop_taken(tools, ["delegate"])
    assert [t.name for t in kept] == ["x", "y"]
    assert [i.details["name"] for i in issues] == ["delegate", "x"]


async def _noop(arguments: dict[str, Any]) -> HostToolResult:
    return HostToolResult(text="")


# ---------------------------------------------------------------- 공급자 없음 = 기존 그대로


async def test_no_providers_keeps_existing_behavior() -> None:
    lead = agent("pl", "정리[$host_1]", **calls(("delegate", {"target": "be", "task": "$prompt"})))
    graph = team(
        [n("pl"), n("be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    outputs = []
    cases: tuple[list[Any] | None, ...] = (None, [])
    for providers in cases:
        stack = make_stack(lead, agent("be", "BE($prompt)"), providers=providers)
        run = await stack.run(graph, "x")
        assert run.status == "completed", run.error
        outputs.append(stack.output(run, "pl"))
        (req,) = stack.requests_of("pl")
        assert [t.name for t in req.host_tools] == ["delegate"]
        (be_req,) = stack.requests_of("be")
        assert be_req.host_tools == []
        assert not any(w["code"].startswith("tools.") for w in stack.warnings(run))
    assert outputs == ["정리[BE(x)]", "정리[BE(x)]"]


# ---------------------------------------------------------------- fake-agent 실행


async def test_provided_tool_is_called_and_emits_event() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo", prefix="메아리:", event_type="t.echoed")
    lead = agent("lead", "[$host_1]", **calls(("t_echo", {"text": "$prompt"})))
    stack = make_stack(lead, providers=[echo])
    run = await stack.run(solo(), "안녕")
    assert run.status == "completed", run.error
    assert stack.output(run, "lead") == "[메아리:안녕]"

    (req,) = stack.requests_of("lead")
    assert [t.name for t in req.host_tools] == ["t_echo"]
    (event,) = stack.events(run, "t.echoed")
    assert event.node_path == ["lead"]
    assert event.payload == {
        "provider": "t.echo",
        "tool": "t_echo",
        "tool_use_id": event.payload["tool_use_id"],
        "chars": 2,
    }
    # 백엔드의 도구 호출 이벤트와 같은 호출 id로 이어진다
    (call,) = stack.events(run, "agent.tool_call")
    assert call.payload["tool_use_id"] == event.payload["tool_use_id"]
    assert stack.events(run, "agent.tool_result")

    (ctx,) = echo.contexts
    assert (ctx.run_id, ctx.root_run_id, ctx.graph_id) == (run.id, run.id, "team")
    assert (ctx.node_id, tuple(ctx.node_path), ctx.agent_id) == ("lead", ("lead",), "lead")
    assert (ctx.call, ctx.iteration) == (0, 0)
    assert ctx.backend_capabilities.host_tools is True


async def test_backend_without_capability_warns_and_continues() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo")
    lead = agent("lead", "끝", **calls(("t_echo", {"text": "a"})))
    stack = make_stack(lead, providers=[echo])
    run = await stack.run(solo(settings={"backend": "plain"}), "x")
    assert run.status == "completed", run.error
    (req,) = stack.requests_of("lead")
    assert req.host_tools == []
    found = [w for w in stack.warnings(run) if w["code"].startswith("tools.")]
    assert found == [
        {
            "code": ToolProviderCodes.BACKEND_CAPABILITY_MISSING,
            "tools": ["t_echo"],
            "node": "lead",
        }
    ]
    assert stack.events(run, "echo.called") == []


async def test_provider_failure_is_isolated() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo")
    lead = agent("lead", "[$host_1]", **calls(("t_echo", {"text": "ok"})))
    stack = make_stack(lead, providers=[Boom(), echo])
    run = await stack.run(solo(), "x")
    assert run.status == "completed", run.error
    assert stack.output(run, "lead") == "[ok]"
    (warning,) = [w for w in stack.warnings(run) if w["code"].startswith("tools.")]
    assert warning == {
        "code": ToolProviderCodes.PROVIDER_FAILED,
        "provider": "t.boom",
        "error": "RuntimeError",
        "node": "lead",
    }
    blob = "\n".join(ev.model_dump_json() for ev in stack.events(run))
    assert "secret-value-123" not in blob


# ---------------------------------------------------------------- 위임과 함께


async def test_name_collision_with_delegation_tool_drops_provided_tool() -> None:
    clash = EchoToolProvider("t.clash", tool_name="delegate", prefix="X")
    echo = EchoToolProvider("t.echo", tool_name="t_echo")
    lead = agent("pl", "[$host_1]", **calls(("delegate", {"target": "be", "task": "$prompt"})))
    stack = make_stack(lead, agent("be", "BE($prompt)"), providers=[clash, echo])
    graph = team(
        [n("pl"), n("be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    # 위임 도구가 이긴다(공급 도구를 뺀다)
    assert stack.output(run, "pl") == "[BE(x)]"
    (req,) = stack.requests_of("pl")
    assert sorted(t.name for t in req.host_tools) == ["delegate", "t_echo"]
    dup = [w for w in stack.warnings(run) if w["code"] == ToolProviderCodes.DUPLICATE_NAME]
    assert dup == [{"code": ToolProviderCodes.DUPLICATE_NAME, "name": "delegate", "node": "pl"}]


async def test_mixed_delegation_appends_provided_tools_after_contributions() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo")
    clash = EchoToolProvider("t.clash", tool_name="delegate")
    lead = agent("pl", "[$host_1]", **calls(("t_echo", {"text": "y"})))
    stack = make_stack(lead, agent("be"), agent("qa"), providers=[clash, echo])
    graph = team(
        [n("pl"), n("be"), n("qa")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            dele("pl", "qa", "subagent"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    assert stack.output(run, "pl") == "[y]"
    (req,) = stack.requests_of("pl")
    assert [t.name for t in req.host_tools] == ["delegate", "t_echo"]
    assert [s.name for s in req.subagents]
    codes = [w["code"] for w in stack.warnings(run)]
    assert codes.count(ToolProviderCodes.DUPLICATE_NAME) == 1
    # sdk-subagents 대상은 위임자 세션 안이라 따로 공급받지 않는다
    assert [c.node_id for c in echo.contexts] == ["pl"]


async def test_host_delegate_target_gets_own_provision() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo", prefix="be:")
    lead = agent("pl", "[$host_1]", **calls(("delegate", {"target": "be", "task": "$prompt"})))
    be = agent("be", "<$host_1>", **calls(("t_echo", {"text": "$prompt"})))
    stack = make_stack(lead, be, providers=[echo])
    graph = team(
        [n("pl"), n("be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            dele("pl", "be"),
            e("r", "pl", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(graph, "일")
    assert run.status == "completed", run.error
    assert stack.output(run, "pl") == "[<be:일>]"
    by_node = {c.node_id: c for c in echo.contexts}
    assert set(by_node) == {"pl", "be"}
    assert tuple(by_node["be"].node_path) == ("pl", "be")
    assert by_node["be"].agent_id == "be"
    (event,) = stack.events(run, "echo.called")
    assert event.node_path == ["pl", "be"]


# ---------------------------------------------------------------- 소비한 칸


def _with_notes(stack: Stack, prefix: str) -> Graph:
    rtype = declarative_type_from_data(
        {
            "id": "t.notes",
            "title": "메모 칸",
            "config_schema": {"type": "object", "properties": {"prefix": {"type": "string"}}},
            "contributes": [{"slot": SLOT, "value": {"prefix": "{prefix}"}}],
        }
    )
    stack.registries.extension(RESOURCE_TYPES_EXTENSION).register("t.notes", rtype)
    stack.services[RESOURCE_LOOKUP] = InMemoryResources(
        [
            Resource.model_validate(
                {"id": "notes", "type": "t.notes", "name": "메모", "config": {"prefix": prefix}}
            )
        ]
    )
    return team(
        [
            n("lead"),
            NodeSpec.model_validate(
                {"id": "res", "type": "resource", "config": {"resource_ref": "notes"}}
            ),
        ],
        [
            e("m", "you", "says", "lead", "in", "message"),
            e("r", "lead", "out", "you", "hears", "reply"),
            e("u", "res", "provides", "lead", "resources", "uses"),
        ],
    )


async def test_consumed_slot_is_removed_from_request_and_warnings() -> None:
    lead = agent("lead", "[$host_1]", **calls(("t_echo", {"text": "a"})))

    # 대조: 공급자가 없으면 칸이 요청에 남고 "받지 않는 칸" 경고가 난다
    plain = make_stack(lead)
    run = await plain.run(_with_notes(plain, "P:"), "x")
    assert run.status == "completed", run.error
    (req,) = plain.requests_of("lead")
    assert req.bundle is not None
    assert SLOT in req.bundle.slots
    assert any(w["code"] == SLOT_UNSUPPORTED and w["slot"] == SLOT for w in plain.warnings(run))

    echo = EchoToolProvider("t.echo", tool_name="t_echo", slot=SLOT)
    stack = make_stack(lead, providers=[echo])
    run = await stack.run(_with_notes(stack, "P:"), "x")
    assert run.status == "completed", run.error
    assert stack.output(run, "lead") == "[P:a]"
    (req,) = stack.requests_of("lead")
    assert req.bundle is not None
    assert SLOT not in req.bundle.slots
    assert SLOT not in req.bundle.sources
    assert not any(w["code"] == SLOT_UNSUPPORTED for w in stack.warnings(run))
    (ctx,) = echo.contexts
    assert SLOT in ctx.bundle.slots


# ---------------------------------------------------------------- 자식 Run 상속


async def test_child_run_inherits_providers() -> None:
    echo = EchoToolProvider("t.echo", tool_name="t_echo")
    c1 = agent("c1", "<$host_1>", **calls(("t_echo", {"text": "$prompt"})))
    stack = make_stack(agent("lead"), c1, providers=[echo])
    child = solo("c1", "child")
    stack.services[TEAM_LOOKUP] = lambda team_id, version: child if team_id == "child" else None
    parent = team(
        [n("lead"), n("T", type="team", team_ref="child")],
        [
            e("m", "you", "says", "lead", "in", "message"),
            e("h", "lead", "out", "T", "in", "handoff"),
            e("r", "T", "out", "you", "hears", "reply"),
        ],
        "parent",
    )
    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    (child_run,) = [r for r in stack.recorder.runs.list() if r.parent_run_id == run.id]
    by_node = {c.node_id: c for c in echo.contexts}
    assert set(by_node) == {"lead", "c1"}
    c = by_node["c1"]
    assert (c.run_id, c.root_run_id, c.graph_id) == (child_run.id, run.id, "child")
    assert stack.output(child_run, "c1") == "<lead:hi>"
