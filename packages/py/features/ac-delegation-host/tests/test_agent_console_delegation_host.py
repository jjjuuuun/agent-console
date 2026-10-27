"""ac-delegation-host 단독 테스트: 엔진(ac-runtime) + fake 백엔드·claude-sdk(SDK 목) + 테스트
위임자.

`ac-nodes-core`(에이전트 노드)를 쓰지 않는다 — 위임자 노드는 이 파일의 `HostLead`다. 대상은
ac-runtime 테스트 노드(`t.step`)이거나 `HostLead` 자신(중첩 위임)이다.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_console_backend_claude_sdk import ClaudeSdkBackend, host_tool_rule
from agent_console_backend_claude_sdk.testing import FakeSdkClient, SdkToolCall, ValidatingSink
from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendDescriptor,
    DelegationSettings,
    EdgeInvocation,
    EdgeSpec,
    EdgeTypeDescriptor,
    ErrorInfo,
    Graph,
    Issue,
    ModelInfo,
    NodeRun,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    Run,
    RunEvent,
)
from agent_console_delegation_host import (
    HOST,
    HostDelegation,
    HostDelegationCodes,
    HostDelegationConfig,
    fill,
    host_descriptor,
)
from agent_console_runtime import (
    Activation,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    ComposableDelegation,
    DelegationContribution,
    DelegationIssueCodes,
    DelegationMember,
    DelegationNameDeclarer,
    DelegationNameGroups,
    DelegationPlan,
    EnvSecretProvider,
    GraphRuntime,
    NodeContext,
    NodeResult,
    NodeRunView,
    Registries,
    SecretResolver,
    StaticDelegationChecks,
    SubagentSpec,
    ValidationContext,
    apply_contribution,
    duplicate_names_code,
    merge_contributions,
)
from agent_console_runtime.testing import (
    InMemoryRecorder,
    SequentialIds,
    StepClock,
    make_registries,
)

HOST_EDGE = "t.host"
"""테스트 위임 연결(invocation = `host`)."""

_LEAD_PORTS = PortSpec(
    inputs=[PortDef(name="in"), PortDef(name="delegated")],
    outputs=[PortDef(name="out"), PortDef(name="delegates")],
)


class HostEdge:
    """위임 연결 `t.host`(scheduling none, invocation `host`)."""

    descriptor = EdgeTypeDescriptor(
        id=HOST_EDGE,
        title="독립 위임(테스트)",
        scheduling="none",
        invocation=EdgeInvocation(strategy=HOST),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        return None


class HostLead:
    """테스트 위임자 `t.hlead`: config `agent`(Agent dict, fake 규칙 포함), `delegation`(방식
    config), `backend`(기본 fake).

    나가는 연결 중 디스크립터 `invocation`이 있는 것의 대상을 모아 그 방식의 `run`에 맡긴다.
    대상이 없으면 fake 백엔드를 바로 부른다(대상 노드로도 쓴다).
    """

    descriptor = NodeTypeDescriptor(id="t.hlead", title="테스트 위임자", static_ports=_LEAD_PORTS)

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return _LEAD_PORTS

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        agent = Agent.model_validate(ctx.config["agent"])
        backend_id = str(ctx.config.get("backend", "fake-agent"))
        request = AgentRequest(agent=agent, prompt=str(inputs.get("in", "")))
        members: list[DelegationMember] = []
        strategy_id: str | None = None
        for e in ctx.graph.edges:
            if e.source.node != ctx.node.id:
                continue
            invocation = ctx.registries.edge_types.get(e.kind).descriptor.invocation
            if invocation is None:
                continue
            strategy_id = invocation.strategy
            target = next(n for n in ctx.graph.nodes if n.id == e.target.node)
            members.append(
                DelegationMember(
                    node_id=target.id,
                    edge_id=e.id,
                    role=target.label,
                    delegate_when=str(target.config.get("when", "")),
                    config=dict(e.config),
                )
            )
        if strategy_id is None:
            result = await ctx.backends.get(backend_id).run(request, ctx, ctx.cancel)
        else:
            strategy = ctx.registries.delegation_strategies.get(strategy_id)
            plan = DelegationPlan(
                strategy=strategy_id,
                delegator_node_id=ctx.node.id,
                backend=backend_id,
                request=request,
                members=members,
                config=dict(ctx.config.get("delegation", {})),
            )
            errors = [i for i in strategy.validate(plan) if i.severity == "error"]
            if errors:
                return NodeResult(
                    status="failed",
                    error=ErrorInfo(code=errors[0].code, message=errors[0].message),
                )
            result = await strategy.run(plan, ctx)
        if result.status != "succeeded":
            return NodeResult(status="failed", error=result.error, usage=result.usage)
        return NodeResult(status="succeeded", outputs={"out": result.text}, usage=result.usage)


@dataclass
class NoHostTools:
    """`capabilities.host_tools = false`인 백엔드(감싼 fake)."""

    inner: FakeBackend
    descriptor: BackendDescriptor = field(init=False)

    def __post_init__(self) -> None:
        caps = self.inner.descriptor.capabilities.model_copy(update={"host_tools": False})
        self.descriptor = self.inner.descriptor.model_copy(
            update={"id": "plain", "capabilities": caps}
        )

    async def list_models(self) -> list[ModelInfo]:
        return await self.inner.list_models()

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        return await self.inner.run(req, sink, cancel)


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder

    def runtime(self, **kwargs: Any) -> GraphRuntime:
        kwargs.setdefault("clock", StepClock())
        kwargs.setdefault("ids", SequentialIds("e"))
        return GraphRuntime(self.registries, self.recorder, **kwargs)

    def node_runs(self, run: Run) -> list[NodeRun]:
        return list(self.recorder.runs.list_node_runs(run.id))

    def events(self, run: Run, type: str | None = None) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if type is None or e.type == type]


def make_stack() -> Stack:
    regs = make_registries()
    regs.node_types.register("t.hlead", HostLead())
    regs.edge_types.register(HOST_EDGE, HostEdge())
    regs.delegation_strategies.register(HOST, HostDelegation())
    fake = FakeBackend(ids=SequentialIds("s"), clock=StepClock())
    regs.backends.register("fake-agent", fake)
    regs.backends.register("plain", NoHostTools(fake))
    return Stack(regs, InMemoryRecorder())


def lead_agent(agent_id: str, rule: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """fake 규칙 하나(항상 맞음)를 가진 에이전트 dict."""
    options: dict[str, Any] = {"default": dict(rule or {"response": "$prompt"})}
    return {"id": agent_id, "name": agent_id, "backend_options": options}


def node(node_id: str, type: str, label: str | None = None, **config: Any) -> NodeSpec:
    return NodeSpec.model_validate({"id": node_id, "type": type, "label": label, "config": config})


def host_edge(src: str, dst: str, tp: str = "in", **config: Any) -> EdgeSpec:
    """위임 연결(대상 포트 `tp`: `t.step`은 `in`, `t.hlead`는 `delegated`)."""
    return EdgeSpec.model_validate(
        {
            "id": f"{src}->{dst}",
            "source": {"node": src, "port": "delegates"},
            "target": {"node": dst, "port": tp},
            "kind": HOST_EDGE,
            "config": config,
        }
    )


def team(nodes: list[NodeSpec], edges: list[EdgeSpec], entry: str) -> Graph:
    """입구(`t.entry`, Run 입력 `text`) 하나를 가진 그래프."""
    you = NodeSpec(id="you", type="t.user")
    first = EdgeSpec.model_validate(
        {
            "id": "entry",
            "source": {"node": "you", "port": "says"},
            "target": {"node": entry, "port": "in"},
            "kind": "t.entry",
            "config": {"key": "text"},
        }
    )
    return Graph(id="g", name="g", nodes=[you, *nodes], edges=[first, *edges])


def host_rule(*calls: Mapping[str, Any], response: str = "$prompt") -> dict[str, Any]:
    return {"response": response, "host_tool_calls": [dict(c) for c in calls]}


def call(target: str, task: str, **extra: Any) -> dict[str, Any]:
    return {"tool": "delegate", "input": {"target": target, "task": task}, "append": False, **extra}


def by_node(stack: Stack, run: Run) -> dict[str, list[NodeRun]]:
    out: dict[str, list[NodeRun]] = {}
    for nr in stack.node_runs(run):
        out.setdefault(nr.node_id, []).append(nr)
    return out


# ---------------------------------------------------------------- 디스크립터·등록


def test_descriptor_rules_are_values() -> None:
    d = HostDelegation().descriptor
    assert d.id == HOST
    assert d.composable is True
    assert d.max_depth is None
    assert d.allows_outgoing_flow is False
    assert d.member_interaction_kinds is None
    assert d.requires_backend_capability == "host_tools"
    assert d.shares_session is False  # 대상은 자기 세션(5.2R.43, 결정 J-10)
    assert d.member_fields == list(AgentSettings.model_fields)
    props = d.config_schema["properties"]
    assert props["tool_name"]["default"] == "delegate"
    assert props["target_param"]["default"] == "target"
    assert props["task_param"]["default"] == "task"
    assert host_descriptor("other").id == "other"


def test_entry_point_registers_host() -> None:
    eps = importlib.metadata.distribution("agent-console-delegation-host").entry_points
    (ep,) = [e for e in eps if e.group == "agent_console.delegation_strategies"]
    assert ep.name == HOST
    impl = ep.load()()
    assert impl.descriptor.id == ep.name
    assert isinstance(impl, ComposableDelegation)


def test_fill_is_safe_substitution() -> None:
    assert fill("{a}-{b}-{a.__class__}-{0}", {"a": 1}) == "1-{b}-{a.__class__}-{0}"


# ---------------------------------------------------------------- 도구 모양·검증


def _plan(config: Mapping[str, Any] | None = None, **members: str) -> DelegationPlan:
    return DelegationPlan(
        strategy=HOST,
        delegator_node_id="lead",
        backend="fake-agent",
        request=AgentRequest(agent=Agent(id="lead", name="lead"), prompt="p"),
        members=[
            DelegationMember(node_id=k, edge_id=f"lead->{k}", role=k.upper(), delegate_when=v)
            for k, v in members.items()
        ],
        config=dict(config or {}),
    )


def test_contribute_builds_one_tool_with_target_enum() -> None:
    plan = _plan(a="설계할 때", b="검토할 때")
    contribution = HostDelegation().contribute(plan, cast(NodeContext, object()))
    (tool,) = contribution.host_tools
    assert tool.name == "delegate"
    assert tool.input_schema["properties"]["target"]["enum"] == ["a", "b"]
    assert tool.input_schema["required"] == ["target", "task"]
    assert "- a: A — 설계할 때" in tool.description
    assert "- b: B — 검토할 때" in tool.description
    assert contribution.subagents == []


def test_config_renames_tool_and_params() -> None:
    plan = _plan(
        {
            "tool_name": "hand_off",
            "target_param": "who",
            "task_param": "what",
            "target_line": "*{id}",
        },
        a="",
    )
    (tool,) = HostDelegation().contribute(plan, cast(NodeContext, object())).host_tools
    assert tool.name == "hand_off"
    assert set(tool.input_schema["properties"]) == {"who", "what"}
    assert "*a" in tool.description


@pytest.mark.parametrize(
    ("config", "members", "code"),
    [
        ({}, {}, HostDelegationCodes.NO_MEMBERS),
        ({"tool_name": "has space"}, {"a": ""}, HostDelegationCodes.INVALID_CONFIG),
        ({"target_param": "x", "task_param": "x"}, {"a": ""}, HostDelegationCodes.INVALID_CONFIG),
        ({"unknown": 1}, {"a": ""}, HostDelegationCodes.INVALID_CONFIG),
    ],
)
def test_validate_reports_errors(
    config: dict[str, Any], members: dict[str, str], code: str
) -> None:
    issues = HostDelegation().validate(_plan(config, **members))
    assert code in [i.code for i in issues]


def test_validate_duplicate_member_and_result_mode() -> None:
    plan = _plan(a="")
    dup = plan.members[0]
    bad = dup.model_copy(update={"config": {"result": "html"}})
    plan = plan.model_copy(update={"members": [dup, bad]})
    codes = [i.code for i in HostDelegation().validate(plan)]
    assert HostDelegationCodes.DUPLICATE_MEMBER in codes
    assert HostDelegationCodes.INVALID_RESULT_MODE in codes
    assert HostDelegationConfig().tool_name == "delegate"


# ---------------------------------------------------------------- 저장 시점 정적 검사(5.2R.37)


def test_static_protocols_are_satisfied() -> None:
    impl = HostDelegation()
    assert isinstance(impl, StaticDelegationChecks)
    assert isinstance(impl, DelegationNameDeclarer)


def test_static_issues_result_mode_and_rules_outside_schema() -> None:
    members = _plan(a="", b="").members
    bad = members[1].model_copy(update={"config": {"result": "html"}})
    issues = HostDelegation().static_issues(
        {"target_param": "x", "task_param": "x"}, [members[0], bad]
    )
    by_code = {i.code: i for i in issues}
    mode = by_code[HostDelegationCodes.INVALID_RESULT_MODE]
    assert (mode.edge_id, mode.path) == ("lead->b", "/result")
    rule = by_code[HostDelegationCodes.INVALID_CONFIG]
    assert rule.path is None  # 호출자가 위임자·경로 접두를 채운다
    assert rule.node_id is None


def test_static_issues_leave_schema_violations_to_general_rule() -> None:
    # 스키마로 표현되는 문제(도구 이름 형식·모르는 키)는 ac-teams 일반 규칙이 낸다(중복 방지)
    members = _plan(a="").members
    assert HostDelegation().static_issues({"tool_name": "has space", "x": 1}, members) == []
    assert HostDelegation().static_issues({}, members) == []


def test_declared_names_follow_config_and_custom_result_key() -> None:
    impl = HostDelegation(descriptor=host_descriptor("zz-other"), result_key="shape")
    members = _plan(a="").members
    assert impl.declared_names({}, members) == {DelegationNameGroups.HOST_TOOL: ["delegate"]}
    assert impl.declared_names({"tool_name": "ask_qa"}, members) == {
        DelegationNameGroups.HOST_TOOL: ["ask_qa"]
    }
    assert impl.declared_names({"tool_name": "has space"}, members) == {}
    bad = members[0].model_copy(update={"config": {"shape": "html", "result": "also-ignored"}})
    (issue,) = impl.static_issues({}, [bad])
    assert issue.path == "/shape"
    assert duplicate_names_code(DelegationNameGroups.HOST_TOOL) == (
        DelegationIssueCodes.DUPLICATE_HOST_TOOL_NAMES
    )


# ---------------------------------------------------------------- 엔진으로 실행


async def test_two_targets_run_as_their_own_node_runs() -> None:
    stack = make_stack()
    lead = lead_agent(
        "lead",
        host_rule(
            call("a", "A 해: $prompt"),
            call("b", "B 해: $prompt"),
            response="정리: $host_1 / $host_2",
        ),
    )
    graph = team(
        [
            node("lead", "t.hlead", agent=lead),
            node("a", "t.step", "설계", when="설계할 때", outputs={"out": "A결과"}),
            node("b", "t.step", "검토"),
        ],
        [host_edge("lead", "a"), host_edge("lead", "b")],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "일"})
    assert run.status == "completed", run.error
    runs = by_node(stack, run)
    (lead_run,) = runs["lead"]
    out = lead_run.outputs["out"]
    assert out.startswith("정리: A결과 / ")
    # 기본 결과 = 대상 첫 출력 포트(t.step 기본 출력 = 받은 입력 → 첫 입력 포트 `in`에 할 일)
    assert json.loads(out.split(" / ", 1)[1]) == {"in": "B 해: 일"}
    for nid in ("a", "b"):
        (nr,) = runs[nid]
        assert nr.invoked_by == ["lead"]
        assert nr.call == 0
    calls = stack.events(run, "agent.tool_call")
    assert [c.payload["name"] for c in calls] == ["delegate", "delegate"]


async def test_failed_target_is_error_result_and_run_completes() -> None:
    stack = make_stack()
    lead = lead_agent(
        "lead",
        host_rule(
            call("a", "해"),
            response="$host_1_status|$host_1",
        ),
    )
    graph = team(
        [node("lead", "t.hlead", agent=lead), node("a", "t.step", fail=True)],
        [host_edge("lead", "a")],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    (lead_run,) = by_node(stack, run)["lead"]
    status, text = lead_run.outputs["out"].split("|", 1)
    assert status == "failed"
    assert "대상 a 실행이 끝나지 못했습니다(failed" in text
    results = stack.events(run, "agent.tool_result")
    assert [r.payload["is_error"] for r in results] == [True]


def test_failure_text_uses_only_redacted_error_values() -> None:
    """5.2R.43: 기본·사용자 `failure_text`의 `{code}`·`{message}`는 가린 값만 쓴다.

    이름 바꾼 방식 id로 확인한다."""
    secret = "sk-very-secret-value-0123456789"
    secrets = SecretResolver([EnvSecretProvider({"API_KEY": secret})])
    assert secrets.resolve("secret://API_KEY") == secret  # 실행 중 해석된 비밀
    ctx = cast(NodeContext, SimpleNamespace(secrets=secrets))
    view = NodeRunView(
        node_id="a",
        node_type="t.step",
        status="failed",
        error=ErrorInfo(code=f"x.{secret}", message=f"인증 실패 key={secret} 끝"),
    )
    strategy = HostDelegation(descriptor=host_descriptor("zz-hand"))
    default = strategy.failure_text(ctx, HostDelegationConfig(), "a", view)
    assert secret not in default
    assert "[REDACTED]" in default
    assert default.startswith("대상 a 실행이 끝나지 못했습니다(failed")
    custom = HostDelegationConfig(failure_text="{target}:{code}:{message}:{status}")
    text = strategy.failure_text(ctx, custom, "a", view)
    assert text == "a:x.[REDACTED]:인증 실패 key=[REDACTED] 끝:failed"
    # 오류 정보가 없으면 빈 값
    bare = NodeRunView(node_id="a", node_type="t.step", status="cancelled")
    assert strategy.failure_text(ctx, custom, "a", bare) == "a:::cancelled"


async def test_failed_target_secret_never_reaches_delegator_output() -> None:
    secret = "sk-very-secret-value-0123456789"
    stack = make_stack()
    lead = lead_agent("lead", host_rule(call("a", "해"), response="$host_1"))
    graph = team(
        [
            node("lead", "t.hlead", agent=lead),
            node("a", "t.step", secret="secret://API_KEY", leak="error"),
        ],
        [host_edge("lead", "a")],
        entry="lead",
    )
    resolver = SecretResolver([EnvSecretProvider({"API_KEY": secret})])
    run = await stack.runtime(secrets=resolver).run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    (lead_run,) = by_node(stack, run)["lead"]
    assert secret not in lead_run.outputs["out"]
    assert "bad [REDACTED]" in lead_run.outputs["out"]


async def test_unknown_target_and_empty_task_do_not_invoke() -> None:
    stack = make_stack()
    lead = lead_agent(
        "lead",
        host_rule(
            call("zzz", "해"),
            call("a", "  "),
            response="$host_1_status;$host_2_status;$host_1",
        ),
    )
    graph = team(
        [node("lead", "t.hlead", agent=lead), node("a", "t.step")],
        [host_edge("lead", "a")],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    runs = by_node(stack, run)
    assert "a" not in runs
    first, second, text = runs["lead"][0].outputs["out"].split(";", 2)
    assert (first, second) == ("failed", "failed")
    assert "알 수 없는 대상입니다: zzz" in text


async def test_reply_result_mode_returns_target_reply_text() -> None:
    stack = make_stack()
    lead = lead_agent("lead", host_rule(call("a", "해"), response="$host_1"))
    reply = EdgeSpec.model_validate(
        {
            "id": "a-reply",
            "source": {"node": "a", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "t.exit",
            "config": {"label": "설계"},
        }
    )
    graph = team(
        [
            node("lead", "t.hlead", agent=lead),
            node("a", "t.step", outputs={"out": "설계안", "extra": "부가"}),
        ],
        [host_edge("lead", "a", result="reply"), reply],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    assert by_node(stack, run)["lead"][0].outputs["out"] == "설계안"
    replies = stack.events(run, "run.reply")
    assert [(r.payload["node_id"], r.node_path) for r in replies] == [("a", ["lead", "a"])]


async def test_backend_without_host_tools_fails() -> None:
    stack = make_stack()
    lead = lead_agent("lead", host_rule(call("a", "해")))
    graph = team(
        [node("lead", "t.hlead", agent=lead, backend="plain"), node("a", "t.step")],
        [host_edge("lead", "a")],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "x"})
    (lead_run,) = by_node(stack, run)["lead"]
    assert lead_run.status == "failed"
    assert lead_run.error is not None
    assert lead_run.error.code == HostDelegationCodes.BACKEND_UNSUPPORTED


async def test_nested_delegation_depth_two_and_setting_limit() -> None:
    mid = lead_agent("mid", host_rule(call("leaf", "깊이 2: $prompt"), response="mid<$host_1>"))
    lead = lead_agent("lead", host_rule(call("mid", "깊이 1"), response="lead<$host_1>"))
    graph = team(
        [
            node("lead", "t.hlead", agent=lead),
            node("mid", "t.hlead", agent=mid),
            node("leaf", "t.step", outputs={"out": "잎"}),
        ],
        [host_edge("lead", "mid", "delegated"), host_edge("mid", "leaf")],
        entry="lead",
    )
    stack = make_stack()
    run = await stack.runtime().run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    runs = by_node(stack, run)
    assert runs["lead"][0].outputs["out"] == "lead<mid<잎>>"
    assert runs["leaf"][0].invoked_by == ["lead", "mid"]

    limited = make_stack()
    run = await limited.runtime(delegation_settings=DelegationSettings(max_depth=1)).run(
        graph, {"text": "x"}
    )
    assert run.status == "completed", run.error
    runs = by_node(limited, run)
    assert "leaf" not in runs
    assert "delegation.depth_exceeded" in runs["lead"][0].outputs["out"]


# ---------------------------------------------------------------- claude-sdk(SDK 목, 실호출 없음)

SDK = "claude-agent-sdk"
SERVER = "platform"


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        result="위임 끝",
    )


def _factory(script: list[Any]) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def make(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script)
        clients.append(client)
        return client

    return clients, make


def _lead() -> dict[str, Any]:
    return {"id": "lead", "name": "Lead", "backend_options": {"host_tool_server": SERVER}}


async def test_claude_sdk_tool_call_invokes_target_node() -> None:
    call = SdkToolCall(server=SERVER, tool="delegate", arguments={"target": "a", "task": "설계"})
    rule = host_tool_rule(SERVER, "delegate")
    script = [
        SystemMessage(
            subtype="init",
            data={"session_id": "s1", "mcp_servers": [{"name": SERVER, "status": "connected"}]},
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="tu1", name=rule, input=call.arguments)], model="m"
        ),
        call,
        UserMessage(content=[ToolResultBlock(tool_use_id="tu1", content="r", is_error=False)]),
        _result(),
    ]
    clients, make = _factory(script)
    stack = make_stack()
    stack.registries.backends.register(SDK, ClaudeSdkBackend(client_factory=make, environ={}))
    graph = team(
        [
            node("lead", "t.hlead", agent=_lead(), backend=SDK),
            node("a", "t.step", outputs={"out": "설계안"}),
        ],
        [host_edge("lead", "a")],
        entry="lead",
    )
    run = await stack.runtime().run(graph, {"text": "x"})
    assert run.status == "completed", run.error
    options = clients[0].options
    assert rule in (options.allowed_tools or [])
    assert options.mcp_servers[SERVER]["type"] == "sdk"
    assert call.results == [{"content": [{"type": "text", "text": "설계안"}], "isError": False}]
    (target,) = [nr for nr in stack.node_runs(run) if nr.node_id == "a"]
    assert target.invoked_by == ["lead"]


async def test_mixed_contributions_reach_claude_sdk_in_one_request() -> None:
    member = DelegationMember(node_id="be", edge_id="lead->be", role="백엔드")
    plan = DelegationPlan(
        strategy=HOST,
        delegator_node_id="lead",
        backend=SDK,
        request=AgentRequest(agent=Agent.model_validate({**_lead(), "backend": SDK}), prompt="p"),
        members=[member],
    )
    host = HostDelegation().contribute(plan, cast(NodeContext, object()))
    sub = DelegationContribution(
        subagents=[SubagentSpec(name="qa", description="검증", prompt="검증한다")]
    )
    merged, issues = merge_contributions([sub, host])
    assert issues == []
    clients, make = _factory([_result()])
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    result = await backend.run(
        apply_contribution(plan.request, merged), ValidatingSink(), CancelToken()
    )
    assert result.status == "succeeded"
    options = clients[0].options
    assert set(options.agents or {}) == {"qa"}
    assert options.mcp_servers[SERVER]["type"] == "sdk"
    assert host_tool_rule(SERVER, "delegate") in (options.allowed_tools or [])
