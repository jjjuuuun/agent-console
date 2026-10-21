"""Run 종료 공개 순서(5.2R.39, design §5.2R.7 "채팅 진행 지연 + f1").

계약: ``RunHandle.run``이 종료 상태(``completed`` 등)를 보이면 그 Run의 기록 — 답변(``run.reply``)을
포함한 모든 이벤트, 최종 Run, ``run.<상태>`` 이벤트 — 은 이미 저장소에 저장되고 구독자(sink)에
발행됐다. 저장이 느린 부하 상황을 저장소 지연 주입으로 흉내 낸다.
"""

from __future__ import annotations

import asyncio
import random
import threading
from collections.abc import Sequence
from typing import Any

import pytest

from agent_console_runtime import RunHandle
from agent_console_runtime.testing import BUILDERS, Builders, Harness, make_harness

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def _graph(b: Builders) -> Any:
    return b.graph(
        [b.node("a", outputs={"out": "hello"}), b.node("c")],
        [b.edge("a", "c"), b.reply("a")],
        entries=["a"],
    )


def _check_visible(h: Harness, handle: RunHandle, seen: list[str]) -> None:
    """손잡이가 종료 상태를 보이면 답변·종료 이벤트가 저장·발행됐는지 본다."""
    run = handle.run
    seen.append(run.status)
    if run.status not in TERMINAL:
        return
    stored = [e.type for e in h.recorder.events.list(run.id)]
    published = [e.type for e in h.sink.events if e.run_id == run.id]
    assert "run.reply" in stored, stored
    assert stored[-1] == f"run.{run.status}", stored
    assert published[-1] == f"run.{run.status}", published
    saved = h.recorder.runs.get(run.id)
    assert saved is not None
    assert saved.status == run.status


async def test_final_status_hidden_until_reply_is_stored(h: Harness, b: Builders) -> None:
    gate = threading.Event()
    reached = threading.Event()
    original = h.recorder.events.append_many

    def gated(events: Sequence[Any]) -> int:
        if any(e.type == "run.reply" for e in events):
            reached.set()
            gate.wait(10)
        return original(events)

    h.recorder.events.append_many = gated  # type: ignore[method-assign]
    handle = await h.make().start(_graph(b), {"text": "hi"})
    blocked: list[str] = []
    try:
        assert await asyncio.to_thread(reached.wait, 10)
        # 답변 저장이 막힌 동안 엔진은 노드를 끝내고 종료 처리까지 간다. 손잡이는 끝난 상태를
        # 숨긴다(실패해도 Run을 끝까지 기다린 뒤 단언한다 — 루프 정리 중 멈춤 방지).
        for _ in range(50):
            await asyncio.sleep(0.005)
            blocked.append(handle.run.status)
    finally:
        gate.set()
        run = await handle.wait()
    assert set(blocked) == {"running"}, blocked
    assert run.status == "completed"
    seen: list[str] = []
    _check_visible(h, handle, seen)
    assert seen == ["completed"]


async def test_visible_final_status_implies_stored_events_under_delay(
    h: Harness, b: Builders
) -> None:
    """저장 지연(0~4ms 무작위)을 넣고 여러 Run을 동시에 돌리며 손잡이를 계속 들여다본다."""
    rng = random.Random(39)
    original = h.recorder.events.append_many
    lock = threading.Lock()

    def slow(events: Sequence[Any]) -> int:
        with lock:
            delay = rng.random() * 0.004
        threading.Event().wait(delay)
        return original(events)

    h.recorder.events.append_many = slow  # type: ignore[method-assign]
    runtime = h.make()

    async def watch() -> tuple[list[str], list[str]]:
        handle = await runtime.start(_graph(b), {"text": "hi"})
        seen: list[str] = []
        problems: list[str] = []
        while not handle.done():
            try:
                _check_visible(h, handle, seen)
            except AssertionError as exc:  # Run은 끝까지 돌린 뒤 모아서 단언한다
                problems.append(str(exc))
            await asyncio.sleep(0)
        await handle.wait()
        _check_visible(h, handle, seen)
        return seen, problems

    results = await asyncio.gather(*(watch() for _ in range(30)))
    assert [p for _, problems in results for p in problems] == []
    assert all(seen[-1] == "completed" for seen, _ in results)
