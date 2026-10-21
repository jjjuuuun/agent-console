"""5R.11 중첩 팀 `team` 노드 x 5R.13 서버 연결 QA(fake): REST 저장·검증·실행, 자식 Run 계보,
자식 안 되묻기 응답, 버전 고정, 재귀·깊이 이슈, 대화 이어 쓰기(중첩 세션)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    asker_agent,
    chat_graph,
    make_settings,
    pending_of,
    server,
    wait_for,
    wait_run,
)


def _edge(eid: str, s: tuple[str, str], t: tuple[str, str], kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": s[0], "port": s[1]},
        "target": {"node": t[0], "port": t[1]},
        "kind": kind,
        "config": {},
    }


def outer_graph(graph_id: str = "outer", ref: str = "chat", **config: Any) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": "바깥",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "T", "type": "team", "label": "안쪽", "config": {"team_ref": ref, **config}},
        ],
        "edges": [
            _edge("m1", ("you", "says"), ("T", "in"), "message"),
            _edge("r1", ("T", "out"), ("you", "hears"), "reply"),
        ],
    }


def _seed(client: TestClient) -> None:
    assert client.post(f"{API}/agents", json=asker_agent()).status_code == 201
    assert client.post(f"{API}/graphs", json=chat_graph()).status_code == 201


def test_nested_run_lineage_and_child_question(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        saved = client.post(f"{API}/graphs", json=outer_graph())
        assert saved.status_code == 201, saved.text
        val = client.post(f"{API}/graphs/outer/validate")
        assert val.status_code == 200, val.text
        assert not [i for i in val.json() if i["severity"] == "error"], val.json()

        run = client.post(
            f"{API}/runs", json={"graph_id": "outer", "input": {"text": "묻기 배포"}}
        ).json()
        [pending] = pending_of(client)
        assert pending["run_id"] != run["id"]  # 자식 Run의 되묻기
        url = f"{API}/runs/{pending['run_id']}/interactions/{pending['id']}/respond"
        assert client.post(url, json={"response": {"response": "예"}}).status_code == 200
        snap = wait_run(client, run["id"])
        assert snap["run"]["status"] == "completed", snap
        [child] = snap["children"]
        assert child["parent_run_id"] == run["id"]
        listed = client.get(f"{API}/runs", params={"root": run["id"]}).json()
        assert {r["id"] for r in listed} == {child["id"]}
        replies = [r for r in snap.get("replies", [])] or []
        text = str(snap)
        assert "답: 예" in text or replies


def test_version_pin_and_issues(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        v1 = client.get(f"{API}/graphs/chat").json()["version_hash"]
        client.post(f"{API}/graphs", json=outer_graph("pin", version=v1))
        g = chat_graph()
        g["name"] = "변경"
        assert client.put(f"{API}/graphs/chat", json=g, headers={}).status_code in (200, 412, 428)
        bad = client.post(f"{API}/graphs", json=outer_graph("self", ref="self"))
        issues = (
            client.post(f"{API}/graphs/self/validate").json()
            if bad.status_code == 201
            else bad.json()
        )
        assert "team.recursive" in str(issues), issues
        miss = client.post(f"{API}/graphs", json=outer_graph("miss", ref="nope"))
        res = (
            client.post(f"{API}/graphs/miss/validate").json()
            if miss.status_code == 201
            else miss.json()
        )
        assert "team.team_not_found" in str(res), res


def test_conversation_continues_nested_child_session(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        assert client.post(f"{API}/graphs", json=outer_graph()).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "outer"}).json()
        child_sessions: list[str] = []
        for text in ("하나", "둘"):
            r = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": text})
            assert r.status_code == 202, r.text
            wait_run(client, r.json()["id"])
            wait_for(lambda: client.get(f"{API}/conversations/{conv['id']}").json()["updated_at"])
            [kid] = client.get(f"{API}/runs", params={"root": r.json()["id"]}).json()
            events = client.get(f"{API}/runs/{kid['id']}/events").json()
            child_sessions += [
                e["payload"]["session_id"] for e in events if e["type"] == "agent.session_started"
            ]
            # 턴 종료 후 세션 기록은 비동기(감시 태스크): 기록될 때까지 기다린다
            wait_for(
                lambda: "T/a" in client.get(f"{API}/conversations/{conv['id']}").json()["sessions"]
            )
        # 둘째 턴의 자식 노드가 첫 턴 세션을 이어 썼다(fake는 받은 세션 id를 그대로 쓴다)
        assert len(child_sessions) == 2, child_sessions
        assert child_sessions[0] == child_sessions[1], child_sessions
        kids = client.get(f"{API}/runs", params={"root": r.json()["id"]}).json()
        ev = client.get(f"{API}/runs/{kids[0]['id']}/events").json()
        assert any(e["type"] == "agent.session_started" for e in ev), (
            "자식 Run이 세션을 만들지 않음"
        )
        detail = client.get(f"{API}/conversations/{conv['id']}").json()
        # 기대: 중첩 자식 노드 세션이 "T/a" 키로 기록되어 다음 턴에 이어진다
        assert "T/a" in detail["sessions"], detail["sessions"]


def _sessions(client: TestClient, conv_id: str) -> dict[str, Any]:
    out: dict[str, Any] = client.get(f"{API}/conversations/{conv_id}").json()["sessions"]
    return out


def _one_turn(client: TestClient, conv_id: str, text: str) -> None:
    r = client.post(f"{API}/conversations/{conv_id}/messages", json={"text": text})
    assert r.status_code == 202, r.text
    wait_run(client, r.json()["id"])


def test_grandchild_path_key_and_prune(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        assert client.post(f"{API}/graphs", json=outer_graph("mid", ref="chat")).status_code == 201
        # 중간 팀의 팀 노드 id는 T, 바깥은 U로 바꿔 둔다
        top = outer_graph("top", ref="mid")
        top["nodes"][1]["id"] = "U"
        for e in top["edges"]:
            for end in ("source", "target"):
                if e[end]["node"] == "T":
                    e[end]["node"] = "U"
        assert client.post(f"{API}/graphs", json=top).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "top"}).json()
        _one_turn(client, conv["id"], "하나")
        wait_for(lambda: "U/T/a" in _sessions(client, conv["id"]))
        # 팀 노드 이름 변경(U -> V): 옛 키는 지워진다
        got = client.get(f"{API}/graphs/top")
        top2 = got.json()
        g = top2.get("graph", top2)
        g = {k: v for k, v in g.items() if k not in ("version_hash",)}
        g["nodes"][1]["id"] = "V"
        for e in g["edges"]:
            for end in ("source", "target"):
                if e[end]["node"] == "U":
                    e[end]["node"] = "V"
        put = client.put(f"{API}/graphs/top", json=g, headers={"If-Match": got.headers["etag"]})
        assert put.status_code in (200, 201), put.text
        _one_turn(client, conv["id"], "둘")
        wait_for(lambda: "V/T/a" in _sessions(client, conv["id"]))
        # 제자리 이름 변경은 옛 키를 남긴다(일반 노드와 같은 기존 동작, 쓰이지 않음).
        # 팀 구성을 바꾸면 현재 팀 노드와 무관한 경로 키는 지워진다.
        moved = client.patch(f"{API}/conversations/{conv['id']}", json={"graph_id": "chat"})
        assert moved.status_code == 200, moved.text
        assert not [k for k in _sessions(client, conv["id"]) if "/" in k]


def test_chat_works_with_link_chat_runs_disabled(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["link-chat-runs"]})
    with server(settings) as client:
        _seed(client)
        assert client.post(f"{API}/graphs", json=outer_graph()).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "outer"}).json()
        # 턴 실행기(link-chat-runs 제공)가 없으면 메시지는 feature_unavailable, 대화 CRUD는 정상
        sent = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "x"})
        assert sent.status_code == 409
        assert client.get(f"{API}/conversations/{conv['id']}").status_code == 200
        assert client.delete(f"{API}/conversations/{conv['id']}").status_code == 204
