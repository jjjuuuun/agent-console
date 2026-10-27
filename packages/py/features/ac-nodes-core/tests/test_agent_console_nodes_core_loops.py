"""연결 종류 `loop`(design §5R.4, 5R.5): 검토 반려 되돌리기를 fake 백엔드·상호작용으로 끝까지.

레지스트리는 이 배포의 entry point만 로드한다. 엔진은 `loop`라는 이름을 모르고 디스크립터 `cycle`만
본다(이름을 바꿔 등록한 사본으로도 같은 결과).
"""

from __future__ import annotations

import asyncio
import importlib.metadata
from typing import Any

import pytest

from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import (
    Agent,
    EdgeSpec,
    FlowSettings,
    Graph,
    Interaction,
    NodeSpec,
    Run,
    WorkspaceSettings,
)
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    DEFAULT_LOOP_MAX_ITERATIONS,
    WORKSPACE_SETTINGS,
    LoopEdge,
    LoopEdgeConfig,
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
    GraphValidationError,
    Registries,
    Services,
    load_registries,
)
from agent_console_runtime.testing import InMemoryRecorder, SequentialIds, StepClock

DIST = "agent-console-nodes-core"
GROUPS = (NODE_TYPES_GROUP, EDGE_TYPES_GROUP, DELEGATION_STRATEGIES_GROUP, INTERACTION_KINDS_GROUP)


class _Recording(FakeBackend):
    def __init__(self) -> None:
        super().__init__(ids=SequentialIds("s"), clock=StepClock())
        self.requests: list[AgentRequest] = []

    async def run(
        self, req: AgentRequest, sink: BackendEventSink, cancel: CancelToken
    ) -> AgentResult:
        self.requests.append(req)
        return await super().run(req, sink, cancel)


def make_runtime(
    *, exclude: frozenset[str] = frozenset(), extra: dict[str, Any] | None = None
) -> tuple[GraphRuntime, InMemoryRecorder, _Recording]:
    eps = [
        ep
        for ep in importlib.metadata.distribution(DIST).entry_points
        if ep.group in GROUPS and ep.name not in exclude
    ]
    regs = Registries()
    assert all(r.ok for r in load_registries(regs, entry_points=eps))
    for key, edge_type in (extra or {}).items():
        regs.edge_types.register(key, edge_type)
    backend = _Recording()
    regs.backends.register("fake-agent", backend)
    agents = {
        a.id: a
        for a in (
            Agent.model_validate(
                {
                    "id": name,
                    "name": name,
                    "backend_options": {"default": {"response": f"{name}:$prompt"}},
                }
            )
            for name in ("writer", "next")
        )
    }
    services = Services(
        {
            AGENT_LOOKUP: agents.get,
            WORKSPACE_SETTINGS: WorkspaceSettings.model_validate(
                {"agent_defaults": {"backend": "fake-agent"}}
            ),
        }
    )
    recorder = InMemoryRecorder()
    runtime = GraphRuntime(
        regs, recorder, services=services, clock=StepClock(), ids=SequentialIds("e")
    )
    return runtime, recorder, backend


def node(node_id: str, type: str, **config: Any) -> NodeSpec:
    return NodeSpec.model_validate({"id": node_id, "type": type, "config": config})


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


REVIEW = {
    "review": {
        "title": "초안 검토",
        "decisions": [
            {"id": "approved", "label": "승인"},
            {"id": "rejected", "label": "반려", "feedback": True},
        ],
        "output_template": "{feedback}",
    }
}


def review_loop(loop_kind: str = "loop", **loop_config: Any) -> Graph:
    """작성자 w → 사용자 검토 rv. 승인 → 다음 n(답변), 반려 ⇢ w(반복) + 반려 답변."""
    return Graph(
        id="team",
        name="검토 반복",
        nodes=[
            node("you", "user"),
            node("w", "agent", agent_ref="writer"),
            node("rv", "user", **REVIEW),
            node("n", "agent", agent_ref="next"),
        ],
        edges=[
            e("m", "you", "says", "w", "in", "message"),
            e("h1", "w", "out", "rv", "review", "handoff"),
            e("ok", "rv", "approved", "n", "in", "handoff"),
            e("back", "rv", "rejected", "w", "in", loop_kind, **loop_config),
            e("r1", "rv", "rejected", "you", "hears", "reply", label="반려됨"),
            e("r2", "n", "out", "you", "hears", "reply"),
        ],
    )


async def pending(runtime: GraphRuntime, run_id: str, seen: set[str]) -> Interaction:
    for _ in range(2000):
        for item in runtime.pending(run_id=run_id):
            if item.id not in seen:
                seen.add(item.id)
                return item
        await asyncio.sleep(0.002)
    raise AssertionError("검토 요청이 열리지 않았다")


async def run_reviews(
    runtime: GraphRuntime, graph: Graph, decisions: list[str], **start: Any
) -> Run:
    handle = await runtime.start(graph, {"text": "초안 써 줘"}, **start)
    seen: set[str] = set()
    for i, decision in enumerate(decisions):
        item = await pending(runtime, handle.run_id, seen)
        response: dict[str, Any] = {"decision": decision}
        if decision == "rejected":
            response["feedback"] = f"고칠 점 {i + 1}"
        await runtime.respond(handle.run_id, item.id, response)
    return await handle.wait()


def iterations(recorder: InMemoryRecorder, run: Run) -> dict[str, list[tuple[int, str]]]:
    found: dict[str, list[tuple[int, str]]] = {}
    for nr in sorted(recorder.runs.list_node_runs(run.id), key=lambda r: (r.node_id, r.iteration)):
        found.setdefault(nr.node_id, []).append((nr.iteration, nr.status))
    return found


# ---------------------------------------------------------------- 디스크립터


def test_loop_descriptor_is_data() -> None:
    desc = LoopEdge.descriptor
    assert desc.scheduling == "flow"
    assert desc.cycle is not None
    assert desc.cycle.max_iterations == DEFAULT_LOOP_MAX_ITERATIONS == 3
    assert desc.connects is not None
    assert desc.config_schema == LoopEdgeConfig.model_json_schema()
    assert "max_iterations" in desc.config_schema["properties"]


# ---------------------------------------------------------------- 검토 반려 되돌리기


async def test_review_rejections_loop_back_to_writer() -> None:
    runtime, recorder, backend = make_runtime()
    run = await run_reviews(runtime, review_loop(), ["rejected", "rejected", "approved"])

    assert run.status == "completed", run.error
    found = iterations(recorder, run)
    assert found["w"] == [(0, "succeeded"), (1, "succeeded"), (2, "succeeded")]
    assert found["rv"] == [(0, "succeeded"), (1, "succeeded"), (2, "succeeded")]
    assert found["n"] == [(0, "succeeded")]

    writer = [r for r in backend.requests if r.agent.id == "writer"]
    assert len(writer) == 3
    # 다음 회차는 직전 회차 세션을 이어 쓰고, 프롬프트는 반려 사유(새 값)만 담는다
    assert writer[0].session is None
    assert writer[1].session is not None
    assert "고칠 점 1" in writer[1].prompt
    assert "초안 써 줘" not in writer[1].prompt
    assert "고칠 점 2" in writer[2].prompt
    replies = [
        (ev.payload.get("label"), ev.payload["text"])
        for ev in recorder.events.list(run.id)
        if ev.type == "run.reply"
    ]
    assert replies[:2] == [("반려됨", "고칠 점 1"), ("반려됨", "고칠 점 2")]
    assert replies[-1][1].startswith("next:")


async def test_fresh_session_resends_carried_input() -> None:
    runtime, _, backend = make_runtime()
    graph = review_loop()
    nodes = [
        n.model_copy(update={"config": {**n.config, "settings": {"session": "fresh"}}})
        if n.id == "w"
        else n
        for n in graph.nodes
    ]
    run = await run_reviews(
        runtime, graph.model_copy(update={"nodes": nodes}), ["rejected", "approved"]
    )
    assert run.status == "completed", run.error
    writer = [r for r in backend.requests if r.agent.id == "writer"]
    assert writer[1].session is None
    assert "초안 써 줘" in writer[1].prompt
    assert "고칠 점 1" in writer[1].prompt


async def test_limit_reached_ends_with_reject_reply() -> None:
    runtime, recorder, _ = make_runtime()
    run = await run_reviews(
        runtime, review_loop(max_iterations=2), ["rejected", "rejected", "rejected"]
    )
    assert run.status == "completed", run.error
    found = iterations(recorder, run)
    assert [i for i, _ in found["w"]] == [0, 1, 2]
    assert found["n"] == [(0, "skipped")]
    exhausted = [ev.payload for ev in recorder.events.list(run.id) if ev.type == "loop.exhausted"]
    assert exhausted == [{"edge_id": "back", "iteration": 2, "max_iterations": 2}]


async def test_settings_limit_applies_when_edge_has_none() -> None:
    runtime, recorder, _ = make_runtime()
    run = await run_reviews(
        runtime,
        review_loop(),
        ["rejected", "rejected"],
        flow_settings=FlowSettings(max_iterations=1),
    )
    assert run.status == "completed", run.error
    assert [i for i, _ in iterations(recorder, run)["w"]] == [0, 1]


# ---------------------------------------------------------------- 이름 무관·플러그인 제거


async def test_renamed_loop_kind_behaves_the_same() -> None:
    renamed = LoopEdge()
    renamed.descriptor = LoopEdge.descriptor.model_copy(update={"id": "go-again"})
    runtime, recorder, _ = make_runtime(exclude=frozenset({"loop"}), extra={"go-again": renamed})
    run = await run_reviews(runtime, review_loop("go-again"), ["rejected", "approved"])
    assert run.status == "completed", run.error
    assert [i for i, _ in iterations(recorder, run)["w"]] == [0, 1]


async def test_without_loop_plugin_graph_is_rejected() -> None:
    runtime, _, _ = make_runtime(exclude=frozenset({"loop"}))
    with pytest.raises(GraphValidationError) as info:
        await runtime.start(review_loop(), {"text": "x"})
    codes = {i.code for i in info.value.issues}
    assert "unknown_edge_type" in codes
