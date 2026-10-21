"""5R.7 QA: 자식 Run이 상호작용 대기 중일 때 서버가 죽은 뒤(실 SQLite) 복구 결과."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from agent_console_runtime import GraphRuntime, recover_unfinished_runs
from agent_console_runtime.testing import BUILDERS as BLD
from agent_console_runtime.testing import make_harness
from agent_console_store import SqliteDatabase, SqliteStorage


async def test_restart_with_waiting_child_on_real_sqlite(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "a.sqlite3")
    db.upgrade()
    storage = SqliteStorage(db.engine)
    h = make_harness()
    rt = GraphRuntime(h.registries, storage, h.sink, services=h.make().services)
    child = BLD.graph(
        [BLD.node("Q", type="t.asker", asks=[{"title": "?"}])],
        [BLD.reply("Q")],
        "child",
        entries=["Q"],
    )
    parent = BLD.graph(
        [BLD.node("N", type="t.nest", graph=child.model_dump(mode="json"))],
        [BLD.reply("N")],
        "parent",
        entries=["N"],
    )
    handle = await rt.start(parent, conversation_id="conv")
    for _ in range(500):
        if rt.pending() and handle.run.status == "waiting":
            break
        await asyncio.sleep(0.01)
    assert rt.pending()
    for _ in range(500):
        if h.sink is not None and storage.interactions.get(rt.pending()[0].id) is not None:
            break
        await asyncio.sleep(0.01)
    # 서버가 죽은 시점의 DB 사본(sqlite backup)
    copy = tmp_path / "b.sqlite3"
    src = sqlite3.connect(tmp_path / "a.sqlite3")
    dst = sqlite3.connect(copy)
    src.backup(dst)
    dst.close()
    src.close()
    await rt.shutdown("x", interrupt=True)
    db.close()
    assert copy.exists()

    db2 = SqliteDatabase.open(copy)
    db2.upgrade()
    st2 = SqliteStorage(db2.engine)
    ids = recover_unfinished_runs(st2)
    runs = {r.id: r for r in st2.runs.list()}
    assert len(runs) == 2
    assert sorted(ids) == sorted(runs)
    assert {r.status for r in runs.values()} == {"interrupted"}
    child_run = next(r for r in runs.values() if r.parent_run_id)
    assert child_run.root_run_id == handle.run_id
    assert child_run.conversation_id is None
    inter = st2.interactions.list(run_id=child_run.id)
    assert len(inter) == 1
    assert (inter[0].status, inter[0].root_run_id, inter[0].conversation_id) == (
        "expired",
        handle.run_id,
        "conv",
    )
    for r in runs.values():
        assert all(
            n.status != "running" and n.status != "waiting" for n in st2.runs.list_node_runs(r.id)
        )
    db2.close()
