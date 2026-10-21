"""5R.13: 자식 Run(중첩 팀)·조건 연산자 경로.

- 자식 Run 준비 = 일반 Run과 같은 준비자(``runs.preparers``) 검사·준비(``prepare_child``).
- ``GET /runs?root=``·``GET /runs/{id}``의 ``children``·``GET /interactions?root=``.
- 부모 취소 → 자식 취소(엔진 전파), 자식 Run은 따로 이어 가지 않는다.
- ``GET /condition-operators``와 연산자를 쓰는 연결 종류가 같은 레지스트리를 본다.

노드·연결 이름을 모른다는 것을 엔진 테스트 타입(``t.nest``·``t.asker`` 등)으로 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_conditions import builtin_operators
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, EdgeTypeDescriptor, Graph, Issue
from agent_console_mod_runs import RUN_PREPARERS, RUNS_STARTER, RunPreparation, RunService, module
from agent_console_mod_runs.plugins import (
    CONDITION_OPERATORS_REPORT_GROUP,
    condition_operators,
    load_plugins,
)
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    Module,
    ModuleContext,
    ModuleParts,
    Paths,
    PluginLoadContext,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, Services, load_registries
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


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    register_scheduling_types(registries)
    register_interaction_types(registries)
    register_child_types(registries)
    return registries


def _child(*, ask: bool = True) -> Graph:
    node = B.node("Q", type="t.asker", asks=[{"title": "확인?"}] if ask else [])
    return B.graph([node], [B.reply("Q")], "child", entries=["Q"])


def _parent(child: Graph) -> Graph:
    return B.graph(
        [B.node("N", type="t.nest", graph=child.model_dump(mode="json"))],
        [B.reply("N")],
        "parent",
        entries=["N"],
    )


class _Preparer:
    """그래프 id를 기록하고, ``block``에 든 그래프는 막는다."""

    def __init__(self, block: Sequence[str] = ()) -> None:
        self.block = set(block)
        self.checked: list[str] = []
        self.prepared: list[str] = []

    def check(
        self, graph: Graph, engine_issues: Sequence[Issue], services: Services, *, strict: bool
    ) -> list[Issue]:
        self.checked.append(graph.id)
        if graph.id in self.block:
            return [Issue(severity="error", code="test.blocked", message="막힘")]
        return []

    def prepare(self, graph: Graph, services: Services) -> RunPreparation:
        self.prepared.append(graph.id)
        return RunPreparation()


def _preparer_module(preparer: _Preparer) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUN_PREPARERS, preparer)
        return ModuleParts()

    return fake_module("test-preparer", kind="link", provides=[RUN_PREPARERS], on_build=build)


@contextmanager
def _client(
    tmp_path: Path, *extra: Module, registries: Registries | None = None
) -> Iterator[tuple[TestClient, Assembly]]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries or _registries(),
    )
    assembly = assemble([module, local_definitions_module(), *extra], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _save(tmp_path: Path, graph: Graph) -> None:
    FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS).create(
        "graph", graph.model_dump(mode="json")
    )


def _until(check: Any, timeout: float = 10.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.02)
    raise AssertionError("조건이 이루어지지 않았다")


def _status(client: TestClient, run_id: str) -> str:
    return str(client.get(f"{API}/runs/{run_id}").json()["run"]["status"])


def test_child_run_uses_same_preparers_and_is_listed_by_root(tmp_path: Path) -> None:
    _save(tmp_path, _parent(_child()))
    preparer = _Preparer()
    with _client(tmp_path, _preparer_module(preparer)) as (client, _assembly):
        root = client.post(
            f"{API}/runs", json={"graph_id": "parent", "input": {"text": "hi"}, "project_id": "p1"}
        )
        assert root.status_code == 202, root.text
        root_id = root.json()["id"]
        pending = _until(lambda: client.get(f"{API}/interactions", params={"root": root_id}).json())
        [asked] = pending
        assert asked["root_run_id"] == root_id
        child_id = asked["run_id"]
        assert child_id != root_id
        # 같은 준비자가 자식 그래프도 검사·준비했다
        assert preparer.checked == ["parent", "child"]
        assert preparer.prepared == ["parent", "child"]
        # 루트 기준 목록·직접 자식
        [listed] = client.get(f"{API}/runs", params={"root": root_id}).json()
        assert (listed["id"], listed["parent_run_id"], listed["root_run_id"]) == (
            child_id,
            root_id,
            root_id,
        )
        assert listed["parent_node_id"] == "N"
        # 5.2R.32: 자식 Run은 루트의 project_id를 받고, root_only 목록에는 루트만 나온다
        assert listed["project_id"] == "p1"
        by_project = client.get(f"{API}/runs", params={"project": "p1"}).json()
        assert {r["id"] for r in by_project} == {child_id, root_id}
        roots = client.get(f"{API}/runs", params={"project": "p1", "root_only": "true"}).json()
        assert [r["id"] for r in roots] == [root_id]
        snap = client.get(f"{API}/runs/{root_id}").json()
        assert [c["id"] for c in snap["children"]] == [child_id]
        assert client.get(f"{API}/runs/{child_id}").json()["children"] == []
        assert client.get(f"{API}/runs", params={"root": child_id}).json() == []
        # 루트 Run 자신의 상호작용 목록에는 없고(그 Run 것만), 루트 기준 목록에는 있다
        assert client.get(f"{API}/runs/{root_id}/interactions").json() == []
        _until(lambda: _status(client, root_id) == "waiting")
        # 자식 요청은 자식 Run id로 답한다
        answered = client.post(
            f"{API}/runs/{child_id}/interactions/{asked['id']}/respond",
            json={"response": {"answer": "네"}},
        )
        assert answered.status_code == 200, answered.text
        _until(lambda: _status(client, root_id) in TERMINAL)
        assert _status(client, root_id) == "completed"
        assert _status(client, child_id) == "completed"


def test_child_blocked_by_preparer_fails_the_calling_node(tmp_path: Path) -> None:
    _save(tmp_path, _parent(_child(ask=False)))
    preparer = _Preparer(block=["child"])
    with _client(tmp_path, _preparer_module(preparer)) as (client, _assembly):
        root_id = client.post(f"{API}/runs", json={"graph_id": "parent"}).json()["id"]
        _until(lambda: _status(client, root_id) in TERMINAL)
        snap = client.get(f"{API}/runs/{root_id}").json()
        assert snap["children"] == []  # 자식 Run을 만들지 않았다
        [node_run] = [n for n in snap["node_runs"] if n["node_id"] == "N"]
        assert node_run["status"] == "failed"
        assert node_run["error"]["code"] == "validation_failed"
        codes = [i["code"] for i in node_run["error"]["details"]["issues"]]
        assert codes == ["test.blocked"]
        assert preparer.prepared == ["parent"]


def test_cancel_root_cancels_child_and_child_is_not_resumable(tmp_path: Path) -> None:
    _save(tmp_path, _parent(_child()))
    with _client(tmp_path) as (client, assembly):
        root_id = client.post(f"{API}/runs", json={"graph_id": "parent"}).json()["id"]
        [asked] = _until(lambda: client.get(f"{API}/interactions", params={"root": root_id}).json())
        child_id = asked["run_id"]
        cancelled = client.post(f"{API}/runs/{root_id}/cancel")
        assert cancelled.status_code == 200
        _until(lambda: _status(client, root_id) in TERMINAL)
        _until(lambda: _status(client, child_id) in TERMINAL)
        assert _status(client, root_id) == "cancelled"
        assert _status(client, child_id) == "cancelled"
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunService)
        assert starter.runtime.get(child_id) is None


def test_interrupted_child_run_resume_is_refused(tmp_path: Path) -> None:
    _save(tmp_path, _parent(_child()))
    with _client(tmp_path) as (client, assembly):
        root_id = client.post(f"{API}/runs", json={"graph_id": "parent"}).json()["id"]
        [asked] = _until(lambda: client.get(f"{API}/interactions", params={"root": root_id}).json())
        child_id = asked["run_id"]
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunService)
        client.portal.call(starter.shutdown)  # type: ignore[union-attr]
        assert _status(client, child_id) == "interrupted"
        assert client.get(f"{API}/runs/{child_id}/resume-options").json()["nodes"] == []
        refused = client.post(f"{API}/runs/{child_id}/resume", json={"node_ids": ["Q"]})
        assert refused.status_code == 409, refused.text
        details = refused.json()["error"]["details"]
        assert (details["root_run_id"], details["parent_run_id"]) == (root_id, root_id)


def _operator_ids(client: TestClient) -> list[str]:
    return [d["id"] for d in client.get(f"{API}/condition-operators").json()]


def test_condition_operators_route_and_edges_share_the_registry(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        assert _operator_ids(client) == sorted(op.descriptor.id for op in builtin_operators())
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunService)
        # 연산자 하나를 지우면(플러그인 제거 흉내) 목록과 조건 연결 검사가 같이 바뀐다
        condition_operators(starter.registries).unregister("contains")
        assert "contains" not in _operator_ids(client)
        # 조건을 쓰는 연결 종류는 이름 대신 config 스키마로 고른다(모듈·테스트는 이름을 모른다)
        kind = next(
            d.id
            for d in starter.edge_types()
            if "conditions" in d.config_schema.get("properties", {})
        )
        item = {"path": "/output", "op": "contains", "value": "x"}
        when = B.edge("a", "b", kind=kind, sp="says", tp="hears", conditions={"all": [item]})
        users = [B.node("a", type="t.user"), B.node("b", type="t.user")]
        graph = B.graph(users, [when], "cond", entries=["a"])
        codes = [i.code for i in starter.check(graph) if i.edge_id == when.id]
        assert "condition.unknown_operator" in codes


def test_plugin_loader_reports_condition_operator_group() -> None:
    registries = Registries()
    reports = load_plugins(PluginLoadContext(registries=registries))
    groups = {g for g, _ in reports}
    assert CONDITION_OPERATORS_REPORT_GROUP in groups
    loaded = {r.key for g, r in reports if g == CONDITION_OPERATORS_REPORT_GROUP}
    assert loaded == {op.descriptor.id for op in builtin_operators()}
    assert {e.key for e in condition_operators(registries).list()} == loaded


class _EvidenceEdge:
    """판정 근거를 만드는 임의 이름 연결 종류(가림 함수를 받는다, ``RedactorConsumer``)."""

    descriptor = EdgeTypeDescriptor(id="zz.evidence", title="근거", scheduling="flow")

    def __init__(self) -> None:
        self.redact: Any = None

    def use_redactor(self, redact: Any) -> None:
        self.redact = redact

    def activates(self, source: Any, edge: Any) -> None:
        return None


def test_module_binds_engine_redactor_to_evidence_kinds(tmp_path: Path) -> None:
    """5.2R.43: 실행 모듈은 비밀 해석기를 만든 뒤 판정 근거를 만드는 종류에 가림 함수를 준다."""
    registries = _registries()
    probe = _EvidenceEdge()
    registries.edge_types.register("zz.evidence", probe)
    with _client(tmp_path, registries=registries) as (_http, assembly):
        starter = assembly.port(RUNS_STARTER)
        assert isinstance(starter, RunService)
        assert callable(probe.redact)
        assert probe.redact("평범한 글") == "평범한 글"
