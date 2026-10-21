"""자식 Run(`ctx.run_child`, design §5R.7) — 테스트 노드 `t.nest`로 확인한다.

엔진은 노드 종류·팀 이름을 모른다. `t.nest`는 config `graph`를 자식 Run으로 실행하는 테스트 노드다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

import pytest

from agent_console_contracts import (
    DelegationSettings,
    ErrorInfo,
    Graph,
    Interaction,
    InteractionGrant,
    Issue,
    NodeRun,
    NodeSpec,
    Run,
    RunEvent,
)
from agent_console_graph import graph_hash
from agent_console_runtime import (
    CancelToken,
    ChildRunPreparation,
    ChildRunRequest,
    ChildRunResult,
    GraphRuntime,
    GraphValidationError,
    NodeContext,
    Registries,
    RuntimeErrorCodes,
    SecretResolver,
    ServiceKey,
    Services,
    recover_unfinished_runs,
)
from agent_console_runtime._journal import RunJournal
from agent_console_runtime.testing import (
    BUILDERS,
    PROBE,
    Builders,
    Harness,
    InMemoryRecorder,
    SequentialIds,
    make_harness,
)

EXTRA = ServiceKey[str]("test.extra")


@pytest.fixture
async def h() -> AsyncIterator[Harness]:
    harness = make_harness()
    made: list[GraphRuntime] = []
    make = harness.make

    def tracked(**kwargs: Any) -> GraphRuntime:
        runtime = make(**kwargs)
        made.append(runtime)
        return runtime

    harness.make = tracked
    yield harness
    for runtime in made:
        await asyncio.wait_for(runtime.shutdown(), 5)


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def until(cond: Callable[[], bool], *, limit: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + limit
    while not cond():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("조건이 시간 안에 참이 되지 않았다")
        await asyncio.sleep(0.001)


def leaf(b: Builders, gid: str = "child", **config: Any) -> Graph:
    """입구 → A(t.step) → 답변."""
    cfg: dict[str, Any] = {"outputs": {"out": f"{gid}-answer"}}
    cfg.update(config)
    return b.graph([b.node("A", **cfg)], [b.reply("A")], gid, entries=["A"])


def asking(b: Builders, gid: str = "child") -> Graph:
    """입구 → Q(t.asker, 질문 하나) → 답변."""
    return b.graph(
        [b.node("Q", type="t.asker", asks=[{"title": "이름?"}])],
        [b.reply("Q")],
        gid,
        entries=["Q"],
    )


def nest(
    b: Builders, child: Graph, gid: str = "parent", node_id: str = "N", **config: Any
) -> Graph:
    """입구 → N(t.nest, 자식 그래프) → 답변."""
    return b.graph(
        [b.node(node_id, type="t.nest", graph=child.model_dump(mode="json"), **config)],
        [b.reply(node_id)],
        gid,
        entries=[node_id],
    )


def all_runs(h: Harness) -> list[Run]:
    return list(h.recorder.runs.list())


def child_of(h: Harness, parent_id: str) -> Run:
    [child] = [r for r in all_runs(h) if r.parent_run_id == parent_id]
    return child


def events(h: Harness, run_id: str) -> list[RunEvent]:
    return h.recorder.events.list(run_id)


def types(h: Harness, run_id: str) -> list[str]:
    return [e.type for e in events(h, run_id)]


def node_runs(h: Harness, run_id: str) -> dict[str, NodeRun]:
    return {n.node_id: n for n in h.recorder.runs.list_node_runs(run_id)}


async def first_pending(rt: GraphRuntime) -> Interaction:
    await until(lambda: bool(rt.pending()))
    return rt.pending()[0]


# ---------------------------------------------------------------- 성공·실패


async def test_child_run_records_lineage_events_and_result(h: Harness, b: Builders) -> None:
    rt = h.make()
    child_graph = leaf(b, usage={"input_tokens": 5, "output_tokens": 2})
    run = await rt.run(nest(b, child_graph, actor="lead"), {"text": "hi"}, conversation_id="c1")

    assert run.status == "completed"
    child = child_of(h, run.id)
    assert child.status == "completed"
    assert (child.parent_run_id, child.parent_node_id, child.root_run_id) == (run.id, "N", run.id)
    assert child.graph_id == "child"
    assert child.graph_version == graph_hash(child_graph)
    assert child.input == {"text": "hi"}
    assert child.origin == run.origin
    assert child.conversation_id is None  # 자식 Run은 대화 턴이 아니다
    assert run.root_run_id is None

    # 결과: 답변·사용량·Run id
    [result] = h.probe.children
    assert result.run_id == child.id
    assert result.status == "completed"
    assert [r.text for r in result.replies] == ["child-answer"]
    assert result.replies[0].node_id == "A"
    assert result.totals is not None
    assert result.totals.input_tokens == 5
    # 부모: 노드가 자식 totals를 usage로 돌려줘 부모 합계에 들어간다
    assert run.totals is not None
    assert run.totals.input_tokens == 5
    assert node_runs(h, run.id)["N"].outputs == {"out": "child-answer"}

    # 부모 이벤트: run.child_started → run.child_finished(자식 상태), node_path = 부른 노드
    parent_events = events(h, run.id)
    started = [e for e in parent_events if e.type == "run.child_started"]
    finished = [e for e in parent_events if e.type == "run.child_finished"]
    assert [(e.node_path, e.actor, e.payload) for e in started] == [
        (["N"], "lead", {"child_run_id": child.id, "node_id": "N", "graph_id": "child"})
    ]
    assert [(e.node_path, e.payload) for e in finished] == [
        (["N"], {"child_run_id": child.id, "node_id": "N", "status": "completed"})
    ]
    # 자식 답변은 자식 Run에만, 부모 답변은 nest 노드의 답변 연결만
    assert [e.payload["text"] for e in parent_events if e.type == "run.reply"] == ["child-answer"]
    assert [e.node_path for e in parent_events if e.type == "run.reply"] == [["N"]]
    child_types = types(h, child.id)
    assert child_types[0] == "run.created"
    assert child_types[-1] == "run.completed"
    assert "run.reply" in child_types
    # 부모 이벤트 순서: 시작 → 자식 시작 → 자식 끝 → 노드 끝 → 완료
    order = types(h, run.id)
    assert order.index("run.child_started") < order.index("run.child_finished")
    assert order.index("run.child_finished") < order.index("run.completed")


async def test_child_failure_is_a_result(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(nest(b, leaf(b, fail=True)))

    child = child_of(h, run.id)
    assert child.status == "failed"
    [result] = h.probe.children
    assert result.status == "failed"
    assert result.run_id == child.id
    assert result.error is not None
    assert result.error.code == RuntimeErrorCodes.NODE_FAILED
    # t.nest는 자식 실패를 노드 실패로 돌려준다 → 부모 Run 실패
    assert run.status == "failed"
    assert node_runs(h, run.id)["N"].status == "failed"
    finished = [e for e in events(h, run.id) if e.type == "run.child_finished"]
    assert [e.payload["status"] for e in finished] == ["failed"]


async def test_graph_version_pin(h: Harness, b: Builders) -> None:
    rt = h.make()
    child_graph = leaf(b)
    ok = await rt.run(nest(b, child_graph, version=graph_hash(child_graph)))
    assert ok.status == "completed"

    bad = await rt.run(nest(b, child_graph, gid="parent2", version="other"))
    assert bad.status == "failed"
    n = node_runs(h, bad.id)["N"]
    assert n.error is not None
    assert n.error.code == RuntimeErrorCodes.NODE_EXCEPTION
    assert "ValueError" in n.error.message
    assert not [r for r in all_runs(h) if r.parent_run_id == bad.id]


async def test_invalid_child_graph_is_refused_without_run(h: Harness, b: Builders) -> None:
    rt = h.make()
    no_entry = b.graph([b.node("A")], [], "child")
    run = await rt.run(nest(b, no_entry))

    assert not [r for r in all_runs(h) if r.parent_run_id == run.id]
    [result] = h.probe.children
    assert result.run_id is None
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == RuntimeErrorCodes.CHILD_INVALID
    assert [i["code"] for i in result.error.details["issues"]] == ["no_entry"]
    warnings = [e for e in events(h, run.id) if e.type == "log.warning"]
    assert [(e.node_path, e.payload["details"]["code"]) for e in warnings] == [
        (["N"], RuntimeErrorCodes.CHILD_INVALID)
    ]
    assert "run.child_started" not in types(h, run.id)


# ---------------------------------------------------------------- 취소·끊김


async def test_parent_cancel_cancels_child(h: Harness, b: Builders) -> None:
    rt = h.make(cancel_grace=1.0)
    handle = await rt.start(nest(b, leaf(b, hang=True)))
    await h.probe.started_event("A").wait()
    child = child_of(h, handle.run_id)
    assert rt.get(child.id) is not None  # 자식도 이 런타임에 등록된다

    assert rt.cancel(handle.run_id)
    run = await handle.wait()

    assert run.status == "cancelled"
    stored_child = child_of(h, run.id)
    assert stored_child.status == "cancelled"
    assert node_runs(h, child.id)["A"].status == "cancelled"
    assert h.probe.cancel_callbacks == ["A"]
    order = types(h, run.id)
    assert order.index("run.child_finished") < order.index("run.cancelled")
    finished = [e for e in events(h, run.id) if e.type == "run.child_finished"]
    assert [e.payload["status"] for e in finished] == ["cancelled"]
    assert rt.active_run_ids() == []


async def test_parent_cancel_with_stubborn_child_still_finishes(h: Harness, b: Builders) -> None:
    rt = h.make(cancel_grace=0.05)
    handle = await rt.start(nest(b, leaf(b, stubborn=True)))
    await h.probe.started_event("A").wait()
    child = child_of(h, handle.run_id)

    rt.cancel(handle.run_id)
    run = await asyncio.wait_for(handle.wait(), 5)

    assert run.status == "cancelled"
    assert child_of(h, run.id).status == "cancelled"
    assert node_runs(h, child.id)["A"].status == "cancelled"
    assert [e.payload["status"] for e in events(h, run.id) if e.type == "run.child_finished"] == [
        "cancelled"
    ]


async def test_cancelling_only_the_child_returns_cancelled_result(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(nest(b, leaf(b, hang=True)))
    await h.probe.started_event("A").wait()
    child = child_of(h, handle.run_id)

    assert rt.cancel(child.id)
    run = await handle.wait()

    [result] = h.probe.children
    assert result.status == "cancelled"
    assert run.status == "failed"  # t.nest가 자식 취소를 실패로 돌려준다


async def test_interrupt_propagates_to_child(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(nest(b, asking(b)))
    pending = await first_pending(rt)

    await rt.shutdown("bye", interrupt=True)

    run = await handle.wait()
    assert run.status == "interrupted"
    child = child_of(h, run.id)
    assert child.status == "interrupted"
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert (stored.status, stored.close_reason) == ("expired", "interrupted")
    finished = [e for e in events(h, run.id) if e.type == "run.child_finished"]
    assert [e.payload["status"] for e in finished] == ["interrupted"]


# ---------------------------------------------------------------- 상호작용·대기


async def test_child_interaction_makes_parent_waiting(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(nest(b, asking(b)), {"text": "x"}, conversation_id="conv-9")
    pending = await first_pending(rt)
    child = child_of(h, handle.run_id)

    # 상호작용: 자식 Run 것이고 루트 id·루트 대화 id를 가진다
    assert pending.run_id == child.id
    assert pending.root_run_id == handle.run_id
    assert pending.conversation_id == "conv-9"
    assert pending.node_path == ["Q"]
    assert rt.pending(run_id=child.id) == [pending]
    await until(lambda: h.recorder.interactions.get(pending.id) is not None)
    stored = h.recorder.interactions.get(pending.id)
    assert stored is not None
    assert stored.root_run_id == handle.run_id

    await until(lambda: handle.run.status == "waiting")
    assert rt.get(child.id) is not None
    await until(lambda: rt.get(child.id).run.status == "waiting")  # type: ignore[union-attr]
    # 부모 노드는 running 그대로(자식을 기다리는 중)
    assert node_runs(h, handle.run_id)["N"].status == "running"

    await rt.respond(child.id, pending.id, {"answer": "철수"})
    run = await handle.wait()

    assert run.status == "completed"
    parent_types = types(h, run.id)
    assert parent_types.index("run.waiting") < parent_types.index("run.resumed")
    assert "run.waiting" in types(h, child.id)
    [result] = h.probe.children
    assert result.status == "completed"


async def test_root_interactions_keep_root_run_id_empty(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(asking(b, "root"), conversation_id="c")
    pending = await first_pending(rt)
    assert pending.root_run_id is None
    assert pending.conversation_id == "c"
    await rt.respond(handle.run_id, pending.id, {"answer": "a"})
    assert (await handle.wait()).status == "completed"


# ---------------------------------------------------------------- 중첩·한도


def two_level(b: Builders, leaf_graph: Graph) -> Graph:
    """parent → N1(t.nest: mid → N2(t.nest: leaf))."""
    mid = nest(b, leaf_graph, gid="mid", node_id="N2")
    return nest(b, mid, gid="parent", node_id="N1")


async def test_two_level_nesting(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(two_level(b, leaf(b, "leaf")))

    assert run.status == "completed"
    mid = child_of(h, run.id)
    grand = child_of(h, mid.id)
    assert (mid.parent_node_id, mid.root_run_id) == ("N1", run.id)
    assert (grand.parent_run_id, grand.parent_node_id, grand.root_run_id) == (
        mid.id,
        "N2",
        run.id,
    )
    assert node_runs(h, run.id)["N1"].outputs == {"out": "leaf-answer"}
    assert [
        e.payload["child_run_id"] for e in events(h, mid.id) if e.type == "run.child_started"
    ] == [grand.id]


async def test_two_level_waiting_and_single_slot(h: Harness, b: Builders) -> None:
    """max_concurrency=1: 부모·자식·손자가 같은 슬롯을 쓰지만 기다리는 쪽이 내놓아 교착이 없다."""
    rt = h.make(max_concurrency=1)
    handle = await rt.start(two_level(b, asking(b, "leaf")))
    pending = await first_pending(rt)
    mid = child_of(h, handle.run_id)
    grand = child_of(h, mid.id)

    assert pending.run_id == grand.id
    assert pending.root_run_id == handle.run_id  # 손자도 루트 id
    await until(lambda: handle.run.status == "waiting")

    await rt.respond(grand.id, pending.id, {"answer": "ok"})
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    assert child_of(h, handle.run_id).status == "completed"


async def test_parallel_children_share_the_slot_limit(h: Harness, b: Builders) -> None:
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [
            b.node("N1", type="t.nest", graph=leaf(b, "c1", sleep=0.01).model_dump(mode="json")),
            b.node("N2", type="t.nest", graph=leaf(b, "c2", sleep=0.01).model_dump(mode="json")),
        ],
        [b.reply("N1"), b.reply("N2")],
        "parent",
        entries=["N1", "N2"],
    )
    run = await asyncio.wait_for(rt.run(g), 5)
    assert run.status == "completed"
    assert h.probe.max_running == 1
    assert len([r for r in all_runs(h) if r.parent_run_id == run.id]) == 2


async def test_nesting_limit_from_delegation_settings(h: Harness, b: Builders) -> None:
    rt = h.make(delegation_settings=DelegationSettings(max_nesting=1))
    run = await rt.run(two_level(b, leaf(b, "leaf")))

    mid = child_of(h, run.id)
    assert not [r for r in all_runs(h) if r.parent_run_id == mid.id]
    refused = [r for r in h.probe.children if r.run_id is None]
    assert len(refused) == 1
    error = refused[0].error
    assert error is not None
    assert error.code == RuntimeErrorCodes.CHILD_NESTING_EXCEEDED == "team.nesting_exceeded"
    assert error.details == {"depth": 2, "limit": 1}
    warnings = [e for e in events(h, mid.id) if e.type == "log.warning"]
    assert [(e.node_path, e.payload["details"]["code"]) for e in warnings] == [
        (["N2"], "team.nesting_exceeded")
    ]
    assert run.status == "failed"


async def test_default_nesting_limit_is_contract_default(h: Harness, b: Builders) -> None:
    rt = h.make()
    graph = leaf(b, "g0")
    for level in range(1, 5):
        graph = nest(b, graph, gid=f"g{level}", node_id=f"N{level}")
    run = await rt.run(graph)  # 깊이 4 > 기본 3

    assert DelegationSettings().max_nesting == 3
    assert run.status == "failed"
    codes = [r.error.code for r in h.probe.children if r.error is not None and r.run_id is None]
    assert codes == ["team.nesting_exceeded"]
    assert len([r for r in all_runs(h) if r.root_run_id == run.id]) == 3


async def test_recursive_graph_is_refused(h: Harness, b: Builders) -> None:
    rt = h.make()
    inner = nest(b, leaf(b), gid="parent", node_id="X")  # 부모와 같은 그래프 id
    run = await rt.run(nest(b, inner, gid="parent"))

    [result] = h.probe.children
    assert result.run_id is None
    assert result.error is not None
    assert result.error.code == RuntimeErrorCodes.CHILD_RECURSIVE == "team.recursive"
    assert result.error.details == {"path": ["parent", "parent"]}
    assert run.status == "failed"


# ---------------------------------------------------------------- 준비자(확장 지점)


async def test_child_preparer_controls_services_and_settings(h: Harness, b: Builders) -> None:
    seen: list[ChildRunRequest] = []

    async def prepare(request: ChildRunRequest) -> ChildRunPreparation:
        seen.append(request)
        return ChildRunPreparation(
            services=request.services.with_(EXTRA, "from-preparer"),
            interaction_grants={"Q": InteractionGrant(kinds=["t.ask"], timeout_seconds=0.01)},
            delegation_settings=DelegationSettings(max_nesting=5),
            checked=True,
        )

    rt = h.make(child_preparer=prepare)
    handle = await rt.start(nest(b, asking(b)), {"text": "x"})
    run = await asyncio.wait_for(handle.wait(), 5)

    assert run.status == "completed"  # grant 시간 제한으로 만료 응답 → 자식 완료
    [request] = seen
    assert request.node_id == "N"
    assert request.node_path == ("N",)
    assert request.parent.id == run.id
    assert [r.id for r in request.ancestors] == [run.id]
    assert request.input == {"text": "x"}
    assert request.graph.id == "child"
    assert PROBE in request.services
    child = child_of(h, run.id)
    [interaction] = h.recorder.interactions.list(run_id=child.id)
    assert interaction.status == "expired"


async def test_child_preparer_can_block(h: Harness, b: Builders) -> None:
    def prepare(request: ChildRunRequest) -> ChildRunPreparation:
        raise GraphValidationError(
            [Issue(severity="error", code="t.blocked", message="막음", node_id="A")]
        )

    rt = h.make(child_preparer=prepare)
    run = await rt.run(nest(b, leaf(b)))

    [result] = h.probe.children
    assert (result.run_id, result.status) == (None, "failed")
    assert result.error is not None
    assert [i["code"] for i in result.error.details["issues"]] == ["t.blocked"]
    assert run.status == "failed"


async def test_run_child_extra_services_reach_the_preparer(h: Harness, b: Builders) -> None:
    seen: list[ChildRunRequest] = []

    def prepare(request: ChildRunRequest) -> ChildRunPreparation:
        seen.append(request)
        return ChildRunPreparation()

    class ExtraNest:
        descriptor = h.registries.node_types.get("t.nest").descriptor.model_copy(
            update={"id": "t.nest_extra"}
        )

        def resolve_ports(self, config: Mapping[str, Any]) -> Any:
            return h.registries.node_types.get("t.nest").resolve_ports(config)

        def validate(self, config: Mapping[str, Any], ctx: Any) -> list[Issue]:
            return []

        async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> Any:
            from agent_console_runtime import NodeResult

            result = await ctx.run_child(
                Graph.model_validate(ctx.config["graph"]), {"text": "t"}, services={EXTRA: "v"}
            )
            return NodeResult(status="succeeded", outputs={"out": result.status})

    h.registries.node_types.register("t.nest_extra", ExtraNest())
    rt = h.make(child_preparer=prepare)
    g = b.graph(
        [b.node("N", type="t.nest_extra", graph=leaf(b).model_dump(mode="json"))],
        [],
        "parent",
        entries=["N"],
    )
    run = await rt.run(g)
    assert run.status == "completed"
    [request] = seen
    assert request.services.get(EXTRA) == "v"
    assert PROBE in request.services


# ---------------------------------------------------------------- 재시작 복구·맥락 밖


def test_recovery_interrupts_unfinished_child_runs() -> None:
    recorder = InMemoryRecorder()
    root = Run(
        id="root",
        graph_id="p",
        graph_version="v",
        status="waiting",
        input={},
        origin="api",
        created_at=1.0,
    )
    child = root.model_copy(
        update={
            "id": "kid",
            "graph_id": "c",
            "parent_run_id": "root",
            "parent_node_id": "N",
            "root_run_id": "root",
        }
    )
    recorder.runs.save(root)
    recorder.runs.save(child)
    recorder.runs.save_node_run(NodeRun(run_id="root", node_id="N", status="running"))
    recorder.runs.save_node_run(NodeRun(run_id="kid", node_id="Q", status="waiting"))
    recorder.interactions.save(
        Interaction(
            id="i1",
            run_id="kid",
            root_run_id="root",
            node_id="Q",
            node_path=["Q"],
            kind="t.ask",
            status="pending",
            created_at=1.0,
        )
    )

    ids = recover_unfinished_runs(recorder, clock=lambda: 9.0, ids=SequentialIds("x"))

    assert sorted(ids) == ["kid", "root"]
    for run_id, node_id in (("root", "N"), ("kid", "Q")):
        stored = recorder.runs.get(run_id)
        assert stored is not None
        assert stored.status == "interrupted"
        [n] = recorder.runs.list_node_runs(run_id)
        assert (n.node_id, n.status) == (node_id, "cancelled")
    closed = recorder.interactions.get("i1")
    assert closed is not None
    assert (closed.status, closed.root_run_id) == ("expired", "root")
    assert recorder.runs.get("kid").parent_run_id == "root"  # type: ignore[union-attr]


async def test_context_outside_engine_cannot_run_child() -> None:
    spec = NodeSpec(id="n", type="t.step")
    recorder = InMemoryRecorder()
    ctx = NodeContext(
        run=Run(
            id="r",
            graph_id="g",
            graph_version="v",
            status="running",
            input={},
            origin="api",
            created_at=0.0,
        ),
        graph=Graph(id="g", name="g", nodes=[spec], edges=[]),
        node=spec,
        attempt=1,
        iteration=0,
        registries=Registries(),
        services=Services(),
        secrets=SecretResolver([]),
        cancel=CancelToken(),
        clock=lambda: 0.0,
        journal=RunJournal("r", recorder, None, clock=lambda: 0.0, ids=SequentialIds("j")),
    )
    with pytest.raises(RuntimeError):
        await ctx.run_child(Graph(id="c", name="c", nodes=[], edges=[]))


def test_child_run_result_defaults() -> None:
    result = ChildRunResult(run_id=None, status="failed", error=ErrorInfo(code="x", message="y"))
    assert result.replies == ()
    assert result.totals is None
