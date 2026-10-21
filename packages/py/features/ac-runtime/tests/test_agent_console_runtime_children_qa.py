"""5R.7 QA 반례: 중첩 한도 경계, 자식 안 반복·호출, 병렬 자식 대기, 슬롯·태스크 누수."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from agent_console_contracts import DelegationSettings, Graph, Run
from agent_console_runtime import GraphRuntime
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

LOOP = "t.loop"
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
        assert runtime.active_run_ids() == []


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def until(cond: Callable[[], bool], *, limit: float = 5.0) -> None:
    end = asyncio.get_running_loop().time() + limit
    while not cond():
        assert asyncio.get_running_loop().time() < end, "timeout"
        await asyncio.sleep(0.001)


def leaf(b: Builders, gid: str = "g0", **config: Any) -> Graph:
    cfg: dict[str, Any] = {"outputs": {"out": f"{gid}-answer"}}
    cfg.update(config)
    return b.graph([b.node("A", **cfg)], [b.reply("A")], gid, entries=["A"])


def nest(b: Builders, child: Graph, gid: str, node_id: str = "N") -> Graph:
    return b.graph(
        [b.node(node_id, type="t.nest", graph=child.model_dump(mode="json"))],
        [b.reply(node_id)],
        gid,
        entries=[node_id],
    )


def tower(b: Builders, levels: int, bottom: Graph | None = None) -> Graph:
    graph = bottom or leaf(b)
    for level in range(1, levels + 1):
        graph = nest(b, graph, f"g{level}", f"N{level}")
    return graph


def kids(h: Harness, root: str) -> list[Run]:
    return [r for r in h.recorder.runs.list() if r.root_run_id == root]


@pytest.mark.parametrize(
    ("limit", "levels", "ok"),
    [(2, 2, True), (2, 3, False), (3, 3, True), (3, 4, False), (None, 6, True), (1, 1, True)],
)
async def test_nesting_boundary(
    h: Harness, b: Builders, limit: int | None, levels: int, ok: bool
) -> None:
    rt = h.make(delegation_settings=DelegationSettings(max_nesting=limit))
    run = await asyncio.wait_for(rt.run(tower(b, levels)), 10)
    assert (run.status == "completed") is ok
    refused = [r for r in h.probe.children if r.run_id is None]
    assert len(refused) == (0 if ok else 1)
    assert len(kids(h, run.id)) == (levels if ok else limit)


async def test_three_levels_ids_events_and_unique_run_paths(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(tower(b, 3))
    assert run.status == "completed"
    assert {r.root_run_id for r in kids(h, run.id)} == {run.id}
    assert all(r.conversation_id is None for r in kids(h, run.id))
    # 모든 Run의 child_started/finished 짝이 맞는다
    for r in [run, *kids(h, run.id)]:
        t = [e.type for e in h.recorder.events.list(r.id)]
        assert t.count("run.child_started") == t.count("run.child_finished")


async def test_loop_inside_child(h: Harness, b: Builders) -> None:
    child = b.graph(
        [b.node("a"), b.node("b")],
        [b.edge("a", "b"), b.edge("b", "a", kind=LOOP, max_iterations=2), b.reply("b")],
        "child",
        entries=["a"],
    )
    rt = h.make()
    run = await asyncio.wait_for(rt.run(nest(b, child, "parent")), 10)
    assert run.status == "completed"
    [c] = kids(h, run.id)
    its = {(n.node_id, n.iteration) for n in h.recorder.runs.list_node_runs(c.id)}
    assert {("a", 0), ("a", 1), ("a", 2), ("b", 2)} <= its


async def test_invoke_inside_child_with_single_slot(h: Harness, b: Builders) -> None:
    child = b.graph(
        [b.node("lead", type="t.lead"), b.node("T")],
        [b.edge("lead", "T", kind=INVOKE, sp="alt", tp="in2")],
        "child",
        entries=["lead"],
    )
    rt = h.make(max_concurrency=1)
    run = await asyncio.wait_for(rt.run(nest(b, child, "parent")), 10)
    assert run.status == "completed"
    [c] = kids(h, run.id)
    assert any(
        n.node_id == "T" and n.invoked_by == ["lead"] for n in h.recorder.runs.list_node_runs(c.id)
    )


async def test_parallel_children_both_waiting_then_parent_cancel(h: Harness, b: Builders) -> None:
    def asking(gid: str) -> Graph:
        return b.graph(
            [b.node("Q", type="t.asker", asks=[{"title": "?"}])], [b.reply("Q")], gid, entries=["Q"]
        )

    g = b.graph(
        [
            b.node("N1", type="t.nest", graph=asking("c1").model_dump(mode="json")),
            b.node("N2", type="t.nest", graph=asking("c2").model_dump(mode="json")),
        ],
        [b.reply("N1"), b.reply("N2")],
        "parent",
        entries=["N1", "N2"],
    )
    rt = h.make(max_concurrency=1)
    handle = await rt.start(g, conversation_id="conv")
    await until(lambda: len(rt.pending()) == 2)
    await until(lambda: handle.run.status == "waiting")
    pend = rt.pending()
    assert {p.root_run_id for p in pend} == {handle.run_id}
    assert {p.conversation_id for p in pend} == {"conv"}

    # 한쪽만 응답하면 아직 waiting(다른 자식이 기다림)
    await rt.respond(pend[0].run_id, pend[0].id, {"answer": "a"})
    await asyncio.sleep(0.05)
    assert handle.run.status == "waiting"

    assert rt.cancel(handle.run_id)
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert rt.active_run_ids() == []
    for r in kids(h, run.id):
        assert r.status in ("cancelled", "completed")
    for p in h.recorder.interactions.list(run_id=pend[1].run_id):
        assert p.status != "pending"
    assert not rt.pending()


async def test_child_failure_then_parent_continues_with_next_run_slot(
    h: Harness, b: Builders
) -> None:
    rt = h.make(max_concurrency=1)
    r1 = await rt.run(nest(b, leaf(b, fail=True), "p1"))
    assert r1.status == "failed"
    # 슬롯 누수가 없으면 같은 런타임에서 다음 Run이 바로 끝난다
    r2 = await asyncio.wait_for(rt.run(tower(b, 2)), 5)
    assert r2.status == "completed"
    assert rt.active_run_ids() == []


async def test_no_stray_tasks_after_nested_cancel(h: Harness, b: Builders) -> None:
    before = {t for t in asyncio.all_tasks()}
    rt = h.make(cancel_grace=0.05)
    handle = await rt.start(tower(b, 3, leaf(b, hang=True)))
    await h.probe.started_event("A").wait()
    rt.cancel(handle.run_id)
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert {r.status for r in kids(h, run.id)} == {"cancelled"}
    await asyncio.sleep(0.05)
    extra = [
        t for t in asyncio.all_tasks() - before if not t.done() and t is not asyncio.current_task()
    ]
    assert extra == [], extra
