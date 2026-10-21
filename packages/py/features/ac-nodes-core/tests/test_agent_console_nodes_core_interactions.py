"""ac-nodes-core 상호작용(1R.29): 기본 종류·`ask_user` 연결·사용자 중간 검토, fake `ask`로 끝까지.

레지스트리는 이 배포의 entry point만 로드하고 fake 백엔드를 등록한다
(design §R14.2·§R14.3·§R14.6·§R14.9).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from dataclasses import dataclass
from typing import Any

import jsonschema
import pytest

from agent_console_backend_fake import FakeBackend
from agent_console_contracts import (
    Agent,
    EdgeSpec,
    Graph,
    Interaction,
    NodeRun,
    NodeSpec,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    QUESTION,
    REVIEW,
    TOOL_PERMISSION,
    WORKSPACE_SETTINGS,
    AskUserEdge,
    NodesCoreErrorCodes,
    UserNode,
    review_response_schema,
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
    Registries,
    ResponseValidationError,
    RunHandle,
    Services,
    ValidationContext,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, ManualClock, SequentialIds, StepClock
from agent_console_teams import team_plan

DIST = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)


def _entry_points(*, exclude: set[str] = frozenset()) -> list[importlib.metadata.EntryPoint]:  # type: ignore[assignment]
    eps = importlib.metadata.distribution(DIST).entry_points
    return [ep for ep in eps if ep.group in GROUPS and ep.name not in exclude]


class _Recording(FakeBackend):
    """fake 백엔드 + 받은 요청 기록."""

    def __init__(self) -> None:
        super().__init__(ids=SequentialIds("s"), clock=StepClock())
        self.requests: list[AgentRequest] = []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        return await super().run(req, sink, cancel)


@dataclass
class Stack:
    runtime: GraphRuntime
    recorder: InMemoryRecorder
    backend: _Recording
    registries: Registries

    async def start(self, graph: Graph, text: str) -> RunHandle:
        return await self.runtime.start(graph, {"text": text})

    async def pending(self, run_id: str, count: int = 1) -> list[Interaction]:
        for _ in range(500):
            found = self.runtime.pending(run_id=run_id)
            if len(found) >= count:
                return found
            await asyncio.sleep(0.005)
        raise AssertionError("상호작용이 열리지 않았다")

    def node_runs(self, run: Run) -> dict[str, NodeRun]:
        return {nr.node_id: nr for nr in self.recorder.runs.list_node_runs(run.id)}

    def events(self, run: Run, type: str) -> list[RunEvent]:
        return [e for e in self.recorder.events.list(run.id) if e.type == type]

    def replies(self, run: Run) -> list[dict[str, Any]]:
        return [dict(e.payload) for e in self.events(run, "run.reply")]

    def interactions(self, run: Run) -> list[Interaction]:
        return self.recorder.interactions.list(run_id=run.id)


def make_stack(*agents: Agent, clock: ManualClock | None = None) -> Stack:
    regs = Registries()
    reports = load_registries(regs, entry_points=_entry_points())
    assert all(r.ok for r in reports), reports
    backend = _Recording()
    regs.backends.register("fake", backend)
    found = {a.id: a for a in agents}
    services = Services(
        {
            AGENT_LOOKUP: found.get,
            WORKSPACE_SETTINGS: WorkspaceSettings.model_validate(
                {"agent_defaults": {"backend": "fake"}}
            ),
        }
    )
    recorder = InMemoryRecorder()
    kwargs: dict[str, Any] = {"clock": StepClock(), "ids": SequentialIds("e")}
    if clock is not None:
        kwargs = {"clock": clock, "sleep": clock.sleep, "ids": SequentialIds("e")}
    runtime = GraphRuntime(regs, recorder, services=services, **kwargs)
    return Stack(runtime, recorder, backend, regs)


def agent(agent_id: str, response: str = "$agent_id:$prompt", **rule: Any) -> Agent:
    options: dict[str, Any] = {"default": {"response": response, **rule}}
    return Agent.model_validate({"id": agent_id, "name": agent_id, "backend_options": options})


def n(node_id: str, ref: str) -> NodeSpec:
    return NodeSpec.model_validate({"id": node_id, "type": "agent", "config": {"agent_ref": ref}})


def user(node_id: str = "you", **config: Any) -> NodeSpec:
    return NodeSpec.model_validate({"id": node_id, "type": "user", "config": config})


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


def team(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> Graph:
    return Graph.model_validate(
        {
            "id": "team",
            "name": "팀",
            "nodes": [x.model_dump() for x in nodes],
            "edges": [x.model_dump() for x in edges],
        }
    )


def asking_graph(**ask_config: Any) -> Graph:
    return team(
        [user(), n("a", "a")],
        [
            e("m", "you", "says", "a", "in", "message"),
            e("q", "a", "out", "you", "asks", "ask_user", **ask_config),
            e("r", "a", "out", "you", "hears", "reply"),
        ],
    )


# ---------------------------------------------------------------- 디스크립터·스키마


def _valid(schema: dict[str, Any], value: Any) -> bool:
    return jsonschema.Draft202012Validator(schema).is_valid(value)


def test_kind_schemas_accept_claude_sdk_shapes() -> None:
    """1R.30 어댑터가 여는 payload·응답 모양을 받아들인다."""
    q_req = {
        "questions": [
            {
                "question": "DB?",
                "header": "저장",
                "options": [{"label": "pg", "description": "Postgres"}, {"label": "sqlite"}],
                "multi_select": False,
            }
        ]
    }
    assert _valid(QUESTION.request_schema, q_req)
    assert _valid(QUESTION.response_schema, {"answers": {"DB?": "pg"}})
    assert _valid(QUESTION.response_schema, {"answers": {"DB?": ["pg", "sqlite"]}})
    assert _valid(QUESTION.response_schema, {"response": "직접 입력"})
    assert not _valid(QUESTION.response_schema, {})
    assert QUESTION.free_text_path == "/response"
    assert QUESTION.expire_response is None

    tp_req = {
        "tool_name": "Bash",
        "input_preview": "ls",
        "title": "t",
        "display_name": "d",
        "description": "x",
        "blocked_path": "/p",
        "decision_reason": "r",
        "tool_use_id": "tu",
        "agent_id": "ag",
    }
    assert _valid(TOOL_PERMISSION.request_schema, tp_req)
    for decision in ("allow", "allow_for_run", "deny"):
        assert _valid(TOOL_PERMISSION.response_schema, {"decision": decision})
    assert _valid(
        TOOL_PERMISSION.response_schema,
        {"decision": "allow", "message": "ok", "updated_input": {"command": "ls"}},
    )
    assert not _valid(TOOL_PERMISSION.response_schema, {"decision": "maybe"})
    assert TOOL_PERMISSION.expire_response == {"decision": "deny", "message": "사용자 응답 없음"}
    assert _valid(TOOL_PERMISSION.response_schema, TOOL_PERMISSION.expire_response)
    assert TOOL_PERMISSION.free_text_path is None

    schema = review_response_schema(["ok", "no"])
    assert _valid(schema, {"decision": "ok", "edited": "x", "feedback": "y"})
    assert not _valid(schema, {"decision": "zz"})
    assert {k.ui_hints.renderer for k in (QUESTION, TOOL_PERMISSION, REVIEW) if k.ui_hints} == {
        "choices",
        "permission",
        "review",
    }


def test_ask_user_descriptor_and_grant_narrowing() -> None:
    d = AskUserEdge.descriptor
    assert d.scheduling == "none"
    assert d.interaction is not None
    assert d.interaction.kinds == ["question", "tool_permission"]
    assert d.connects is not None
    assert (d.connects.source, d.connects.target) == (["agent"], ["user"])
    assert d.default_ports is not None
    assert d.default_ports.target == "asks"
    plan = team_plan(
        asking_graph(kinds=["question"], timeout_seconds=30, on_timeout="cancel_run"),
        node_types=[UserNode.descriptor, *(_node_descs())],
        edge_types=_edge_descs(),
    )
    grant = plan.grants["a"]
    assert (grant.kinds, grant.timeout_seconds, grant.on_timeout) == (
        ["question"],
        30,
        "cancel_run",
    )


def _node_descs() -> list[Any]:
    regs = Registries()
    load_registries(regs, entry_points=_entry_points())
    return [x.item.descriptor for x in regs.node_types.list()]


def _edge_descs() -> list[Any]:
    regs = Registries()
    load_registries(regs, entry_points=_entry_points())
    return [x.item.descriptor for x in regs.edge_types.list()]


def test_removing_entry_points_removes_kinds_and_edges() -> None:
    regs = Registries()
    load_registries(regs, entry_points=_entry_points(exclude={"ask_user", "question"}))
    assert "ask_user" not in regs.edge_types
    assert "question" not in regs.interaction_kinds
    assert {"tool_permission", "review"} <= {x.key for x in regs.interaction_kinds.list()}


def test_user_node_review_ports_and_validation() -> None:
    node = UserNode()
    config = {
        "review": {
            "decisions": [
                {"id": "approved", "label": "승인", "edit": True},
                {"id": "says", "label": "충돌"},
                {"id": "review", "label": "입력 포트 이름과 같아도 됨"},
            ],
            "kind": "nope",
        }
    }
    outputs = [p.name for p in node.resolve_ports(config).outputs]
    # 고정 출력 포트(says)와 겹치는 결정만 포트가 되지 않는다. 입력 포트 이름(review)은 써도 된다.
    assert outputs == ["says", "approved", "review"]
    regs = Registries()
    load_registries(regs, entry_points=_entry_points())
    graph = team([user("rv", **config)], [])
    ctx = ValidationContext(graph=graph, node=graph.nodes[0], registries=regs, services=Services())
    codes = {i.code for i in node.validate(config, ctx)}
    assert codes == {
        NodesCoreErrorCodes.REVIEW_RESERVED_PORT,
        NodesCoreErrorCodes.REVIEW_UNKNOWN_KIND,
    }
    assert [p.name for p in node.resolve_ports({}).outputs] == ["says"]


# ---------------------------------------------------------------- 되묻기·승인 (fake ask)


async def test_question_answered_then_completes() -> None:
    a = agent(
        "a",
        "답: $answer_1 ($answer_1_status)",
        ask=[
            {
                "kind": "question",
                "title": "질문",
                "payload": {"text": "$prompt 어느 DB?"},
                "answer_path": "/response",
            }
        ],
    )
    stack = make_stack(a)
    handle = await stack.start(asking_graph(), "설계")
    [pending] = await stack.pending(handle.run_id)
    assert pending.kind == "question"
    assert pending.node_id == "a"
    assert pending.payload == {"text": "설계 어느 DB?"}
    with pytest.raises(ResponseValidationError):
        await stack.runtime.respond(handle.run_id, pending.id, {})
    await stack.runtime.respond(handle.run_id, pending.id, {"response": "postgres"})
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert [r["text"] for r in stack.replies(run)] == ["답: postgres (answered)"]
    grant = stack.backend.requests[0].interactions
    assert grant is not None
    assert grant.kinds == ["question", "tool_permission"]


async def test_tool_permission_denied() -> None:
    a = agent(
        "a",
        "결정: $answer_1",
        ask=[
            {
                "kind": "tool_permission",
                "payload": {"tool_name": "Bash", "input_preview": "rm -rf x"},
                "answer_path": "/decision",
            }
        ],
    )
    stack = make_stack(a)
    handle = await stack.start(asking_graph(), "정리")
    [pending] = await stack.pending(handle.run_id)
    await stack.runtime.respond(handle.run_id, pending.id, {"decision": "deny", "message": "안 됨"})
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert stack.replies(run)[0]["text"] == "결정: deny"
    [closed] = stack.interactions(run)
    assert closed.status == "answered"


async def test_node_without_ask_connection_cannot_open() -> None:
    a = agent("a", "$answer_1", ask=[{"kind": "question", "payload": {"text": "?"}}])
    stack = make_stack(a)
    graph = team(
        [user(), n("a", "a")],
        [
            e("m", "you", "says", "a", "in", "message"),
            e("r", "a", "out", "you", "hears", "reply"),
        ],
    )
    handle = await stack.start(graph, "x")
    run = await handle.wait()
    assert run.status == "completed", run.error
    assert stack.replies(run)[0]["text"] == "unavailable"
    assert stack.interactions(run) == []
    assert stack.backend.requests[0].interactions is None


async def test_connection_kinds_narrow_what_can_open() -> None:
    a = agent(
        "a",
        "$answer_1",
        ask=[{"kind": "tool_permission", "payload": {"tool_name": "Bash"}}],
    )
    stack = make_stack(a)
    handle = await stack.start(asking_graph(kinds=["question"]), "x")
    run = await handle.wait()
    assert stack.replies(run)[0]["text"] == "unavailable"
    assert stack.interactions(run) == []


async def test_cancel_while_waiting() -> None:
    a = agent("a", "$answer_1", ask=[{"kind": "question", "payload": {"text": "?"}}])
    stack = make_stack(a)
    handle = await stack.start(asking_graph(), "x")
    await stack.pending(handle.run_id)
    handle.cancel()
    run = await handle.wait()
    assert run.status == "cancelled"
    [closed] = stack.interactions(run)
    assert closed.status == "cancelled"
    assert stack.replies(run) == []


# ---------------------------------------------------------------- 사용자 중간 검토 A → 사용자 → B


REVIEW_CONFIG: dict[str, Any] = {
    "review": {
        "title": "설계안을 검토해 주세요",
        "decisions": [
            {"id": "approved", "label": "승인", "edit": True, "ui_hints": {"color": "accent"}},
            {"id": "rejected", "label": "반려", "feedback": True},
        ],
        "output_template": "{content}\n\n{feedback}",
    }
}


def review_graph(**review: Any) -> Graph:
    config = {"review": {**REVIEW_CONFIG["review"], **review}}
    return team(
        [user(), user("rv", **config), n("pl", "pl"), n("be", "be")],
        [
            e("m", "you", "says", "pl", "in", "message"),
            e("h1", "pl", "out", "rv", "review", "handoff"),
            e("h2", "rv", "approved", "be", "in", "handoff"),
            e("a1", "rv", "rejected", "you", "hears", "reply", label="반려됨"),
            e("a2", "be", "out", "you", "hears", "reply"),
        ],
    )


async def test_review_approve_passes_edited_content() -> None:
    stack = make_stack(agent("pl", "설계: $prompt"), agent("be"))
    handle = await stack.start(review_graph(), "로그인")
    [pending] = await stack.pending(handle.run_id)
    assert pending.kind == "review"
    assert pending.node_id == "rv"
    assert pending.payload["content"] == "설계: 로그인"
    assert pending.payload["source_node"] == "pl"
    assert [d["id"] for d in pending.payload["decisions"]] == ["approved", "rejected"]
    assert pending.payload["decisions"][0]["ui_hints"] == {"color": "accent"}
    assert pending.response_schema["properties"]["decision"] == {"enum": ["approved", "rejected"]}
    with pytest.raises(ResponseValidationError):
        await stack.runtime.respond(handle.run_id, pending.id, {"decision": "maybe"})
    await stack.runtime.respond(
        handle.run_id, pending.id, {"decision": "approved", "edited": "고친 설계"}
    )
    run = await handle.wait()
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs["rv"].outputs == {"approved": "고친 설계\n\n"}
    assert "you" not in runs
    assert [(r["node_id"], r["text"]) for r in stack.replies(run)] == [("be", "be:고친 설계\n\n")]


async def test_review_reject_skips_downstream_and_replies() -> None:
    stack = make_stack(agent("pl", "설계: $prompt"), agent("be"))
    handle = await stack.start(review_graph(), "로그인")
    [pending] = await stack.pending(handle.run_id)
    # 반려에는 edit이 없으므로 edited는 무시된다
    await stack.runtime.respond(
        handle.run_id,
        pending.id,
        {"decision": "rejected", "feedback": "보안 보완", "edited": "무시"},
    )
    run = await handle.wait()
    assert run.status == "completed", run.error
    runs = stack.node_runs(run)
    assert runs["be"].status == "skipped"
    assert [(r["node_id"], r.get("label"), r["text"]) for r in stack.replies(run)] == [
        ("rv", "반려됨", "설계: 로그인\n\n보안 보완")
    ]


async def test_review_expired_fails_node() -> None:
    clock = ManualClock()
    stack = make_stack(agent("pl"), agent("be"), clock=clock)
    handle = await stack.start(review_graph(timeout_seconds=5), "x")
    await stack.pending(handle.run_id)
    await clock.advance(6)
    run = await handle.wait()
    runs = stack.node_runs(run)
    assert runs["rv"].status == "failed"
    assert runs["rv"].error is not None
    assert runs["rv"].error.code == NodesCoreErrorCodes.REVIEW_EXPIRED
    assert runs["be"].status == "skipped"
    [closed] = stack.interactions(run)
    assert closed.status == "expired"


async def test_user_node_without_review_still_fails_on_flow_input() -> None:
    stack = make_stack(agent("a"))
    graph = team(
        [user(), user("rv"), n("a", "a")],
        [
            e("m", "you", "says", "a", "in", "message"),
            e("h", "a", "out", "rv", "review", "handoff"),
        ],
    )
    handle = await stack.start(graph, "x")
    run = await handle.wait()
    nr = stack.node_runs(run)["rv"]
    assert nr.error is not None
    assert nr.error.code == NodesCoreErrorCodes.USER_NOT_REVIEWABLE


async def test_review_template_variables_original_source_title() -> None:
    stack = make_stack(agent("pl", "설계: $prompt"), agent("be"))
    graph = review_graph(
        output_template="[{title}] {source_node}: {original} -> {content} ({decision})"
    )
    handle = await stack.start(graph, "x")
    [pending] = await stack.pending(handle.run_id)
    await stack.runtime.respond(
        handle.run_id, pending.id, {"decision": "approved", "edited": "고침"}
    )
    run = await handle.wait()
    assert stack.node_runs(run)["rv"].outputs == {
        "approved": "[설계안을 검토해 주세요] pl: 설계: x -> 고침 (approved)"
    }


def test_review_decision_id_says_is_rejected() -> None:
    """결정 id가 고정 출력 포트 `says`면 검증 오류(정확한 경로)이고 결정 포트가 되지 않는다."""
    node = UserNode()
    config = {"review": {"decisions": [{"id": "ok", "label": "확인"}, {"id": "says"}]}}
    regs = Registries()
    load_registries(regs, entry_points=_entry_points())
    graph = team([user("rv", **config)], [])
    ctx = ValidationContext(graph=graph, node=graph.nodes[0], registries=regs, services=Services())
    issues = node.validate(config, ctx)
    assert [(i.code, i.path, i.severity) for i in issues] == [
        (NodesCoreErrorCodes.REVIEW_RESERVED_PORT, "/review/decisions/1/id", "error")
    ]
    outputs = [p.name for p in node.resolve_ports(config).outputs]
    assert outputs == ["says", "ok"]  # says는 사용자 메시지 포트 하나뿐
    # 런타임 검증 경로(엔진 validate)에서도 같은 이슈가 노드에 붙는다
    runtime = GraphRuntime(regs, InMemoryRecorder())
    found = [
        i for i in runtime.validate(graph) if i.code == NodesCoreErrorCodes.REVIEW_RESERVED_PORT
    ]
    assert [(i.node_id, i.path) for i in found] == [("rv", "/review/decisions/1/id")]
