"""5.7R.33t1: 맡는 범위 없는 프로젝트 실행 막기(design K33-10·§PI.10 끄기 표).

프로젝트 기능(선택 포트 ``projects.lookup``)이 있는데 ``project_id``를 맡는 ``runs.scopes`` 공급자
(``RunProjectScoper.accepts_project``)가 없으면 409 ``feature_unavailable``로 막고 Run을 만들지
않는다. 프로젝트 기능이 없거나 ``project_id``가 없으면 단독 실행 그대로. 실행 모듈은 프로젝트를
모른다는 것을 테스트 공급자·불투명 ``project_id``로 보인다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    ErrorCodes,
    Graph,
    Issue,
    Run,
)
from agent_console_mod_runs import (
    DEFINITIONS_LOOKUP,
    PROJECTS_LOOKUP,
    RUN_SCOPES,
    RUNS_STARTER,
    SERVER_WARNINGS,
    UNSCOPED_PROJECT_PORT,
    RunPreflightError,
    RunProjectScoper,
    RunService,
    UnscopedProjectRuns,
    module,
    unscoped_project_policy,
)
from agent_console_modkit import (
    BaseServices,
    Module,
    ModuleContext,
    ModuleParts,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, Services, load_registries
from agent_console_runtime.testing import BUILDERS as B
from agent_console_runtime.testing import make_registries
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore

API = "/api/v1"
TOKEN = "t" * 32


@dataclass
class _Projects:
    """``projects.lookup`` 흉내(등록 프로젝트 목록만)."""

    ids: tuple[str, ...] = ("p1",)

    def list_projects(self) -> list[Any]:
        return [type("P", (), {"id": i, "archived": False})() for i in self.ids]


@dataclass
class _ProjectScoper:
    """프로젝트 범위를 맡는 공급자(``accepts`` = 맡는 id, ``boom`` = 예외)."""

    accepts: frozenset[str] = frozenset({"p1"})
    boom: bool = False
    calls: list[str] = field(default_factory=list)

    def scope_run(self, graph: Graph, services: Services, *, project_id: str | None) -> None:
        return None

    def accepts_project(self, project_id: str) -> bool:
        self.calls.append(project_id)
        if self.boom:
            raise RuntimeError("고장")
        return project_id in self.accepts


class _PlainScoper:
    """``accepts_project``가 없는 범위 공급자(예: 메모리·위키 연동) — 프로젝트를 맡지 않는다."""

    def scope_run(self, graph: Graph, services: Services, *, project_id: str | None) -> None:
        return None


def _registries() -> Registries:
    registries = make_registries()
    load_registries(registries)
    return registries


def _library() -> InMemoryDefinitionStore:
    store = InMemoryDefinitionStore(DEFAULT_KINDS)
    graph = B.graph([B.node("A")], [B.reply("A")], "flow", entries=["A"])
    store.create("graph", graph.model_dump(mode="json"))
    return store


def _module(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


def _grab(found: list[Any]) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        found.append(ctx.port(RUNS_STARTER))
        return ModuleParts()

    return fake_module("t-grab", kind="testing", requires=[RUNS_STARTER], on_build=build)


@contextmanager
def _client(
    tmp_path: Path, *extra: Module, options: dict[str, Any] | None = None
) -> Iterator[tuple[TestClient, Any]]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=_registries(),
    )
    modules = [module, _module("t-defs", DEFINITIONS_LOOKUP, _library()), *extra]
    config = ModulesConfig(options={"mod-runs": options} if options else {})
    assembly = assemble(modules, config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _run(client: TestClient, project_id: str | None = None) -> Any:
    body: dict[str, Any] = {"graph_id": "flow", "input": {"text": "hi"}}
    if project_id is not None:
        body["project_id"] = project_id
    return client.post(f"{API}/runs", json=body)


def _warnings(assembly: Any) -> list[Issue]:
    found: list[Issue] = []
    for source in assembly.ports(SERVER_WARNINGS):
        found.extend(source())
    return [w for w in found if w.code == ErrorCodes.FEATURE_UNAVAILABLE]


def test_projects_on_without_scope_blocks_project_runs(tmp_path: Path) -> None:
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    plain = _module("t-plain", RUN_SCOPES, _PlainScoper())
    with _client(tmp_path, projects, plain) as (client, assembly):
        blocked = _run(client, "p1")
        assert blocked.status_code == 409, blocked.text
        error = blocked.json()["error"]
        assert error["code"] == ErrorCodes.FEATURE_UNAVAILABLE
        assert error["details"] == {
            "module": "mod-runs",
            "port": UNSCOPED_PROJECT_PORT,
            "project_id": "p1",
        }
        assert error["message"] == UnscopedProjectRuns().message
        # 등록하지 않은 id도 같은 이유로 막힌다(범위를 맡는 쪽이 없으니 폴더를 정할 수 없다)
        assert _run(client, "ghost").status_code == 409
        assert client.get(f"{API}/runs").json() == []  # Run을 만들지 않았다
        # 프로젝트 없는 실행은 그대로
        assert _run(client).status_code == 202
        [warning] = _warnings(assembly)
        assert warning.severity == "warning"
        assert warning.details == {"module": "mod-runs", "port": UNSCOPED_PROJECT_PORT}


def test_projects_off_keeps_opaque_project_id_runs(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, assembly):
        created = _run(client, "p1")
        assert created.status_code == 202, created.text
        assert created.json()["project_id"] == "p1"
        assert _warnings(assembly) == []


def test_accepting_scoper_lets_project_runs_through(tmp_path: Path) -> None:
    scoper = _ProjectScoper()
    assert isinstance(scoper, RunProjectScoper)
    assert not isinstance(_PlainScoper(), RunProjectScoper)
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    with _client(tmp_path, projects, _module("t-scope", RUN_SCOPES, scoper)) as (client, assembly):
        assert _run(client, "p1").status_code == 202
        assert scoper.calls == ["p1"]
        # 맡지 않는 id는 막힌다(다른 공급자가 맡을 수도 있어 공급자별로 묻는다)
        assert _run(client, "other").status_code == 409
        assert _warnings(assembly) == []


def test_failing_scoper_counts_as_not_accepting(tmp_path: Path) -> None:
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    scope = _module("t-scope", RUN_SCOPES, _ProjectScoper(boom=True))
    with _client(tmp_path, projects, scope) as (client, _assembly):
        assert _run(client, "p1").status_code == 409


def test_policy_allow_runs_without_scope(tmp_path: Path) -> None:
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    options = {"unscoped_project_runs": {"policy": "allow"}}
    with _client(tmp_path, projects, options=options) as (client, assembly):
        assert _run(client, "p1").status_code == 202
        assert _warnings(assembly) == []


def test_message_is_settings_data(tmp_path: Path) -> None:
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    options = {"unscoped_project_runs": {"message": "연동을 켜세요"}}
    with _client(tmp_path, projects, options=options) as (client, assembly):
        assert _run(client, "p1").json()["error"]["message"] == "연동을 켜세요"
        assert [w.message for w in _warnings(assembly)] == ["연동을 켜세요"]


def test_validation_and_graph_reads_follow_the_gate(tmp_path: Path) -> None:
    grabbed: list[Any] = []
    projects = _module("t-projects", PROJECTS_LOOKUP, _Projects())
    with _client(tmp_path, projects, _grab(grabbed)) as (client, _assembly):
        [service] = grabbed
        assert isinstance(service, RunService)
        for call in (
            lambda: service.check_project("flow", "p1"),
            lambda: service.load_graph("flow", project_id="p1"),
            lambda: service.definitions_for("p1", "flow"),
        ):
            with pytest.raises(RunPreflightError) as caught:
                call()
            assert caught.value.error.code == ErrorCodes.FEATURE_UNAVAILABLE
        assert service.find_graph("flow", project_id="p1") is None
        assert service.load_graph("flow").id == "flow"  # 프로젝트 없는 읽기는 그대로
        # 지난 Run의 그래프 보기는 막지 않는다(기록 보기)
        created = _run(client)
        run = Run.model_validate(created.json()).model_copy(update={"project_id": "p1"})
        assert service.graph_of_run(run) is not None


def test_policy_function_alone() -> None:
    on = unscoped_project_policy(UnscopedProjectRuns(), projects_on=lambda: True, module_id="m")
    error = on("x")
    assert error is not None
    assert error.details == {"module": "m", "port": "runs.scopes", "project_id": "x"}
    assert unscoped_project_policy(UnscopedProjectRuns(), projects_on=lambda: False)("x") is None
