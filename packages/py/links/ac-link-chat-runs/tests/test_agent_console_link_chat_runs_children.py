"""실제 모듈(mod-chat·mod-runs·mod-definitions)과 함께: 중첩 팀의 자식 Run 요청이 루트 턴에 모인다
(5R.13, design §5R.11).

- 턴의 상호작용 = 루트 Run과 자식 Run의 요청(``root_run_id``), 대화 대기 수에도 들어간다.
- 자식 Run의 상호작용 이벤트가 루트 대화 요약 알림을 부른다.
- 자식 Run은 대화 턴이 아니다(턴 목록에 없음).

노드 종류 이름을 모른다는 것을 엔진 테스트 타입(``t.nest``·``t.asker``)으로 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_link_chat_runs import CHAT_CONVERSATIONS, module
from agent_console_mod_chat import module as chat_module
from agent_console_mod_definitions import module as definitions_module
from agent_console_mod_runs import module as runs_module
from agent_console_modkit import Assembly, BaseServices, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import Registries, load_registries
from agent_console_runtime.testing import BUILDERS as B
from agent_console_runtime.testing import (
    register_child_types,
    register_interaction_types,
    register_scheduling_types,
)

API = "/api/v1"
TOKEN = "t" * 32


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    register_scheduling_types(registries)
    register_interaction_types(registries)
    register_child_types(registries)
    return registries


def _assembly(tmp_path: Path) -> Assembly:
    paths = Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    return assemble(
        [chat_module, runs_module, definitions_module, module],
        base=BaseServices(paths=paths, registries=_registries()),
    )


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _graph() -> dict[str, Any]:
    child = B.graph(
        [B.node("Q", type="t.asker", asks=[{"title": "확인?"}])],
        [B.reply("Q")],
        "child",
        entries=["Q"],
    )
    parent = B.graph(
        [B.node("N", type="t.nest", graph=child.model_dump(mode="json"))],
        [B.reply("N")],
        "nested",
        entries=["N"],
    )
    return parent.model_dump(mode="json")


def _until(check: Callable[[], Any], timeout: float = 10.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.02)
    raise AssertionError("조건이 이루어지지 않았다")


def test_child_run_requests_belong_to_root_turn(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        notified: list[str] = []
        chat: Any = assembly.port(CHAT_CONVERSATIONS)
        original = chat.notify

        def spy(conversation_id: str) -> None:
            notified.append(conversation_id)
            original(conversation_id)

        chat.notify = spy  # 실행 이벤트 → 대화 알림 경로(ConversationNotifier)를 본다
        assert client.post(f"{API}/graphs", json=_graph()).status_code == 201
        conv = client.post(f"{API}/conversations", json={"graph_id": "nested"}).json()
        res = client.post(f"{API}/conversations/{conv['id']}/messages", json={"text": "안녕"})
        assert res.status_code == 202, res.text
        root_id = res.json()["id"]

        def turn_with_request() -> Any:
            turns = client.get(f"{API}/conversations/{conv['id']}/turns").json()
            return turns if turns and turns[-1]["interactions"] else None

        turns = _until(turn_with_request)
        assert [t["run_id"] for t in turns] == [root_id]  # 자식 Run은 턴이 아니다
        [asked] = turns[-1]["interactions"]
        assert asked["root_run_id"] == root_id
        assert asked["run_id"] != root_id
        assert asked["conversation_id"] == conv["id"]
        [summary] = [c for c in client.get(f"{API}/conversations").json() if c["id"] == conv["id"]]
        assert summary["pending_interactions"] == 1
        _until(lambda: conv["id"] in notified)  # 자식 Run의 interaction.* → 루트 대화 알림

        answered = client.post(
            f"{API}/runs/{asked['run_id']}/interactions/{asked['id']}/respond",
            json={"response": {"answer": "네"}},
        )
        assert answered.status_code == 200, answered.text

        def finished() -> Any:
            turn = client.get(f"{API}/conversations/{conv['id']}/turns").json()[-1]
            return turn if turn["status"] == "completed" else None

        turn = _until(finished)
        [closed] = turn["interactions"]
        assert closed["status"] != "pending"
        assert len(turn["replies"]) == 1  # 중첩 노드의 답변만(자식 답변은 채팅에 흘리지 않음)
