"""5R.6 QA: 호출 대상이 되묻기 대기 중일 때 서버 재시작 복구(실 SQLite 저장소)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from agent_console_runtime import recover_unfinished_runs
from agent_console_runtime.testing import BUILDERS, Harness, make_harness
from agent_console_store import open_sqlite


async def test_waiting_call_target_is_interrupted_after_restart(tmp_path: Path) -> None:
    from agent_console_runtime import GraphRuntime, Services
    from agent_console_runtime.testing import PROBE, Probe

    h: Harness = make_harness()
    db_path = tmp_path / "db.sqlite3"
    db = open_sqlite(db_path)
    probe = Probe()
    rt = GraphRuntime(h.registries, db, None, services=Services({PROBE: probe}), max_concurrency=1)
    g = BUILDERS.graph(
        [
            BUILDERS.node("lead", type="t.lead"),
            BUILDERS.node("M", type="t.lead"),
            BUILDERS.node("Q", type="t.asker", asks=[{}]),
        ],
        [
            BUILDERS.edge("lead", "M", kind="t.invoke", sp="alt", tp="in2"),
            BUILDERS.edge("M", "Q", kind="t.invoke", sp="alt", tp="in2"),
        ],
        entries=["lead"],
    )
    handle = await rt.start(g)
    for _ in range(500):
        if rt.pending(run_id=handle.run_id):
            break
        await asyncio.sleep(0.01)
    assert len(rt.pending(run_id=handle.run_id)) == 1
    for _ in range(100):
        if handle.run.status == "waiting":
            break
        await asyncio.sleep(0.01)
    for _ in range(200):
        got = {(n.node_id, n.call): n.status for n in db.runs.list_node_runs(handle.run_id)}
        if got.get(("Q", 0)) == "waiting":
            break
        await asyncio.sleep(0.01)
    # 크래시 흉내: 별도 연결로 복구를 돌린다(엔진 프로세스는 그대로).
    db2 = open_sqlite(db_path)
    try:
        run_id = handle.run_id
        before = {(n.node_id, n.call): n.status for n in db2.runs.list_node_runs(run_id)}
        assert before[("Q", 0)] == "waiting", before
        assert recover_unfinished_runs(db2) == [run_id]
        after = {
            (n.node_id, n.call): (n.status, n.invoked_by) for n in db2.runs.list_node_runs(run_id)
        }
        assert after[("Q", 0)][0] == "cancelled"
        assert after[("Q", 0)][1] == ["lead", "M"]
        assert after[("M", 0)][0] == "cancelled"
        assert after[("lead", 0)][0] == "cancelled"
        stored = db2.runs.get(run_id)
        assert stored is not None
        assert stored.status == "interrupted"
        assert db2.interactions.list(run_id=run_id, status="pending") == []
        ev = [e for e in db2.events.list(run_id) if e.type == "node.cancelled"]
        assert ["lead", "M", "Q"] in [e.node_path for e in ev]
    finally:
        db2.close()
        # 살아 있는 엔진은 복구가 바꾼 기록과 충돌하므로(흉내의 부산물) 정리 오류는 무시한다.
        handle.cancel()
        try:
            await asyncio.wait_for(handle.wait(), 5)
            await rt.shutdown()
        except Exception:
            pass
        db.close()
