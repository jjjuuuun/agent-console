"""5R.6 QA 반례: 깊이 3 이상, 같은 대상 동시 호출, 회차 경계, 오류 연결 대상, 한도 경계, 누수."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from agent_console_contracts import (
    DelegationSettings,
    EdgeSpec,
    FlowSettings,
    Graph,
    NodeRun,
    NodeSpec,
    RunEvent,
)
from agent_console_runtime import GraphRuntime
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


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
            raise AssertionError("timeout")
        await asyncio.sleep(0.001)


def call(b: Builders, src: str, dst: str) -> EdgeSpec:
    return b.edge(src, dst, kind="t.invoke", sp="alt", tp="in2")


def lead_graph(
    b: Builders, targets: list[NodeSpec], *, lead: dict[str, Any] | None = None
) -> Graph:
    return b.graph(
        [b.node("lead", type="t.lead", **(lead or {})), *targets],
        [call(b, "lead", t.id) for t in targets],
        entries=["lead"],
    )


def node_runs(h: Harness, run_id: str) -> list[NodeRun]:
    return h.recorder.runs.list_node_runs(run_id)


def runs_of(h: Harness, run_id: str, node_id: str) -> list[NodeRun]:
    return sorted((n for n in node_runs(h, run_id) if n.node_id == node_id), key=lambda n: n.call)


def events(h: Harness, run_id: str) -> list[RunEvent]:
    return h.recorder.events.list(run_id)


def chain(b: Builders, depth: int, last: dict[str, Any] | None = None) -> Any:
    names = ["lead"] + [f"M{i}" for i in range(1, depth)]
    nodes = [b.node(n, type="t.lead") for n in names] + [b.node("S", **(last or {}))]
    ids = [*names, "S"]
    edges = [call(b, ids[i], ids[i + 1]) for i in range(len(ids) - 1)]
    return b.graph(nodes, edges, entries=["lead"])


@pytest.mark.parametrize("slots", [None, 1, 2])
async def test_depth_four_chain_completes(h: Harness, b: Builders, slots: int | None) -> None:
    rt = h.make(max_concurrency=slots) if slots else h.make()
    run = await asyncio.wait_for(rt.run(chain(b, 4)), 5)
    assert run.status == "completed"
    [s] = runs_of(h, run.id, "S")
    assert s.invoked_by == ["lead", "M1", "M2", "M3"]
    assert all(n.status == "succeeded" for n in node_runs(h, run.id))


async def test_depth_three_refused_by_limit_two(h: Harness, b: Builders) -> None:
    rt = h.make(delegation_settings=DelegationSettings(max_depth=2), max_concurrency=1)
    run = await asyncio.wait_for(rt.run(chain(b, 3)), 5)  # lead->M1->M2->S : S depth 3
    assert run.status == "completed"
    assert runs_of(h, run.id, "S") == []
    assert [n.status for n in runs_of(h, run.id, "M2")] == ["succeeded"]


async def test_two_delegators_same_target_serial_and_session_chain(h: Harness, b: Builders) -> None:
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [
            b.node("lead", type="t.lead", parallel=True),
            b.node("M1", type="t.lead"),
            b.node("M2", type="t.lead"),
            b.node("S", sleep=0.02, session="s"),
        ],
        [call(b, "lead", "M1"), call(b, "lead", "M2"), call(b, "M1", "S"), call(b, "M2", "S")],
        entries=["lead"],
    )
    run = await asyncio.wait_for(rt.run(g), 5)
    assert run.status == "completed"
    calls = runs_of(h, run.id, "S")
    assert [c.call for c in calls] == [0, 1]
    assert {tuple(c.invoked_by or []) for c in calls} == {("lead", "M1"), ("lead", "M2")}
    seen = [s.previous_session_id for s in h.probe.seen if s.node_id == "S"]
    assert seen == [None, "s-0"]
    ev = [
        (e.type, e.payload.get("call"))
        for e in events(h, run.id)
        if e.node_path and e.node_path[-1] == "S" and e.type in ("node.started", "node.completed")
    ]
    assert ev == [
        ("node.started", 0),
        ("node.completed", 0),
        ("node.started", 1),
        ("node.completed", 1),
    ]


async def test_boundary_of_loop_waits_for_delegator_with_running_call(
    h: Harness, b: Builders
) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("chk"), b.node("A", sleep=0.03)],
        [
            b.edge("lead", "chk"),
            b.edge("chk", "lead", kind="t.loop", max_iterations=2),
            call(b, "lead", "A"),
        ],
        entries=["lead"],
    )
    run = await asyncio.wait_for(rt.run(g), 5)
    assert run.status == "completed"
    assert [(n.iteration, n.call, n.status) for n in runs_of(h, run.id, "A")] == [
        (0, 0, "succeeded"),
        (1, 1, "succeeded"),
        (2, 2, "succeeded"),
    ]
    leads = runs_of(h, run.id, "lead")
    assert len(leads) == 3 or len(leads) == 1  # 회차별 NodeRun
    order = [
        (e.node_path, e.type)
        for e in events(h, run.id)
        if e.type in ("node.started", "node.completed") and e.node_path in (["lead"], ["lead", "A"])
    ]
    # 같은 회차의 lead는 A가 끝난 뒤에 끝난다
    first_a_done = order.index((["lead", "A"], "node.completed"))
    first_lead_done = order.index((["lead"], "node.completed"))
    assert first_a_done < first_lead_done


async def test_target_with_outgoing_flow_and_on_error_does_not_schedule(
    h: Harness, b: Builders
) -> None:
    rt = h.make()
    g = b.graph(
        [b.node("lead", type="t.lead"), b.node("A", fail=True), b.node("C"), b.node("H")],
        [call(b, "lead", "A"), b.edge("A", "C"), b.edge("A", "H", kind="t.err")],
        entries=["lead"],
    )
    run = await asyncio.wait_for(rt.run(g, validate=False), 5)
    done = {n.node_id for n in node_runs(h, run.id) if n.status != "skipped"}
    print("RESULT", run.status, [(n.node_id, n.status, n.call) for n in node_runs(h, run.id)])
    assert run.status == "completed"
    # 핵심: 호출 대상의 오류 연결/흐름이 엔진 스케줄을 일으키지 않는다(위임자가 판단)
    assert "C" not in done
    assert "H" not in done


@pytest.mark.parametrize(("cap", "status"), [(3, "completed"), (2, "failed")])
async def test_max_node_runs_boundary(h: Harness, b: Builders, cap: int, status: str) -> None:
    rt = h.make(flow_settings=FlowSettings(max_node_runs=cap))
    run = await asyncio.wait_for(rt.run(lead_graph(b, [b.node("A"), b.node("B")])), 5)
    assert run.status == status
    assert all(n.status != "running" and n.status != "queued" for n in node_runs(h, run.id))


async def test_cancel_while_target_waiting_leaves_nothing(h: Harness, b: Builders) -> None:
    rt = h.make(max_concurrency=1)
    g = lead_graph(b, [b.node("Q", type="t.asker", asks=[{}, {}])])
    before = len(asyncio.all_tasks())
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    await until(lambda: handle.run.status == "waiting")
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert rt.pending(run_id=run.id) == []
    assert {n.status for n in node_runs(h, run.id)} == {"cancelled"}
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(asyncio.all_tasks()) <= before + 1
    # 슬롯이 반납됐다: 같은 런타임에서 다음 Run이 돈다
    run2 = await asyncio.wait_for(rt.run(lead_graph(b, [b.node("A")])), 5)
    assert run2.status == "completed"


async def test_second_run_after_depth_two_waiting_response(h: Harness, b: Builders) -> None:
    """깊이 2에서 대상이 되묻기 → 응답 → 완료, 슬롯 1개."""
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [
            b.node("lead", type="t.lead"),
            b.node("M", type="t.lead"),
            b.node("Q", type="t.asker", asks=[{}]),
        ],
        [call(b, "lead", "M"), call(b, "M", "Q")],
        entries=["lead"],
    )
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    [p] = rt.pending(run_id=handle.run_id)
    assert p.node_path == ["lead", "M", "Q"]
    await until(lambda: handle.run.status == "waiting")
    await rt.respond(handle.run_id, p.id, {"answer": "x"})
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
