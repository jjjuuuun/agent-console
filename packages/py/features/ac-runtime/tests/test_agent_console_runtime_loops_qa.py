"""5R.5 QA 반례: 같은 영역 사이클 연결 둘, 병렬 분기, 실패+on_error, 대기 중 취소, 안전 한도."""

from __future__ import annotations

import asyncio

import pytest

from agent_console_contracts import FlowSettings
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

LOOP = "t.loop"


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def runs_of(h: Harness, run_id: str) -> dict[tuple[str, int], str]:
    return {(n.node_id, n.iteration): n.status for n in h.recorder.runs.list_node_runs(run_id)}


async def until(cond, limit: float = 5.0) -> None:  # type: ignore[no-untyped-def]
    end = asyncio.get_running_loop().time() + limit
    while not cond():
        assert asyncio.get_running_loop().time() < end, "timeout"
        await asyncio.sleep(0.001)


async def test_two_cycle_edges_same_region(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("a"),
            b.node(
                "c",
                per_iteration=[
                    {"outputs": {"alt": "x"}},
                    {"outputs": {"out": "y"}},
                    {"outputs": {"out": "y"}},
                ],
            ),
        ],
        [
            b.edge("a", "c"),
            b.edge("c", "a", kind=LOOP, sp="alt", max_iterations=1),
            b.edge("c", "a", kind=LOOP, sp="out", max_iterations=1),
        ],
        entries=["a"],
    )
    run = await asyncio.wait_for(h.make().run(g), 10)
    assert run.status == "completed"
    assert {k for k in runs_of(h, run.id) if k[0] == "a"} == {("a", 0), ("a", 1), ("a", 2)}
    assert {k for k in runs_of(h, run.id) if k[0] == "c"} == {("c", 0), ("c", 1), ("c", 2)}


async def test_parallel_branches_inside_region(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": 1}), b.node("p"), b.node("q"), b.node("d", join="all")],
        [
            b.edge("a", "p"),
            b.edge("a", "q"),
            b.edge("p", "d", tp="in"),
            b.edge("q", "d", tp="in2"),
            b.edge("d", "a", kind=LOOP, max_iterations=2),
        ],
        entries=["a"],
    )
    run = await asyncio.wait_for(h.make().run(g), 10)
    r = runs_of(h, run.id)
    assert run.status == "completed", r
    for n in "apqd":
        assert [i for (x, i) in sorted(r) if x == n] == [0, 1, 2], (n, r)
    assert all(v == "succeeded" for v in r.values()), r


async def test_failure_with_on_error_inside_region(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("a"),
            b.node("c", outputs={"out": 1}, per_iteration=[{}, {"fail": True}]),
            b.node("h"),
        ],
        [
            b.edge("a", "c"),
            b.edge("c", "a", kind=LOOP, max_iterations=5),
            b.edge("c", "h", kind="t.err"),
        ],
        entries=["a"],
    )
    run = await asyncio.wait_for(h.make().run(g), 10)
    r = runs_of(h, run.id)
    assert r[("c", 1)] == "failed"
    assert r[("h", 0)] == "succeeded"
    assert ("a", 2) not in r  # 실패한 회차 뒤 더 돌지 않는다
    assert run.status == "completed", (run.status, r)  # 처리된 실패


async def test_cancel_while_waiting_for_human_in_region(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("a"),
            b.node(
                "q",
                type="t.asker",
                asks=[{"title": "?"}],
            ),
        ],
        [b.edge("a", "q"), b.edge("q", "a", kind=LOOP, max_iterations=3)],
        entries=["a"],
    )
    rt = h.make()
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    [p] = rt.pending(run_id=handle.run_id)
    await rt.respond(handle.run_id, p.id, {"answer": "x"})
    await until(lambda: any(i.id != p.id for i in rt.pending(run_id=handle.run_id)))
    rt.cancel(handle.run_id)
    run = await asyncio.wait_for(handle.wait(), 10)
    assert run.status == "cancelled"
    assert runs_of(h, run.id)[("q", 1)] == "cancelled"
    assert rt.pending(run_id=handle.run_id) == []


async def test_cancel_during_wait_leaves_no_pending(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a"), b.node("q", type="t.asker", asks=[{"title": "?"}])],
        [b.edge("a", "q")],
        entries=["a"],
    )
    rt = h.make()
    handle = await rt.start(g)
    await until(lambda: len(rt.pending(run_id=handle.run_id)) == 1)
    rt.cancel(handle.run_id)
    run = await asyncio.wait_for(handle.wait(), 10)
    assert run.status == "cancelled"
    assert rt.pending(run_id=handle.run_id) == []


async def test_nested_big_limits_stopped_by_max_node_runs(h: Harness, b: Builders) -> None:
    g = b.graph(
        [
            b.node("a"),
            b.node("b"),
            b.node("c", per_iteration=[{"outputs": {"alt": 1}}, {"outputs": {"out": 1}}]),
            b.node("d", outputs={"out": 1}),
        ],
        [
            b.edge("a", "b"),
            b.edge("b", "c"),
            b.edge("c", "d"),
            b.edge("c", "b", kind=LOOP, sp="alt", max_iterations=1000),
            b.edge("d", "a", kind=LOOP, max_iterations=1000),
        ],
        entries=["a"],
    )
    run = await asyncio.wait_for(h.make().run(g, flow_settings=FlowSettings(max_node_runs=40)), 20)
    assert run.status == "failed"
    assert run.error is not None
    assert run.error.code == "flow.max_node_runs_exceeded"
    executed = [k for k, v in runs_of(h, run.id).items() if v != "skipped"]
    assert len(executed) == 40


async def test_three_level_nested_terminates(h: Harness, b: Builders) -> None:
    # 세 겹: a b c d e, e⇢a(1) d⇢b(1) c⇢c(self,1) 모두 한도 1 -> 유한
    g = b.graph(
        [
            b.node("a"),
            b.node("b"),
            b.node("c", outputs={"out": 1, "alt": 1}),
            b.node("d", outputs={"out": 1, "alt": 1}),
            b.node("e", outputs={"out": 1}),
        ],
        [
            b.edge("a", "b"),
            b.edge("b", "c"),
            b.edge("c", "d"),
            b.edge("d", "e"),
            b.edge("c", "c", kind=LOOP, sp="alt", max_iterations=1),
            b.edge("d", "b", kind=LOOP, sp="alt", max_iterations=1),
            b.edge("e", "a", kind=LOOP, max_iterations=1),
        ],
        entries=["a"],
    )
    run = await asyncio.wait_for(h.make().run(g, flow_settings=FlowSettings(max_node_runs=500)), 20)
    r = runs_of(h, run.id)
    n_exec = len([1 for v in r.values() if v != "skipped"])
    assert run.status == "completed"
    assert n_exec == 20


async def test_resume_inside_cycle_counts_from_zero(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("a", outputs={"out": 1}), b.node("b", outputs={"out": 1})],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP, max_iterations=2)],
        entries=["a"],
    )
    run = await asyncio.wait_for(
        h.make().run(g, {"text": "x"}, origin="resume", seed={"b": {"in": 7}}, resumed_from="old"),
        10,
    )
    r = runs_of(h, run.id)
    assert run.status == "completed", r
    assert {k for k in r if k[0] == "b"} == {("b", 0), ("b", 1), ("b", 2)}, r
