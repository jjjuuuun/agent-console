"""상호작용 API 통합(fake 백엔드 + 실제 SQLite + 엔진, design §R14.4, 1R.14 (c)).

대기 → 응답 → 완료, 동시 응답 중 하나만 성공, 404·409·422, WS `interactions` 토픽(대기 목록 먼저),
재시작 시뮬레이션 후 대기 `expired(interrupted)`, 종료 시 `runtime.shutdown` 선행.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import Interaction, Run
from agent_console_server.testing import (
    API,
    TEST_TOKEN,
    make_settings,
    pending_of,
    receive_until,
    seed_chat,
    server,
    wait_for,
    wait_run,
    ws_path,
)
from agent_console_store import open_sqlite


def _ask(client: TestClient, text: str = "묻기 배포") -> dict[str, Any]:
    run: dict[str, Any] = client.post(
        f"{API}/runs", json={"graph_id": "chat", "input": {"text": text}}
    ).json()
    return run


def test_interaction_kinds_are_listed(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        kinds = {k["id"] for k in client.get(f"{API}/interaction-kinds").json()}
    assert {"question", "tool_permission", "review"} <= kinds


def test_wait_respond_complete(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        run = _ask(client)
        [pending] = pending_of(client)
        assert pending["run_id"] == run["id"]
        assert pending["kind"] == "question"
        assert pending["node_id"] == "a"
        assert pending["actor"] == "asker"
        wait_for(lambda: client.get(f"{API}/runs/{run['id']}").json()["run"]["status"] == "waiting")
        assert client.get(f"{API}/runs", params={"status": "waiting"}).json()[0]["id"] == run["id"]

        url = f"{API}/runs/{run['id']}/interactions/{pending['id']}/respond"
        bad = client.post(url, json={"response": {"nope": 1}})
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "validation_failed"
        assert bad.json()["error"]["details"]["issues"]

        missing = client.post(
            f"{API}/runs/{run['id']}/interactions/zzz/respond", json={"response": {}}
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"

        no_token = client.post(
            url, json={"response": {"response": "예"}}, headers={"X-Console-Token": ""}
        )
        assert no_token.status_code == 401

        answered = client.post(url, json={"response": {"response": "예"}})
        assert answered.status_code == 200, answered.text
        assert Interaction.model_validate(answered.json()).status == "answered"
        snap = wait_run(client, run["id"])
        assert snap["run"]["status"] == "completed"
        [node] = [n for n in snap["node_runs"] if n["node_id"] == "a"]
        assert node["outputs"]["out"] == "답: 예 (answered)"

        again = client.post(url, json={"response": {"response": "예"}})
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "interaction_closed"
        assert again.json()["error"]["details"]["interaction"]["status"] == "answered"

        listed = client.get(f"{API}/runs/{run['id']}/interactions").json()
        assert [i["status"] for i in listed] == ["answered"]
        assert client.get(f"{API}/interactions", params={"status": "pending"}).json() == []


def test_two_concurrent_responses_only_one_wins(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        run = _ask(client)
        [pending] = pending_of(client)
        url = f"{API}/runs/{run['id']}/interactions/{pending['id']}/respond"
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, url, json={"response": {"response": answer}})
                for answer in ("하나", "둘")
            ]
            responses = [f.result() for f in futures]
        assert sorted(r.status_code for r in responses) == [200, 409]
        loser = next(r for r in responses if r.status_code == 409)
        assert loser.json()["error"]["code"] == "interaction_closed"
        assert wait_run(client, run["id"])["run"]["status"] == "completed"


def test_unconnected_node_cannot_ask(tmp_path: Path) -> None:
    """`ask_user` 연결이 없는 그래프에서는 요청이 열리지 않는다(grant 없음)."""
    from agent_console_server.testing import asker_agent, chat_graph

    with server(make_settings(tmp_path)) as client:
        client.post(f"{API}/agents", json=asker_agent())
        client.post(f"{API}/graphs", json=chat_graph(ask=False))
        run = _ask(client)
        snap = wait_run(client, run["id"])
        assert snap["run"]["status"] == "completed"
        [node] = [n for n in snap["node_runs"] if n["node_id"] == "a"]
        assert node["outputs"]["out"] == "답: unavailable (unavailable)"
        assert client.get(f"{API}/runs/{run['id']}/interactions").json() == []


def test_ws_interactions_topic_sends_pending_first(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed_chat(client)
        run = _ask(client)
        [pending] = pending_of(client)
        with client.websocket_connect(ws_path()) as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": "interactions"}})
            first = ws.receive_json()
            assert first["type"] == "interaction.updated"
            assert first["payload"]["interaction"]["id"] == pending["id"]
            assert first["payload"]["interaction"]["status"] == "pending"
            url = f"{API}/runs/{run['id']}/interactions/{pending['id']}/respond"
            assert client.post(url, json={"response": {"response": "예"}}).status_code == 200
            updates = receive_until(
                ws,
                lambda m: (
                    m["type"] == "interaction.updated"
                    and m["payload"]["interaction"]["status"] == "answered"
                ),
            )
            assert updates[-1]["payload"]["interaction"]["id"] == pending["id"]
            # 재구독하면 대기 목록을 다시 보낸다(지금은 비어 있음 → 새 요청만)
            run2 = _ask(client)
            update = receive_until(
                ws,
                lambda m: (
                    m["type"] == "interaction.updated"
                    and m["payload"]["interaction"]["run_id"] == run2["id"]
                ),
            )[-1]
            assert update["payload"]["interaction"]["status"] == "pending"
            ws.send_json({"type": "subscribe", "payload": {"topic": "interactions"}})
            resent = receive_until(
                ws,
                lambda m: (
                    m["type"] == "interaction.updated"
                    and m["payload"]["interaction"]["run_id"] == run2["id"]
                ),
            )[-1]
            assert resent["payload"]["interaction"]["status"] == "pending"
            client.post(f"{API}/runs/{run2['id']}/cancel")
            wait_run(client, run2["id"])


def test_restart_expires_pending_and_marks_turn_interrupted(tmp_path: Path) -> None:
    """이전 프로세스가 대기 중에 죽은 상태 → 재시작 시 정리된다.

    대화는 HTTP로 만들고(대화 저장소는 mod-chat 소유라 SQL로 쓰지 않는다, 3R.16), 서버를 끈 뒤
    죽은 프로세스가 남긴 것처럼 대기 중 Run·상호작용만 실행 기록에 직접 쓴다.
    """
    settings = make_settings(tmp_path)
    with server(settings) as client:
        seed_chat(client)
        conv_id = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()["id"]
    db = open_sqlite(settings.database_path)
    try:
        db.runs.save(
            Run(
                id="r1",
                graph_id="chat",
                graph_version="v",
                status="waiting",
                input={"text": "묻기"},
                origin="chat",
                conversation_id=conv_id,
                created_at=1.0,
            )
        )
        db.interactions.save(
            Interaction(
                id="i1",
                run_id="r1",
                conversation_id=conv_id,
                node_id="a",
                node_path=["a"],
                attempt=1,
                kind="question",
                status="pending",
                created_at=1.0,
            )
        )
    finally:
        db.close()
    with server(settings) as client:
        assert client.get(f"{API}/interactions", params={"status": "pending"}).json() == []
        [closed] = client.get(f"{API}/runs/r1/interactions").json()
        assert closed["status"] == "expired"
        assert closed["close_reason"] == "interrupted"
        assert client.get(f"{API}/runs/r1").json()["run"]["status"] == "interrupted"
        [turn] = client.get(f"{API}/conversations/{conv_id}/turns").json()
        assert (turn["run_id"], turn["status"]) == ("r1", "interrupted")
        [summary] = client.get(f"{API}/conversations").json()
        assert summary["pending_interactions"] == 0
        response = client.post(f"{API}/runs/r1/interactions/i1/respond", json={"response": {}})
        assert response.status_code == 409
        assert client.get(f"{API}/server-info").json()["attributes"]["recovered_runs"] == 1


def test_shutdown_interrupts_waiting_runs_before_closing_store(tmp_path: Path) -> None:
    """lifespan 종료(SIGTERM·Ctrl-C)가 `runtime.shutdown`을 먼저 기다린다(1R.26 회귀).

    정상 종료도 비정상 종료 뒤 재시작 복구와 같게 정리한다(§R14.5): 대기 요청은
    `expired`(close_reason `interrupted`), Run은 `interrupted`. 다시 시작한 뒤에도 그대로다.
    """
    settings = make_settings(tmp_path)
    with server(settings) as client:
        seed_chat(client)
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        sent = client.post(
            f"{API}/conversations/{conv['id']}/messages", json={"text": "묻기 배포"}
        ).json()
        [waiting] = pending_of(client)
        run = {"id": waiting["run_id"]}
        assert waiting["conversation_id"] == conv["id"], sent
    db = open_sqlite(settings.database_path)
    try:
        stored = db.runs.get(run["id"])
        assert stored is not None
        assert stored.status == "interrupted"
        assert stored.error is not None
        assert stored.error.code == "interrupted"
        [interaction] = db.interactions.list(run_id=run["id"])
        assert interaction.status == "expired"
        assert interaction.close_reason == "interrupted"
    finally:
        db.close()
    with server(settings) as client:
        assert client.get(f"{API}/runs/{run['id']}").json()["run"]["status"] == "interrupted"
        [summary] = client.get(f"{API}/conversations").json()
        assert summary["last_status"] == "interrupted"
        assert summary["pending_interactions"] == 0
        assert client.get(f"{API}/interactions", params={"status": "pending"}).json() == []


def test_shutdown_timeout_does_not_hang(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, options={"mod-runs": {"runtime": {"shutdown_timeout": 0, "cancel_grace": 0}}}
    )
    with server(settings) as client:
        seed_chat(client)
        _ask(client)
        pending_of(client)
    assert TEST_TOKEN  # 종료가 돌아왔으면 통과
