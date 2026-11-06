"""6R.19 서버 후속: ``GET /runs/page``의 ``agent_id``·``conversation_id``·``root`` 거르기와
행마다 ``has_children``.

- 거르기는 옛 ``GET /runs``와 같은 결과다(같은 뜻).
- ``has_children``은 페이지 행 전체를 한 질의로 센다(행 수와 무관, N+1 없음, 계보 있는 SQLite).
- 기록 공간이 있는 조립에서도 폴더 기록 DB의 행에 채워지고, 출처 잇기 규칙은 그대로다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import Run, RunEvent
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.storage import BRANCH
from agent_console_store import InMemoryStorage, SqliteDatabase, SqliteStorage

from .test_agent_console_mod_runs_page_6r12 import (  # type: ignore[import-not-found]
    _app,
    _collect,
)
from .test_agent_console_mod_runs_records_33y2 import (  # type: ignore[import-not-found]
    API,
    Spaces,
)


def mk(id: str, at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {}, "origin": "api", "created_at": at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)


def ev(run_id: str, actor: str) -> RunEvent:
    return RunEvent(
        event_id=f"{run_id}-1", run_id=run_id, seq=1, ts=1.0, type="node.started",
        node_path=["n1"], attempt=1, actor=actor, payload={},
    )  # fmt: skip


@pytest.fixture
def db(tmp_path: Path) -> Iterator[SqliteDatabase]:
    found = SqliteDatabase.open(tmp_path / "h.sqlite3")
    found.upgrade([BRANCH])
    yield found
    found.close()


def _seed(store: Any, *, project_id: str | None = None) -> None:
    p = {"project_id": project_id} if project_id else {}
    store.runs.save(mk("r1", 1.0, conversation_id="c1", **p))
    store.runs.save(mk("k1", 2.0, parent_run_id="r1", root_run_id="r1", **p))
    store.runs.save(mk("g1", 3.0, parent_run_id="k1", root_run_id="r1", **p))
    store.runs.save(mk("r2", 4.0, conversation_id="c2", **p))
    store.runs.save(mk("r3", 5.0, conversation_id="c1", **p))
    store.events.append(ev("r1", "pl"))
    store.events.append(ev("k1", "dev"))
    store.events.append(ev("r3", "pl"))


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_filters_match_old_list_route(kind: str, db: SqliteDatabase) -> None:
    host: Any = SqliteStorage(db.engine) if kind == "sqlite" else InMemoryStorage()
    _seed(host)
    client = _app(SpaceRecorder(host))
    for query in (
        "agent_id=pl",
        "agent_id=dev",
        "conversation_id=c1",
        "root=r1",
        "root=r1&agent_id=dev",
        "conversation_id=c1&root_only=true",
        "agent_id=nobody",
    ):
        paged, _, _ = _collect(client, f"limit=1&{query}")
        old = [r["id"] for r in client.get(f"{API}/runs?{query}").json()]
        assert paged == old, query
    assert _collect(client, "root=r1&limit=1")[0] == ["g1", "k1"]


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_rows_carry_has_children(kind: str, db: SqliteDatabase) -> None:
    host: Any = SqliteStorage(db.engine) if kind == "sqlite" else InMemoryStorage()
    _seed(host)
    client = _app(SpaceRecorder(host))
    body = client.get(f"{API}/runs/page?root_only=true").json()
    assert {r["id"]: r["has_children"] for r in body["items"]} == {
        "r3": False,
        "r2": False,
        "r1": True,
    }
    kids = client.get(f"{API}/runs/page?root=r1").json()["items"]
    assert {r["id"]: r["has_children"] for r in kids} == {"g1": False, "k1": True}
    # 옛 목록은 채우지 않는다(null)
    assert {r["has_children"] for r in client.get(f"{API}/runs").json()} == {None}


def test_has_children_is_one_query_per_page(db: SqliteDatabase) -> None:
    host = SqliteStorage(db.engine)
    for i in range(60):
        host.runs.save(mk(f"r{i:02d}", float(i)))
        if i % 2:
            host.runs.save(
                mk(f"c{i:02d}", float(i) + 0.5, parent_run_id=f"r{i:02d}", root_run_id=f"r{i:02d}")
            )
    client = _app(SpaceRecorder(host))
    seen: list[str] = []

    def count(_c: Any, _cur: Any, statement: str, *_a: Any) -> None:
        seen.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", count)
    try:
        body = client.get(f"{API}/runs/page?root_only=true&limit=50").json()
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", count)
    assert len(body["items"]) == 50
    flags = {r["id"]: r["has_children"] for r in body["items"]}
    assert all(flags[k] is (int(k[1:]) % 2 == 1) for k in flags)
    selects = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2  # 페이지 한 번 + 자식 유무 한 번(행 수와 무관)


def test_spaced_project_rows_and_filters(tmp_path: Path) -> None:
    spaces = Spaces(tmp_path / "folders")
    try:
        host = InMemoryStorage()
        recorder = SpaceRecorder(host, space_records(lambda: spaces, prefix="project:"))
        folder = SqliteStorage(spaces.open("project:pa").writable_engine())
        _seed(folder, project_id="pa")
        host.runs.save(mk("old", 9.0, project_id="pa", conversation_id="c1"))
        client = _app(recorder)
        ids, sources, _ = _collect(client, "project=pa&conversation_id=c1&limit=1")
        assert ids == ["r3", "r1", "old"]
        assert sources == ["project", "project", "app"]
        kids = client.get(f"{API}/runs/page?project=pa&root=r1").json()
        assert {r["id"]: r["has_children"] for r in kids["items"]} == {"g1": False, "k1": True}
        assert kids["next_cursor"] is None  # 앱 DB에 그 루트의 자손이 없다
        agent = client.get(f"{API}/runs/page?project=pa&agent_id=dev").json()
        assert [r["id"] for r in agent["items"]] == ["k1"]
        assert agent["items"][0]["project_id"] == "pa"
    finally:
        spaces.close_all()
