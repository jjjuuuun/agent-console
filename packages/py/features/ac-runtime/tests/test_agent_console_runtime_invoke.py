"""호출 NodeRun — `ctx.invoke_node`(design §5R.6, 작업 5R.6).

테스트 위임 방식 `t.invoker`(연결 `t.invoke`)와 위임자 `t.lead`만 쓴다. 엔진은 연결·방식 이름을
모른다(디스크립터 `invocation`만 본다).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

import pytest

from agent_console_contracts import (
    DelegationSettings,
    EdgeSpec,
    ErrorInfo,
    FlowSettings,
    Graph,
    NodeRun,
    NodeSpec,
    Run,
    RunEvent,
)
from agent_console_runtime import (
    CancelToken,
    GraphRuntime,
    NodeContext,
    NodeResult,
    NodeRunView,
    Registries,
    SecretResolver,
    Services,
    recover_unfinished_runs,
    resume_options,
    resume_seed,
)
from agent_console_runtime._journal import RunJournal
from agent_console_runtime.testing import (
    BUILDERS,
    Builders,
    Harness,
    InMemoryRecorder,
    SequentialIds,
    make_harness,
)

INVOKE = "t.invoke"


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


def call(b: Builders, src: str, dst: str) -> EdgeSpec:
    return b.edge(src, dst, kind=INVOKE, sp="alt", tp="in2")


def lead_graph(
    b: Builders, targets: list[NodeSpec], *, lead: Mapping[str, Any] | None = None
) -> Graph:
    """사용자 → lead(t.lead) → (t.invoke) 대상들."""
    return b.graph(
        [b.node("lead", type="t.lead", **dict(lead or {})), *targets],
        [call(b, "lead", t.id) for t in targets],
        entries=["lead"],
    )


def node_runs(h: Harness, run_id: str) -> list[NodeRun]:
    return h.recorder.runs.list_node_runs(run_id)


def runs_of(h: Harness, run_id: str, node_id: str) -> list[NodeRun]:
    return sorted((n for n in node_runs(h, run_id) if n.node_id == node_id), key=lambda n: n.call)


def events(h: Harness, run_id: str) -> list[RunEvent]:
    return h.recorder.events.list(run_id)


def lead_out(h: Harness, run_id: str) -> str:
    [lead] = runs_of(h, run_id, "lead")
    return str(lead.outputs["out"])


# ---------------------------------------------------------------- 기본


async def test_invoked_target_gets_own_node_run(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("A", actor="dev"), b.node("B")])
    run = await rt.run(g, {"text": "hi"})

    assert run.status == "completed"
    [a] = runs_of(h, run.id, "A")
    [bb] = runs_of(h, run.id, "B")
    for target in (a, bb):
        assert target.status == "succeeded"
        assert (target.call, target.iteration, target.invoked_by) == (0, 0, ["lead"])
        assert target.inputs == {"in": str({"text": "hi"})}  # t.lead는 입력을 문자열 프롬프트로
    [lead] = runs_of(h, run.id, "lead")
    assert lead.invoked_by is None
    assert lead.call == 0
    assert lead_out(h, run.id).startswith("A#0:succeeded:")
    a_events = [e for e in events(h, run.id) if e.node_path == ["lead", "A"]]
    assert [e.type for e in a_events] == ["node.queued", "node.started", "node.completed"]
    assert all(e.payload["call"] == 0 for e in a_events)
    assert all(e.actor == "dev" for e in a_events)
    # 스케줄 실행의 node.* payload에는 call이 없다
    lead_events = [e for e in events(h, run.id) if e.node_path == ["lead"]]
    assert all(e.payload.get("call") is None for e in lead_events if e.type.startswith("node."))
    # 결과 view
    [va, vb] = h.probe.invocations
    assert (va.node_id, va.status, va.call) == ("A", "succeeded", 0)
    assert vb.outputs["out"] == {"in": str({"text": "hi"})}


async def test_target_replies_are_emitted_with_target_path(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("A", outputs={"out": "answer"}, actor="dev")])
    g = g.model_copy(update={"edges": [*g.edges, b.reply("A")]})
    run = await rt.run(g)

    assert run.status == "completed"
    replies = [e for e in events(h, run.id) if e.type == "run.reply"]
    assert [(e.node_path, e.payload["text"], e.actor) for e in replies] == [
        (["lead", "A"], "answer", "dev")
    ]


async def test_repeated_calls_count_up_and_continue_session(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("A", session="s")], lead={"calls": ["A", "A", "A"]})
    run = await rt.run(g)

    assert run.status == "completed"
    calls = runs_of(h, run.id, "A")
    assert [n.call for n in calls] == [0, 1, 2]
    assert [n.backend_session_id for n in calls] == ["s-0", "s-0", "s-0"]
    # 같은 대상의 다음 호출은 직전 호출의 세션을 받는다
    seen = [s.previous_session_id for s in h.probe.seen if s.node_id == "A"]
    assert seen == [None, "s-0", "s-0"]


async def test_call_iteration_follows_delegator_loop_iteration(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("chk"), b.node("A")],
        [
            b.edge("lead", "chk"),
            b.edge("chk", "lead", kind="t.loop", max_iterations=1),
            call(b, "lead", "A"),
        ],
        entries=["lead"],
    )
    run = await rt.run(g)

    assert run.status == "completed"
    calls = runs_of(h, run.id, "A")
    assert [(n.iteration, n.call) for n in calls] == [(0, 0), (1, 1)]


async def test_usage_of_calls_is_in_run_totals(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(
        b,
        [b.node("A", usage={"input_tokens": 3}), b.node("B", usage={"input_tokens": 4})],
    )
    run = await rt.run(g)
    assert run.totals is not None
    assert run.totals.input_tokens == 7


async def test_node_both_scheduled_and_invoked_does_not_reuse_call_zero(
    h: Harness, b: Builders
) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("A")],
        [call(b, "lead", "A")],
        entries=["lead", "A"],
    )
    run = await rt.run(g)
    assert run.status == "completed"
    assert [(n.call, n.invoked_by) for n in runs_of(h, run.id, "A")] == [
        (0, None),
        (1, ["lead"]),
    ]


# ---------------------------------------------------------------- 깊이 2·한도


async def test_depth_two_nested_invocation(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("M", type="t.lead"), b.node("S", actor="sub")],
        [call(b, "lead", "M"), call(b, "M", "S")],
        entries=["lead"],
    )
    run = await rt.run(g, {"q": 1})

    assert run.status == "completed"
    [m] = runs_of(h, run.id, "M")
    [s] = runs_of(h, run.id, "S")
    assert m.invoked_by == ["lead"]
    assert s.invoked_by == ["lead", "M"]
    assert s.status == "succeeded"
    s_paths = {tuple(e.node_path) for e in events(h, run.id) if e.payload.get("call") == 0}
    assert ("lead", "M", "S") in s_paths
    assert "S#0:succeeded" in str(m.outputs["out"])
    assert lead_out(h, run.id).startswith("M#0:succeeded:")


@pytest.mark.parametrize("where", ["settings", "strategy"])
async def test_depth_limit_is_checked_while_running(h: Harness, b: Builders, where: str) -> None:
    if where == "settings":
        rt = h.make(delegation_settings=DelegationSettings(max_depth=1))
        lead_cfg: dict[str, Any] = {}
    else:
        rt = h.make()
        lead_cfg = {"max_depth": 1}
    g = b.graph(
        [
            b.node("lead", type="t.lead", **lead_cfg),
            b.node("M", type="t.lead", **lead_cfg),
            b.node("S"),
        ],
        [call(b, "lead", "M"), call(b, "M", "S")],
        entries=["lead"],
    )
    run = await rt.run(g)

    assert run.status == "completed"
    assert runs_of(h, run.id, "S") == []  # 실행하지 않았다
    [m] = runs_of(h, run.id, "M")
    assert "S#0:failed" in str(m.outputs["out"])
    refused = [v for v in h.probe.invocations if v.node_id == "S"]
    assert refused[0].error is not None
    assert refused[0].error.code == "delegation.depth_exceeded"
    assert refused[0].error.details == {"depth": 2, "max_depth": 1, "node_id": "S"}
    assert "'S'" not in refused[0].error.message  # 노드 id가 아니라 이름(5.2R.5)
    [warning] = [e for e in events(h, run.id) if e.type == "log.warning"]
    assert warning.node_path == ["lead", "M", "S"]
    assert warning.payload["details"]["code"] == "delegation.depth_exceeded"


async def test_start_delegation_settings_override_runtime_default(h: Harness, b: Builders) -> None:
    rt = h.make(delegation_settings=DelegationSettings(max_depth=1))
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("M", type="t.lead"), b.node("S")],
        [call(b, "lead", "M"), call(b, "M", "S")],
        entries=["lead"],
    )
    run = await rt.run(g, delegation_settings=DelegationSettings(max_depth=2))
    assert [n.status for n in runs_of(h, run.id, "S")] == ["succeeded"]


async def test_delegation_cycle_is_refused_at_runtime(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("M", type="t.lead")],
        [call(b, "lead", "M"), call(b, "M", "lead")],
        entries=["lead"],
    )
    run = await rt.run(g, validate=False)
    assert run.status == "completed"
    cycle = [v for v in h.probe.invocations if v.node_id == "lead"]
    assert cycle[0].error is not None
    assert cycle[0].error.code == "delegation.cycle"


async def test_calls_count_toward_max_node_runs(h: Harness, b: Builders) -> None:
    rt = h.make(flow_settings=FlowSettings(max_node_runs=2))
    g = lead_graph(b, [b.node("A"), b.node("B")])
    run = await rt.run(g)

    assert run.status == "failed"
    assert run.error is not None
    assert run.error.code == "flow.max_node_runs_exceeded"
    assert [n.status for n in runs_of(h, run.id, "A")] == ["succeeded"]
    assert runs_of(h, run.id, "B") == []


# ---------------------------------------------------------------- 동시 호출


async def test_same_target_serial_other_targets_parallel(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(
        b,
        [b.node("A", sleep=0.03), b.node("B", sleep=0.03)],
        lead={"calls": ["A", "A", "B"], "parallel": True},
    )
    run = await rt.run(g)

    assert run.status == "completed"
    assert h.probe.max_running == 2  # A와 B는 함께, A 두 번은 따로
    order = [
        (e.type, e.payload.get("call"))
        for e in events(h, run.id)
        if e.node_path == ["lead", "A"] and e.type in ("node.started", "node.completed")
    ]
    assert order == [
        ("node.started", 0),
        ("node.completed", 0),
        ("node.started", 1),
        ("node.completed", 1),
    ]


@pytest.mark.parametrize("limit", [1, 2])
async def test_parallel_calls_stay_within_max_concurrency(
    h: Harness, b: Builders, limit: int
) -> None:
    rt = h.make(max_concurrency=limit)
    g = lead_graph(
        b,
        [b.node("A", sleep=0.01), b.node("B", sleep=0.01), b.node("C", sleep=0.01)],
        lead={"parallel": True},
    )
    run = await asyncio.wait_for(rt.run(g), 5)  # max_concurrency=1에서도 교착 없음

    assert run.status == "completed"
    assert h.probe.max_running == limit
    assert all(n.status == "succeeded" for n in node_runs(h, run.id))


async def test_depth_two_with_single_slot_does_not_deadlock(h: Harness, b: Builders) -> None:
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("M", type="t.lead"), b.node("S")],
        [call(b, "lead", "M"), call(b, "M", "S")],
        entries=["lead"],
    )
    run = await asyncio.wait_for(rt.run(g), 5)
    assert run.status == "completed"


# ---------------------------------------------------------------- 실패한 대상


@pytest.mark.parametrize(
    ("config", "code"), [({"fail": True}, "t.fail"), ({"raise": "boom"}, "node_exception")]
)
async def test_failed_target_is_a_result_not_a_run_failure(
    h: Harness, b: Builders, config: dict[str, Any], code: str
) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("A", **config), b.node("B")])
    run = await rt.run(g)

    assert run.status == "completed"
    [a] = runs_of(h, run.id, "A")
    assert a.status == "failed"
    assert a.error is not None
    assert a.error.code == code
    [va, vb] = h.probe.invocations
    assert va.status == "failed"
    assert vb.status == "succeeded"
    assert lead_out(h, run.id).startswith("A#0:failed:")


# ---------------------------------------------------------------- 취소·대기·끊김


async def test_cancel_propagates_to_invoked_target(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("A", hang=True)])
    handle = await rt.start(g)
    await asyncio.wait_for(h.probe.started_event("A").wait(), 5)
    handle.cancel("stop")
    run = await asyncio.wait_for(handle.wait(), 5)

    assert run.status == "cancelled"
    [a] = runs_of(h, run.id, "A")
    assert a.status == "cancelled"
    assert a.error is not None
    assert a.error.code == "cancelled"
    assert "A" in h.probe.cancel_callbacks
    [lead] = runs_of(h, run.id, "lead")
    assert lead.status == "cancelled"


async def test_cancel_cleans_up_stubborn_target(h: Harness, b: Builders) -> None:
    rt = h.make(cancel_grace=0.01)
    g = lead_graph(b, [b.node("A", stubborn=True)])
    handle = await rt.start(g)
    await asyncio.wait_for(h.probe.started_event("A").wait(), 5)
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)

    assert run.status == "cancelled"
    assert [n.status for n in runs_of(h, run.id, "A")] == ["cancelled"]
    cancelled = [
        e for e in events(h, run.id) if e.type == "node.cancelled" and e.node_path == ["lead", "A"]
    ]
    assert len(cancelled) == 1  # 한 번만 기록


async def test_target_waiting_for_user_makes_run_waiting(h: Harness, b: Builders) -> None:
    rt = h.make(max_concurrency=1)
    g = lead_graph(b, [b.node("Q", type="t.asker", asks=[{"title": "어느 쪽?"}], actor="dev")])
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    [pending] = rt.pending(run_id=handle.run_id)

    assert (pending.node_id, pending.node_path, pending.actor) == ("Q", ["lead", "Q"], "dev")
    await until(lambda: handle.run.status == "waiting")
    # 위임자는 실행 중이지만 Run은 대기(저장은 기록 줄 뒤에서 끝난다)
    await until(lambda: [n.status for n in runs_of(h, handle.run_id, "Q")] == ["waiting"])
    await until(lambda: [n.status for n in runs_of(h, handle.run_id, "lead")] == ["running"])

    await rt.respond(handle.run_id, pending.id, {"answer": "왼쪽"})
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    types = [e.type for e in events(h, run.id)]
    assert "run.waiting" in types
    assert types.index("run.resumed") > types.index("run.waiting")
    [q] = runs_of(h, run.id, "Q")
    assert q.status == "succeeded"
    assert q.outputs["out"][0]["response"] == {"answer": "왼쪽"}


async def test_run_stays_running_while_another_target_works(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(
        b,
        [b.node("Q", type="t.asker", asks=[{}]), b.node("A", hang=True)],
        lead={"parallel": True},
    )
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    await asyncio.wait_for(h.probe.started_event("A").wait(), 5)
    for _ in range(5):
        await asyncio.sleep(0)
    assert handle.run.status == "running"
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert {n.node_id: n.status for n in node_runs(h, run.id)} == {
        "lead": "cancelled",
        "Q": "cancelled",
        "A": "cancelled",
    }


async def test_interrupt_marks_invoked_target_interrupted(h: Harness, b: Builders) -> None:
    rt = h.make()
    g = lead_graph(b, [b.node("Q", type="t.asker", asks=[{}])])
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    handle.interrupt()
    run = await asyncio.wait_for(handle.wait(), 5)

    assert run.status == "interrupted"
    [q] = runs_of(h, run.id, "Q")
    assert q.status == "cancelled"
    assert q.error is not None
    assert q.error.code == "interrupted"


def _run(run_id: str, status: Any) -> Run:
    return Run(
        id=run_id,
        graph_id="g",
        graph_version="v",
        input={},
        origin="api",
        status=status,
        created_at=1.0,
    )


def test_recovery_cancels_unfinished_call_node_runs() -> None:
    recorder = InMemoryRecorder()
    recorder.runs.save(_run("r1", "running"))
    recorder.runs.save_node_run(NodeRun(run_id="r1", node_id="lead", status="running"))
    for n in (0, 1):
        recorder.runs.save_node_run(
            NodeRun(
                run_id="r1",
                node_id="A",
                status="succeeded" if n == 0 else "waiting",
                call=n,
                invoked_by=["lead"],
            )
        )

    assert recover_unfinished_runs(recorder, clock=lambda: 9.0, ids=SequentialIds("x")) == ["r1"]
    calls = sorted(
        (n for n in recorder.runs.list_node_runs("r1") if n.node_id == "A"), key=lambda n: n.call
    )
    assert [n.status for n in calls] == ["succeeded", "cancelled"]
    assert calls[1].error is not None
    assert calls[1].error.code == "interrupted"
    cancelled = [e for e in recorder.events.list("r1") if e.type == "node.cancelled"]
    assert [(e.node_path, e.payload.get("call")) for e in cancelled] == [
        (["lead"], None),
        (["lead", "A"], 1),
    ]


def test_resume_ignores_call_node_runs() -> None:
    run = _run("r1", "interrupted")
    interrupted = ErrorInfo(code="interrupted", message="x")
    runs = [
        NodeRun(
            run_id="r1", node_id="lead", status="cancelled", error=interrupted, inputs={"a": 1}
        ),
        NodeRun(
            run_id="r1",
            node_id="A",
            status="cancelled",
            error=interrupted,
            call=0,
            invoked_by=["lead"],
            inputs={"b": 2},
        ),
    ]
    options = resume_options(run, runs, [], graph=None, node_types=[])
    assert [o.node_id for o in options.nodes] == ["lead"]
    assert resume_seed(runs, ["lead", "A"]) == {"lead": {"a": 1}}


# ---------------------------------------------------------------- 잘못된 호출


class _BadInvoker:
    """config `edge`·`target`으로 `invoke_node`를 부르고 예외 형식을 출력에 남기는 노드."""

    def __init__(self, base: Any) -> None:
        self.descriptor = base.descriptor.model_copy(update={"id": "t.bad_invoker"})
        self._base = base

    def resolve_ports(self, config: Mapping[str, Any]) -> Any:
        return self._base.resolve_ports(config)

    def validate(self, config: Mapping[str, Any], ctx: Any) -> list[Any]:
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        try:
            await ctx.invoke_node(str(ctx.config["target"]), {}, by_edge=str(ctx.config["edge"]))
        except ValueError as exc:
            return NodeResult(status="succeeded", outputs={"out": f"ValueError:{exc}"})
        return NodeResult(status="succeeded", outputs={"out": "called"})


@pytest.mark.parametrize(
    ("edge_id", "target"),
    [
        ("x.out->A.in", "A"),  # 흐름 연결(invocation 아님)
        ("x.alt->A.in2", "B"),  # 대상이 연결과 다름
        ("nope", "A"),  # 없는 연결
        ("x.alt->R.in2", "R"),  # 실행할 수 없는 노드
    ],
)
async def test_invoke_rejects_non_invocation_targets(
    h: Harness, b: Builders, edge_id: str, target: str
) -> None:
    h.registries.node_types.register(
        "t.bad_invoker", _BadInvoker(h.registries.node_types.get("t.step"))
    )
    rt = h.make()
    g = b.graph(
        [
            b.node("x", type="t.bad_invoker", edge=edge_id, target=target),
            b.node("A"),
            b.node("B"),
            b.node("R", type="t.res"),
        ],
        [b.edge("x", "A"), call(b, "x", "A"), call(b, "x", "R")],
        entries=["x"],
    )
    run = await rt.run(g, validate=False)
    [x] = runs_of(h, run.id, "x")
    assert str(x.outputs["out"]).startswith("ValueError:")


async def test_context_outside_engine_cannot_invoke() -> None:
    spec = NodeSpec(id="n", type="t.step")
    recorder = InMemoryRecorder()
    ctx = NodeContext(
        run=_run("r", "running"),
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
    assert ctx.node_path == ["n"]
    assert (ctx.call, ctx.invoked_by) == (0, None)
    with pytest.raises(RuntimeError):
        await ctx.invoke_node("m", {}, by_edge="e")


def test_node_run_view_call_defaults_to_zero() -> None:
    assert NodeRunView(node_id="a", node_type="t", status="succeeded").call == 0
