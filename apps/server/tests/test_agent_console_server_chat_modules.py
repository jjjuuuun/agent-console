"""3R.14 채팅 모듈 + 연동(M.9): mod-chat·link-chat-runs 조립.

- 대화·대기열 경로와 WS `conversation:`은 `mod-chat`, 턴 시작·이어 가기·실행 이벤트 알림·재시작
  대기열 정책·종료 순서는 `link-chat-runs`가 맡는다(웹 역할 `conversations`·`conversations:runs`).
- "core + definitions + chat" 조합: 대화 목록·만들기는 동작하고 메시지 전송은 409
  `feature_unavailable{module: mod-chat, port: chat.turn_launcher}`.
- 연동만 끄면 같은 409, 채팅 모듈을 끄면 대화 경로 404·연동 unsatisfied.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts import ErrorCodes, ErrorResponse, FeatureUnavailableDetails
from agent_console_server.testing import API, make_settings, seed_chat, server, wait_for

CHAT_ROLES: dict[str, list[str]] = {
    "mod-chat": ["conversations"],
    "link-chat-runs": ["conversations:runs"],
}


def _infos(client: Any) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in client.get(f"{API}/modules").json()}


def _assert_send_unavailable(client: Any, conversation_id: str) -> None:
    res = client.post(f"{API}/conversations/{conversation_id}/messages", json={"text": "안녕"})
    assert res.status_code == 409, res.text
    error = ErrorResponse.model_validate(res.json()).error
    assert error.code == ErrorCodes.FEATURE_UNAVAILABLE
    details = FeatureUnavailableDetails.model_validate(error.details)
    assert (details.module, details.port) == ("mod-chat", "chat.turn_launcher")
    assert client.get(f"{API}/conversations/{conversation_id}/queue").json() == []


def test_chat_module_and_link_are_active_with_roles(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        infos = _infos(client)
        for module_id, roles in CHAT_ROLES.items():
            assert infos[module_id]["status"] == "active", infos[module_id]
            assert infos[module_id]["web_roles"] == roles
        assert infos["mod-chat"]["kind"] == "feature"
        assert infos["link-chat-runs"]["kind"] == "link"
        assert "chat.conversations" in infos["mod-chat"]["provides"]
        assert "chat.turn_launcher" in infos["mod-chat"]["requires"]  # 선택 포트도 보고에 담긴다
        assert "runs.resume_handlers" in infos["link-chat-runs"]["provides"]
        seed_chat(client)
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        run = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "hi"})
        assert run.status_code == 202, run.text
        assert run.json()["conversation_id"] == conv["id"]

        def done() -> Any:
            turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
            return turns and turns[-1]["status"] not in ("queued", "running", "waiting")

        wait_for(done)


def test_core_definitions_chat_only_lists_and_rejects_send(tmp_path: Path) -> None:
    """ "core + definitions + chat": 대화 목록 정상, 메시지 전송 409 `feature_unavailable`."""
    settings = make_settings(tmp_path, modules={"enabled": ["mod-definitions", "mod-chat"]})
    with server(settings) as client:
        infos = _infos(client)
        assert infos["mod-chat"]["status"] == "active"
        assert infos["mod-definitions"]["status"] == "active"
        assert infos["link-chat-runs"]["status"] == "disabled"
        assert infos["mod-runs"]["status"] == "disabled"
        assert client.get(f"{API}/conversations").json() == []
        seed_chat(client)
        created = client.post(f"{API}/conversations", json={"graph_id": "chat", "title": "t"})
        assert created.status_code == 201, created.text
        conv = created.json()
        listed = client.get(f"{API}/conversations").json()
        assert [c["id"] for c in listed] == [conv["id"]]
        assert listed[0]["last_status"] is None
        assert listed[0]["pending_interactions"] == 0
        assert client.get(f"{API}/conversations/{conv['id']}/turns").json() == []
        renamed = client.patch(f"{API}/conversations/{conv['id']}", json={"title": "새 이름"})
        assert renamed.json()["title"] == "새 이름"
        _assert_send_unavailable(client, conv["id"])
        assert client.get(f"{API}/runs").status_code == 404
        assert client.delete(f"{API}/conversations/{conv['id']}").status_code == 204
        assert client.get(f"{API}/conversations").json() == []


def test_chat_without_definitions_cannot_create(tmp_path: Path) -> None:
    """정의 읽기가 없으면 대화 만들기만 409(목록은 동작)."""
    settings = make_settings(tmp_path, modules={"enabled": ["mod-chat"]})
    with server(settings) as client:
        assert client.get(f"{API}/conversations").json() == []
        res = client.post(f"{API}/conversations", json={"graph_id": "chat"})
        assert res.status_code == 409, res.text
        details = FeatureUnavailableDetails.model_validate(res.json()["error"]["details"])
        assert (details.module, details.port) == ("mod-chat", "definitions.lookup")


def test_disabling_link_turns_off_send_only(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["link-chat-runs"]})
    with server(settings) as client:
        infos = _infos(client)
        assert infos["link-chat-runs"]["status"] == "disabled"
        assert infos["mod-runs"]["status"] == "active"
        seed_chat(client)
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        _assert_send_unavailable(client, conv["id"])
        assert client.get(f"{API}/runs").status_code == 200


def test_disabling_chat_module(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["mod-chat"]})
    with server(settings) as client:
        infos = _infos(client)
        assert infos["mod-chat"]["status"] == "disabled"
        assert infos["link-chat-runs"]["status"] == "unsatisfied"
        assert "chat.conversations" in infos["link-chat-runs"]["reason"]
        assert client.get(f"{API}/conversations").status_code == 404
        assert client.get(f"{API}/runs").status_code == 200
