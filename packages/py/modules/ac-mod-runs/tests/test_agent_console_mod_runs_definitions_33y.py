"""5.7R.33y: 실행별 정의 출처(X26 ``runs.scopes``의 선택 메서드 ``run_definitions``).

- 공급자가 출처를 주면 루트 그래프(현재·버전)를 그 출처에서만 읽는다(라이브러리로 넘어가지 않음).
- 노드 서비스 공급자는 ``RunEnvironment.definitions``로, 준비자·자식 Run은 서비스
  ``RUN_DEFINITIONS``로 같은 출처를 본다.
- 오류 본문을 돌려주면 Run을 만들지 않고 그 코드의 상태로 거부한다.
- ``project_id``가 없거나 공급자가 메서드를 갖지 않으면 지금 동작(서비스 ``RUN_DEFINITIONS`` 없음).

실행 모듈은 프로젝트를 모른다는 것을 테스트 공급자·불투명 ``project_id``로 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    ErrorCodes,
    ErrorInfo,
    Graph,
    Issue,
    Run,
)
from agent_console_graph import graph_hash
from agent_console_mod_runs import (
    DEFINITIONS_LOOKUP,
    RUN_DEFINITIONS,
    RUN_PREPARERS,
    RUN_SCOPES,
    RUN_SERVICES,
    RUNS_STARTER,
    RunDefinitionsScoper,
    RunEnvironment,
    RunPreparation,
    RunScoper,
    module,
)
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
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
ENV_KEY = ServiceKey[str]("test.env_definitions")


class Spy:
    """정의 저장소를 감싸 읽기 호출을 기록한다(조회 감시)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.store = InMemoryDefinitionStore(DEFAULT_KINDS)
        self.calls: list[tuple[str, str, str]] = []

    def get(self, kind: str, id: str) -> Any:
        self.calls.append(("get", kind, id))
        return self.store.get(kind, id)

    def get_version(self, kind: str, id: str, version_hash: str) -> Any:
        self.calls.append(("get_version", kind, id))
        return self.store.get_version(kind, id, version_hash)

    def ids(self) -> set[str]:
        return {c[2] for c in self.calls}


def _registries() -> Registries:
    registries = Registries()
    load_registries(registries)
    register_scheduling_types(registries)
    register_interaction_types(registries)
    register_child_types(registries)
    return registries


def _child() -> Graph:
    return B.graph([B.node("Q", type="t.asker", asks=[])], [B.reply("Q")], "child", entries=["Q"])


def _parent(graph_id: str) -> Graph:
    return B.graph(
        [B.node("N", type="t.nest", graph=_child().model_dump(mode="json"))],
        [B.reply("N")],
        graph_id,
        entries=["N"],
    )


@dataclass
class _Scoper:
    """``project_id`` → 출처(``sources``), ``blocked``는 오류 본문, ``boom``은 예외."""

    sources: Mapping[str, Any]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def scope_run(self, graph: Graph, services: Services, *, project_id: str | None) -> None:
        return None

    def run_definitions(self, project_id: str, graph_id: str) -> Any:
        self.calls.append((project_id, graph_id))
        if project_id == "blocked":
            return ErrorInfo(
                code=ErrorCodes.PROJECT_NOT_IMPORTED,
                message="가져오지 않은 구성",
                details={"project_id": project_id, "kind": "graph", "id": graph_id},
            )
        if project_id == "boom":
            raise RuntimeError("고장")
        return self.sources.get(project_id)


@dataclass
class _Preparer:
    """준비 때 본 서비스 ``RUN_DEFINITIONS``(출처 이름)를 기록한다."""

    seen: list[tuple[str, str | None]] = field(default_factory=list)

    def check(
        self, graph: Graph, engine_issues: Sequence[Issue], services: Services, *, strict: bool
    ) -> list[Issue]:
        return []

    def prepare(self, graph: Graph, services: Services) -> RunPreparation:
        source = services.get(RUN_DEFINITIONS)
        env = services.get(ENV_KEY)
        self.seen.append((graph.id, getattr(source, "name", None)))
        return RunPreparation(run_context={"env": env or ""})


class _Provider:
    """노드 서비스 공급자: 실행 환경의 ``definitions``(출처 이름)를 서비스로 싣는다."""

    def services(self, env: RunEnvironment) -> Mapping[ServiceKey[Any], Any]:
        return {ENV_KEY: getattr(env.definitions, "name", "") or ""}


def _module(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


@contextmanager
def _client(tmp_path: Path, library: Spy, *extra: Module) -> Iterator[TestClient]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    modules = [module, _module("t-defs", DEFINITIONS_LOOKUP, library), *extra]
    assembly = assemble(modules, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _finish(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    created = client.post(f"{API}/runs", json=body)
    assert created.status_code == 202, created.text
    run_id = str(created.json()["id"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()
        if snap["run"]["status"] in TERMINAL and all(
            c["status"] in TERMINAL for c in snap["children"]
        ):
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _started(client: TestClient, run_id: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
    payload: dict[str, Any] = next(e for e in events if e["type"] == "run.started")["payload"]
    return payload


def _setup() -> tuple[Spy, Spy]:
    library, project = Spy("library"), Spy("project")
    library.store.create("graph", _parent("shared").model_dump(mode="json"))
    library.store.create("graph", _parent("library-only").model_dump(mode="json"))
    project.store.create("graph", _parent("shared").model_dump(mode="json"))
    project.store.create("graph", _parent("project-only").model_dump(mode="json"))
    library.calls.clear()
    project.calls.clear()
    return library, project


def _grab(found: list[Any]) -> Module:
    """``runs.starter``(실행 서비스)를 꺼내 두는 모듈."""

    def build(ctx: ModuleContext) -> ModuleParts:
        found.append(ctx.port(RUNS_STARTER))
        return ModuleParts()

    return fake_module("t-grab", kind="testing", requires=[RUNS_STARTER], on_build=build)


def _assembly(
    tmp_path: Path, library: Spy, scoper: object, preparer: _Preparer, *extra: Module
) -> Any:
    return _client(
        tmp_path,
        library,
        _module("t-scope", RUN_SCOPES, scoper),
        _module("t-prep", RUN_PREPARERS, preparer),
        _module("t-svc", RUN_SERVICES, _Provider()),
        *extra,
    )


def test_scoped_source_serves_graph_services_and_child_runs(tmp_path: Path) -> None:
    library, project = _setup()
    scoper, preparer = _Scoper({"p1": project}), _Preparer()
    assert isinstance(scoper, RunScoper)
    assert isinstance(scoper, RunDefinitionsScoper)
    with _assembly(tmp_path, library, scoper, preparer) as client:
        snap = _finish(client, {"graph_id": "project-only", "project_id": "p1"})
        assert snap["run"]["status"] == "completed"
        assert scoper.calls == [("p1", "project-only")]  # 한 번만(자식 Run은 물려받음)
        # 루트·자식 준비 모두 같은 출처를 봤다
        assert preparer.seen == [("project-only", "project"), ("child", "project")]
        assert _started(client, snap["run"]["id"])["env"] == "project"
        [child] = snap["children"]
        assert _started(client, child["id"])["env"] == "project"
        assert ("get", "graph", "project-only") in project.calls
        assert library.calls == []  # 라이브러리는 한 번도 읽지 않았다


def test_scoped_run_does_not_fall_back_to_library(tmp_path: Path) -> None:
    library, project = _setup()
    with _assembly(tmp_path, library, _Scoper({"p1": project}), _Preparer()) as client:
        missing = client.post(f"{API}/runs", json={"graph_id": "library-only", "project_id": "p1"})
        assert missing.status_code == 404, missing.text
        assert missing.json()["error"]["code"] == "not_found"
        assert library.calls == []
        assert client.get(f"{API}/runs").json() == []  # Run을 만들지 않았다


def test_same_id_uses_project_copy_and_versions_from_project(tmp_path: Path) -> None:
    library, project = _setup()
    with _assembly(tmp_path, library, _Scoper({"p1": project}), _Preparer()) as client:
        stored = project.store.get("graph", "shared")
        project.calls.clear()
        body = {"graph_id": "shared", "project_id": "p1", "version_hash": stored.version_hash}
        snap = _finish(client, body)
        assert snap["run"]["graph_version"] == graph_hash(stored.model(Graph))
        assert ("get_version", "graph", "shared") in project.calls
        assert library.calls == []


def test_graph_of_run_reads_from_run_source(tmp_path: Path) -> None:
    library, project = _setup()
    grabbed: list[Any] = []
    scoper = _Scoper({"p1": project})
    with _assembly(tmp_path, library, scoper, _Preparer(), _grab(grabbed)) as client:
        run_id = _finish(client, {"graph_id": "project-only", "project_id": "p1"})["run"]["id"]
        [service] = grabbed
        run = Run.model_validate(client.get(f"{API}/runs/{run_id}").json()["run"])
        project.calls.clear()
        found = service.graph_of_run(run)
        assert found is not None
        assert found.id == "project-only"
        assert project.calls
        assert library.calls == []
        # 출처 공급자가 막으면 None(이어 가기 선택지 없음)
        blocked = run.model_copy(update={"project_id": "blocked"})
        assert service.graph_of_run(blocked) is None


def test_error_info_blocks_without_creating_a_run(tmp_path: Path) -> None:
    library, project = _setup()
    with _assembly(tmp_path, library, _Scoper({"p1": project}), _Preparer()) as client:
        blocked = client.post(f"{API}/runs", json={"graph_id": "shared", "project_id": "blocked"})
        assert blocked.status_code == 422, blocked.text
        error = blocked.json()["error"]
        assert error["code"] == ErrorCodes.PROJECT_NOT_IMPORTED
        assert error["details"]["id"] == "shared"
        assert client.get(f"{API}/runs").json() == []


def test_without_project_or_method_nothing_changes(tmp_path: Path) -> None:
    library, project = _setup()
    scoper, preparer = _Scoper({"p1": project}), _Preparer()
    with _assembly(tmp_path, library, scoper, preparer) as client:
        snap = _finish(client, {"graph_id": "library-only"})  # project_id 없음
        assert scoper.calls == []  # 부르지 않는다
        assert preparer.seen[0] == ("library-only", None)  # RUN_DEFINITIONS 없음
        assert _started(client, snap["run"]["id"])["env"] == ""
        assert project.calls == []
        # 출처를 정하지 않은 project_id(공급자가 None)·고장 난 공급자도 라이브러리
        assert _finish(client, {"graph_id": "library-only", "project_id": "unknown"})
        assert _finish(client, {"graph_id": "library-only", "project_id": "boom"})
        assert preparer.seen[-1] == ("child", None)


def test_scopers_without_method_keep_library(tmp_path: Path) -> None:
    library, _ = _setup()

    class Plain:
        def scope_run(self, graph: Graph, services: Services, *, project_id: str | None) -> None:
            return None

    preparer = _Preparer()
    with _assembly(tmp_path, library, Plain(), preparer) as client:
        snap = _finish(client, {"graph_id": "shared", "project_id": "p1"})
        assert snap["run"]["status"] == "completed"
        assert preparer.seen[0] == ("shared", None)
        assert ("get", "graph", "shared") in library.calls


def test_last_provider_wins(tmp_path: Path) -> None:
    library, project = _setup()
    other = Spy("other")
    other.store.create("graph", _parent("project-only").model_dump(mode="json"))
    preparer = _Preparer()
    with _client(
        tmp_path,
        library,
        _module("t-scope-a", RUN_SCOPES, _Scoper({"p1": project})),
        _module("t-scope-b", RUN_SCOPES, _Scoper({"p1": other})),
        _module("t-prep", RUN_PREPARERS, preparer),
    ) as client:
        _finish(client, {"graph_id": "project-only", "project_id": "p1"})
        assert preparer.seen[0] == ("project-only", "other")
