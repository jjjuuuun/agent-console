"""`WorkGate`: 배경 스레드 작업 수 세기 + 닫힘(종료 훅이 진행 중인 작업을 기다린다)."""

from __future__ import annotations

import asyncio
import threading

from agent_console_modkit import WorkGate


def test_close_and_wait_waits_for_running_thread_work() -> None:
    gate = WorkGate()
    entered = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def work() -> str:
        entered.set()
        assert release.wait(5)
        order.append("work-done")
        return "ok"

    async def scenario() -> None:
        job = asyncio.ensure_future(asyncio.to_thread(gate.run, work, lambda: "stopped"))
        assert await asyncio.to_thread(entered.wait, 5)
        assert gate.busy == 1
        waiting = asyncio.ensure_future(gate.close_and_wait(5))
        await asyncio.sleep(0.1)
        assert not waiting.done()
        assert gate.run(lambda: "late", lambda: "stopped") == "stopped"  # 닫힌 뒤 새 작업 없음
        release.set()
        assert await waiting
        order.append("closed")
        assert await job == "ok"

    asyncio.run(scenario())
    assert order == ["work-done", "closed"]
    assert gate.busy == 0


def test_close_and_wait_is_bounded_and_reopen_accepts_work() -> None:
    gate = WorkGate()
    release = threading.Event()
    entered = threading.Event()

    def stuck() -> None:
        entered.set()
        release.wait(5)

    worker = threading.Thread(target=gate.run, args=(stuck,))
    worker.start()
    try:
        assert entered.wait(5)
        assert asyncio.run(gate.close_and_wait(0.05)) is False
    finally:
        release.set()
        worker.join(5)
    gate.reopen()
    assert gate.run(lambda: 1, lambda: 0) == 1


def test_run_without_stopped_still_runs_after_close() -> None:
    gate = WorkGate()
    gate.close()
    assert gate.run(lambda: "ran") == "ran"
    assert asyncio.run(gate.close_and_wait(0)) is True
