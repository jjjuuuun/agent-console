"""3R.15 QA: 대화를 지워도 그 대화의 Run·이벤트는 남는다(사용자 데이터 보존).

ac-store의 `test_conversation_delete_keeps_runs`가 mod-chat 이동 때 사라져 서버 조립 수준(mod-chat +
mod-runs)에서 같은 보장을 확인한다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import API, make_settings, seed_chat, server, wait_run


def test_deleting_conversation_keeps_its_runs(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        messages = f"{API}/conversations/{conv['id']}/messages"
        run = client.post(messages, json={"text": "안녕"}).json()
        wait_run(client, run["id"])

        assert client.delete(f"{API}/conversations/{conv['id']}").status_code == 204
        assert client.get(f"{API}/conversations/{conv['id']}").status_code == 404

        kept = client.get(f"{API}/runs/{run['id']}")
        assert kept.status_code == 200
        listed = client.get(f"{API}/runs", params={"conversation_id": conv["id"]}).json()
        assert [r["id"] for r in listed] == [run["id"]]
