"""6R.19 잔여: ``GET /runs/page``의 ``since``(created_at 하한)·``q``(부분 일치 검색).

- ``q``는 run id·graph_id·입력 최상위 문자열 값(대소문자 무시, LIKE 특수 글자는 글자 그대로),
  길이 상한을 넘으면 422.
- 커서로 이어 붙여도 조건이 유지된다. 기록 공간이 있는 조립에서는 폴더 기록 DB → 앱 DB 옛 기록
  잇기에도 같은 조건이 걸린다(옛 기록에 맞는 행이 없으면 끝).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from agent_console_contracts import Run
from agent_console_mod_runs import SpaceRecorder, space_records
from agent_console_mod_runs.routes import MAX_RUN_QUERY_LENGTH
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


@pytest.fixture
def db(tmp_path: Path) -> Iterator[SqliteDatabase]:
    found = SqliteDatabase.open(tmp_path / "h.sqlite3")
    found.upgrade([BRANCH])
    yield found
    found.close()


def _seed(store: Any, *, project_id: str | None = None) -> None:
    p = {"project_id": project_id} if project_id else {}
    store.runs.save(mk("r1", 1.0, input={"text": "Login 버그"}, **p))
    store.runs.save(mk("r2", 2.0, graph_id="pay-team", input={"text": "50% off"}, **p))
    store.runs.save(mk("r3", 3.0, input={"text": "login again"}, **p))
    store.runs.save(mk("k3", 3.5, parent_run_id="r3", root_run_id="r3", **p))
    store.runs.save(mk("r4", 4.0, input={"text": "other"}, **p))


@pytest.mark.parametrize("kind", ["sqlite", "memory"])
def test_q_and_since_follow_cursor(kind: str, db: SqliteDatabase) -> None:
    host: Any = SqliteStorage(db.engine) if kind == "sqlite" else InMemoryStorage()
    _seed(host)
    client = _app(SpaceRecorder(host))
    assert _collect(client, "limit=1&q=LOGIN")[0] == ["r3", "r1"]
    assert _collect(client, f"limit=1&q={quote('버그')}")[0] == ["r1"]
    assert _collect(client, "limit=1&q=PAY")[0] == ["r2"]  # graph_id
    assert _collect(client, "limit=1&q=R3")[0] == ["r3"]  # id만(자식 k3의 부모 id는 보지 않음)
    assert _collect(client, f"limit=1&q={quote('0%')}")[0] == ["r2"]
    assert _collect(client, f"limit=1&q={quote('_')}")[0] == []
    assert _collect(client, "limit=1&since=3")[0] == ["r4", "k3", "r3"]
    assert _collect(client, "limit=1&since=3&q=login&root_only=true")[0] == ["r3"]
    assert _collect(client, "limit=2&q=")[0] == ["r4", "k3", "r3", "r2", "r1"]


def test_q_matches_id_not_parent(db: SqliteDatabase) -> None:
    host = SqliteStorage(db.engine)
    host.runs.save(mk("root", 1.0))
    host.runs.save(mk("kid", 2.0, parent_run_id="root", root_run_id="root"))
    client = _app(SpaceRecorder(host))
    assert _collect(client, "q=root")[0] == ["root"]


def test_q_length_limit(db: SqliteDatabase) -> None:
    client = _app(SpaceRecorder(SqliteStorage(db.engine)))
    ok = client.get(f"{API}/runs/page?q={'a' * MAX_RUN_QUERY_LENGTH}")
    assert ok.status_code == 200
    too_long = client.get(f"{API}/runs/page?q={'a' * (MAX_RUN_QUERY_LENGTH + 1)}")
    assert too_long.status_code == 422
    assert client.get(f"{API}/runs/page?since=abc").status_code == 422


def test_spaced_project_applies_q_and_since_to_both_sources(tmp_path: Path) -> None:
    spaces = Spaces(tmp_path / "folders")
    try:
        host = InMemoryStorage()
        recorder = SpaceRecorder(host, space_records(lambda: spaces, prefix="project:"))
        folder = SqliteStorage(spaces.open("project:pa").writable_engine())
        _seed(folder, project_id="pa")
        host.runs.save(mk("old-login", 0.5, project_id="pa", input={"text": "x"}))
        host.runs.save(mk("old-other", 9.0, project_id="pa", input={"text": "LOGIN 옛"}))
        host.runs.save(mk("old-none", 9.5, project_id="pa"))
        client = _app(recorder)
        ids, sources, _ = _collect(client, "project=pa&q=login&limit=1")
        assert ids == ["r3", "r1", "old-other", "old-login"]
        assert sources == ["project", "project", "app", "app"]
        ids, sources, _ = _collect(client, "project=pa&since=4&limit=1")
        assert ids == ["r4", "old-none", "old-other"]
        assert sources == ["project", "app", "app"]
        # 옛 기록에 맞는 행이 없으면 폴더 기록 끝에서 멈춘다
        body = client.get(f"{API}/runs/page?project=pa&q=pay").json()
        assert [r["id"] for r in body["items"]] == ["r2"]
        assert body["next_cursor"] is None
    finally:
        spaces.close_all()
