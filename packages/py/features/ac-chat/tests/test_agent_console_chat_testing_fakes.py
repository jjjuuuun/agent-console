"""공개 테스트 도우미(`agent_console_chat.testing`) 자체 테스트."""

import asyncio

import pytest

from agent_console_chat import TurnStart
from agent_console_chat.testing import FakeLauncher, MemoryEvents, MemoryRuns
from agent_console_contracts import Graph


def _turn(text: str) -> TurnStart:
    return TurnStart(
        conversation_id="c", graph=Graph(id="g", name="g"), input={"text": text}, text=text
    )


async def test_wait_started_returns_handle_of_nth_turn_started_later() -> None:
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    await launcher.start_turn(_turn("a"))
    waiter = asyncio.create_task(launcher.wait_started(2))
    await asyncio.sleep(0)
    assert not waiter.done()
    second = await launcher.start_turn(_turn("b"))
    assert await waiter is second
    assert (await launcher.wait_started(1)).run_id == "run-1"  # 이미 시작한 턴은 바로


async def test_wait_started_times_out_and_rejects_bad_count() -> None:
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    with pytest.raises(TimeoutError):
        await launcher.wait_started(1, timeout=0.01)
    with pytest.raises(ValueError, match="count"):
        await launcher.wait_started(0)
