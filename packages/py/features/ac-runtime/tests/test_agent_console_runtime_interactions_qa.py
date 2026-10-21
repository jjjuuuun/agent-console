"""1R.28 QA 반례: 슬롯 반납·재획득 순서, Run 상태 갱신 시점, 실제 저장소 계약 호환."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_console_contracts import Interaction
from agent_console_runtime import GraphRuntime, InteractionClosedError
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


async def until(cond: Any, *, limit: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + limit
    while not cond():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("조건이 시간 안에 참이 되지 않았다")
        await asyncio.sleep(0.001)


async def pending_of(rt: GraphRuntime, run_id: str) -> list[Interaction]:
    await until(lambda: len(rt.pending(run_id=run_id)) >= 1)
    return rt.pending(run_id=run_id)


def types_of(h: Harness, run_id: str) -> list[str]:
    return [e.type for e in h.recorder.events.list(run_id)]


def node_status(h: Harness, run_id: str) -> dict[str, str]:
    return {n.node_id: n.status for n in h.recorder.runs.list_node_runs(run_id)}


def _stored_status(h: Harness, run_id: str) -> str | None:
    run = h.recorder.runs.get(run_id)
    return None if run is None else run.status


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


async def test_answered_node_waits_for_slot_then_resumes(h: Harness, b: Builders) -> None:
    """max_concurrency=1: 응답이 와도 다른 노드가 슬롯을 쥐고 있으면 그 노드가 끝난 뒤 재개한다."""
    rt = h.make(max_concurrency=1)
    g = b.graph(
        [b.node("a", type="t.asker", asks=[{}]), b.node("s", sleep=0.15)],
        [],
        entries=["a", "s"],
    )
    handle = await rt.start(g)
    [item] = await pending_of(rt, handle.run_id)
    await until(lambda: node_status(h, handle.run_id).get("s") == "running")
    await rt.respond(handle.run_id, item.id, {"answer": "x"})
    await asyncio.sleep(0.03)
    assert node_status(h, handle.run_id)["a"] == "waiting"  # 슬롯 대기
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    assert "node.resumed" in types_of(h, run.id)  # 슬롯이 반납돼 재개했다(데드락 없음)


async def test_run_becomes_waiting_when_last_runner_finishes(h: Harness, b: Builders) -> None:
    """질문 노드가 먼저 대기하고 다른 노드가 끝나면 그때 run.waiting이 나온다."""
    rt = h.make()
    g = b.graph(
        [b.node("a", type="t.asker", asks=[{}]), b.node("s", sleep=0.4)],
        [],
        entries=["a", "s"],
    )
    handle = await rt.start(g)
    [item] = await pending_of(rt, handle.run_id)
    first: str = handle.run.status
    assert first == "running"
    await until(lambda: handle.run.status == "waiting", limit=3)
    # `handle.run`은 메모리 사본이라 저장소 기록(기록 줄, FIFO)보다 먼저 바뀐다. 저장된 Run이
    # waiting이 될 때까지 기다리면 그 앞에 넣은 노드 s의 succeeded 기록도 반드시 저장돼 있다(4R.22).
    await until(lambda: _stored_status(h, handle.run_id) == "waiting", limit=3)
    assert node_status(h, handle.run_id)["s"] == "succeeded"
    await rt.respond(handle.run_id, item.id, {"answer": "x"})
    run = await handle.wait()
    assert run.status == "completed"
    types = types_of(h, run.id)
    assert types.count("run.waiting") == 1
    assert types.count("run.resumed") == 1


async def test_second_response_after_expire_is_closed(h: Harness, b: Builders) -> None:
    rt = h.make()
    handle = await rt.start(b.graph([b.node("a", type="t.asker", asks=[{}])], [], entries=["a"]))
    [item] = await pending_of(rt, handle.run_id)
    handle.cancel()
    await handle.wait()
    with pytest.raises(InteractionClosedError) as info:
        await rt.respond(handle.run_id, item.id, {"answer": "late"})
    assert info.value.interaction.status == "cancelled"
