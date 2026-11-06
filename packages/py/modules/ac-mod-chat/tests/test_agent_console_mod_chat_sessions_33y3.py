"""5.7R.33y3: ``GET /conversations/{id}/sessions``와 409 ``chat.session_unavailable``(선택 포트
``records.sessions``). 포트가 없으면 모든 세션이 ``not_applicable``(지금 동작)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from agent_console_chat import ChatService
from agent_console_chat.testing import FakeLauncher, MemoryContinuity, MemoryEvents, MemoryRuns
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, SessionRef
from agent_console_mod_chat import CHAT_CONVERSATIONS, DEFINITIONS_LOOKUP, RECORDS_SESSIONS, module
from agent_console_mod_chat.testing import fake_turns_module
from agent_console_modkit import Assembly, Module, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module

API = "/api/v1"
TOKEN = "t" * 32
GRAPH = {"id": "team", "name": "팀", "nodes": [{"id": "pl", "type": "agent"}]}


def _definitions() -> Module:
    found = SimpleNamespace(get=lambda kind, id: SimpleNamespace(document=GRAPH))
    return fake_module(
        "defs",
        provides=[DEFINITIONS_LOOKUP],
        on_build=lambda ctx: ctx.provide(DEFINITIONS_LOOKUP, found),
    )


def _continuity(found: MemoryContinuity) -> Module:
    return fake_module(
        "sessions",
        provides=[RECORDS_SESSIONS],
        on_build=lambda ctx: ctx.provide(RECORDS_SESSIONS, found),
    )


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    client = TestClient(
        create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    )
    client.headers["X-Console-Token"] = TOKEN
    return client


def _with_session(assembly: Assembly, client: TestClient) -> str:
    conv: dict[str, Any] = client.post(f"{API}/conversations", json={"graph_id": "team"}).json()
    service = assembly.port(CHAT_CONVERSATIONS)
    assert isinstance(service, ChatService)
    stored = service.get(conv["id"])
    ref = SessionRef(backend="fake-agent", session_id="s1")
    service._conversations.save(stored.model_copy(update={"sessions": {"pl": ref}}))
    return str(conv["id"])


def test_without_port_sessions_are_not_applicable() -> None:
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    assembly = assemble([module, _definitions(), fake_turns_module(launcher=launcher)])
    with _client(assembly) as client:
        cid = _with_session(assembly, client)
        body = client.get(f"{API}/conversations/{cid}/sessions").json()
        assert body == {
            "conversation_id": cid,
            "continuable": True,
            "items": [
                {
                    "node_id": "pl",
                    "backend": "fake-agent",
                    "session_id": "s1",
                    "state": "not_applicable",
                }
            ],
        }
        assert (
            client.post(f"{API}/conversations/{cid}/messages", json={"text": "a"}).status_code
            == 202
        )
        assert client.get(f"{API}/conversations/nope/sessions").status_code == 404


def test_missing_session_is_409_and_fresh_starts() -> None:
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    found = MemoryContinuity({"s1": "missing"})
    assembly = assemble(
        [module, _definitions(), fake_turns_module(launcher=launcher), _continuity(found)]
    )
    with _client(assembly) as client:
        cid = _with_session(assembly, client)
        body = client.get(f"{API}/conversations/{cid}/sessions").json()
        assert body["continuable"] is False
        refused = client.post(f"{API}/conversations/{cid}/messages", json={"text": "a"})
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "chat.session_unavailable"
        assert refused.json()["error"]["details"] == {"conversation_id": cid, "node_ids": ["pl"]}
        fresh = client.post(
            f"{API}/conversations/{cid}/messages", json={"text": "a", "on_missing_session": "fresh"}
        )
        assert fresh.status_code == 202, fresh.text
        assert launcher.started[0].sessions == {}
        assert dict(launcher.started[0].session_notes) == {"pl": "fresh"}
