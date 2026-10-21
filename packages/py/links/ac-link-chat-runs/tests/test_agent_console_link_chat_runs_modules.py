"""실제 기능 모듈(mod-chat·mod-runs·mod-definitions)과 함께: 포트 계약과 HTTP 흐름(3R.14).

- 계약: ``mod-runs``의 ``runs.starter``는 ``RunStarter``, ``mod-chat``의 ``chat.conversations``는
  ``ChatLike``를 만족한다.
- 흐름: 대화 → 메시지 → 실제 엔진 턴(Run, ``conversation_id``) → 턴 목록. 연동을 빼면 409.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_chat_runs import (
    CHAT_CONVERSATIONS,
    RESUME_HANDLERS,
    RUNS_STARTER,
    ChatLike,
    ConversationResume,
    RunStarter,
    module,
)
from agent_console_mod_chat import module as chat_module
from agent_console_mod_definitions import module as definitions_module
from agent_console_mod_runs import module as runs_module
from agent_console_modkit import Assembly, BaseServices, Module, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _assembly(tmp_path: Path, *, link: bool = True) -> Assembly:
    paths = Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    modules: list[Module] = [chat_module, runs_module, definitions_module]
    if link:
        modules.append(module)
    return assemble(modules, base=BaseServices(paths=paths))


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _graph() -> dict[str, Any]:
    def edge(eid: str, source: tuple[str, str], target: tuple[str, str], kind: str) -> Any:
        return {
            "id": eid,
            "source": {"node": source[0], "port": source[1]},
            "target": {"node": target[0], "port": target[1]},
            "kind": kind,
        }

    return {
        "id": "chat",
        "name": "채팅 팀",
        "nodes": [
            {"id": "you", "type": "user"},
            {"id": "a", "type": "agent", "config": {"agent_ref": "asker"}},
        ],
        "edges": [
            edge("m1", ("you", "says"), ("a", "in"), "message"),
            edge("r1", ("a", "out"), ("you", "hears"), "reply"),
        ],
    }


def test_real_ports_satisfy_consumer_protocols(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    assert all(r.state.value == "active" for r in assembly.report), assembly.report
    assert isinstance(assembly.port(RUNS_STARTER), RunStarter)
    assert isinstance(assembly.port(CHAT_CONVERSATIONS), ChatLike)
    assert any(isinstance(h, ConversationResume) for h in assembly.ports(RESUME_HANDLERS))


def test_message_starts_engine_turn(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        assert client.post(f"{API}/graphs", json=_graph()).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        res = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert res.status_code == 202, res.text
        run = res.json()
        assert run["conversation_id"] == conv["id"]
        assert run["origin"] == "chat"
        deadline = time.monotonic() + 10
        turns: list[Any] = []
        while time.monotonic() < deadline:
            turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
            if turns and turns[-1]["status"] in TERMINAL:
                break
            time.sleep(0.02)
        # 노드 서비스(link-runs-teams)가 없어 에이전트 노드는 실패하지만, 턴은 엔진 Run이다
        assert [t["run_id"] for t in turns] == [run["id"]]
        assert turns[-1]["status"] in TERMINAL
        assert client.get(f"{API}/runs/{run['id']}").status_code == 200


def test_without_link_send_is_feature_unavailable(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path, link=False)) as client:
        assert client.post(f"{API}/graphs", json=_graph()).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "chat"}).json()
        res = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "feature_unavailable"
        assert error["details"] == {"module": "mod-chat", "port": "chat.turn_launcher"}
