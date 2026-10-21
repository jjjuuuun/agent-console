"""취소 전파, 재시작 복구, 프로세스 그룹 종료."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any

import pytest

from agent_console_contracts import NodeRun, Run, RunStatus
from agent_console_runtime import (
    CancelToken,
    OperationCancelledError,
    RuntimeErrorCodes,
    aterminate_process_group,
    process_group_kwargs,
    recover_unfinished_runs,
    terminate_process_group,
)
from agent_console_runtime.testing import (
    BUILDERS,
    Builders,
    Harness,
    InMemoryRecorder,
    SequentialIds,
    make_harness,
)


@pytest.fixture
def h() -> Harness:
    return make_harness()


@pytest.fixture
def b() -> Builders:
    return BUILDERS


def statuses(h: Harness, run_id: str) -> dict[str, str]:
    return {nr.node_id: nr.status for nr in h.recorder.runs.list_node_runs(run_id)}


async def test_cancel_propagates_to_running_nodes(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("s"), b.node("hang1", hang=True), b.node("hang2", hang=True), b.node("next")],
        [b.edge("s", "hang1"), b.edge("s", "hang2"), b.edge("hang1", "next")],
        entries=["s"],
    )
    rt = h.make()
    handle = await rt.start(g)
    await h.probe.started_event("hang1").wait()
    await h.probe.started_event("hang2").wait()
    assert rt.cancel(handle.run_id, "사용자 취소") is True
    assert rt.cancel(handle.run_id) is False  # 두 번째 요청은 무시
    run = await handle.wait()

    assert run.status == "cancelled"
    assert run.error is not None
    assert run.error.code == RuntimeErrorCodes.CANCELLED
    assert run.error.message == "사용자 취소"
    assert sorted(h.probe.cancel_callbacks) == ["hang1", "hang2"]
    assert statuses(h, run.id) == {
        "s": "succeeded",
        "hang1": "cancelled",
        "hang2": "cancelled",
        "next": "skipped",
    }
    types = [e.type for e in h.recorder.events.list(run.id)]
    assert types.count("node.cancelled") == 2
    assert types[-1] == "run.cancelled"


async def test_cancel_ignoring_nodes_are_force_cancelled(h: Harness, b: Builders) -> None:
    g = b.graph([b.node("stub", stubborn=True)], [], entries=["stub"])
    rt = h.make(cancel_grace=0.05)
    handle = await rt.start(g)
    await h.probe.started_event("stub").wait()
    started = time.monotonic()
    handle.cancel()
    run = await asyncio.wait_for(handle.wait(), 5)
    assert time.monotonic() - started < 2
    assert run.status == "cancelled"
    assert statuses(h, run.id) == {"stub": "cancelled"}


async def test_queued_nodes_are_cancelled_without_starting(h: Harness, b: Builders) -> None:
    g = b.graph(
        [b.node("s"), b.node("a", hang=True), b.node("q")],
        [b.edge("s", "a"), b.edge("s", "q")],
        entries=["s"],
    )
    rt = h.make(max_concurrency=1)
    handle = await rt.start(g)
    await h.probe.started_event("a").wait()
    handle.cancel()
    run = await handle.wait()
    assert statuses(h, run.id) == {"s": "succeeded", "a": "cancelled", "q": "cancelled"}
    assert "q" not in {c[0] for c in h.probe.calls}


async def test_shutdown_cancels_all_runs(h: Harness, b: Builders) -> None:
    rt = h.make()
    handles = [
        await rt.start(b.graph([b.node("a", hang=True)], [], entries=["a"])) for _ in range(2)
    ]
    await asyncio.sleep(0.01)
    await rt.shutdown()
    assert [hd.run.status for hd in handles] == ["cancelled", "cancelled"]
    assert rt.active_run_ids() == []


async def test_cancel_token_basics() -> None:
    token = CancelToken()
    seen: list[str] = []
    unregister = token.on_cancel(lambda: seen.append("a"))
    token.on_cancel(lambda: 1 / 0)  # 콜백 예외는 다른 콜백을 막지 않는다
    token.on_cancel(lambda: seen.append("b"))
    unregister()
    token.raise_if_cancelled()
    assert token.cancel("why") is True
    assert token.cancel() is False
    assert seen == ["b"]
    assert token.reason == "why"
    token.on_cancel(lambda: seen.append("late"))
    assert seen == ["b", "late"]
    await asyncio.wait_for(token.wait(), 1)
    with pytest.raises(OperationCancelledError):
        token.raise_if_cancelled()


def test_recover_marks_unfinished_runs_interrupted() -> None:
    rec = InMemoryRecorder()
    statuses_: list[tuple[str, RunStatus]] = [
        ("r1", "running"),
        ("r2", "completed"),
        ("r3", "queued"),
    ]
    for rid, status in statuses_:
        rec.runs.save(
            Run(
                id=rid,
                graph_id="g",
                graph_version="v",
                status=status,
                input={},
                origin="api",
                created_at=1.0,
            )
        )
    rec.runs.save_node_run(NodeRun(run_id="r1", node_id="a", status="succeeded"))
    rec.runs.save_node_run(NodeRun(run_id="r1", node_id="b", status="running", started_at=5.0))
    rec.runs.save_node_run(NodeRun(run_id="r1", node_id="w", status="waiting"))
    from agent_console_contracts import RunEvent

    rec.events.append(
        RunEvent(event_id="old", run_id="r1", seq=7, ts=1.0, type="run.started", node_path=[])
    )
    published: list[Any] = []

    class Sink:
        def publish(self, event: Any) -> None:
            published.append(event)

    ids = recover_unfinished_runs(rec, clock=lambda: 10.0, ids=SequentialIds("x"), sink=Sink())

    assert sorted(ids) == ["r1", "r3"]
    assert rec.runs.get("r1") is not None
    r1 = rec.runs.get("r1")
    assert r1 is not None
    assert r1.status == "interrupted"
    assert r1.ended_at == 10.0
    assert r1.error is not None
    assert r1.error.code == "interrupted"
    nodes = {n.node_id: n for n in rec.runs.list_node_runs("r1")}
    assert nodes["a"].status == "succeeded"
    assert nodes["b"].status == "cancelled"
    assert nodes["b"].duration_ms == 5000
    # 1R(design §R14.5): 재개할 parked wait가 없으므로 waiting 노드도 끊긴 것으로 정리한다.
    assert nodes["w"].status == "cancelled"
    assert nodes["w"].error is not None
    assert nodes["w"].error.code == "interrupted"
    events = rec.events.list("r1")
    assert [(e.seq, e.type) for e in events[1:]] == [
        (8, "node.cancelled"),
        (9, "node.cancelled"),
        (10, "run.interrupted"),
    ]
    assert [e.type for e in published].count("run.interrupted") == 2
    r2 = rec.runs.get("r2")
    assert r2 is not None
    assert r2.status == "completed"


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX 프로세스 그룹 검사")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # 좀비(종료됐지만 회수 전)는 죽은 것으로 본다.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except OSError:
        return True


def _child_pid(proc_pid: int, deadline: float = 5.0) -> int:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        out = subprocess.run(
            ["pgrep", "-g", str(proc_pid)], capture_output=True, text=True, check=False
        ).stdout.split()
        children = [int(p) for p in out if int(p) != proc_pid]
        if children:
            return children[0]
        time.sleep(0.05)
    raise AssertionError("자식 프로세스가 보이지 않음")


@posix_only
def test_terminate_process_group_kills_children() -> None:
    proc = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], **process_group_kwargs())
    child = _child_pid(proc.pid)
    terminate_process_group(proc, grace=1.0)
    assert proc.poll() is not None
    deadline = time.monotonic() + 3
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child)
    terminate_process_group(proc)  # 이미 끝난 그룹: 조용히 무시
    terminate_process_group(None)


@posix_only
async def test_aterminate_process_group_kills_sigterm_ignoring_group() -> None:
    proc = await asyncio.create_subprocess_exec(
        "sh", "-c", "trap '' TERM; sleep 30 & wait", **process_group_kwargs()
    )
    await asyncio.sleep(0.2)
    await aterminate_process_group(proc, grace=0.3)
    assert proc.returncode is not None
    await aterminate_process_group(None)
