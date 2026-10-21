"""채팅 API 통합(fake, design §R5.1): 대화 CRUD, 메시지 → 턴(Run 메타 conversation_id), 대기열·거절,
턴 목록 커서, 세션 이어 쓰기, WS `conversation:<id>`, TurnLauncher 어댑터 계약.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    make_settings,
    pending_of,
    receive_until,
    seed_chat,
    server,
    wait_for,
    wait_run,
    ws_path,
)


def _conversation(client: TestClient) -> dict[str, Any]:
    response = client.post(f"{API}/conversations", json={"graph_id": "chat"})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _post(client: TestClient, conversation_id: str, text: str) -> Any:
    return client.post(f"{API}/conversations/{conversation_id}/messages", json={"text": text})


def test_conversation_turns_and_run_meta(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        missing = client.post(f"{API}/conversations", json={"graph_id": "nope"})
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
        conv = _conversation(client)

        first = _post(client, conv["id"], "안녕")
        assert first.status_code == 202
        run = first.json()
        assert run["conversation_id"] == conv["id"]  # TurnLauncher 어댑터 계약: Run 메타
        assert run["origin"] == "chat"
        wait_run(client, run["id"])
        wait_for(lambda: client.get(f"{API}/conversations/{conv['id']}").json()["sessions"])
        second = _post(client, conv["id"], "두 번째")
        wait_run(client, second.json()["id"])

        turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
        assert [t["user_text"] for t in turns] == ["안녕", "두 번째"]
        assert turns[0]["replies"][0]["text"] == "에코: 안녕"
        older = client.get(
            f"{API}/conversations/{conv['id']}/turns", params={"before": turns[1]["run_id"]}
        ).json()
        assert [t["run_id"] for t in older] == [turns[0]["run_id"]]
        bad = client.get(f"{API}/conversations/{conv['id']}/turns", params={"before": "zzz"})
        assert bad.status_code == 404

        detail = client.get(f"{API}/conversations/{conv['id']}").json()
        assert set(detail["sessions"]) == {"a"}  # 세션 이어 쓰기
        assert detail["title"] == "안녕"  # chat.title = first_message
        runs = client.get(f"{API}/runs", params={"conversation_id": conv["id"]}).json()
        assert {r["id"] for r in runs} == {t["run_id"] for t in turns}

        patched = client.patch(f"{API}/conversations/{conv['id']}", json={"title": "새 제목"})
        assert patched.json()["title"] == "새 제목"
        [summary] = client.get(f"{API}/conversations").json()
        assert summary["last_status"] == "completed"
        assert client.delete(f"{API}/conversations/{conv['id']}").status_code == 204
        assert client.get(f"{API}/conversations/{conv['id']}").status_code == 404


def test_interaction_conversation_id_matches_run(tmp_path: Path) -> None:
    """(a) 채팅 어댑터가 `GraphRuntime.start(conversation_id=)`를 채운다 → Run·Interaction 일치."""
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        conv = _conversation(client)
        run = _post(client, conv["id"], "묻기 계속").json()
        [pending] = pending_of(client)
        assert pending["conversation_id"] == run["conversation_id"] == conv["id"]
        listed = client.get(f"{API}/interactions", params={"conversation_id": conv["id"]}).json()
        assert [i["id"] for i in listed] == [pending["id"]]
        [summary] = client.get(f"{API}/conversations").json()
        assert summary["pending_interactions"] == 1
        url = f"{API}/runs/{run['id']}/interactions/{pending['id']}/respond"
        client.post(url, json={"response": {"response": "예"}})
        wait_run(client, run["id"])
        [turn] = client.get(f"{API}/conversations/{conv['id']}/turns").json()
        assert turn["interactions"][0]["status"] == "answered"


def test_busy_queue_cancel_and_reject(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        conv = _conversation(client)
        run = _post(client, conv["id"], "묻기 하나").json()
        pending_of(client)
        queued = _post(client, conv["id"], "다음 것")
        assert queued.status_code == 202
        body = queued.json()
        assert body["queued"] is True
        assert body["position"] == 1
        assert body["id"]
        assert [q["id"] for q in client.get(f"{API}/conversations/{conv['id']}/queue").json()] == [
            body["id"]
        ]
        url = f"{API}/conversations/{conv['id']}/queue/{body['id']}"
        assert client.delete(url).status_code == 204
        again = client.delete(url)
        assert again.status_code == 404
        assert again.json()["error"]["code"] == "not_found"

        settings = client.get(f"{API}/settings").json()
        settings.setdefault("chat", {})["busy_policy"] = "reject"
        assert client.put(f"{API}/settings", json=settings).status_code == 200
        busy = _post(client, conv["id"], "또")
        assert busy.status_code == 409
        assert busy.json()["error"]["code"] == "conversation_busy"
        empty = _post(client, conv["id"], "   ")
        assert empty.status_code == 400

        client.post(f"{API}/runs/{run['id']}/cancel")
        assert wait_run(client, run["id"])["run"]["status"] == "cancelled"


def test_ws_conversation_topic(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        conv = _conversation(client)
        with client.websocket_connect(ws_path()) as ws:
            ws.send_json(
                {"type": "subscribe", "id": "x", "payload": {"topic": "conversation:nope"}}
            )
            assert ws.receive_json()["payload"]["code"] == "not_found"
            ws.send_json({"type": "subscribe", "payload": {"topic": f"conversation:{conv['id']}"}})
            first = ws.receive_json()
            assert first["type"] == "conversation.updated"
            assert first["payload"]["conversation"]["id"] == conv["id"]
            run = _post(client, conv["id"], "묻기 웹소켓").json()
            waiting = receive_until(
                ws,
                lambda m: (
                    m["type"] == "conversation.updated"
                    and m["payload"]["conversation"]["pending_interactions"] == 1
                ),
            )[-1]
            assert waiting["payload"]["conversation"]["last_run_id"] == run["id"]
            client.post(f"{API}/runs/{run['id']}/cancel")
            done = receive_until(
                ws,
                lambda m: (
                    m["type"] == "conversation.updated"
                    and m["payload"]["conversation"]["last_status"] == "cancelled"
                ),
            )[-1]
            assert done["payload"]["conversation"]["pending_interactions"] == 0
