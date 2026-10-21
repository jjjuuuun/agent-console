"""5.2R.34: 실행 범위(``runs.scopes``)와 Run 맥락(``run_context``).

- 범위 공급자는 요청 ``project_id``(불투명 문자열)를 받아 이 Run에만 더할 노드 서비스·경고를 준다.
  검사·준비보다 먼저 불려 준비자도 그 서비스를 본다. 자식 Run은 부모 서비스를 물려받는다.
- 경고는 Run 이벤트 ``log.warning``(``details.code``)으로 남는다.
- 준비자의 선택 속성 ``run_context``는 ``run.started`` payload에 실린다(자식 Run도 같다).
- 범위 공급자가 없으면 지금과 같다(``project_id`` 기록만).

실행 모듈은 프로젝트를 모른다는 것을 테스트 서비스 키·테스트 타입으로 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Graph, Issue
from agent_console_mod_runs import (
    RUN_PREPARERS,
    RUN_SCOPES,
    RunPreparation,
    RunScope,
    RunScoper,
    module,
)
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, ServiceKey, Services, load_registries
from agent_console_runtime.testing import BUILDERS as B
from agent_console_runtime.testing import (
    register_child_types,
    register_interaction_types,
    register_scheduling_types,
)
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
SCOPE_KEY = ServiceKey[str]("test.scope")


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    register_scheduling_types(registries)
    register_interaction_types(registries)
    register_child_types(registries)
    return registries


def _child() -> Graph:
    return B.graph([B.node("Q", type="t.asker", asks=[])], [B.reply("Q")], "child", entries=["Q"])


def _parent() -> Graph:
    return B.graph(
        [B.node("N", type="t.nest", graph=_child().model_dump(mode="json"))],
        [B.reply("N")],
        "parent",
        entries=["N"],
    )


class _Scoper:
    """``project_id`` → 서비스 ``test.scope``, ``ghost``는 경고만."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScope | None:
        self.calls.append(project_id)
        if project_id is None:
            return None
        if project_id == "ghost":
            issue = Issue(severity="warning", code="test.unknown", message="없는 범위")
            return RunScope(warnings=[issue])
        return RunScope(services={SCOPE_KEY: f"scope:{project_id}"})


class _Broken:
    def scope_run(
        self, graph: Graph, services: Services, *, project_id: str | None
    ) -> RunScope | None:
        raise RuntimeError("고장")


@dataclass
class _Preparer:
    """준비 때 본 서비스 값을 기록하고, 그 값을 Run 맥락 ``seen``으로 싣는다."""

    seen: list[tuple[str, str | None]] = field(default_factory=list)

    def check(
        self, graph: Graph, engine_issues: Sequence[Issue], services: Services, *, strict: bool
    ) -> list[Issue]:
        return []

    def prepare(self, graph: Graph, services: Services) -> RunPreparation:
        value = services.get(SCOPE_KEY)
        self.seen.append((graph.id, value))
        return RunPreparation(run_context={"seen": value or "", "status": "무시됨"})


def _module(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


@contextmanager
def _client(tmp_path: Path, *extra: Module) -> Iterator[TestClient]:
    FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS).create(
        "graph", _parent().model_dump(mode="json")
    )
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    assembly = assemble([module, local_definitions_module(), *extra], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _finish(client: TestClient, body: dict[str, Any]) -> str:
    created = client.post(f"{API}/runs", json={"graph_id": "parent", **body})
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap = client.get(f"{API}/runs/{run_id}").json()
        children = snap["children"]
        if snap["run"]["status"] in TERMINAL and all(c["status"] in TERMINAL for c in children):
            return run_id
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _events(client: TestClient, run_id: str, type_: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
    return [e for e in events if e["type"] == type_]


def test_scope_services_reach_preparers_and_child_runs(tmp_path: Path) -> None:
    scoper, preparer = _Scoper(), _Preparer()
    assert isinstance(scoper, RunScoper)
    with _client(
        tmp_path, _module("t-scope", RUN_SCOPES, scoper), _module("t-prep", RUN_PREPARERS, preparer)
    ) as client:
        root_id = _finish(client, {"project_id": "p1"})
        assert scoper.calls == ["p1"]  # 자식 Run은 범위를 다시 정하지 않는다
        # 부모·자식 준비 모두 범위 서비스를 봤다(자식은 부모 서비스를 물려받음)
        assert preparer.seen == [("parent", "scope:p1"), ("child", "scope:p1")]
        [started] = _events(client, root_id, "run.started")
        assert started["payload"]["seen"] == "scope:p1"
        assert started["payload"]["status"] == "running"  # 상태 필드는 맥락이 덮지 않는다
        [child] = client.get(f"{API}/runs/{root_id}").json()["children"]
        [child_started] = _events(client, child["id"], "run.started")
        assert child_started["payload"]["seen"] == "scope:p1"
        assert _events(client, root_id, "log.warning") == []


def test_scope_warnings_become_run_warnings(tmp_path: Path) -> None:
    scoper, preparer = _Scoper(), _Preparer()
    with _client(
        tmp_path, _module("t-scope", RUN_SCOPES, scoper), _module("t-prep", RUN_PREPARERS, preparer)
    ) as client:
        run_id = _finish(client, {"project_id": "ghost"})
        [warning] = _events(client, run_id, "log.warning")
        assert warning["payload"]["details"]["code"] == "test.unknown"
        assert warning["node_path"] == []
        assert preparer.seen[0] == ("parent", None)  # 층 없이 실행
        run = client.get(f"{API}/runs/{run_id}").json()["run"]
        assert run["status"] == "completed"
        assert run["project_id"] == "ghost"


def test_without_project_or_scopes_nothing_changes(tmp_path: Path) -> None:
    preparer = _Preparer()
    with _client(tmp_path, _module("t-prep", RUN_PREPARERS, preparer)) as client:
        run_id = _finish(client, {"project_id": "p1"})  # 범위 공급자 없음
        assert preparer.seen[0] == ("parent", None)
        assert client.get(f"{API}/runs/{run_id}").json()["run"]["project_id"] == "p1"
    scoper = _Scoper()
    with _client(tmp_path / "b", _module("t-scope", RUN_SCOPES, scoper)) as client:
        run_id = _finish(client, {})
        assert scoper.calls == [None]
        [started] = _events(client, run_id, "run.started")
        assert set(started["payload"]) >= {"status"}
        assert "seen" not in started["payload"]


def test_broken_scope_is_logged_and_skipped(tmp_path: Path) -> None:
    preparer = _Preparer()
    with _client(
        tmp_path,
        _module("t-broken", RUN_SCOPES, _Broken()),
        _module("t-prep", RUN_PREPARERS, preparer),
    ) as client:
        run_id = _finish(client, {"project_id": "p1"})
        assert client.get(f"{API}/runs/{run_id}").json()["run"]["status"] == "completed"
        assert preparer.seen[0] == ("parent", None)
