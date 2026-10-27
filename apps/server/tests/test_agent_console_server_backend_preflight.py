"""통합 서버: 실행 백엔드 사전 점검 `backend.unresolved`(5.2R.4, UX-F1·UX-B7).

빈 workspace에서 에이전트 하나짜리 팀으로 `POST /runs`와 채팅 턴이 422를 받고, Run·턴 기록이
남지 않는지 본다. 기본값을 고르면(`default_backend`) 같은 메시지가 실행된다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import BackendUnresolvedDetails, ErrorCodes
from agent_console_server.testing import API, chat_graph, make_settings, server, wait_run


def _agent() -> dict[str, Any]:
    # 백엔드를 정하지 않은 에이전트(응답 규칙만, 어느 층에도 backend 없음)
    return {"id": "asker", "name": "안내원", "backend_options": {"default": {"response": "네"}}}


def _assert_unresolved(body: dict[str, Any]) -> None:
    error = body["error"]
    assert error["code"] == ErrorCodes.BACKEND_UNRESOLVED
    details = BackendUnresolvedDetails.model_validate(error["details"])
    assert [n.id for n in details.nodes] == ["a"]
    assert details.nodes[0].label  # 노드 이름(사용자 문구)
    assert details.options  # 등록된 백엔드 디스크립터
    assert len(error["fix"]["actions"]) == 2


def test_run_and_chat_turn_without_backend_are_422_and_leave_no_records(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        assert client.post(f"{API}/agents", json=_agent()).status_code == 201
        assert client.post(f"{API}/graphs", json=chat_graph()).status_code == 201

        res = client.post(f"{API}/runs", json={"graph_id": "chat", "input": {"text": "hi"}})
        assert res.status_code == 422, res.text
        _assert_unresolved(res.json())

        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        turn = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert turn.status_code == 422, turn.text
        _assert_unresolved(turn.json())

        # 기록 0건: Run·턴·실패 기록이 없다
        assert client.get(f"{API}/runs").json() == []
        assert client.get(f"{API}/conversations/{conv['id']}/turns").json() == []
        summary = client.get(f"{API}/conversations/{conv['id']}").json()
        assert summary.get("last_run_id") is None

        # 기본값으로 고르면 같은 메시지가 실행된다(자동 선택은 없다)
        got = client.get(f"{API}/settings")
        etag = got.headers.get("etag")
        body = {**got.json(), "default_backend": "fake-agent"}
        put = client.put(f"{API}/settings", json=body, headers={"If-Match": etag} if etag else {})
        assert put.status_code == 200, put.text
        again = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert again.status_code == 202, again.text
        assert wait_run(client, again.json()["id"])["run"]["status"] == "completed"
