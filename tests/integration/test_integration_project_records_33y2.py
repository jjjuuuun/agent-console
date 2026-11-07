"""5.7R.33y2 통합: 실행·대화 기록을 프로젝트 기록 DB(``<폴더>/.agent-console/records.sqlite3``)에.

design §PI.4.6.3·.5·.6(K33-27·K33-30·K33-31). 설치된 모듈 전부(앱 조립, fake 백엔드).

- 프로젝트 A·B의 실행·대화가 각 폴더 기록 DB에만 있고 앱 DB에는 0행. ``?source=app``은 앱 DB.
- Run에 ``host_id``. 다른 앱(``host_id``가 다름)의 끝나지 않은 Run은 재시작 복구가 건드리지 않고,
  자기 앱 것만 ``interrupted``. [끊긴 것으로 표시]는 다른 앱 Run도 바꾼다.
- 앞선 리비전(더 새 앱이 올린 기록 DB) → 실행 시작 409 ``project.records_unavailable``(``newer``),
  목록은 읽힘.
- 실행 중 폴더가 사라짐 → Run 취소 + 앱 대기 파일 → 폴더가 돌아오면 다음 열기 때 모두 들어감.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    register_project,
    server,
    team_graph,
)

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _records(folder: Path) -> Path:
    return folder / ".agent-console" / "records.sqlite3"


def _count(db: Path, table: str, where: str = "") -> int:
    con = sqlite3.connect(db)
    try:
        return int(con.execute(f"select count(*) from {table} {where}").fetchone()[0])
    finally:
        con.close()


def _app_db(tmp_path: Path) -> Path:
    found = sorted((tmp_path / "ws").rglob("*.sqlite3"))
    found = [p for p in found if "records" not in p.name and "memory" not in p.name]
    assert found, "앱 DB가 없다"
    return found[0]


def _graph() -> dict[str, Any]:
    doc = team_graph()
    for edge in doc["edges"]:
        edge["config"].pop("input_key", None)
    return doc


def _seed(client: TestClient, project: str, *, slow: dict[str, Any] | None = None) -> None:
    fast = agent_doc("fast", f"{project} 빠른 답")
    deep = agent_doc("slow", f"{project} 깊은 답 " + "가" * 40)
    if slow:
        deep["backend_options"].update(slow)
    for doc in (fast, deep):
        assert client.post(f"{API}/agents?project={project}", json=doc).status_code == 201
    response = client.post(f"{API}/graphs?project={project}", json=_graph())
    assert response.status_code == 201, response.text


def _start(client: TestClient, project: str) -> str:
    body = {"graph_id": "flow", "input": {"text": "hi"}, "project_id": project}
    response = client.post(f"{API}/runs", json=body)
    assert response.status_code == 202, response.text
    run_id: str = response.json()["id"]
    return run_id


def _wait(client: TestClient, run_id: str, project: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}?project={project}").json()
        if snap.get("run", {}).get("status") in TERMINAL:
            return snap
        time.sleep(0.03)
    raise AssertionError(f"Run {run_id}가 끝나지 않았다")


@contextmanager
def _app(tmp_path: Path) -> Iterator[TestClient]:
    with server(make_settings(tmp_path)) as client:
        yield client


def _host_id(tmp_path: Path) -> str:
    found = sorted((tmp_path / "ws").rglob("host_id"))
    assert found, "host_id 파일이 없다"
    return found[0].read_text(encoding="utf-8").strip()


def test_runs_and_conversations_go_to_each_project_records_db(tmp_path: Path) -> None:
    folders = {"pa": tmp_path / "A", "pb": tmp_path / "B"}
    for folder in folders.values():
        folder.mkdir()
    with _app(tmp_path) as client:
        for pid, folder in folders.items():
            register_project(client, pid, folder)
            _seed(client, pid)
        runs = {pid: _start(client, pid) for pid in folders}
        snaps = {pid: _wait(client, rid, pid) for pid, rid in runs.items()}
        for pid, snap in snaps.items():
            assert snap["run"]["status"] == "completed"
            assert snap["run"]["project_id"] == pid
            assert snap["run"]["host_id"] == _host_id(tmp_path)

        # 목록 = 그 프로젝트 기록 DB만, 앱 DB 옛 기록(source=app)은 비어 있다.
        listed_a = client.get(f"{API}/runs?project=pa").json()
        assert [r["id"] for r in listed_a] == [runs["pa"]]
        assert client.get(f"{API}/runs?project=pa&source=app").json() == []
        events = client.get(f"{API}/runs/{runs['pa']}/events?project=pa").json()
        assert events
        assert all(e["run_id"] == runs["pa"] for e in events)

        # 대화도 그 프로젝트 기록 DB에.
        conv = client.post(
            f"{API}/conversations", json={"graph_id": "flow", "project_id": "pb", "title": "t"}
        )
        assert conv.status_code == 201, conv.text
        cid = conv.json()["id"]
        sent = client.post(f"{API}/conversations/{cid}/messages?project=pb", json={"text": "안녕"})
        assert sent.status_code == 202, sent.text
        # 턴은 보낸 Run id로 찾는다(목록 순서는 벽시계 created_at 순이라 시계가 뒤로 가면 흔들린다).
        run_id = sent.json()["id"]
        deadline = time.monotonic() + 15
        mine: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            turns = client.get(f"{API}/conversations/{cid}/turns?project=pb").json()
            mine = [t for t in turns if t["run_id"] == run_id]
            if mine and mine[0]["status"] in TERMINAL:
                break
            time.sleep(0.05)
        assert mine, turns
        assert mine[0]["status"] == "completed"
        listed = client.get(f"{API}/conversations?project=pb").json()
        assert [c["id"] for c in listed] == [cid]
        assert client.get(f"{API}/conversations?project=pa").json() == []
        assert client.get(f"{API}/conversations/{cid}?project=pb").status_code == 200

    app = _app_db(tmp_path)
    assert _count(app, "runs") == 0
    assert _count(app, "conversations") == 0
    assert _count(_records(folders["pa"]), "runs") == 1
    assert _count(_records(folders["pb"]), "runs") == 2  # 실행 1 + 대화 턴 1
    assert _count(_records(folders["pb"]), "conversations") == 1
    assert _count(_records(folders["pa"]), "conversations") == 0
    assert _count(_records(folders["pa"]), "run_events") > 0


def test_restart_recovery_only_touches_own_host_runs(tmp_path: Path) -> None:
    folder = tmp_path / "B"
    folder.mkdir()
    with _app(tmp_path) as client:
        register_project(client, "pb", folder)
        _seed(client, "pb")
        _wait(client, _start(client, "pb"), "pb")
    mine = _host_id(tmp_path)
    db = _records(folder)
    con = sqlite3.connect(db)
    try:
        row = con.execute("select doc from runs limit 1").fetchone()[0]
    finally:
        con.close()

    import json

    base = json.loads(row)

    def put(run_id: str, host: str) -> None:
        doc = {**base, "id": run_id, "status": "running", "ended_at": None, "host_id": host}
        con = sqlite3.connect(db)
        try:
            con.execute(
                "insert into runs (id, graph_id, graph_version, status, origin, created_at, doc,"
                " project_id) values (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    doc["graph_id"],
                    doc["graph_version"],
                    "running",
                    doc["origin"],
                    doc["created_at"],
                    json.dumps(doc),
                    "pb",
                ),
            )
            con.commit()
        finally:
            con.close()

    put("own-run", mine)
    put("other-run", "other-host-1234")
    with _app(tmp_path) as client:
        listed = {r["id"]: r for r in client.get(f"{API}/runs?project=pb").json()}
        assert listed["own-run"]["status"] == "interrupted"
        assert listed["other-run"]["status"] == "running"  # 다른 앱의 실행을 끊지 않는다
        assert listed["other-run"]["host_id"] == "other-host-1234"
        marked = client.post(f"{API}/runs/other-run/mark-interrupted?project=pb")
        assert marked.status_code == 200, marked.text
        assert marked.json()["status"] == "interrupted"
        snap = client.get(f"{API}/runs/other-run?project=pb").json()
        assert snap["run"]["status"] == "interrupted"
        missing = client.post(f"{API}/runs/nope/mark-interrupted?project=pb")
        assert missing.status_code == 404


def test_newer_records_db_refuses_new_runs_but_reads(tmp_path: Path) -> None:
    folder = tmp_path / "C"
    folder.mkdir()
    with _app(tmp_path) as client:
        register_project(client, "pc", folder)
        _seed(client, "pc")
        _wait(client, _start(client, "pc"), "pc")
    con = sqlite3.connect(_records(folder))
    try:
        con.execute("update alembic_version_runs set version_num = 'runs_9999_future'")
        con.commit()
    finally:
        con.close()
    with _app(tmp_path) as client:
        refused = client.post(
            f"{API}/runs", json={"graph_id": "flow", "input": {"text": "x"}, "project_id": "pc"}
        )
        assert refused.status_code == 409, refused.text
        error = refused.json()["error"]
        assert error["code"] == "project.records_unavailable"
        assert error["details"]["reason"] == "newer"
        assert len(client.get(f"{API}/runs?project=pc").json()) == 1  # 읽기 전용으로 보인다
    assert _count(_app_db(tmp_path), "runs") == 0  # 앱 DB로 대신 쓰지 않는다


def test_folder_vanishing_mid_run_cancels_and_spools_then_replays(tmp_path: Path) -> None:
    folder = tmp_path / "D"
    folder.mkdir()
    away = tmp_path / "D-away"
    with _app(tmp_path) as client:
        register_project(client, "pd", folder)
        _seed(client, "pd", slow={"delay_ms": 40, "chunk_chars": 1})
        run_id = _start(client, "pd")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:  # 깊은(느린) 노드가 돌기 시작한 뒤
            nodes = client.get(f"{API}/runs/{run_id}?project=pd").json().get("node_runs", [])
            if any(n["node_id"] == "b" and n["status"] == "running" for n in nodes):
                break
            time.sleep(0.02)
        folder.rename(away)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if client.get(f"{API}/runs/{run_id}/interactions").status_code == 404:
                break  # 더는 이 프로세스에서 돌지 않는다(폴더가 없어 저장본도 못 읽음)
            time.sleep(0.05)
        spooled = sorted(tmp_path.rglob("records-spool/**/*.jsonl"))
        assert spooled, "대기 파일이 없다"
        away.rename(folder)
        snap = client.get(f"{API}/runs/{run_id}?project=pd").json()
        assert snap["run"]["status"] == "cancelled"
        assert snap["run"]["error"]["code"] == "project.records_unavailable"
        assert not sorted(tmp_path.rglob("records-spool/**/*.jsonl"))  # 다 들어가고 지워졌다
        events = client.get(f"{API}/runs/{run_id}/events?project=pd").json()
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(set(seqs))  # 중복 없음
        assert events[-1]["type"] == "run.cancelled"
