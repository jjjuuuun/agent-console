"""5.7R.33y3 통합: 대화 세션 기록 보관(``<폴더>/.agent-console/sessions/``)과 이어 가기 상태(X38).

design §PI.4.6.4(K33-29). 설치된 모듈 전부(앱 조립). 실행 백엔드는 fake(``session_dir``로 세션 기록
파일 흉내 — 이어 쓰는 요청인데 그 앱에 파일이 없으면 실패). SDK·``~/.claude``를 쓰지 않는다.

- 앱 A에서 대화 → 폴더에 보관 사본(그 세션 파일만).
- 다른 workspace의 앱 B가 같은 폴더를 등록 → 지난 대화가 보이고 상태 ``archived``, 보내면 보관
  사본을 B 자격 폴더로 복원해 이어 간다(``run.started`` 맥락 ``chat_sessions``).
- 보관 사본을 지우면 앱 C는 ``continuable=false``, 보내기 409 ``chat.session_unavailable``,
  ``on_missing_session: "fresh"``면 새 세션으로 이어 간다.
- 보관을 끄면 ``sessions/``가 생기지 않는다.
"""

from __future__ import annotations

import shutil
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
SESSION_DIR = ".state/fake-sessions"


def _graph() -> dict[str, Any]:
    doc = team_graph()
    for edge in doc["edges"]:
        edge["config"].pop("input_key", None)
    return doc


@contextmanager
def _app(base: Path, *, archive: bool = True) -> Iterator[TestClient]:
    options: dict[str, dict[str, Any]] = {
        "mod-runs": {"backends": {"fake-agent": {"session_dir": SESSION_DIR}}},
    }
    if not archive:
        options["link-projects-records"] = {"session_archive": {"enabled": False}}
    base.mkdir(parents=True, exist_ok=True)
    with server(make_settings(base, options=options)) as client:
        yield client


def _seed(client: TestClient, project: str) -> None:
    for doc in (agent_doc("fast", "빠른 답"), agent_doc("slow", "깊은 답")):
        assert client.post(f"{API}/agents?project={project}", json=doc).status_code == 201
    response = client.post(f"{API}/graphs?project={project}", json=_graph())
    assert response.status_code == 201, response.text


def _send(client: TestClient, cid: str, project: str, **body: Any) -> Any:
    return client.post(
        f"{API}/conversations/{cid}/messages?project={project}", json={"text": "안녕", **body}
    )


def _wait_turn(client: TestClient, cid: str, project: str, sent: Any) -> dict[str, Any]:
    """보낸 메시지가 시작한 턴(응답의 Run id)이 끝날 때까지 기다린다.

    턴 목록의 "마지막"으로 고르지 않는다. 목록은 Run ``created_at``(벽시계) 순이라 시스템 시계가
    뒤로 가면(WSL 시계 맞춤 등) 앞 앱의 턴이 뒤에 놓여 다른 턴을 볼 수 있다.
    """
    assert sent.status_code == 202, sent.text
    run_id = sent.json()["id"]
    deadline = time.monotonic() + 20
    turns: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        turns = client.get(f"{API}/conversations/{cid}/turns?project={project}").json()
        mine = [t for t in turns if t["run_id"] == run_id]
        if mine and mine[0]["status"] in TERMINAL:
            conv = client.get(f"{API}/conversations/{cid}?project={project}").json()
            if conv["sessions"] or mine[0]["status"] != "completed":
                return mine[0]
        time.sleep(0.05)
    raise AssertionError(f"턴 {run_id}이 끝나지 않았다: {turns}")


def _wait_files(folder: Path, count: int) -> list[str]:
    deadline = time.monotonic() + 10
    found: list[str] = []
    while time.monotonic() < deadline:
        found = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
        if len(found) >= count:
            return found
        time.sleep(0.05)
    return found


def _chat_sessions(client: TestClient, run_id: str, project: str) -> dict[str, str]:
    events = client.get(f"{API}/runs/{run_id}/events?project={project}").json()
    started = [e for e in events if e["type"] == "run.started"]
    assert started, events
    found: dict[str, str] = started[0]["payload"].get("chat_sessions") or {}
    return found


def test_archive_lets_another_app_continue_and_missing_needs_fresh(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    sessions_dir = folder / ".agent-console" / "sessions"

    # 앱 A: 대화 한 턴 → 노드 a·b 세션이 폴더에 보관된다.
    with _app(tmp_path / "a") as client:
        register_project(client, "p", folder)
        _seed(client, "p")
        created = client.post(f"{API}/conversations", json={"graph_id": "flow", "project_id": "p"})
        assert created.status_code == 201, created.text
        cid = created.json()["id"]
        assert _wait_turn(client, cid, "p", _send(client, cid, "p"))["status"] == "completed"
        conv = client.get(f"{API}/conversations/{cid}?project=p").json()
        sids = {node: ref["session_id"] for node, ref in conv["sessions"].items()}
        assert set(sids) == {"a", "b"}
        state = client.get(f"{API}/conversations/{cid}/sessions?project=p").json()
        assert state["continuable"] is True
        assert {i["node_id"]: i["state"] for i in state["items"]} == {
            "a": "available",
            "b": "available",
        }
        saved = _wait_files(sessions_dir, 2)
        assert saved == sorted(f"fake-agent/{sid}/{sid}.jsonl" for sid in sids.values())

    # 앱 B(다른 workspace): 같은 폴더를 등록하면 지난 대화가 보이고 보관 사본으로 이어 간다.
    with _app(tmp_path / "b") as client:
        register_project(client, "p", folder)
        listed = client.get(f"{API}/conversations?project=p").json()
        assert [c["id"] for c in listed] == [cid]
        state = client.get(f"{API}/conversations/{cid}/sessions?project=p").json()
        assert state["continuable"] is True
        assert {i["state"] for i in state["items"]} == {"archived"}
        sent = _send(client, cid, "p")
        assert sent.status_code == 202, sent.text
        turn = _wait_turn(client, cid, "p", sent)
        assert turn["status"] == "completed"
        assert _chat_sessions(client, turn["run_id"], "p") == {"a": "archived", "b": "archived"}
        restored = sorted((tmp_path / "b" / "ws" / SESSION_DIR).rglob("*.jsonl"))
        assert {p.stem for p in restored} == set(sids.values())
        after = client.get(f"{API}/conversations/{cid}/sessions?project=p").json()
        assert {i["state"] for i in after["items"]} == {"available"}

    # 보관 사본을 지우면 앱 C에는 세션 기록이 없다: 409, fresh면 새 세션으로.
    shutil.rmtree(sessions_dir)
    with _app(tmp_path / "c") as client:
        register_project(client, "p", folder)
        state = client.get(f"{API}/conversations/{cid}/sessions?project=p").json()
        assert state["continuable"] is False
        assert {i["state"] for i in state["items"]} == {"missing"}
        refused = _send(client, cid, "p")
        assert refused.status_code == 409, refused.text
        error = refused.json()["error"]
        assert error["code"] == "chat.session_unavailable"
        assert error["details"] == {"conversation_id": cid, "node_ids": ["a", "b"]}
        fresh = _send(client, cid, "p", on_missing_session="fresh")
        assert fresh.status_code == 202, fresh.text
        turn = _wait_turn(client, cid, "p", fresh)
        assert turn["status"] == "completed"
        assert _chat_sessions(client, turn["run_id"], "p") == {"a": "fresh", "b": "fresh"}
        assert client.get(f"{API}/conversations/{cid}/sessions?project=p").json()["continuable"]


def test_archive_off_writes_no_sessions_folder(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with _app(tmp_path / "a", archive=False) as client:
        register_project(client, "p", folder)
        _seed(client, "p")
        created = client.post(f"{API}/conversations", json={"graph_id": "flow", "project_id": "p"})
        cid = created.json()["id"]
        assert _wait_turn(client, cid, "p", _send(client, cid, "p"))["status"] == "completed"
        time.sleep(0.3)  # 보관 작업이 있었다면 끝났을 시간
    assert not (folder / ".agent-console" / "sessions").exists()
    with _app(tmp_path / "b", archive=False) as client:
        register_project(client, "p", folder)
        state = client.get(f"{API}/conversations/{cid}/sessions?project=p").json()
        assert state["continuable"] is False
