"""held_run 해제 보장(5.2R.39 QA): 기록 실패·취소 경로에서도 종료 상태가 영영 숨겨지지 않는다."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from agent_console_runtime import RecorderError
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


async def test_held_run_released_when_flush_fails(h: Harness, b: Builders) -> None:
    original = h.recorder.events.append_many

    def fail_on_terminal(events: Sequence[Any]) -> int:
        if any(e.type == "run.completed" for e in events):
            raise OSError("disk full")
        return original(events)

    h.recorder.events.append_many = fail_on_terminal  # type: ignore[method-assign]
    g = b.graph([b.node("a")], [], entries=["a"])
    handle = await h.make().start(g)
    with pytest.raises(RecorderError):
        await asyncio.wait_for(handle.wait(), 5)
    assert handle._execution.held_run is None
    assert handle.run.status == "failed"  # 엔진이 내부 오류로 다시 마무리, 숨김은 풀림


async def test_held_run_released_when_task_cancelled_during_flush(h: Harness, b: Builders) -> None:
    import threading

    gate = threading.Event()
    reached = threading.Event()
    original = h.recorder.events.append_many

    def slow(events: Sequence[Any]) -> int:
        if any(e.type == "run.completed" for e in events):
            reached.set()
            gate.wait(5)
        return original(events)

    h.recorder.events.append_many = slow  # type: ignore[method-assign]
    g = b.graph([b.node("a")], [], entries=["a"])
    handle = await h.make().start(g)
    assert await asyncio.to_thread(reached.wait, 5)
    handle._task.cancel()  # 종료 처리(flush) 중 바깥 취소
    gate.set()
    with pytest.raises((asyncio.CancelledError, RecorderError)):
        await handle._task
    assert handle._execution.held_run is None
    assert handle.run.status != "running"


async def test_cancelled_run_status_visible_after_wait(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("a", hang=True)], [], entries=["a"])
    handle = await h.make().start(g)
    await h.probe.started_event("a").wait()
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)
    assert run.status == "cancelled"
    assert handle.run.status == "cancelled"
    assert handle._execution.held_run is None
