"""mod-chat: 대화·대기열 경로, WS conversation:, 선택 포트(3R.14).

- 실행 연결이 없으면 대화 목록·만들기·고치기·지우기·대기열은 동작하고, 메시지 전송은 409
  ``feature_unavailable{module: mod-chat, port: chat.turn_launcher}``.
- 정의 읽기가 없으면 대화 만들기만 409(``definitions.lookup``).
- 실행 연결(가짜)이 있으면 턴이 시작되고, WS ``conversation:<id>``가 요약을 보낸다.
- DB 핸들이 있으면 SQLite에, 없으면 메모리에 두고 경고한다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_chat import ChatService
from agent_console_chat.testing import FakeLauncher, MemoryEvents, MemoryRuns
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ConversationSummary
from agent_console_mod_chat import (
    CHAT_CONVERSATIONS,
    CONVERSATIONS_UPDATED,
    DEFINITIONS_LOOKUP,
    SERVER_WARNINGS,
    STORAGE_MEMORY,
    PortGraphLookup,
    module,
)
from agent_console_mod_chat.testing import fake_turns_module, local_definitions_module
from agent_console_modkit import Assembly, BaseServices, Module, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "t" * 32
GRAPH_DOC = {"id": "team", "name": "팀", "nodes": [{"id": "pl", "type": "agent"}]}


class _Definitions:
    """``definitions.lookup`` 가짜(팀 구성 하나)."""

    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def get(self, kind: str, id: str) -> Any:
        from agent_console_store import NotFound

        if id not in self.documents:
            raise NotFound(f"{kind} {id}")
        return SimpleNamespace(document=self.documents[id])


def _definitions(documents: dict[str, dict[str, Any]] | None = None) -> Module:
    from agent_console_modkit.testing import fake_module

    found = _Definitions(documents if documents is not None else {"team": GRAPH_DOC})
    return fake_module(
        "my-definitions",
        provides=[DEFINITIONS_LOOKUP],
        on_build=lambda ctx: ctx.provide(DEFINITIONS_LOOKUP, found),
    )


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _warnings(assembly: Assembly) -> list[str]:
    return [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]


def test_alone_lists_and_reports_unavailable_parts() -> None:
    assembly = assemble([module])
    assert [(r.id, r.state.value) for r in assembly.report] == [("mod-chat", "active")]
    assert _warnings(assembly) == [STORAGE_MEMORY]
    with _client(assembly) as client:
        assert client.get(f"{API}/conversations").json() == []
        res = client.post(f"{API}/conversations", json={"graph_id": "team"})
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "feature_unavailable"
        assert error["details"] == {"module": "mod-chat", "port": "definitions.lookup"}
        assert client.get(f"{API}/conversations/nope").status_code == 404


def test_without_turns_conversations_work_and_send_is_409() -> None:
    with _client(assemble([module, _definitions()])) as client:
        res = client.post(f"{API}/conversations", json={"graph_id": "team", "title": "t"})
        assert res.status_code == 201, res.text
        conv = res.json()
        assert client.post(f"{API}/conversations", json={"graph_id": "nope"}).status_code == 404
        listed = client.get(f"{API}/conversations").json()
        assert [(c["id"], c["last_status"], c["queued"]) for c in listed] == [(conv["id"], None, 0)]
        patched = client.patch(f"{API}/conversations/{conv['id']}", json={"archived": True})
        assert patched.json()["archived"] is True
        assert client.get(f"{API}/conversations/{conv['id']}/turns").json() == []
        assert client.get(f"{API}/conversations/{conv['id']}/queue").json() == []
        res = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "feature_unavailable"
        assert error["details"] == {"module": "mod-chat", "port": "chat.turn_launcher"}
        bad = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "  "})
        assert bad.status_code == 400
        missing = client.delete(f"{API}/conversations/{conv['id']}/queue/q1")
        assert missing.status_code == 404
        assert client.delete(f"{API}/conversations/{conv['id']}").status_code == 204
        assert client.get(f"{API}/conversations").json() == []


def test_with_fake_turns_sends_and_streams_summary() -> None:
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    summaries: list[ConversationSummary] = []
    assembly = assemble([module, _definitions(), fake_turns_module(launcher=launcher)])
    assembly.services.events.subscribe(CONVERSATIONS_UPDATED, summaries.append)
    with _client(assembly) as client:
        conv = client.post(f"{API}/conversations", json={"graph_id": "team"}).json()
        with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": f"conversation:{conv['id']}"}})
            first = ws.receive_json()
            assert first["type"] == "conversation.updated"
            assert first["payload"]["conversation"]["id"] == conv["id"]
            res = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
            assert res.status_code == 202, res.text
            assert res.json()["conversation_id"] == conv["id"]
            update = ws.receive_json()
            assert update["payload"]["conversation"]["last_status"] == "running"
        queued = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "둘"})
        assert queued.status_code == 202
        assert queued.json()["queued"] is True
        queue = client.get(f"{API}/conversations/{conv['id']}/queue").json()
        assert [q["text"] for q in queue] == ["둘"]
        turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
        assert [t["user_text"] for t in turns] == ["안녕"]
    assert any(s.id == conv["id"] for s in summaries)


def test_project_id_is_stored_and_listed_by_query(tmp_path: Path) -> None:
    """5.2R.32: ``project_id`` 저장, ``?project=`` 거르기(불투명 문자열), 재시작 뒤에도 유지."""

    def build() -> Assembly:
        database = SqliteDatabase.open(tmp_path / "console.sqlite3")
        return assemble([module, _definitions()], base=BaseServices(database=database))

    first = build()
    with _client(first) as client:
        inside = client.post(f"{API}/conversations", json={"graph_id": "team", "project_id": "p1"})
        assert inside.status_code == 201, inside.text
        assert inside.json()["project_id"] == "p1"
        outside = client.post(f"{API}/conversations", json={"graph_id": "team"}).json()
        assert outside["project_id"] is None

        def ids(**q: str) -> list[str]:
            return [c["id"] for c in client.get(f"{API}/conversations", params=q).json()]

        assert ids(project="p1") == [inside.json()["id"]]
        assert ids(project="zzz") == []
        assert set(ids()) == {inside.json()["id"], outside["id"]}
        assert (
            client.get(f"{API}/conversations", params={"project": "p1"}).json()[0]["project_id"]
            == "p1"
        )
    first.services.database.close()  # type: ignore[union-attr]
    second = build()
    with _client(second) as client:
        got = client.get(f"{API}/conversations/{inside.json()['id']}").json()
        assert got["project_id"] == "p1"
    second.services.database.close()  # type: ignore[union-attr]


def test_ws_unknown_conversation_is_not_found() -> None:
    with (
        _client(assemble([module])) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:nope"}})
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["payload"]["code"] == "not_found"


def test_sqlite_storage_survives_restart(tmp_path: Path) -> None:
    def build() -> Assembly:
        database = SqliteDatabase.open(tmp_path / "console.sqlite3")
        return assemble([module, _definitions()], base=BaseServices(database=database))

    first = build()
    assert _warnings(first) == []
    with _client(first) as client:
        conv = client.post(f"{API}/conversations", json={"graph_id": "team"}).json()
    first.services.database.close()  # type: ignore[union-attr]
    second = build()
    with _client(second) as client:
        assert [c["id"] for c in client.get(f"{API}/conversations").json()] == [conv["id"]]
    second.services.database.close()  # type: ignore[union-attr]


def test_local_definitions_module_reads_workspace_files(tmp_path: Path) -> None:
    from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

    workspace = tmp_path / "ws"
    store = FileDefinitionStore(workspace, DEFAULT_KINDS)
    store.create("graph", GRAPH_DOC)
    paths = Paths(base_dir=tmp_path, workspace=workspace, state=tmp_path / "state")
    assembly = assemble([module, local_definitions_module()], base=BaseServices(paths=paths))
    chat: ChatService = assembly.port(CHAT_CONVERSATIONS)  # type: ignore[assignment]
    with _client(assembly) as client:
        assert client.post(f"{API}/conversations", json={"graph_id": "team"}).status_code == 201
    assert len(chat.list()) == 1


@pytest.mark.parametrize(
    ("documents", "expected"),
    [({"team": GRAPH_DOC}, "team"), ({"team": {"id": "team"}}, None), ({}, None)],
)
def test_port_graph_lookup(documents: dict[str, Any], expected: str | None) -> None:
    lookup = PortGraphLookup(lambda: _Definitions(documents))
    assert lookup.available
    graph = lookup.get_graph("team")
    assert (graph.id if graph is not None else None) == expected
    assert PortGraphLookup(lambda: None).get_graph("team") is None
    assert not PortGraphLookup(lambda: None).available
