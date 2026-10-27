"""ac-nodes-core: fake 백엔드로 팀 구성 그래프를 끝까지 실행한다(design §R1.3 모양들).

레지스트리는 이 배포의 entry point(설치 메타데이터)만 로드하고 fake 백엔드를 등록한다.
계층·순차·병렬·혼합·팀원 입구·중간 답변, 설정 층·세션·리소스 묶음·위임 답변을 본다.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    BackendDescriptor,
    EdgeInteraction,
    EdgeSpec,
    EdgeTypeDescriptor,
    Graph,
    ModelInfo,
    NodeRun,
    NodeSpec,
    Resource,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    RUN_FILES_ROOT,
    SESSIONS,
    WORKSPACE_SETTINGS,
    HandoffEdge,
    MessageEdge,
    NodesCoreErrorCodes,
    ReplyEdge,
    SubagentEdge,
)
from agent_console_resources import InMemoryResources, load_resource_types
from agent_console_runtime import (
    DELEGATION_STRATEGIES_GROUP,
    EDGE_TYPES_GROUP,
    NODE_TYPES_GROUP,
    Activation,
    AgentRequest,
    AgentResult,
    BackendEventSink,
    CancelToken,
    EdgeType,
    GraphRuntime,
    NodeRunView,
    Registries,
    Services,
    SessionRef,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

DIST = "agent-console-nodes-core"
PLUGIN_GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP)


def plugin_entry_points() -> list[importlib.metadata.EntryPoint]:
    eps = importlib.metadata.distribution(DIST).entry_points
    return [ep for ep in eps if ep.group in PLUGIN_GROUPS]


@dataclass
class Recording:
    """백엔드를 감싸 요청을 기록한다(실행은 감싼 백엔드가 한다)."""

    inner: Any
    requests: list[AgentRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.descriptor: BackendDescriptor = self.inner.descriptor

    async def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = await self.inner.list_models()
        return models

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        result: AgentResult = await self.inner.run(req, sink, cancel)
        return result


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    backend: Recording
    agents: dict[str, Agent]
    services: dict[Any, Any]

    def runtime(self) -> GraphRuntime:
        return GraphRuntime(
            self.registries,
            self.recorder,
            clock=StepClock(),
            ids=SequentialIds("e"),
            services=Services(self.services),
        )

    async def run(self, graph: Graph, text: str, **extra: Any) -> Run:
        return await self.runtime().run(graph, {"text": text}, **extra)

    def node_runs(self, run: Run) -> dict[str, NodeRun]:
        return {nr.node_id: nr for nr in self.recorder.runs.list_node_runs(run.id)}

    def events(self, run: Run, type: str | None = None) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if type is None or e.type == type]

    def replies(self, run: Run) -> list[dict[str, Any]]:
        return [dict(e.payload) for e in self.events(run, "run.reply")]

    def request_of(self, agent_id: str) -> AgentRequest:
        return next(r for r in self.backend.requests if r.agent.id == agent_id)


def agent(agent_id: str, response: str = "$agent_id:$prompt", **extra: Any) -> Agent:
    options: dict[str, Any] = {"default": {"response": response}}
    if "rules" in extra:
        options["rules"] = extra.pop("rules")
    return Agent.model_validate(
        {"id": agent_id, "name": agent_id.upper(), "backend_options": options, **extra}
    )


def make_stack(*agents: Agent, workspace: WorkspaceSettings | None = None) -> Stack:
    regs = Registries()
    reports = load_registries(regs, entry_points=plugin_entry_points())
    assert all(r.ok for r in reports), reports
    backend = Recording(FakeBackend(ids=SequentialIds("s"), clock=StepClock()))
    regs.backends.register("fake-agent", backend)
    found = {a.id: a for a in agents}
    services: dict[Any, Any] = {
        AGENT_LOOKUP: found.get,
        WORKSPACE_SETTINGS: workspace
        or WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake-agent"}}),
    }
    return Stack(regs, InMemoryRecorder(), backend, found, services)


def n(node_id: str, ref: str | None = None, *, type: str = "agent", **config: Any) -> NodeSpec:
    cfg = dict(config)
    if ref is not None:
        cfg["agent_ref"] = ref
    return NodeSpec.model_validate({"id": node_id, "type": type, "label": node_id, "config": cfg})


def you(node_id: str = "you") -> NodeSpec:
    return NodeSpec(id=node_id, type="user", label="나")


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


def msg(eid: str, dst: str, **config: Any) -> EdgeSpec:
    return e(eid, "you", "says", dst, "in", "message", **config)


def ans(eid: str, src: str, **config: Any) -> EdgeSpec:
    return e(eid, src, "out", "you", "hears", "reply", **config)


def hand(eid: str, src: str, dst: str) -> EdgeSpec:
    return e(eid, src, "out", dst, "in", "handoff")


def sub(eid: str, src: str, dst: str, **config: Any) -> EdgeSpec:
    return e(eid, src, "delegates", dst, "delegated", "subagent", **config)


def team(nodes: list[NodeSpec], edges: list[EdgeSpec], **extra: Any) -> Graph:
    return Graph.model_validate(
        {
            "id": "team",
            "name": "팀",
            "nodes": [x.model_dump() for x in nodes],
            "edges": [x.model_dump() for x in edges],
            **extra,
        }
    )


# ---------------------------------------------------------------- 모양별 실행


async def test_hierarchy_delegates_in_one_session_and_replies_per_result() -> None:
    lead = agent(
        "pl",
        rules=[
            {
                "contains": "구현",
                "delegate": [
                    {"to": "be", "prompt": "API: $prompt", "response": "BE 완료($prompt)"},
                    {"to": "qa", "prompt": "검증: $prompt", "response": "QA 통과"},
                ],
                "response": "정리: $delegate_1 / $delegate_2",
            }
        ],
    )
    stack = make_stack(
        lead, agent("backend-lead", description="API 담당", role="백엔드"), agent("qa-lead")
    )
    graph = team(
        [
            you(),
            n("pl", "pl"),
            n("be", "backend-lead", delegate_when="서버 작업일 때"),
            n("qa", "qa-lead", role="검증"),
        ],
        [
            msg("m1", "pl"),
            sub("d1", "pl", "be"),
            sub("d2", "pl", "qa"),
            ans("a1", "be", label="백엔드", final=False),
            ans("a2", "pl"),
        ],
    )
    run = await stack.run(graph, "로그인 구현")
    assert run.status == "completed", run.error

    # 위임받는 노드는 스케줄되지 않는다(NodeRun 없음).
    # 사용자 노드도 흐름 입력이 없어 실행되지 않는다.
    assert set(stack.node_runs(run)) == {"pl"}
    assert stack.node_runs(run)["pl"].outputs == {
        "out": "정리: BE 완료(API: 로그인 구현) / QA 통과"
    }

    req = stack.request_of("pl")
    specs = {s.name: s for s in req.subagents}
    assert set(specs) == {"be", "qa"}
    assert specs["be"].actor == "backend-lead"
    assert (
        specs["be"].description == "백엔드 — 서버 작업일 때"
    )  # 노드 delegate_when > 정의 description
    assert specs["qa"].description == "검증"  # 노드 role, 정의 description 비어 있음

    started = stack.events(run, "agent.subagent_started")
    assert [(ev.actor, ev.node_path) for ev in started] == [
        ("backend-lead", ["pl", "be"]),
        ("qa-lead", ["pl", "qa"]),
    ]
    # 위임 결과마다 대상의 답변(중간), 끝에 위임자 답변. 결과는 잘리지 않은 전체 텍스트.
    replies = stack.replies(run)
    assert [(r["node_id"], r["text"], r["final"], r.get("label")) for r in replies] == [
        ("be", "BE 완료(API: 로그인 구현)", False, "백엔드"),
        ("pl", "정리: BE 완료(API: 로그인 구현) / QA 통과", True, None),
    ]
    be_reply = stack.events(run, "run.reply")[0]
    assert be_reply.node_path == ["pl", "be"]
    assert be_reply.actor == "backend-lead"


async def test_sequential_handoff_passes_results_in_order() -> None:
    stack = make_stack(agent("a"), agent("b"), agent("c"))
    graph = team(
        [you(), n("a", "a"), n("b", "b"), n("c", "c")],
        [msg("m", "a"), hand("h1", "a", "b"), hand("h2", "b", "c"), ans("r", "c")],
    )
    run = await stack.run(graph, "시작")
    assert run.status == "completed", run.error
    assert [r["text"] for r in stack.replies(run)] == ["c:b:a:시작"]
    # 각 노드는 별도 세션(자기 NodeRun·backend_session_id)
    runs = stack.node_runs(run)
    sessions = {runs[x].backend_session_id for x in "abc"}
    assert len(sessions) == 3
    assert None not in sessions


async def test_parallel_fan_out_and_join_all() -> None:
    stack = make_stack(agent("a"), agent("b"), agent("c"), agent("d"))
    graph = team(
        [
            you(),
            n("a", "a"),
            n("b", "b"),
            n("c", "c"),
            NodeSpec.model_validate(
                {"id": "d", "type": "agent", "config": {"agent_ref": "d"}, "join": "all"}
            ),
        ],
        [
            msg("m", "a"),
            hand("h1", "a", "b"),
            hand("h2", "a", "c"),
            hand("h3", "b", "d"),
            hand("h4", "c", "d"),
            ans("r", "d"),
        ],
    )
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert {k: v.status for k, v in runs.items()} == dict.fromkeys("abcd", "succeeded")
    # join all: d는 b·c가 모두 끝난 뒤 한 번 실행된다
    assert runs["d"].started_at is not None
    assert runs["d"].started_at > max(runs["b"].ended_at or 0, runs["c"].ended_at or 0)
    assert sum(1 for r in stack.backend.requests if r.agent.id == "d") == 1
    assert len(stack.replies(run)) == 1


async def test_mixed_delegation_and_handoff() -> None:
    lead = agent(
        "lead",
        rules=[{"delegate": [{"to": "dev", "response": "코드"}], "response": "결과: $delegate_1"}],
    )
    stack = make_stack(lead, agent("dev"), agent("rev"))
    graph = team(
        [you(), n("lead", "lead"), n("dev", "dev"), n("rev", "rev")],
        [msg("m", "lead"), sub("d", "lead", "dev"), hand("h", "lead", "rev"), ans("r", "rev")],
    )
    run = await stack.run(graph, "작업")
    assert run.status == "completed", run.error
    assert set(stack.node_runs(run)) == {"lead", "rev"}
    assert [r["text"] for r in stack.replies(run)] == ["rev:결과: 코드"]
    assert [r.agent.id for r in stack.backend.requests] == ["lead", "rev"]
    assert stack.request_of("rev").subagents == []


async def test_member_as_entry_without_leader() -> None:
    stack = make_stack(agent("pl"), agent("be"))
    graph = team(
        [you(), n("pl", "pl"), n("be", "be")],
        [msg("m", "be"), ans("r", "be")],
    )
    run = await stack.run(graph, "바로 받기")
    assert run.status == "completed", run.error
    assert set(stack.node_runs(run)) == {"be"}  # 연결 없는 pl은 스케줄되지 않는다
    assert stack.replies(run)[0]["text"] == "be:바로 받기"


async def test_intermediate_reply_before_final() -> None:
    stack = make_stack(agent("a"), agent("b"))
    graph = team(
        [you(), n("a", "a"), n("b", "b")],
        [
            msg("m", "a"),
            hand("h", "a", "b"),
            ans("r1", "a", label="중간", final=False, order=1),
            ans("r2", "b", order=2),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    replies = stack.replies(run)
    assert [(r["node_id"], r["final"], r.get("label"), r.get("order")) for r in replies] == [
        ("a", False, "중간", 1),
        ("b", True, None, 2),
    ]


async def test_user_node_with_flow_input_is_scheduled() -> None:
    """흐름 입력이 있으면 사용자 노드도 스케줄된다(검토 실행은 상호작용 플러그인 몫)."""
    stack = make_stack(agent("a"))
    graph = team(
        [you(), you("review"), n("a", "a")],
        [msg("m", "a"), e("h", "a", "out", "review", "hears", "handoff")],
    )
    run = await stack.run(graph, "q")
    runs = stack.node_runs(run)
    assert "you" not in runs
    assert runs["review"].status == "failed"
    assert runs["review"].error is not None
    assert runs["review"].error.code == NodesCoreErrorCodes.USER_NOT_REVIEWABLE


async def test_message_input_key_and_template() -> None:
    stack = make_stack(agent("a"))
    graph = team(
        [you(), n("a", "a")],
        [msg("m", "a", input_key="request", template="요청: {message} ({who})"), ans("r", "a")],
    )
    run = await stack.runtime().run(graph, {"request": "로그인", "who": "민수"})
    assert run.status == "completed", run.error
    assert stack.request_of("a").prompt == "요청: 로그인 (민수)"


# ---------------------------------------------------------------- 설정 층·세션·상호작용


async def test_effective_settings_layers_and_prompt_template() -> None:
    workspace = WorkspaceSettings.model_validate(
        {"agent_defaults": {"backend": "fake-agent", "model": "m-common", "system_prompt": "공통"}}
    )
    stack = make_stack(agent("a", model="m-agent"), agent("b"), workspace=workspace)
    graph = team(
        [
            you(),
            n("a", "a"),
            n(
                "b",
                "b",
                settings={
                    "system_prompt": "노드",
                    "prompt_template": "[{node}] {inputs} / 원문 {message}",
                },
            ),
        ],
        [msg("m", "a"), hand("h", "a", "b"), ans("r", "b")],
        settings={"model": "m-team"},
    )
    run = await stack.run(graph, "hi")
    assert run.status == "completed", run.error
    a_req, b_req = stack.request_of("a"), stack.request_of("b")
    assert (a_req.agent.model, a_req.agent.system_prompt) == ("m-agent", "공통")
    assert (b_req.agent.model, b_req.agent.system_prompt) == ("m-team", "노드")
    assert b_req.agent.backend == "fake-agent"
    assert b_req.prompt == "[b] a:hi / 원문 hi"


async def test_session_continue_and_fresh() -> None:
    stack = make_stack(agent("a"), agent("b", session="fresh"))
    stack.services[SESSIONS] = {
        "a": SessionRef(backend="fake-agent", session_id="old-a"),
        "b": SessionRef(backend="fake-agent", session_id="old-b"),
    }
    graph = team(
        [you(), n("a", "a"), n("b", "b")],
        [msg("m", "a"), hand("h", "a", "b"), ans("r", "b")],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    session = stack.request_of("a").session
    assert session is not None
    assert session.session_id == "old-a"
    assert stack.request_of("b").session is None


async def test_interaction_grant_is_passed_with_member_kinds_filtered() -> None:
    """디스크립터 `interaction`이 있는 연결(이름 무관)로 grant를 계산해 요청에 싣는다."""

    class AskEdge:
        descriptor = EdgeTypeDescriptor(
            id="x.ask",
            title="묻기 테스트",
            scheduling="none",
            interaction=EdgeInteraction(kinds=["question", "tool_permission"]),
        )

        def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
            return None

    lead = agent("lead", rules=[{"delegate": [{"to": "dev"}], "response": "ok"}])
    stack = make_stack(lead, agent("dev"))
    ask: EdgeType = AskEdge()
    stack.registries.edge_types.register("x.ask", ask)
    graph = team(
        [you(), n("lead", "lead"), n("dev", "dev")],
        [
            msg("m", "lead"),
            sub("d", "lead", "dev"),
            ans("r", "lead"),
            e("q1", "lead", "out", "you", "asks", "x.ask", kinds=["question"]),
            e("q2", "dev", "out", "you", "asks", "x.ask", timeout_seconds=30),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    grant = stack.request_of("lead").interactions
    assert grant is not None
    # 위임자 question + 대상은 sdk-subagents member_interaction_kinds(tool_permission)만
    assert grant.kinds == ["question", "tool_permission"]


# ---------------------------------------------------------------- 리소스 묶음


def _resources(tmp_path: Path) -> InMemoryResources:
    return InMemoryResources(
        [
            Resource.model_validate(
                {
                    "id": "team-guide",
                    "type": "instruction",
                    "name": "팀 지침",
                    "config": {"text": "팀 규칙"},
                }
            ),
            Resource.model_validate(
                {
                    "id": "spec",
                    "type": "file",
                    "name": "스펙",
                    "config": {"name": "docs/spec.md"},
                    "content": {"file": "spec.md", "media_type": "text/markdown"},
                }
            ),
        ],
        contents={"spec": "# 스펙 본문"},
    )


async def test_resource_node_attaches_bundle_and_writes_files(tmp_path: Path) -> None:
    lead = agent("lead", rules=[{"delegate": [{"to": "dev"}], "response": "ok"}])
    stack = make_stack(lead, agent("dev"))
    load_resource_types(stack.registries.extension(RESOURCE_TYPES_EXTENSION))
    stack.services[RESOURCE_LOOKUP] = _resources(tmp_path)
    stack.services[RUN_FILES_ROOT] = str(tmp_path / "runs")
    graph = team(
        [
            you(),
            n("lead", "lead"),
            n("dev", "dev"),
            NodeSpec.model_validate(
                {"id": "guide", "type": "resource", "config": {"resource_ref": "team-guide"}}
            ),
            NodeSpec.model_validate(
                {"id": "doc", "type": "resource", "config": {"resource_ref": "spec"}}
            ),
        ],
        [
            msg("m", "lead"),
            sub("d", "lead", "dev"),
            ans("r", "lead"),
            e("u1", "guide", "provides", "lead", "resources", "uses"),
            e("u2", "doc", "provides", "lead", "resources", "uses"),
            e("u3", "guide", "provides", "dev", "resources", "uses"),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    assert "guide" not in stack.node_runs(run)  # executable=false

    req = stack.request_of("lead")
    assert req.bundle is not None
    assert req.bundle.slots["instructions"]
    files = req.bundle.slots["files"]
    assert len(files) == 1
    written = Path(files[0]["path"])
    assert written == (tmp_path / "runs" / run.id / "lead" / "docs" / "spec.md").resolve()
    assert written.read_text(encoding="utf-8") == "# 스펙 본문"
    assert "content" not in files[0]
    # 위임 대상의 묶음은 대상 노드 층에서 따로 만든다
    member = req.subagents[0]
    assert member.bundle is not None
    assert "files" not in member.bundle.slots
    assert member.bundle.slots["instructions"]


async def test_missing_resource_service_warns_and_runs() -> None:
    stack = make_stack(agent("a", resources=[{"ref": "x"}]))
    graph = team([you(), n("a", "a")], [msg("m", "a"), ans("r", "a")])
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    assert stack.request_of("a").bundle is None
    codes = [
        dict(w.payload).get("details", {}).get("code") for w in stack.events(run, "log.warning")
    ]
    assert NodesCoreErrorCodes.AGENT_RESOURCES_UNAVAILABLE in codes


# ---------------------------------------------------------------- R0: 이름에 기대지 않음


async def test_engine_and_plugin_work_with_renamed_edge_kinds() -> None:
    """연결 종류를 다른 id로 등록해도(디스크립터 속성은 같음) 같은 실행이 된다."""
    lead = agent("lead", rules=[{"delegate": [{"to": "dev", "response": "D"}], "response": "L"}])
    stack = make_stack(lead, agent("dev"))
    renamed: dict[str, EdgeType] = {
        "z.in": MessageEdge(),
        "z.out": ReplyEdge(),
        "z.call": SubagentEdge(),
        "z.next": HandoffEdge(),
    }
    for key, impl in renamed.items():
        impl.descriptor = impl.descriptor.model_copy(update={"id": key})
        stack.registries.edge_types.register(key, impl)
    graph = team(
        [you(), n("lead", "lead"), n("dev", "dev"), n("tail", "dev")],
        [
            e("m", "you", "says", "lead", "in", "z.in"),
            e("d", "lead", "delegates", "dev", "delegated", "z.call"),
            e("h", "lead", "out", "tail", "in", "z.next"),
            e("r1", "dev", "out", "you", "hears", "z.out"),
            e("r2", "tail", "out", "you", "hears", "z.out"),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    assert [(r["node_id"], r["text"]) for r in stack.replies(run)] == [
        ("dev", "D"),
        ("tail", "dev:L"),
    ]


async def test_agent_not_found_fails_node() -> None:
    stack = make_stack()
    graph = team([you(), n("a", "ghost")], [msg("m", "a")])
    run = await stack.run(graph, "q", validate=False)
    nr = stack.node_runs(run)["a"]
    assert nr.status == "failed"
    assert nr.error is not None
    assert nr.error.code == NodesCoreErrorCodes.AGENT_NOT_FOUND


@pytest.mark.parametrize("setting", [{"backend": "nope"}])
async def test_unknown_backend_fails_node(setting: Mapping[str, Any]) -> None:
    stack = make_stack(agent("a"))
    graph = team([you(), n("a", "a", settings=dict(setting))], [msg("m", "a")])
    issues = stack.runtime().validate(graph)
    assert any(i.code == NodesCoreErrorCodes.AGENT_UNKNOWN_BACKEND for i in issues)
    run = await stack.run(graph, "q", validate=False)
    nr = stack.node_runs(run)["a"]
    assert nr.error is not None
    assert nr.error.code == NodesCoreErrorCodes.AGENT_UNKNOWN_BACKEND


# ---------------------------------------------------------------- QA 추가 (1R.8 검증)


def _join_all_graph(prompt_template: str | None = None) -> Graph:
    d_config: dict[str, Any] = {"agent_ref": "d"}
    if prompt_template is not None:
        d_config["settings"] = {"prompt_template": prompt_template}
    return team(
        [
            you(),
            n("a", "a"),
            NodeSpec.model_validate(
                {"id": "b", "type": "agent", "label": "설계", "config": {"agent_ref": "b"}}
            ),
            n("c", "c"),
            NodeSpec.model_validate(
                {"id": "d", "type": "agent", "config": d_config, "join": "all"}
            ),
        ],
        [
            msg("m", "a"),
            hand("h1", "a", "b"),
            hand("h2", "a", "c"),
            hand("h3", "b", "d"),
            hand("h4", "c", "d"),
            ans("r", "d"),
        ],
    )


async def test_parallel_join_all_delivers_every_value() -> None:
    """join all 합류 값이 모두 d 프롬프트에 들어간다(§R3.2-4, 1R.35). 기본 = "보낸 노드: 값"."""
    stack = make_stack(agent("a"), agent("b"), agent("c"), agent("d"))
    run = await stack.run(_join_all_graph(), "x")
    assert run.status == "completed", run.error
    prompt = stack.request_of("d").prompt
    assert prompt == "설계: b:a:x\n\nc: c:a:x"


async def test_parallel_join_all_format_from_settings_layers() -> None:
    """값별 형식·구분자를 공통 층·노드 층 설정(데이터)으로 바꾸면 프롬프트가 달라진다."""
    workspace = WorkspaceSettings.model_validate(
        {
            "agent_defaults": {
                "backend": "fake-agent",
                "prompt_input_template": "- {source} => {value}",
            }
        }
    )
    stack = make_stack(agent("a"), agent("b"), agent("c"), agent("d"), workspace=workspace)
    graph = _join_all_graph()
    d = next(nd for nd in graph.nodes if nd.id == "d")
    d.config["settings"] = {"prompt_input_separator": "\n---\n"}
    run = await stack.run(graph, "x")
    assert run.status == "completed", run.error
    assert stack.request_of("d").prompt == "- 설계 => b:a:x\n---\n- c => c:a:x"


async def test_parallel_join_all_uses_prompt_template() -> None:
    stack = make_stack(agent("a"), agent("b"), agent("c"), agent("d"))
    run = await stack.run(_join_all_graph("[{node}] 합류\n{inputs}\n(원문 {message})"), "x")
    assert run.status == "completed", run.error
    prompt = stack.request_of("d").prompt
    assert prompt == "[d] 합류\n설계: b:a:x\n\nc: c:a:x\n(원문 x)"


async def test_qa_file_content_and_secret_do_not_leak_into_events(tmp_path: Path) -> None:
    stack = make_stack(agent("lead"))
    load_resource_types(stack.registries.extension(RESOURCE_TYPES_EXTENSION))
    stack.services[RESOURCE_LOOKUP] = _resources(tmp_path)
    stack.services[RUN_FILES_ROOT] = str(tmp_path / "runs")
    graph = team(
        [
            you(),
            n("lead", "lead"),
            NodeSpec.model_validate(
                {"id": "doc", "type": "resource", "config": {"resource_ref": "spec"}}
            ),
        ],
        [
            msg("m", "lead"),
            ans("r", "lead"),
            e("u", "doc", "provides", "lead", "resources", "uses"),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    blob = "\n".join(ev.model_dump_json() for ev in stack.events(run))
    assert "# 스펙 본문" not in blob


# ---------------------------------------------------------------- 2R.12 항목 파일 트리(skill·rule)


def _tree_resources() -> InMemoryResources:
    return InMemoryResources(
        [
            Resource.model_validate(
                {"id": "review", "type": "skill", "name": "리뷰", "config": {"name": "review"}}
            ),
            Resource.model_validate(
                {
                    "id": "api",
                    "type": "rule",
                    "name": "API",
                    "config": {"paths": ["src/**"], "text": "검증 먼저"},
                }
            ),
            Resource.model_validate(
                {
                    "id": "fmt",
                    "type": "hook",
                    "name": "fmt",
                    "config": {"event": "PostToolUse", "command": "fmt"},
                }
            ),
            Resource.model_validate(
                {
                    "id": "sneaky",
                    "type": "file",
                    "name": "sneaky",
                    "config": {"name": "_bundle/lead/skills/x/SKILL.md"},
                    "content": {"file": "a.md"},
                }
            ),
        ],
        contents={
            "review": {"SKILL.md": b"# review", "scripts/run.sh": b"echo"},
            "sneaky": "x",
        },
    )


async def test_item_trees_written_per_node_and_reserved_dir_protected(tmp_path: Path) -> None:
    lead = agent("lead", rules=[{"delegate": [{"to": "dev"}], "response": "ok"}])
    stack = make_stack(lead, agent("dev"))
    load_resource_types(stack.registries.extension(RESOURCE_TYPES_EXTENSION))
    stack.services[RESOURCE_LOOKUP] = _tree_resources()
    stack.services[RUN_FILES_ROOT] = str(tmp_path / "runs")
    graph = team(
        [
            you(),
            n("lead", "lead"),
            n("dev", "dev"),
            *(
                NodeSpec.model_validate(
                    {"id": f"res-{ref}", "type": "resource", "config": {"resource_ref": ref}}
                )
                for ref in ("review", "api", "fmt", "sneaky")
            ),
        ],
        [
            msg("m", "lead"),
            sub("d", "lead", "dev"),
            ans("r", "lead"),
            *(
                e(f"u-{ref}", f"res-{ref}", "provides", "lead", "resources", "uses")
                for ref in ("review", "api", "fmt", "sneaky")
            ),
            e("u-dev", "res-review", "provides", "dev", "resources", "uses"),
        ],
    )
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    req = stack.request_of("lead")
    assert req.bundle is not None
    tree_root = (tmp_path / "runs" / run.id / "lead" / "_bundle" / "lead").resolve()
    (skill,) = req.bundle.slots["skills"]
    assert skill["tree_root"] == str(tree_root)
    assert skill["root"] == str(tree_root / "skills" / "review")
    assert {f["name"] for f in skill["files"]} == {"SKILL.md", "scripts/run.sh"}
    assert all("content" not in f for f in skill["files"])
    assert (tree_root / "skills" / "review" / "SKILL.md").read_bytes() == b"# review"
    (rule,) = req.bundle.slots["rules"]
    rule_file = tree_root / "rules" / "api" / ".claude" / "rules" / "api.md"
    assert rule["root"] == str(tree_root / "rules" / "api")
    assert rule_file.read_text(encoding="utf-8").startswith("---\npaths:")
    assert req.bundle.slots["hooks"][0]["command"] == "fmt"
    # 파일 칸은 예약 폴더(_bundle)에 쓰지 못한다
    assert req.bundle.slots.get("files") == []
    assert (tree_root / "skills" / "x").exists() is False
    # 위임 대상은 자기 폴더(이름 = 대상 노드 id)에 따로 쓴다
    member = req.subagents[0]
    assert member.bundle is not None
    dev_root = (tmp_path / "runs" / run.id / "dev" / "_bundle" / "dev").resolve()
    assert member.bundle.slots["skills"][0]["tree_root"] == str(dev_root)


# ---------------------------------------------------------------- 4R.9: 실행 폴더·맥락


async def test_request_carries_run_folder_and_context_for_hook_probe(tmp_path: Path) -> None:
    rule = {"hook_probe": [{"event": "Stop", "after": "end"}], "response": "ok"}
    stack = make_stack(agent("lead", rules=[rule], observe={"hook_probe": True}))
    stack.services[RUN_FILES_ROOT] = str(tmp_path / "runs")
    graph = team([you(), n("lead", "lead")], [msg("m", "lead"), ans("r", "lead")])
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    req = stack.request_of("lead")
    folder = tmp_path / "runs" / run.id / "lead"
    assert req.run_folder == str(folder)
    assert req.run_context == {"run_id": run.id, "node_path": "lead"}
    assert req.observe == {"hook_probe": True}
    (record_file,) = (folder / "hook-probe").iterdir()  # fake 흉내 기록(hook-probe-jsonl 경로 규칙)
    assert '"run_id": "' + run.id in record_file.read_text(encoding="utf-8")


async def test_request_without_run_files_root_has_no_folder() -> None:
    stack = make_stack(agent("lead"))
    graph = team([you(), n("lead", "lead")], [msg("m", "lead"), ans("r", "lead")])
    run = await stack.run(graph, "q")
    assert run.status == "completed", run.error
    req = stack.request_of("lead")
    assert req.run_folder is None
    assert req.run_context["run_id"] == run.id
