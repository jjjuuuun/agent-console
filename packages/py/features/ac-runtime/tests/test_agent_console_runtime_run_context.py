"""5.2R.34: `start(run_context=, start_warnings=)` — `run.started` payload에 더하는 Run 맥락(엔진은
뜻을 모른다)과 실행 수준 경고(`log.warning`). 자식 Run은 준비자가 다른 값을 주지 않으면 부모 맥락을
물려받는다."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent_console_contracts import Graph, Issue, Run, RunEvent
from agent_console_runtime import ChildRunPreparation, ChildRunRequest, GraphRuntime
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


def _leaf(b: Builders) -> Graph:
    return b.graph([b.node("A", outputs={"out": "x"})], [b.reply("A")], "child", entries=["A"])


def _nest(b: Builders) -> Graph:
    return b.graph(
        [b.node("N", type="t.nest", graph=_leaf(b).model_dump(mode="json"))],
        [b.reply("N")],
        "parent",
        entries=["N"],
    )


def _events(h: Harness, run_id: str, type_: str) -> list[RunEvent]:
    return [e for e in h.recorder.events.list(run_id) if e.type == type_]


def _child(h: Harness, parent: Run) -> Run:
    [child] = [r for r in h.recorder.runs.list() if r.parent_run_id == parent.id]
    return child


async def test_run_context_goes_into_run_started_and_child_inherits(
    h: Harness, b: Builders
) -> None:
    rt = h.make()
    warning = Issue(severity="warning", code="t.scope", message="범위 경고", details={"k": 1})
    handle = await rt.start(
        _nest(b),
        {"text": "x"},
        run_context={"cwd": "/w", "status": "덮지 않음"},
        start_warnings=[warning],
    )
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "completed"
    [started] = _events(h, run.id, "run.started")
    assert started.payload["cwd"] == "/w"
    assert started.payload["status"] == "running"
    [logged] = _events(h, run.id, "log.warning")
    assert logged.payload["message"] == "범위 경고"
    assert logged.payload["details"] == {"code": "t.scope", "k": 1}
    assert logged.seq == started.seq + 1
    child = _child(h, run)
    [child_started] = _events(h, child.id, "run.started")
    assert child_started.payload["cwd"] == "/w"  # 부모 맥락을 물려받음
    assert _events(h, child.id, "log.warning") == []  # 경고는 루트 Run에만


async def test_child_preparer_can_replace_run_context(h: Harness, b: Builders) -> None:
    def prepare(request: ChildRunRequest) -> ChildRunPreparation:
        return ChildRunPreparation(run_context={"cwd": "/child"})

    rt = h.make(child_preparer=prepare)
    run = await rt.run(_nest(b), {"text": "x"}, run_context={"cwd": "/w"})
    [child_started] = _events(h, _child(h, run).id, "run.started")
    assert child_started.payload["cwd"] == "/child"


async def test_default_payload_is_unchanged(h: Harness, b: Builders) -> None:
    rt = h.make()
    run = await rt.run(_leaf(b), {"text": "x"})
    [started] = _events(h, run.id, "run.started")
    assert "cwd" not in started.payload
    assert _events(h, run.id, "log.warning") == []
