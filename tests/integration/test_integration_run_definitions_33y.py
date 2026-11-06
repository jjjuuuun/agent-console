"""5.7R.33y 실행별 정의 출처(X26 ``runs.scopes``의 선택 메서드 ``run_definitions``).

design §PI.4.5 규칙 3·4, §PI.10 ``ac-mod-runs``·``ac-runtime`` 행, §PI.13 위험 7.

서버(설치된 모듈 전부, fake 백엔드)에 가짜 범위 모듈 하나를 더한다. 그 모듈은 ``project_id``
``p1``의 Run에 별도 정의 저장소(감시 래퍼)를 출처로 준다. 라이브러리(앱 workspace)와 그 저장소에
**같은 id를 다른 내용**으로 둔다.

- 프로젝트 Run의 루트 그래프·에이전트·리소스(본문)·팀 노드 고정 버전·자식 Run의 에이전트가 모두
  그 저장소에서 읽힌다(조회 감시 + 답 내용).
- 그 저장소에 없는 참조(라이브러리에만 있는 에이전트·그래프)는 실행 실패(라이브러리로 넘어가지
  않음).
- ``project_id`` 없는 Run은 지금처럼 라이브러리(회귀).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_mod_runs import RUN_SCOPES
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Services
from agent_console_server import create_app, installed_modules
from agent_console_server.testing import (
    API,
    TEST_TOKEN,
    agent_doc,
    default_environ,
    make_settings,
    wait_run,
)
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

PROJECT = "p1"


class Spy:
    """정의 저장소 읽기 감시(메서드 이름, 종류, id)."""

    def __init__(self, store: FileDefinitionStore) -> None:
        self.store = store
        self.calls: list[tuple[str, str, str]] = []

    def __getattr__(self, name: str) -> Any:
        method = getattr(self.store, name)

        def call(kind: str, id: str, *rest: Any) -> Any:
            self.calls.append((name, kind, id))
            return method(kind, id, *rest)

        return call

    def seen(self, method: str, kind: str) -> set[str]:
        return {i for m, k, i in self.calls if (m, k) == (method, kind)}


class _ProjectDefinitions:
    """``runs.scopes`` 항목: ``p1`` → 감시 저장소(프로젝트를 모르는 실행 모듈에 출처만 준다)."""

    def __init__(self, source: Spy) -> None:
        self.source = source
        self.calls: list[tuple[str, str]] = []

    def scope_run(self, graph: Any, services: Services, *, project_id: str | None) -> None:
        return None

    def run_definitions(self, project_id: str, graph_id: str) -> Spy | None:
        self.calls.append((project_id, graph_id))
        return self.source if project_id == PROJECT else None


def _scope_module(scoper: _ProjectDefinitions) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_SCOPES, scoper)
        return ModuleParts()

    return fake_module("t-project-definitions", kind="link", provides=[RUN_SCOPES], on_build=build)


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": {},
    }


def _node(node_id: str, type: str = "agent", **config: Any) -> dict[str, Any]:
    return {"id": node_id, "type": type, "label": node_id, "config": config}


def _child() -> dict[str, Any]:
    return {
        "id": "child",
        "name": "자식 팀",
        "nodes": [_node("you", "user"), _node("ca", agent_ref="c-agent")],
        "edges": [
            _edge("m-ca", "you", "says", "ca", "in", "message"),
            _edge("a-ca", "ca", "out", "you", "hears", "reply"),
        ],
    }


def _root(team: dict[str, Any], lead: str = "lead") -> dict[str, Any]:
    return {
        "id": "root",
        "name": "루트",
        "nodes": [_node("you", "user"), _node("T", "team", **team), _node("L", agent_ref=lead)],
        "edges": [
            _edge("m-T", "you", "says", "T", "in", "message"),
            _edge("h1", "T", "out", "L", "in", "handoff"),
            _edge("a-L", "L", "out", "you", "hears", "reply"),
        ],
    }


def _guide() -> dict[str, Any]:
    return {"id": "guide", "type": "instruction", "name": "지침", "config": {"title": "규칙"}}


def _seed_library(client: TestClient) -> None:
    for body in (
        agent_doc("lead", "library-lead", resources=[{"ref": "guide"}]),
        agent_doc("c-agent", "library-child"),
        agent_doc("library-only", "library-only"),
    ):
        assert client.post(f"{API}/agents", json=body).status_code == 201, body["id"]
    assert client.post(f"{API}/resources", json=_guide()).status_code == 201
    for graph in (_child(), _root({"team_ref": "child"})):
        assert client.post(f"{API}/graphs", json=graph).status_code == 201, graph["id"]


def _seed_project(store: FileDefinitionStore) -> str:
    """프로젝트 사본(같은 id, 다른 내용). 자식 팀 구성의 첫 버전 해시를 돌려준다."""
    store.create("agent", agent_doc("lead", "project-lead", resources=[{"ref": "guide"}]))
    store.create("agent", agent_doc("c-agent", "project-child-v1"))
    created = store.create("resource", _guide())
    store.write_content(
        "resource", "guide", b"project rule", file="body.md", expected_version=created.version_hash
    )
    pinned = store.create("graph", _child()).version_hash
    # 고정한 뒤 자식 팀을 고친다(고정 버전 = 고치기 전, 다른 에이전트)
    store.create("agent", agent_doc("c-agent-v2", "project-child-v2"))
    changed = _child()
    changed["nodes"][1]["config"]["agent_ref"] = "c-agent-v2"
    store.save("graph", changed, expected_version=pinned)
    store.create("graph", _root({"team_ref": "child", "version": pinned}))
    return pinned


@contextmanager
def _server(tmp_path: Path, scoper: _ProjectDefinitions) -> Iterator[TestClient]:
    settings = make_settings(tmp_path)
    # 실제 프로젝트 연동(link-projects-runs, 5.7R.33g)은 등록되지 않은 p1을 404로 막으므로 뺀다 —
    # 이 테스트는 가짜 범위 모듈 하나로 정의 출처만 본다. 기록 연동(link-projects-records,
    # 5.7R.33y2)도 등록되지 않은 p1의 기록 DB를 404로 막으므로 뺀다(기록은 호스트 DB).
    skipped = {"link-projects-runs", "link-projects-records"}
    modules = [
        *(m for m in installed_modules() if m.descriptor.id not in skipped),
        _scope_module(scoper),
    ]
    app = create_app(settings, environ=default_environ(), token=TEST_TOKEN, modules=modules)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TEST_TOKEN
        yield client


def _texts(client: TestClient, run_id: str) -> str:
    events = client.get(f"{API}/runs/{run_id}/events").json()
    return json.dumps(
        [e["payload"] for e in events if e["type"] in {"run.reply", "agent.message"}],
        ensure_ascii=False,
    )


def test_project_run_reads_every_definition_from_run_source(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path / "project-defs", DEFAULT_KINDS)
    _seed_project(store)
    spy = Spy(store)
    scoper = _ProjectDefinitions(spy)
    with _server(tmp_path, scoper) as client:
        _seed_library(client)
        spy.calls.clear()
        started = client.post(
            f"{API}/runs", json={"graph_id": "root", "input": {"text": "hi"}, "project_id": PROJECT}
        )
        assert started.status_code == 202, started.text
        snap = wait_run(client, started.json()["id"], timeout=30)
        assert snap["run"]["status"] == "completed", snap["run"]
        assert scoper.calls == [(PROJECT, "root")]  # 출처는 루트에서 한 번(자식은 물려받음)
        root_text = _texts(client, snap["run"]["id"])
        assert "project-lead" in root_text
        assert "library-lead" not in root_text
        [child] = snap["children"]
        child_text = _texts(client, child["id"])
        # 팀 노드 고정 버전(고치기 전 자식 팀 = c-agent)이 프로젝트 저장소에서 읽혔다
        assert "project-child-v1" in child_text
        assert "project-child-v2" not in child_text
        assert "library-child" not in child_text
        # 조회 감시: 루트 그래프·에이전트·리소스(본문)·고정 버전이 모두 이 출처로 갔다
        assert "root" in spy.seen("get", "graph")
        assert {"lead", "c-agent"} <= spy.seen("get", "agent")
        assert "guide" in spy.seen("get", "resource")
        assert "guide" in spy.seen("read_content", "resource")
        assert "child" in spy.seen("get_version", "graph")

        # project_id 없는 Run은 라이브러리(회귀)
        spy.calls.clear()
        plain = client.post(f"{API}/runs", json={"graph_id": "root", "input": {"text": "hi"}})
        assert plain.status_code == 202, plain.text
        snap = wait_run(client, plain.json()["id"], timeout=30)
        assert snap["run"]["status"] == "completed", snap["run"]
        assert "library-lead" in _texts(client, snap["run"]["id"])
        assert spy.calls == []


def test_library_only_references_fail_in_project_run(tmp_path: Path) -> None:
    store = FileDefinitionStore(tmp_path / "project-defs", DEFAULT_KINDS)
    _seed_project(store)
    # 프로젝트 그래프가 라이브러리에만 있는 에이전트를 가리킨다
    store.create("graph", {**_root({"team_ref": "child"}, lead="library-only"), "id": "uses-lib"})
    scoper = _ProjectDefinitions(Spy(store))
    with _server(tmp_path, scoper) as client:
        _seed_library(client)
        blocked = client.post(
            f"{API}/runs",
            json={"graph_id": "uses-lib", "input": {"text": "hi"}, "project_id": PROJECT},
        )
        assert blocked.status_code == 422, blocked.text
        issues = blocked.json()["error"]["details"]["issues"]
        # 엔진 검사(agent.not_found)와 팀 규칙(team.agent_not_found)은 같은 뜻이면 하나로 합친다
        codes = {i["code"] for i in issues if i.get("node_id") == "L"}
        assert codes & {"agent.not_found", "team.agent_not_found"}, issues
        # 라이브러리에만 있는 그래프도 프로젝트 Run으로는 찾지 않는다
        store.delete("graph", "root", expected_version=store.get("graph", "root").version_hash)
        missing = client.post(
            f"{API}/runs", json={"graph_id": "root", "input": {"text": "hi"}, "project_id": PROJECT}
        )
        assert missing.status_code == 404, missing.text
        assert client.get(f"{API}/runs").json() == []
