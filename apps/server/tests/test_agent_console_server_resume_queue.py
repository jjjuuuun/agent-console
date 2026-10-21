"""저장 대기열·재시작 뒤 처리·끊긴 실행 이어 가기 API 통합(2R.14, design §2R.10).

fake 백엔드 + 실제 SQLite + 엔진. 재시작은 같은 설정으로 서버를 다시 띄워 흉내 낸다(종료 시
실행 중 Run은 `interrupted`가 된다 — 비정상 종료 뒤 복구와 같은 결과, §R14.5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import ErrorCodes, NodeRun, Run
from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    pending_of,
    seed_chat,
    server,
    wait_for,
    wait_run,
)
from agent_console_store import open_sqlite

REVIEW = {
    "title": "설계안 검토",
    "decisions": [{"id": "approved", "label": "승인"}, {"id": "rejected", "label": "반려"}],
}


def _edge(edge_id: str, src: tuple[str, str], dst: tuple[str, str], kind: str) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": {"node": src[0], "port": src[1]},
        "target": {"node": dst[0], "port": dst[1]},
        "kind": kind,
    }


def _review_team(client: TestClient) -> None:
    """사용자 → PL → 사용자 검토 → BE → (답변) 사용자."""
    assert client.post(f"{API}/agents", json=agent_doc("pl", "설계: $prompt")).status_code == 201
    assert client.post(f"{API}/agents", json=agent_doc("be", "구현: $prompt")).status_code == 201
    graph = {
        "id": "review",
        "name": "검토 팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "pl", "type": "agent", "label": "PL", "config": {"agent_ref": "pl"}},
            {"id": "rv", "type": "user", "label": "문서 검토", "config": {"review": REVIEW}},
            {"id": "be", "type": "agent", "label": "BE", "config": {"agent_ref": "be"}},
        ],
        "edges": [
            _edge("m", ("you", "says"), ("pl", "in"), "message"),
            _edge("h1", ("pl", "out"), ("rv", "review"), "handoff"),
            _edge("h2", ("rv", "approved"), ("be", "in"), "handoff"),
            _edge("r", ("be", "out"), ("you", "hears"), "reply"),
        ],
    }
    response = client.post(f"{API}/graphs", json=graph)
    assert response.status_code == 201, response.text


def _node_events(client: TestClient, run_id: str, type: str) -> dict[str, Any]:
    events = client.get(f"{API}/runs/{run_id}/events", params={"type_prefix": type}).json()
    return {e["node_path"][0]: e["payload"] for e in events}


def test_review_wait_restart_resume_reopens_review_and_runs_downstream(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        _review_team(client)
        conv = client.post(f"{API}/conversations", json={"graph_id": "review"}).json()
        first = client.post(
            f"{API}/conversations/{conv['id']}/messages", json={"text": "로그인"}
        ).json()
        [opened] = pending_of(client)
        assert opened["run_id"] == first["id"]
    # --- 재시작
    with server(settings) as client:
        assert client.get(f"{API}/runs/{first['id']}").json()["run"]["status"] == "interrupted"
        options = client.get(f"{API}/runs/{first['id']}/resume-options").json()
        assert options["run_id"] == first["id"]
        assert [
            (n["node_id"], n["label"], n["rerunnable"], n["status"]) for n in options["nodes"]
        ] == [("rv", "문서 검토", True, "waiting")]
        # 끊긴 노드가 아닌 노드는 422(노드별 이슈)
        bad = client.post(f"{API}/runs/{first['id']}/resume", json={"node_ids": ["pl"]})
        assert bad.status_code == 422
        assert bad.json()["error"]["details"]["issues"][0]["node_id"] == "pl"
        assert (
            client.post(f"{API}/runs/{first['id']}/resume", json={"node_ids": []}).status_code
            == 422
        )

        response = client.post(f"{API}/runs/{first['id']}/resume", json={"node_ids": ["rv"]})
        assert response.status_code == 202, response.text
        new = response.json()
        assert (new["origin"], new["resumed_from"], new["conversation_id"]) == (
            "resume",
            first["id"],
            conv["id"],
        )
        [reopened] = pending_of(client)
        assert reopened["run_id"] == new["id"]
        assert (reopened["kind"], reopened["title"], reopened["payload"]) == (
            opened["kind"],
            opened["title"],
            opened["payload"],
        )
        answered = client.post(
            f"{API}/runs/{new['id']}/interactions/{reopened['id']}/respond",
            json={"response": {"decision": "approved"}},
        )
        assert answered.status_code == 200, answered.text
        snap = wait_run(client, new["id"])
        assert snap["run"]["status"] == "completed"
        statuses = {n["node_id"]: n["status"] for n in snap["node_runs"]}
        assert statuses == {"pl": "skipped", "rv": "succeeded", "be": "succeeded"}
        assert _node_events(client, new["id"], "node.skipped")["pl"]["reason"] == "resumed"

        turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
        assert [(t["run_id"], t["resumed_from"]) for t in turns] == [
            (first["id"], None),
            (new["id"], first["id"]),
        ]
        assert "구현: " in turns[-1]["replies"][0]["text"]
        listed = client.get(f"{API}/runs", params={"conversation_id": conv["id"]}).json()
        assert {r["id"] for r in listed} == {first["id"], new["id"]}

        # 이미 이어 간 실행은 다시 이어 가지 않는다
        assert client.get(f"{API}/runs/{first['id']}/resume-options").json()["nodes"] == []
        again = client.post(f"{API}/runs/{first['id']}/resume", json={"node_ids": ["rv"]})
        assert again.status_code == 409
        assert again.json()["error"]["code"] == ErrorCodes.RUN_NOT_RESUMABLE
        assert again.json()["error"]["details"]["resumed_by"] == new["id"]
        # 끝난 실행은 선택지가 없고 이어 갈 수 없다
        assert client.get(f"{API}/runs/{new['id']}/resume-options").json()["nodes"] == []
        assert (
            client.post(f"{API}/runs/{new['id']}/resume", json={"node_ids": ["rv"]}).status_code
            == 409
        )
        assert client.get(f"{API}/runs/missing/resume-options").status_code == 404


def test_resume_rejects_node_type_that_is_not_rerunnable(tmp_path: Path) -> None:
    """디스크립터가 `rerunnable`이 아닌(여기서는 등록되지 않은) 노드 타입은 422."""
    settings = make_settings(tmp_path)
    with server(settings) as client:
        seed_chat(client)
        version = client.get(f"{API}/graphs/chat").json()["version_hash"]
    db = open_sqlite(settings.database_path)
    try:
        db.runs.save(
            Run(
                id="r1",
                graph_id="chat",
                graph_version=version,
                status="interrupted",
                input={"text": "x"},
                origin="api",
                created_at=1.0,
            )
        )
        db.runs.save_node_run(
            NodeRun.model_validate(
                {
                    "run_id": "r1",
                    "node_id": "a",
                    "status": "cancelled",
                    "node_type": "x.unregistered",
                    "error": {"code": "interrupted", "message": "끊김"},
                }
            )
        )
    finally:
        db.close()
    with server(settings) as client:
        [node] = client.get(f"{API}/runs/r1/resume-options").json()["nodes"]
        assert (node["node_id"], node["rerunnable"], node["status"]) == ("a", False, "running")
        response = client.post(f"{API}/runs/r1/resume", json={"node_ids": ["a"]})
        assert response.status_code == 422
        [issue] = response.json()["error"]["details"]["issues"]
        assert (issue["node_id"], issue["code"]) == ("a", "resume.not_rerunnable")


def _queue(client: TestClient, conv: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = client.get(f"{API}/conversations/{conv}/queue").json()
    return items


def _busy_with_queue(client: TestClient) -> str:
    """질문 대기로 바쁜 대화 + 대기열 2건."""
    seed_chat(client)
    conv: str = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()["id"]
    client.post(f"{API}/conversations/{conv}/messages", json={"text": "묻기 하나"})
    pending_of(client)
    for text in ("둘", "셋"):
        body = client.post(f"{API}/conversations/{conv}/messages", json={"text": text}).json()
        assert body["queued"] is True
    return conv


def test_queue_survives_restart_held_then_release_and_cancel(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        conv = _busy_with_queue(client)
    with server(settings) as client:  # 기본 chat.queue_after_restart = ask
        items = _queue(client, conv)
        assert [(q["text"], q["position"], q["held"]) for q in items] == [
            ("둘", 1, True),
            ("셋", 2, True),
        ]
        [summary] = client.get(f"{API}/conversations").json()
        assert (summary["queued"], summary["held"], summary["last_status"]) == (
            2,
            2,
            "interrupted",
        )
        assert len(client.get(f"{API}/conversations/{conv}/turns").json()) == 1  # 자동 실행 없음

        released = client.post(f"{API}/conversations/{conv}/queue/{items[0]['id']}/release")
        assert released.status_code == 200, released.text
        assert released.json()["held"] is False
        turns = wait_for(
            lambda: (
                (t := client.get(f"{API}/conversations/{conv}/turns").json()) and len(t) == 2 and t
            )
        )
        assert turns[-1]["user_text"] == "둘"
        assert [(q["text"], q["held"]) for q in _queue(client, conv)] == [("셋", True)]
        # 취소(기존 DELETE), 없는 항목 404
        assert (
            client.delete(f"{API}/conversations/{conv}/queue/{items[1]['id']}").status_code == 204
        )
        assert _queue(client, conv) == []
        missing = client.post(f"{API}/conversations/{conv}/queue/{items[1]['id']}/release")
        assert missing.status_code == 404


def test_queue_after_restart_drop_and_run_modes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        conv = _busy_with_queue(client)
        doc = client.get(f"{API}/settings").json()
        doc.setdefault("chat", {})["queue_after_restart"] = "run"
        assert client.put(f"{API}/settings", json=doc).status_code == 200
    with server(settings) as client:  # run: 앞 턴이 끊겼어도 순서대로 실행
        turns = wait_for(
            lambda: (
                (t := client.get(f"{API}/conversations/{conv}/turns").json()) and len(t) == 3 and t
            )
        )
        assert [t["user_text"] for t in turns] == ["묻기 하나", "둘", "셋"]
        assert _queue(client, conv) == []
        doc = client.get(f"{API}/settings").json()
        doc["chat"]["queue_after_restart"] = "drop"
        assert client.put(f"{API}/settings", json=doc).status_code == 200
    with server(settings) as client:  # drop: 지운다
        assert _queue(client, conv) == []
        [summary] = client.get(f"{API}/conversations").json()
        assert (summary["queued"], summary["held"]) == (0, 0)
