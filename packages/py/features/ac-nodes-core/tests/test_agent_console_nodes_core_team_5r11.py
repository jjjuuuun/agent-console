"""ac-nodes-core 중첩 팀 노드 `team`(5R.11, design §5R.7): fake 백엔드로 끝까지 실행.

2단 중첩, 버전 고정, 답변 고르기, 자기·순환 참조, 깊이 한도, 조회 끄기, 자식 대기(live·parked),
자식 안 조건 연결, 반복 영역 안 중첩 팀, 대화 세션 경로 키, 팀 층 덮어쓰기, 정적 검증.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_console_backend_fake import FakeBackend
from agent_console_contracts import (
    Agent,
    DelegationSettings,
    EdgeSpec,
    Graph,
    Issue,
    KnownIssueCodes,
    NodeRun,
    NodeSpec,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    Run,
    RunReplyPayload,
    WaitInfo,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    SESSIONS,
    TEAM_CHILD_WAITING,
    TEAM_LOOKUP,
    WORKSPACE_SETTINGS,
    NodesCoreErrorCodes,
    TeamNode,
    child_sessions,
    pick_replies,
    session_path_key,
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
    ChildRunPreparation,
    ChildRunRequest,
    GraphRuntime,
    NodeContext,
    NodeResult,
    Registries,
    Services,
    SessionRef,
    ValidationContext,
    edge_type_descriptors,
    load_registries,
    node_type_descriptors,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock
from agent_console_teams import TeamIssueCodes, team_plan, validate_team

DIST = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)
WORKSPACE = WorkspaceSettings.model_validate({"agent_defaults": {"backend": "fake"}})


class Recording(FakeBackend):
    def __init__(self) -> None:
        super().__init__(ids=SequentialIds("s"), clock=StepClock())
        self.requests: list[AgentRequest] = []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        return await super().run(req, sink, cancel)


class ParkNode:
    """테스트 노드: 늘 parked wait(`NodeResult(waiting)`)로 끝난다."""

    descriptor = NodeTypeDescriptor(
        id="t.park",
        title="멈춤",
        static_ports=PortSpec(inputs=[PortDef(name="in")], outputs=[PortDef(name="out")]),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        return self.descriptor.static_ports or PortSpec()

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        return NodeResult(status="waiting", wait=WaitInfo(reason="t.later"))


class Shelf:
    """팀 구성 조회 흉내(`TEAM_LOOKUP`): (id, 버전) → 그래프, 받은 요청 기록."""

    def __init__(self) -> None:
        self.latest: dict[str, Graph] = {}
        self.versions: dict[tuple[str, str], Graph] = {}
        self.calls: list[tuple[str, str | None]] = []

    def add(self, graph: Graph, version: str | None = None) -> None:
        if version is None:
            self.latest[graph.id] = graph
        else:
            self.versions[(graph.id, version)] = graph

    def __call__(self, team_id: str, version: str | None) -> Graph | None:
        self.calls.append((team_id, version))
        if version is None:
            return self.latest.get(team_id)
        return self.versions.get((team_id, version))


@dataclass
class Stack:
    registries: Registries
    recorder: InMemoryRecorder
    backend: Recording
    shelf: Shelf
    agents: dict[str, Agent]
    extra: dict[Any, Any] = field(default_factory=dict)
    lookup: bool = True
    _runtime: GraphRuntime | None = None

    def services(self) -> Services:
        items: dict[Any, Any] = {AGENT_LOOKUP: self.agents.get, WORKSPACE_SETTINGS: WORKSPACE}
        if self.lookup:
            items[TEAM_LOOKUP] = self.shelf
        items.update(self.extra)
        return Services(items)

    def runtime(self) -> GraphRuntime:
        """스택 하나에 런타임 하나(Run id가 겹치지 않게). 자식 Run 준비자는 팀 규칙의 허용
        상호작용을 넣는다(통합 서버에서는 실행 모듈이 일반 Run 준비로 같은 일을 한다)."""
        if self._runtime is None:
            self._runtime = GraphRuntime(
                self.registries,
                self.recorder,
                clock=StepClock(),
                ids=SequentialIds("e"),
                services=self.services(),
                child_preparer=self.prepare_child,
            )
        return self._runtime

    def prepare_child(self, request: ChildRunRequest) -> ChildRunPreparation:
        plan = team_plan(
            request.graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
        )
        return ChildRunPreparation(interaction_grants=dict(plan.grants))

    async def run(self, graph: Graph, text: str, **kwargs: Any) -> Run:
        return await self.runtime().run(graph, {"text": text}, **kwargs)

    def runs(self) -> list[Run]:
        return self.recorder.runs.list()

    def children_of(self, run: Run) -> list[Run]:
        return [r for r in self.runs() if r.parent_run_id == run.id]

    def node_runs(self, run: Run) -> dict[str, list[NodeRun]]:
        out: dict[str, list[NodeRun]] = {}
        for nr in self.recorder.runs.list_node_runs(run.id):
            out.setdefault(nr.node_id, []).append(nr)
        return out

    def replies(self, run: Run) -> list[str]:
        return [
            str(ev.payload["text"])
            for ev in self.recorder.events.list(run.id)
            if ev.type == "run.reply"
        ]

    def issues(self, graph: Graph, **kwargs: Any) -> list[Issue]:
        return validate_team(
            graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
            strategies=[e.item.descriptor for e in self.registries.delegation_strategies.list()],
            agents=self.agents,
            workspace=WORKSPACE,
            teams=self.shelf,
            **kwargs,
        )


def agent(
    agent_id: str,
    response: str | None = None,
    *,
    rule: dict[str, Any] | None = None,
    **options: Any,
) -> Agent:
    """fake 백엔드 에이전트. `rule`은 기본 규칙에 더하고 `options`는 backend_options 위에 둔다."""
    default = {"response": response or f"{agent_id}:$prompt", **(rule or {})}
    opts: dict[str, Any] = {"default": default}
    opts.update(options)
    return Agent.model_validate({"id": agent_id, "name": agent_id, "backend_options": opts})


def make_stack(*agents: Agent) -> Stack:
    regs = Registries()
    eps = [ep for ep in importlib.metadata.distribution(DIST).entry_points if ep.group in GROUPS]
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    regs.node_types.register("t.park", ParkNode())
    backend = Recording()
    regs.backends.register("fake", backend)
    return Stack(regs, InMemoryRecorder(), backend, Shelf(), {a.id: a for a in agents})


def n(node_id: str, type: str = "agent", **config: Any) -> NodeSpec:
    if type == "agent":
        config.setdefault("agent_ref", node_id)
    return NodeSpec.model_validate(
        {"id": node_id, "type": type, "label": node_id, "config": config}
    )


def team_node(node_id: str, ref: str, **config: Any) -> NodeSpec:
    return n(node_id, "team", team_ref=ref, **config)


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


def graph(graph_id: str, nodes: list[NodeSpec], edges: list[EdgeSpec], **extra: Any) -> Graph:
    return Graph.model_validate(
        {
            "id": graph_id,
            "name": graph_id,
            "nodes": [{"id": "you", "type": "user", "label": "나"}]
            + [x.model_dump(exclude_unset=True) for x in nodes],
            "edges": [x.model_dump(exclude_unset=True) for x in edges],
            **extra,
        }
    )


def chain(graph_id: str, *nodes: NodeSpec, **extra: Any) -> Graph:
    """you → nodes[0] → … → nodes[-1] → 답변."""
    edges = [e("m", "you", "says", nodes[0].id, "in", "message")]
    for a, b in itertools.pairwise(nodes):
        edges.append(e(f"h-{a.id}-{b.id}", a.id, "out", b.id, "in", "handoff"))
    edges.append(e("r", nodes[-1].id, "out", "you", "hears", "reply"))
    return graph(graph_id, list(nodes), edges, **extra)


# ---------------------------------------------------------------- 디스크립터·도우미


def test_team_descriptor_is_data() -> None:
    d = TeamNode.descriptor
    assert d.binds is not None
    assert (d.binds.kind, d.binds.field) == ("graph", "team_ref")
    assert d.role == "team"
    assert d.executable
    assert d.ui_hints is not None
    assert d.ui_hints.shape == "stacked"
    props = d.config_schema["properties"]
    assert {"team_ref", "version", "input_key", "reply", "settings"} <= props.keys()
    assert d.config_schema["required"] == ["team_ref"]
    eps = {
        ep.name: ep.value
        for ep in importlib.metadata.distribution(DIST).entry_points
        if ep.group == NODE_TYPES_GROUP
    }
    assert eps["team"] == "agent_console_nodes_core.team:TeamNode"


def test_session_path_keys_and_reply_picking() -> None:
    ref = SessionRef(backend="fake", session_id="s1")
    sessions = {"lead": ref, "T/a": ref, "T/U/b": ref, "TX/c": ref, "T/": ref}
    assert child_sessions(sessions, "T") == {"a": ref, "U/b": ref}
    assert child_sessions(child_sessions(sessions, "T"), "U") == {"b": ref}
    assert child_sessions(None, "T") == {}
    assert session_path_key("T", "a") == "T/a"

    def r(
        text: str, label: str | None = None, final: bool = True, order: int | None = None
    ) -> RunReplyPayload:
        return RunReplyPayload(
            edge_id=text, node_id=text, text=text, label=label, final=final, order=order
        )

    replies = [r("draft", "초안", final=False), r("b", "B", order=2), r("a", "A", order=1), r("z")]
    assert [x.text for x in pick_replies(replies, None)] == ["a", "b", "z"]
    assert [x.text for x in pick_replies(replies, ["B", "초안"])] == ["b", "draft"]
    assert pick_replies(replies, ["없음"]) == []


# ---------------------------------------------------------------- 실행


async def test_two_level_nesting_runs_child_runs_and_sums_usage() -> None:
    stack = make_stack(agent("lead"), agent("c1"), agent("g1"))
    stack.shelf.add(chain("grand", n("g1")))
    stack.shelf.add(chain("child", n("c1"), team_node("TG", "grand")))
    parent = chain("parent", n("lead"), team_node("T", "child"))
    assert [i.code for i in stack.issues(parent) if i.severity == "error"] == []

    run = await stack.run(parent, "hi")
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["g1:c1:lead:hi"]
    (child,) = stack.children_of(run)
    (grand,) = stack.children_of(child)
    assert (child.graph_id, child.parent_node_id, child.root_run_id) == ("child", "T", run.id)
    assert (grand.graph_id, grand.parent_node_id, grand.root_run_id) == ("grand", "TG", run.id)
    # 자식 답변은 자식 Run에만, 부모에는 team 노드의 답변만
    assert stack.replies(child) == ["g1:c1:lead:hi"]
    t_run = stack.node_runs(run)["T"][0]
    assert t_run.status == "succeeded"
    assert t_run.outputs == {"out": "g1:c1:lead:hi"}
    # 사용량: 노드 usage = 자식 totals, 부모 totals에 포함
    assert child.totals is not None
    assert t_run.usage == child.totals
    assert run.totals is not None
    assert child.totals.input_tokens is not None
    assert run.totals.input_tokens is not None
    assert run.totals.input_tokens >= child.totals.input_tokens > 0
    types = [ev.type for ev in stack.recorder.events.list(run.id)]
    assert types.count("run.child_started") == 1
    assert types.count("run.child_finished") == 1


async def test_pinned_version_runs_that_version() -> None:
    stack = make_stack(agent("old", "옛:$prompt"), agent("new", "새:$prompt"))
    stack.shelf.add(chain("child", n("new")))
    stack.shelf.add(chain("child", n("old")), version="v1")
    run = await stack.run(chain("parent", team_node("T", "child", version="v1")), "x")
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["옛:x"]
    assert ("child", "v1") in stack.shelf.calls
    latest = await stack.run(chain("parent", team_node("T", "child")), "x")
    assert stack.replies(latest) == ["새:x"]

    missing = await stack.run(chain("parent", team_node("T", "child", version="v9")), "x")
    assert missing.status == "failed"
    (t_run,) = stack.node_runs(missing)["T"]
    assert t_run.error is not None
    assert t_run.error.code == KnownIssueCodes.TEAM_TEAM_NOT_FOUND
    assert t_run.error.details == {"team": "child", "version": "v9"}


def _labelled_child() -> Graph:
    """you → w → 답변 둘(초안: 중간 결과 / 최종) + q → 답변(label 없음)."""
    return graph(
        "child",
        [n("w"), n("q")],
        [
            e("m", "you", "says", "w", "in", "message"),
            e("h", "w", "out", "q", "in", "handoff"),
            e("r1", "w", "out", "you", "hears", "reply", label="초안", final=False),
            e("r2", "q", "out", "you", "hears", "reply", label="최종"),
        ],
    )


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({}, "q:w:x"),
        ({"reply": ["초안"]}, "w:x"),
        ({"reply": ["최종", "초안"], "reply_separator": " | "}, "q:w:x | w:x"),
        ({"reply": ["없음"]}, ""),
    ],
)
async def test_reply_rule_picks_child_answers(config: dict[str, Any], expected: str) -> None:
    stack = make_stack(agent("w"), agent("q"))
    stack.shelf.add(_labelled_child())
    run = await stack.run(chain("parent", team_node("T", "child", **config)), "x")
    assert run.status == "completed", run.error
    assert stack.node_runs(run)["T"][0].outputs == {"out": expected}
    assert stack.replies(run) == [expected]


async def test_input_key_picks_value_from_object() -> None:
    class Emit:
        descriptor = NodeTypeDescriptor(
            id="t.obj",
            title="객체",
            static_ports=PortSpec(inputs=[PortDef(name="in")], outputs=[PortDef(name="out")]),
        )

        def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
            return self.descriptor.static_ports or PortSpec()

        def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
            return NodeResult(status="succeeded", outputs={"out": {"task": "고치기", "x": 1}})

    stack = make_stack(agent("w"))
    stack.registries.node_types.register("t.obj", Emit())
    stack.shelf.add(chain("child", n("w")))
    parent = chain("parent", n("o", "t.obj"), team_node("T", "child", input_key="task"))
    run = await stack.run(parent, "x")
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["w:고치기"]


@pytest.mark.parametrize("cycle", ["self", "a-b-a"])
async def test_recursive_reference_is_refused_at_run_time(cycle: str) -> None:
    stack = make_stack(agent("lead"))
    if cycle == "self":
        parent = chain("a", n("lead"), team_node("T", "a"))
        expected_path = ["a", "a"]
    else:
        parent = chain("a", n("lead"), team_node("T", "b"))
        stack.shelf.add(chain("b", team_node("TB", "a")))
        expected_path = ["a", "b", "a"]
    stack.shelf.add(parent)
    # 정적 검사(ac-teams)가 같은 코드로 막는다
    static = [i for i in stack.issues(parent) if i.code == TeamIssueCodes.TEAM_RECURSIVE]
    assert [i.details["path"] for i in static] == [expected_path]
    # 엔진은 실행 중에도 막는다(검증을 건너뛰고 돌려도)
    run = await stack.run(parent, "x")
    assert run.status == "failed"
    errors = [
        nr.error.code
        for r in [run, *stack.children_of(run)]
        for nr in stack.recorder.runs.list_node_runs(r.id)
        if nr.error is not None
    ]
    assert KnownIssueCodes.TEAM_RECURSIVE in errors


async def test_nesting_limit_is_enforced_at_run_time() -> None:
    stack = make_stack(agent("g1"))
    stack.shelf.add(chain("grand", n("g1")))
    stack.shelf.add(chain("child", team_node("TG", "grand")))
    parent = chain("parent", team_node("T", "child"))
    limit = DelegationSettings(max_nesting=1)
    run = await stack.run(parent, "x", delegation_settings=limit)
    assert run.status == "failed"
    (child,) = stack.children_of(run)
    assert stack.children_of(child) == []  # 손자 Run은 만들지 않음
    (tg,) = stack.node_runs(child)["TG"]
    assert tg.error is not None
    assert tg.error.code == KnownIssueCodes.TEAM_NESTING_EXCEEDED
    (t_run,) = stack.node_runs(run)["T"]
    assert t_run.error is not None
    assert t_run.error.details["child_run_id"] == child.id
    # 정적 검사도 같은 코드
    ws = WorkspaceSettings.model_validate(
        {"agent_defaults": {"backend": "fake"}, "delegation": {"max_nesting": 1}}
    )
    codes = [i.code for i in stack.issues(parent) if i.severity == "error"]
    assert codes == []
    tight = validate_team(
        parent,
        node_types=node_type_descriptors(stack.registries),
        edge_types=edge_type_descriptors(stack.registries),
        workspace=ws,
        teams=stack.shelf,
    )
    assert [i.code for i in tight if i.severity == "error"] == [
        KnownIssueCodes.TEAM_NESTING_EXCEEDED
    ]


async def test_lookup_off_fails_with_lookup_unavailable() -> None:
    stack = make_stack(agent("w"))
    stack.lookup = False
    run = await stack.run(chain("parent", team_node("T", "child")), "x")
    assert run.status == "failed"
    (t_run,) = stack.node_runs(run)["T"]
    assert t_run.error is not None
    assert (
        t_run.error.code == NodesCoreErrorCodes.TEAM_LOOKUP_UNAVAILABLE == "team.lookup_unavailable"
    )
    assert "link-runs-teams" in t_run.error.message
    assert stack.children_of(run) == []


async def test_child_failure_fails_node_and_on_error_handles_it() -> None:
    stack = make_stack(
        agent("fix"), agent("boom", rule={"fail": {"code": "boom", "message": "터짐"}})
    )
    stack.shelf.add(chain("child", n("boom")))  # 백엔드 실패 → 자식 Run 실패
    parent = graph(
        "parent",
        [team_node("T", "child"), n("fix")],
        [
            e("m", "you", "says", "T", "in", "message"),
            e("err", "T", "out", "fix", "in", "on_error"),
            e("r", "fix", "out", "you", "hears", "reply"),
        ],
    )
    run = await stack.run(parent, "x")
    assert run.status == "completed", run.error
    (t_run,) = stack.node_runs(run)["T"]
    assert t_run.status == "failed"
    (child,) = stack.children_of(run)
    assert child.status == "failed"
    assert t_run.error is not None
    assert t_run.error.details["child_run_id"] == child.id
    assert stack.node_runs(run)["fix"][0].status == "succeeded"


async def test_child_refused_by_validation_creates_no_child_run() -> None:
    stack = make_stack()
    stack.shelf.add(chain("child", n("ghost")))  # 에이전트 정의 없음 → 엔진 검증이 자식을 거절
    run = await stack.run(chain("parent", team_node("T", "child")), "x")
    assert run.status == "failed"
    assert stack.children_of(run) == []
    (t_run,) = stack.node_runs(run)["T"]
    assert t_run.error is not None
    assert t_run.error.code == "validation_failed"


async def test_question_inside_child_makes_parent_wait_and_resumes() -> None:
    asker = agent(
        "be",
        "선택=$answer_1",
        rule={
            "ask": [{"kind": "question", "payload": {"text": "DB?"}, "answer_path": "/response"}]
        },
    )
    stack = make_stack(asker)
    stack.shelf.add(
        graph(
            "child",
            [n("be")],
            [
                e("m", "you", "says", "be", "in", "message"),
                e("q", "be", "out", "you", "asks", "ask_user"),
                e("r", "be", "out", "you", "hears", "reply"),
            ],
        )
    )
    runtime = stack.runtime()
    handle = await runtime.start(chain("parent", team_node("T", "child")), {"text": "x"})
    for _ in range(1000):
        if runtime.pending():
            break
        await asyncio.sleep(0.005)
    (question,) = runtime.pending()
    child_id = question.run_id
    assert child_id != handle.run_id
    assert question.root_run_id == handle.run_id
    assert handle.run.status == "waiting"
    await runtime.respond(child_id, question.id, {"response": "pg"})
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert stack.replies(run) == ["선택=pg"]


async def test_parked_child_makes_team_node_wait() -> None:
    stack = make_stack(agent("w"))
    stack.shelf.add(chain("child", n("w"), n("p", "t.park")))
    run = await stack.run(chain("parent", team_node("T", "child")), "x")
    (child,) = stack.children_of(run)
    assert child.status == "waiting"
    assert run.status == "waiting"
    (t_run,) = stack.node_runs(run)["T"]
    assert t_run.status == "waiting"
    (waiting,) = [
        ev.payload
        for ev in stack.recorder.events.list(run.id)
        if ev.type == "node.waiting" and ev.node_path == ["T"]
    ]
    assert waiting["wait"]["reason"] == TEAM_CHILD_WAITING
    assert waiting["wait"]["data"] == {"child_run_id": child.id}


@pytest.mark.parametrize(("text", "branch"), [("good", "ok"), ("bad", "fix")])
async def test_when_conditions_inside_child(text: str, branch: str) -> None:
    check = agent("check", rules=[{"contains": "good", "response": "all tests PASS"}])
    stack = make_stack(check, agent("ok"), agent("fix"))
    passes = {"all": [{"path": "/output", "op": "contains", "value": "PASS"}]}
    stack.shelf.add(
        graph(
            "child",
            [n("check"), n("ok"), n("fix")],
            [
                e("m", "you", "says", "check", "in", "message"),
                e("p", "check", "out", "ok", "in", "when", conditions=passes),
                e("f", "check", "out", "fix", "in", "when", conditions={**passes, "negate": True}),
                e("a1", "ok", "out", "you", "hears", "reply"),
                e("a2", "fix", "out", "you", "hears", "reply"),
            ],
        )
    )
    run = await stack.run(chain("parent", team_node("T", "child")), text)
    assert run.status == "completed", run.error
    (child,) = stack.children_of(run)
    runs = stack.node_runs(child)
    assert runs[branch][0].status == "succeeded"
    other = "fix" if branch == "ok" else "ok"
    assert runs[other][0].status == "skipped"
    assert stack.replies(run) == [stack.replies(child)[0]]
    assert stack.replies(run)[0].startswith(f"{branch}:")


async def test_team_node_inside_loop_runs_child_each_iteration() -> None:
    """반복 영역 안 중첩 팀: 회차마다 자식 Run 하나, 정적 검증 이슈 없음."""
    stack = make_stack(agent("w"), agent("chk"))
    stack.shelf.add(chain("child", n("w")))
    parent = graph(
        "parent",
        [team_node("T", "child"), n("chk")],
        [
            e("m", "you", "says", "T", "in", "message"),
            e("h", "T", "out", "chk", "in", "handoff"),
            e("back", "chk", "out", "T", "in", "loop", max_iterations=2),
            e("r", "chk", "out", "you", "hears", "reply"),
        ],
    )
    assert [i.code for i in stack.issues(parent) if i.severity == "error"] == []
    run = await stack.run(parent, "x")
    assert run.status == "completed", run.error
    t_runs = stack.node_runs(run)["T"]
    assert sorted(nr.iteration for nr in t_runs) == [0, 1, 2]
    children = stack.children_of(run)
    assert len(children) == 3
    assert all(c.status == "completed" for c in children)
    assert all(nr.status == "succeeded" for nr in t_runs)


async def test_sessions_use_path_keys() -> None:
    stack = make_stack(agent("lead"), agent("c1"))
    stack.shelf.add(chain("child", n("c1")))
    ref = SessionRef(backend="fake", session_id="sess-c1")
    stack.extra[SESSIONS] = {
        "lead": SessionRef(backend="fake", session_id="sess-lead"),
        "T/c1": ref,
    }
    run = await stack.run(chain("parent", n("lead"), team_node("T", "child")), "x")
    assert run.status == "completed", run.error
    by_agent = {r.agent.id: r for r in stack.backend.requests}
    assert by_agent["lead"].session is not None
    assert by_agent["lead"].session.session_id == "sess-lead"
    assert by_agent["c1"].session is not None
    assert by_agent["c1"].session.session_id == "sess-c1"


async def test_settings_override_applies_to_child_team_layer() -> None:
    stack = make_stack(agent("w"))
    stack.shelf.add(chain("child", n("w"), settings={"model": "base-model"}))
    override = {"model": "override-model"}
    run = await stack.run(chain("parent", team_node("T", "child", settings=override)), "x")
    assert run.status == "completed", run.error
    (req,) = stack.backend.requests
    assert req.agent.model == "override-model"
    # 덮어쓰기는 이 자리에서만: 저장된 자식 팀 구성은 그대로
    assert stack.shelf.latest["child"].settings is not None
    assert stack.shelf.latest["child"].settings.model == "base-model"


def test_team_node_connects_with_flow_entry_reply_loop_and_conditions() -> None:
    stack = make_stack(agent("lead"))
    stack.shelf.add(chain("child", n("lead")))
    parent = graph(
        "parent",
        [team_node("T", "child"), n("lead")],
        [
            e("m", "you", "says", "T", "in", "message"),
            e("w", "T", "out", "lead", "in", "when", conditions={"all": []}),
            e("x", "T", "out", "lead", "in", "on_error"),
            e("r", "T", "out", "you", "hears", "reply"),
            e("r2", "lead", "out", "you", "hears", "reply"),
        ],
    )
    codes = [i.code for i in stack.issues(parent)]
    assert TeamIssueCodes.CONNECTS_MISMATCH not in codes
    # 팀 노드는 위임 대상이 될 수 없다(연결 규칙 데이터)
    bad = graph(
        "parent",
        [n("lead"), team_node("T", "child")],
        [
            e("m", "you", "says", "lead", "in", "message"),
            e("d", "lead", "delegates", "T", "in", "subagent"),
        ],
    )
    assert TeamIssueCodes.CONNECTS_MISMATCH in [i.code for i in stack.issues(bad)]
