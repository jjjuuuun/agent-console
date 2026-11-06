"""5.7R.33y: 프로젝트 대화의 팀 구성 = ``definitions.spaces``(선택 포트)의 그 공간에서만.

- 포트가 있으면 ``project_id``가 있는 대화의 팀 구성은 그 공간에서 찾는다. 라이브러리에만 있는
  팀 구성·모르는 공간은 404(라이브러리로 넘어가지 않는다). 같은 id면 공간 사본으로 턴을 시작한다.
- 포트가 없으면 지금 동작(프로젝트 대화도 ``definitions.lookup``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from agent_console_chat.testing import FakeLauncher, MemoryEvents, MemoryRuns
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_chat import (
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SPACES,
    PortGraphLookup,
    module,
)
from agent_console_mod_chat.testing import fake_turns_module
from agent_console_modkit import Assembly, Module, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import NotFound

API = "/api/v1"
TOKEN = "t" * 32


def _graph(graph_id: str, node: str) -> dict[str, Any]:
    return {"id": graph_id, "name": graph_id, "nodes": [{"id": node, "type": "agent"}]}


class _Store:
    def __init__(self, *documents: dict[str, Any]) -> None:
        self.documents = {d["id"]: d for d in documents}
        self.calls: list[str] = []

    def get(self, kind: str, id: str) -> Any:
        self.calls.append(id)
        if id not in self.documents:
            raise NotFound(f"{kind} {id}")
        return SimpleNamespace(document=self.documents[id])


class _Spaces:
    def __init__(self, spaces: dict[str, _Store]) -> None:
        self.spaces = spaces

    def open(self, project_id: str) -> _Store:
        if project_id not in self.spaces:
            raise LookupError(project_id)
        return self.spaces[project_id]


def _stores() -> tuple[_Store, _Store]:
    library = _Store(_graph("team", "library-node"), _graph("library-only", "x"))
    project = _Store(_graph("team", "project-node"), _graph("project-only", "y"))
    return library, project


def _provider(port: Any, value: object, module_id: str) -> Module:
    return fake_module(module_id, provides=[port], on_build=lambda ctx: ctx.provide(port, value))


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_port_graph_lookup_reads_space_only() -> None:
    library, project = _stores()
    graphs = PortGraphLookup(lambda: library, spaces=lambda: _Spaces({"p1": project}))
    found = graphs.get_project_graph("p1", "team")
    assert found is not None
    assert [n.id for n in found.nodes] == ["project-node"]
    assert graphs.get_project_graph("p1", "library-only") is None
    assert graphs.get_project_graph("ghost", "team") is None
    assert library.calls == []
    without = PortGraphLookup(lambda: library)
    fallback = without.get_project_graph("p1", "team")
    assert fallback is not None
    assert [n.id for n in fallback.nodes] == ["library-node"]


def test_project_conversations_use_space_graphs() -> None:
    library, project = _stores()
    launcher = FakeLauncher(MemoryRuns(), MemoryEvents())
    assembly = assemble(
        [
            module,
            _provider(DEFINITIONS_LOOKUP, library, "t-library"),
            _provider(DEFINITIONS_SPACES, _Spaces({"p1": project}), "t-spaces"),
            fake_turns_module(launcher=launcher),
        ]
    )
    with _client(assembly) as client:
        missing = client.post(
            f"{API}/conversations", json={"graph_id": "library-only", "project_id": "p1"}
        )
        assert missing.status_code == 404, missing.text
        created = client.post(f"{API}/conversations", json={"graph_id": "team", "project_id": "p1"})
        assert created.status_code == 201, created.text
        conv = created.json()["id"]
        sent = client.post(f"{API}/conversations/{conv}/messages", json={"text": "hi"})
        assert sent.status_code in (200, 201, 202), sent.text
        [start] = launcher.started
        assert [n.id for n in start.graph.nodes] == ["project-node"]
        assert library.calls == []
        # 프로젝트 없는 대화는 라이브러리
        plain = client.post(f"{API}/conversations", json={"graph_id": "library-only"})
        assert plain.status_code == 201, plain.text
