"""ac-nodes-core 독립 위임(5R.9, design §5R.6): 연결 `delegate` + 위임 방식 `host` + 혼합 위임.

레지스트리는 이 배포와 `agent-console-delegation-host`(테스트 전용 dev 의존)의 entry point만
로드하고 fake 백엔드 규칙 `host_tool_calls`로 위임자 모델의 위임 도구 호출을 흉내 낸다.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_backend_fake import FakeBackend
from agent_console_contracts import (
    Agent,
    BackendDescriptor,
    DelegationSettings,
    EdgeInvocation,
    EdgeSpec,
    Graph,
    Interaction,
    Issue,
    ModelInfo,
    NodeRun,
    NodeSpec,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_delegation_host import HostDelegation, host_descriptor
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    WORKSPACE_SETTINGS,
    DelegateEdge,
    NodesCoreErrorCodes,
    SdkSubagentsStrategy,
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
    ComposableDelegation,
    DelegationIssueCodes,
    DelegationMember,
    DelegationNameDeclarer,
    DelegationNameGroups,
    GraphRuntime,
    Registries,
    Services,
    StaticDelegationChecks,
    duplicate_names_code,
    edge_type_descriptors,
    load_registries,
    node_type_descriptors,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock
from agent_console_teams import TeamIssueCodes, validate_team

DISTS = ("agent-console-nodes-core", "agent-console-delegation-host")
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)


def _entry_points() -> list[importlib.metadata.EntryPoint]:
    return [
        ep
        for dist in DISTS
        for ep in importlib.metadata.distribution(dist).entry_points
        if ep.group in GROUPS
    ]


@dataclass
class Recording:
    """백엔드를 감싸 요청을 기록한다. `host_tools`를 끄면 능력 없는 백엔드 흉내."""

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
    services: Services

    def runtime(self, **kwargs: Any) -> GraphRuntime:
        return GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds("e"),
            services=self.services,
            **kwargs,
        )

    async def run(self, graph: Graph, text: str, *, validate: bool = True, **kwargs: Any) -> Run:
        return await self.runtime(**kwargs).run(graph, {"text": text}, validate=validate)

    def node_runs(self, run: Run) -> dict[str, list[NodeRun]]:
        out: dict[str, list[NodeRun]] = {}
        for nr in self.recorder.runs.list_node_runs(run.id):
            out.setdefault(nr.node_id, []).append(nr)
        for runs in out.values():
            runs.sort(key=lambda nr: nr.call)
        return out

    def events(self, run: Run, type: str) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if e.type == type]

    def requests_of(self, agent_id: str) -> list[AgentRequest]:
        return [r for b in self.backends.values() for r in b.requests if r.agent.id == agent_id]

    def issues(self, graph: Graph, agents: dict[str, Agent] | None = None) -> list[str]:
        found = validate_team(
            graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
            strategies=[e.item.descriptor for e in self.registries.delegation_strategies.list()],
            agents=agents,
            workspace=WORKSPACE,
            backends={k: b.descriptor.capabilities for k, b in self.backends.items()},
        )
        return [i.code for i in found if i.severity == "error"]


WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake"}})


def make_stack(*agents: Agent) -> Stack:
    regs = Registries()
    reports = load_registries(regs, entry_points=_entry_points())
    assert all(r.ok for r in reports), reports
    backends = {
        "fake": Recording(FakeBackend(ids=SequentialIds("s"), clock=StepClock()), "fake"),
        "fake2": Recording(FakeBackend(ids=SequentialIds("t"), clock=StepClock()), "fake2"),
        "plain": Recording(
            FakeBackend(ids=SequentialIds("p"), clock=StepClock()), "plain", host_tools=False
        ),
    }
    for key, backend in backends.items():
        regs.backends.register(key, backend)
    found = {a.id: a for a in agents}
    services = Services({AGENT_LOOKUP: found.get, WORKSPACE_SETTINGS: WORKSPACE})
    return Stack(regs, InMemoryRecorder(), backends, services)


def agent(agent_id: str, response: str = "$agent_id:$prompt", **extra: Any) -> Agent:
    rules = extra.pop("rules", None)
    default = {"response": response, **extra.pop("rule", {})}
    options: dict[str, Any] = {"default": default}
    if rules is not None:
        options["rules"] = rules
    return Agent.model_validate(
        {"id": agent_id, "name": agent_id.upper(), "backend_options": options, **extra}
    )


def n(node_id: str, ref: str | None = None, *, type: str = "agent", **config: Any) -> NodeSpec:
    cfg = dict(config)
    if ref is not None:
        cfg["agent_ref"] = ref
    return NodeSpec.model_validate({"id": node_id, "type": type, "label": node_id, "config": cfg})


def you() -> NodeSpec:
    return NodeSpec(id="you", type="user", label="나")


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


def msg(dst: str) -> EdgeSpec:
    return e(f"m-{dst}", "you", "says", dst, "in", "message")


def ans(src: str, **config: Any) -> EdgeSpec:
    return e(f"a-{src}", src, "out", "you", "hears", "reply", **config)


def dele(src: str, dst: str, kind: str = "delegate", **config: Any) -> EdgeSpec:
    return e(f"{src}->{dst}", src, "delegates", dst, "delegated", kind, **config)


def ask(src: str) -> EdgeSpec:
    return e(f"q-{src}", src, "out", "you", "asks", "ask_user")


def team(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> Graph:
    return Graph.model_validate(
        {
            "id": "team",
            "name": "팀",
            "nodes": [x.model_dump() for x in nodes],
            "edges": [x.model_dump() for x in edges],
        }
    )


def call(target: str, task: str, **extra: Any) -> dict[str, Any]:
    return {"tool": "delegate", "input": {"target": target, "task": task}, "append": False, **extra}


# ---------------------------------------------------------------- 디스크립터


def test_delegate_edge_and_composable_strategies() -> None:
    d = DelegateEdge.descriptor
    assert (d.scheduling, d.invocation) == ("none", EdgeInvocation(strategy="host"))
    assert d.config_schema["properties"]["result"]["anyOf"][0]["enum"] == ["text", "reply"]
    assert SdkSubagentsStrategy.descriptor.composable is True
    assert isinstance(SdkSubagentsStrategy(), ComposableDelegation)
    assert isinstance(HostDelegation(), ComposableDelegation)


# ---------------------------------------------------------------- 독립 위임


async def test_two_targets_with_different_settings_run_in_own_sessions() -> None:
    lead = agent(
        "pl",
        "정리[$host_1][$host_2]",
        rule={"host_tool_calls": [call("be", "API: $prompt"), call("fe", "화면: $prompt")]},
    )
    stack = make_stack(lead, agent("backend", "BE($prompt)"), agent("frontend", "FE($prompt)"))
    graph = team(
        [
            you(),
            n("pl", "pl"),
            n("be", "backend", delegate_when="서버 작업", settings={"model": "m-big"}),
            n("fe", "frontend", settings={"backend": "fake2", "model": "m-small"}),
        ],
        [msg("pl"), dele("pl", "be"), dele("pl", "fe"), ans("pl"), ans("be", label="백엔드")],
    )
    assert stack.issues(graph) == []
    run = await stack.run(graph, "로그인")
    assert run.status == "completed", run.error

    runs = stack.node_runs(run)
    assert runs["pl"][0].outputs["out"] == "정리[BE(API: 로그인)][FE(화면: 로그인)]"
    (be,) = runs["be"]
    (fe,) = runs["fe"]
    assert (be.invoked_by, fe.invoked_by) == (["pl"], ["pl"])
    # 대상마다 자기 백엔드·모델·세션
    (be_req,) = stack.requests_of("backend")
    (fe_req,) = stack.requests_of("frontend")
    assert (be_req.agent.backend, be_req.agent.model) == ("fake", "m-big")
    assert (fe_req.agent.backend, fe_req.agent.model) == ("fake2", "m-small")
    assert be.backend_session_id != fe.backend_session_id
    # 위임자 요청에는 위임 도구 하나(대상 enum), 하위 에이전트 없음
    (pl_req,) = stack.requests_of("pl")
    (tool,) = pl_req.host_tools
    assert tool.input_schema["properties"]["target"]["enum"] == ["be", "fe"]
    assert "서버 작업" in tool.description
    assert pl_req.subagents == []
    # 대상의 답변 연결은 엔진이 대상 경로로 낸다
    replies = [(r.payload["node_id"], r.node_path) for r in stack.events(run, "run.reply")]
    assert ("be", ["pl", "be"]) in replies


async def test_nested_delegation_depth_two_and_runtime_limit() -> None:
    lead = agent("pl", "pl<$host_1>", rule={"host_tool_calls": [call("mid", "1단")]})
    mid = agent("mid", "mid<$host_1>", rule={"host_tool_calls": [call("leaf", "2단: $prompt")]})
    leaf = agent("leaf", "잎($prompt)")
    graph = team(
        [you(), n("pl", "pl"), n("mid", "mid"), n("leaf", "leaf")],
        [msg("pl"), dele("pl", "mid"), dele("mid", "leaf"), ans("pl")],
    )
    stack = make_stack(lead, mid, leaf)
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs["pl"][0].outputs["out"] == "pl<mid<잎(2단: 1단)>>"
    assert runs["leaf"][0].invoked_by == ["pl", "mid"]

    stack = make_stack(lead, mid, leaf)
    run = await stack.run(graph, "x", delegation_settings=DelegationSettings(max_depth=1))
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert "leaf" not in runs
    assert "delegation.depth_exceeded" in runs["pl"][0].outputs["out"]


async def test_question_inside_delegate_target_waits_and_resumes() -> None:
    """Q9: 독립 위임 대상은 자기 `ask_user` 연결로 사용자에게 되물을 수 있다."""
    lead = agent("pl", "pl<$host_1>", rule={"host_tool_calls": [call("be", "DB 고르기")]})
    be = agent(
        "be",
        "선택=$answer_1",
        rule={
            "ask": [
                {"kind": "question", "payload": {"text": "어느 DB?"}, "answer_path": "/response"}
            ]
        },
    )
    stack = make_stack(lead, be)
    graph = team(
        [you(), n("pl", "pl"), n("be", "be")],
        [msg("pl"), dele("pl", "be"), ask("be"), ans("pl")],
    )
    runtime = stack.runtime()
    handle = await runtime.start(graph, {"text": "x"})
    pending: list[Interaction] = []
    for _ in range(500):
        pending = runtime.pending(run_id=handle.run_id)
        if pending:
            break
        await asyncio.sleep(0.005)
    (question,) = pending
    assert question.node_path == ["pl", "be"]
    assert question.kind == "question"
    await runtime.respond(handle.run_id, question.id, {"response": "postgres"})
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert stack.node_runs(run)["pl"][0].outputs["out"] == "pl<선택=postgres>"
    # 위임자 세션에는 대상의 되묻기 권한이 없어도 된다(대상이 자기 세션에서 묻는다)
    (be_req,) = stack.requests_of("be")
    assert be_req.interactions is not None
    assert "question" in be_req.interactions.kinds


async def test_review_rejection_calls_writer_again_with_session() -> None:
    """검토 반려 반복: 위임자가 반려면 작성자를 다시 부른다(같은 대상은 세션을 이어 쓴다)."""
    lead = agent(
        "pl",
        "최종: $host_4",
        rule={
            "host_tool_calls": [
                call("writer", "작성"),
                call("reviewer", "검토: $host_1"),
                call("writer", "다시: $host_2", when={"contains": "반려"}),
                call("reviewer", "검토: $host_3", when={"after": 2, "contains": "반려"}),
            ]
        },
    )
    writer = agent("writer", "초안 v1", rules=[{"contains": "다시", "response": "초안 v2"}])
    reviewer = agent(
        "reviewer",
        "?",
        rules=[
            {"contains": "v1", "response": "반려: 근거 부족"},
            {"contains": "v2", "response": "승인"},
        ],
    )
    stack = make_stack(lead, writer, reviewer)
    graph = team(
        [you(), n("pl", "pl"), n("writer", "writer"), n("reviewer", "reviewer")],
        [msg("pl"), dele("pl", "writer"), dele("pl", "reviewer"), ans("pl")],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs["pl"][0].outputs["out"] == "최종: 승인"
    assert [nr.call for nr in runs["writer"]] == [0, 1]
    assert [nr.outputs["out"] for nr in runs["writer"]] == ["초안 v1", "초안 v2"]
    assert [nr.outputs["out"] for nr in runs["reviewer"]] == ["반려: 근거 부족", "승인"]
    first, second = stack.requests_of("writer")
    assert first.session is None
    assert second.session is not None
    assert second.session.session_id == runs["writer"][0].backend_session_id
    assert "반려: 근거 부족" in second.prompt


# ---------------------------------------------------------------- 혼합 위임


async def test_mixed_subagent_and_delegate_run_in_one_backend_call() -> None:
    lead = agent(
        "pl",
        "정리[$delegate_1][$host_1]",
        rule={
            "delegate": [{"to": "qa", "prompt": "검증: $prompt", "response": "QA 통과"}],
            "host_tool_calls": [call("be", "API: $prompt")],
        },
    )
    stack = make_stack(lead, agent("qa"), agent("backend", "BE($prompt)"))
    graph = team(
        [you(), n("pl", "pl"), n("qa", "qa"), n("be", "backend")],
        [
            msg("pl"),
            dele("pl", "qa", "subagent"),
            dele("pl", "be"),
            ans("pl"),
            ans("qa", label="QA", final=False),
        ],
    )
    assert TeamIssueCodes.MIXED_STRATEGIES not in stack.issues(graph)
    run = await stack.run(graph, "로그인")
    assert run.status == "completed", run.error
    (pl_req,) = stack.requests_of("pl")  # 위임자 백엔드 호출은 한 번
    assert [s.name for s in pl_req.subagents] == ["qa"]
    assert [t.name for t in pl_req.host_tools] == ["delegate"]
    assert pl_req.host_tools[0].input_schema["properties"]["target"]["enum"] == ["be"]
    runs = stack.node_runs(run)
    assert runs["pl"][0].outputs["out"] == "정리[QA 통과][BE(API: 로그인)]"
    assert "qa" not in runs  # 서브에이전트는 위임자 세션 안
    assert runs["be"][0].invoked_by == ["pl"]
    # 합친 실행에서도 서브에이전트 결과가 대상 답변으로 나간다(sink 감싸기)
    replies = [(r.payload["node_id"], r.payload["text"]) for r in stack.events(run, "run.reply")]
    assert ("qa", "QA 통과") in replies


class _InlineOnly:
    """합칠 수 없는 방식(디스크립터 composable=false, contribute 없음)."""

    descriptor = host_descriptor("t.solo").model_copy(update={"composable": False})

    def validate(self, plan: Any) -> list[Any]:
        return []

    async def run(self, plan: Any, ctx: Any) -> AgentResult:
        raise AssertionError("합칠 수 없는 방식이 섞이면 실행하지 않는다")


async def test_not_composable_mix_fails_and_duplicate_tool_names_fail() -> None:
    lead = agent("pl", "ok", rule={"host_tool_calls": [call("be", "x")]})
    stack = make_stack(lead, agent("backend"), agent("qa"))
    # 두 번째 host 인스턴스(다른 id) → 같은 기본 도구 이름 `delegate`가 겹친다
    stack.registries.delegation_strategies.register(
        "host2", HostDelegation(descriptor=host_descriptor("host2"))
    )
    graph = team(
        [you(), n("pl", "pl"), n("be", "backend"), n("qa", "qa")],
        [msg("pl"), dele("pl", "be"), dele("pl", "qa", strategy="host2"), ans("pl")],
    )
    # 저장 시점 검사가 먼저 막는다(5.2R.37). 실행 시점 합치기 검사는 검증을 끄고 확인한다.
    engine = [i.code for i in stack.runtime().validate(graph) if i.severity == "error"]
    assert engine == [DelegationIssueCodes.DUPLICATE_HOST_TOOL_NAMES]
    run = await stack.run(graph, "x", validate=False)
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.status == "failed"
    assert pl.error is not None
    assert pl.error.code == DelegationIssueCodes.DUPLICATE_HOST_TOOL_NAMES
    assert pl.error.details["issues"][0]["details"] == {"names": ["delegate"]}

    # 방식 config로 도구 이름을 바꾸면 합쳐 실행된다
    renamed = n("pl", "pl", delegation={"host2": {"tool_name": "ask_qa"}})
    nodes = [renamed if x.id == "pl" else x for x in graph.nodes]
    fixed = graph.model_copy(update={"nodes": nodes})
    stack = make_stack(lead, agent("backend"), agent("qa"))
    stack.registries.delegation_strategies.register(
        "host2", HostDelegation(descriptor=host_descriptor("host2"))
    )
    run = await stack.run(fixed, "x")
    assert run.status == "completed", run.error
    (pl_req,) = stack.requests_of("pl")
    assert sorted(t.name for t in pl_req.host_tools) == ["ask_qa", "delegate"]

    # composable이 아닌 방식이 섞이면 실행 오류(팀 검증도 막는다)
    stack = make_stack(lead, agent("backend"), agent("qa"))
    stack.registries.delegation_strategies.register("t.solo", _InlineOnly())
    solo = graph.model_copy(
        update={
            "edges": [
                dele("pl", "qa", strategy="t.solo") if x.id == "pl->qa" else x for x in graph.edges
            ]
        }
    )
    assert TeamIssueCodes.MIXED_STRATEGIES in stack.issues(solo)
    run = await stack.run(solo, "x", validate=False)
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.error is not None
    assert pl.error.code == NodesCoreErrorCodes.AGENT_MIXED_STRATEGIES
    assert pl.error.details["not_composable"] == ["t.solo"]


async def test_backend_without_host_tools_is_validation_and_run_error() -> None:
    lead = agent("pl", "ok", rule={"host_tool_calls": [call("be", "x")]})
    stack = make_stack(lead, agent("backend"), agent("qa"))
    graph = team(
        [you(), n("pl", "pl", settings={"backend": "plain"}), n("be", "backend")],
        [msg("pl"), dele("pl", "be"), ans("pl")],
    )
    assert TeamIssueCodes.BACKEND_CAPABILITY_MISSING in stack.issues(graph)
    run = await stack.run(graph, "x")
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.status == "failed"
    assert pl.error is not None
    assert pl.error.code == NodesCoreErrorCodes.DELEGATION_BACKEND_UNSUPPORTED

    # 혼합 위임에서도 방식마다 필요한 능력을 본다
    mixed = team(
        [you(), n("pl", "pl", settings={"backend": "plain"}), n("be", "backend"), n("qa", "qa")],
        [msg("pl"), dele("pl", "be"), dele("pl", "qa", "subagent"), ans("pl")],
    )
    stack = make_stack(lead, agent("backend"), agent("qa"))
    run = await stack.run(mixed, "x")
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.error is not None
    assert pl.error.code == NodesCoreErrorCodes.DELEGATION_BACKEND_UNSUPPORTED
    assert pl.error.details["capability"] == "host_tools"


# ---------------------------------------------------------------- 저장 시점 위임 검증(5.2R.37)


def saved_issues(stack: Stack, graph: Graph) -> list[Issue]:
    """서버 경로와 같은 조합: 엔진 검증(노드 타입 검사가 위임 방식 정적 검사를 부름) + 팀 규칙."""
    engine = stack.runtime().validate(graph)
    team_issues = validate_team(
        graph,
        node_types=node_type_descriptors(stack.registries),
        edge_types=edge_type_descriptors(stack.registries),
        strategies=[e.item.descriptor for e in stack.registries.delegation_strategies.list()],
        agents={"pl": agent("pl"), "backend": agent("backend"), "qa": agent("qa")},
        workspace=WORKSPACE,
        backends={k: b.descriptor.capabilities for k, b in stack.backends.items()},
        graph_checks=False,
    )
    return [*engine, *team_issues]


def _errors(issues: list[Issue]) -> list[tuple[str, str | None, str | None]]:
    return [(i.code, i.edge_id or i.node_id, i.path) for i in issues if i.severity == "error"]


async def test_invalid_tool_name_is_reported_before_run_for_renamed_strategy() -> None:
    lead = agent("pl", "ok")
    stack = make_stack(lead, agent("backend"))
    stack.registries.delegation_strategies.register(
        "zz-hand", HostDelegation(descriptor=host_descriptor("zz-hand"))
    )
    graph = team(
        [
            you(),
            n("pl", "pl", delegation={"zz-hand": {"tool_name": "bad name"}}),
            n("be", "backend"),
        ],
        [msg("pl"), dele("pl", "be", strategy="zz-hand"), ans("pl")],
    )
    assert _errors(saved_issues(stack, graph)) == [
        ("delegation.invalid_config", "pl", "/delegation/zz-hand/tool_name")
    ]
    # 실행 시점 검사(`validate(plan)`)는 그대로다
    run = await stack.run(graph, "x", validate=False)
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.error is not None
    assert pl.error.code == NodesCoreErrorCodes.AGENT_DELEGATION_INVALID


async def test_duplicate_member_is_reported_before_run() -> None:
    stack = make_stack(agent("pl", "ok"), agent("backend"))
    twice = e("pl->be#2", "pl", "delegates", "be", "delegated", "delegate")
    graph = team(
        [you(), n("pl", "pl"), n("be", "backend")],
        [msg("pl"), dele("pl", "be"), twice, ans("pl")],
    )
    assert _errors(saved_issues(stack, graph)) == [
        ("delegation.duplicate_member", "pl->be#2", None)
    ]
    run = await stack.run(graph, "x", validate=False)
    (pl,) = stack.node_runs(run)["pl"]
    assert pl.error is not None
    assert pl.error.code == NodesCoreErrorCodes.AGENT_DELEGATION_INVALID


def test_composed_name_collision_engine_and_standalone_paths_agree() -> None:
    stack = make_stack(agent("pl", "ok"), agent("backend"), agent("qa"))
    stack.registries.delegation_strategies.register(
        "host2", HostDelegation(descriptor=host_descriptor("host2"))
    )
    graph = team(
        [you(), n("pl", "pl"), n("be", "backend"), n("qa", "qa")],
        [msg("pl"), dele("pl", "be"), dele("pl", "qa", strategy="host2"), ans("pl")],
    )
    expected = [("delegation.duplicate_host_tool_names", "pl", None)]
    assert _errors(saved_issues(stack, graph)) == expected
    # 단독 ac-teams: 엔진 없이 `delegation_checks`로 주입
    standalone = validate_team(
        graph,
        node_types=node_type_descriptors(stack.registries),
        edge_types=edge_type_descriptors(stack.registries),
        strategies=[x.item.descriptor for x in stack.registries.delegation_strategies.list()],
        workspace=WORKSPACE,
        delegation_checks={x.key: x.item for x in stack.registries.delegation_strategies.list()},
    )
    assert _errors(standalone) == expected


def test_subagents_and_host_compose_without_collision_and_declare_names() -> None:
    stack = make_stack(agent("pl", "ok"), agent("backend"), agent("qa"))
    graph = team(
        [you(), n("pl", "pl"), n("be", "backend"), n("qa", "qa")],
        [msg("pl"), dele("pl", "be"), dele("pl", "qa", "subagent"), ans("pl")],
    )
    assert _errors(saved_issues(stack, graph)) == []
    sdk = SdkSubagentsStrategy()
    assert isinstance(sdk, StaticDelegationChecks)
    assert isinstance(sdk, DelegationNameDeclarer)
    member = DelegationMember(node_id="qa", edge_id="pl->qa")
    assert sdk.declared_names({}, [member]) == {DelegationNameGroups.SUBAGENT: ["qa"]}
    assert sdk.static_issues({}, [member]) == []
    assert duplicate_names_code(DelegationNameGroups.SUBAGENT) == (
        DelegationIssueCodes.DUPLICATE_SUBAGENT_NAMES
    )


# ---------------------------------------------------------------- 5.2R.43 같은 세션 여부


def _perm(**payload: Any) -> dict[str, Any]:
    return {"kind": "tool_permission", "payload": {"tool_name": "Bash", **payload}}


@pytest.mark.parametrize("strategy", [None, "zz-own"], ids=["host", "renamed"])
async def test_own_session_member_grant_and_approval_stay_in_member_session(
    strategy: str | None,
) -> None:
    """5.2R.43(J-10): `shares_session` false 방식의 대상 종류·대기 한도는 위임자 세션에 없다.

    대상이 연 도구 승인에 "이번 실행 동안 허용"으로 답해도 그 응답은 대상 NodeRun의 대기만
    푼다. 위임자 세션 grant에는 도구 승인 종류가 없어 위임자의 도구 승인은 열리지도 않는다
    (위임자 도구 실행을 허용하는 경로가 없다).
    """
    lead = agent(
        "pl",
        "pl<$host_1>|$answer_1_status",
        rule={"host_tool_calls": [call("be", "정리")], "ask": [_perm(input_preview="rm -rf")]},
    )
    be_ask = {**_perm(input_preview="ls"), "answer_path": "/decision"}
    be = agent("be", "be:$answer_1", rule={"ask": [be_ask]})
    stack = make_stack(lead, be)
    extra: dict[str, Any] = {}
    if strategy is not None:
        stack.registries.delegation_strategies.register(
            strategy, HostDelegation(descriptor=host_descriptor(strategy))
        )
        extra["strategy"] = strategy
    own_ask = e("q-pl", "pl", "out", "you", "asks", "ask_user", kinds=["question"])
    member_ask = e(
        "q-be", "be", "out", "you", "asks", "ask_user", timeout_seconds=600, on_timeout="expire"
    )
    graph = team(
        [you(), n("pl", "pl"), n("be", "be")],
        [msg("pl"), dele("pl", "be", **extra), own_ask, member_ask, ans("pl")],
    )
    runtime = stack.runtime()
    handle = await runtime.start(graph, {"text": "x"})
    pending: list[Interaction] = []
    for _ in range(500):
        pending = runtime.pending(run_id=handle.run_id)
        if pending:
            break
        await asyncio.sleep(0.005)
    try:
        (asked,) = pending
        assert asked.node_path == ["pl", "be"]
        assert asked.kind == "tool_permission"
    except BaseException:
        handle.cancel()
        await handle.wait()
        raise
    await runtime.respond(handle.run_id, asked.id, {"decision": "allow_for_run"})
    run = await handle.wait()
    assert run.status == "completed", run.error
    # 위임자의 도구 승인은 열리지 않았다(grant에 종류 없음) — 대상 승인이 넘어오지 않는다
    assert stack.node_runs(run)["pl"][0].outputs["out"] == "pl<be:allow_for_run>|unavailable"
    requested = stack.events(run, "interaction.requested")
    assert [ev.payload["interaction"]["node_id"] for ev in requested] == ["be"]
    (pl_req,) = stack.requests_of("pl")
    assert pl_req.interactions is not None
    assert pl_req.interactions.kinds == ["question"]  # 자기 연결 것만
    assert pl_req.interactions.timeout_seconds is None  # 대상 600초가 오지 않는다
    (be_req,) = stack.requests_of("be")
    assert be_req.interactions is not None
    assert "tool_permission" in be_req.interactions.kinds
    assert be_req.interactions.timeout_seconds == 600


async def test_same_session_member_still_adds_kinds_and_timeout() -> None:
    """대조: `shares_session` true 방식(sdk-subagents)은 대상 종류·한도를 위임자 세션에 더한다."""
    stack = make_stack(agent("pl", "ok"), agent("qa"))
    graph = team(
        [you(), n("pl", "pl"), n("qa", "qa")],
        [
            msg("pl"),
            dele("pl", "qa", "subagent"),
            e("q-qa", "qa", "out", "you", "asks", "ask_user", timeout_seconds=7),
            ans("pl"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    (pl_req,) = stack.requests_of("pl")
    assert pl_req.interactions is not None
    assert pl_req.interactions.kinds == ["tool_permission"]  # 방식 member_interaction_kinds
    assert pl_req.interactions.timeout_seconds == 7
