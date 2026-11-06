"""link-projects-runs: 실행의 project_id → 프로젝트 층·정의 출처·사전 점검(design §PI.4.5·§PI.5,
5.2R.34·5.7R.33g).

정의·실행·프로젝트 모듈과 다른 연동은 dev 의존이다(이 패키지는 import하지 않는다). 노드·백엔드는
설치된 entry point(``ac-nodes-core``·``ac-backend-fake-agent``)에서 읽는다. fake 응답 틀 ``$cwd``·
``$model``로 실제 요청(``AgentRequest.cwd``·모델)에 들어간 값을 본다. 기록 공간
(``records.spaces``)은 실제 ``link-projects-records``다(폴더의 ``records.sqlite3``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Graph,
    Issue,
    Project,
    ProjectView,
)
from agent_console_link_definitions_teams import module as definitions_teams
from agent_console_link_projects_records import module as projects_records
from agent_console_link_projects_runs import (
    MODULE_ID,
    RUN_SCOPES,
    SCOPE_LAYERS,
    ProjectScope,
    module,
    not_imported_error,
    view_error,
)
from agent_console_link_projects_runs.testing import MemoryProjects, memory_projects_module
from agent_console_link_runs_teams import module as runs_teams
from agent_console_mod_definitions import module as definitions
from agent_console_mod_projects import DEFINITIONS_SPACES, ProjectsModule
from agent_console_mod_runs import RunDefinitionsScoper, RunScoper
from agent_console_mod_runs import module as runs
from agent_console_modkit import (
    BaseServices,
    Module,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core import SCOPE_LAYERS as SCOPE_LAYERS_SERVICE
from agent_console_runtime import Registries, Services, load_registries
from agent_console_store import InMemoryVersionRepository

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
RESPONSE = "cwd=$cwd model=$model"
CFG = ".agent-console"


def _write(folder: Path, item_id: str, document: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item_id}.yaml").write_text(json.dumps(document, ensure_ascii=False), "utf-8")


def _agent(agent_id: str, response: str = RESPONSE, **extra: Any) -> dict[str, Any]:
    return {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {"default": {"response": response}},
        **extra,
    }


def _graph(graph_id: str, agent_ref: str) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _team_graph(graph_id: str, child: str) -> dict[str, Any]:
    """you → 중첩 팀 노드 T(자식 팀 구성 ``child``) → 답변."""
    data = _graph(graph_id, "unused")
    data["nodes"][1] = {"id": "T", "type": "team", "label": "중첩", "config": {"team_ref": child}}
    for edge in data["edges"]:
        for side in ("source", "target"):
            if edge[side]["node"] == "a":
                edge[side]["node"] = "T"
    return data


def _library(tmp_path: Path) -> Path:
    """앱 workspace(라이브러리): a1은 다른 응답, lib-only 그래프·에이전트."""
    ws = tmp_path / "ws"
    _write(ws / "agents", "a1", _agent("a1", "라이브러리"))
    _write(ws / "agents", "lib-agent", _agent("lib-agent", "라이브러리"))
    _write(ws / "graphs", "g1", _graph("g1", "a1"))
    _write(ws / "graphs", "lib-only", _graph("lib-only", "a1"))
    return ws


def _project_folder(tmp_path: Path, name: str = "proj") -> Path:
    """프로젝트 폴더와 그 공간의 사본(같은 id a1이 라이브러리와 다르다)."""
    folder = tmp_path / name
    space = folder / CFG
    _write(space / "agents", "a1", _agent("a1", RESPONSE, model="m-proj"))
    _write(space / "graphs", "g1", _graph("g1", "a1"))
    _write(space / "graphs", "uses-lib", _graph("uses-lib", "lib-agent"))
    _write(space / "graphs", "child", _graph("child", "a1"))
    _write(space / "graphs", "parent", _team_graph("parent", "child"))
    return folder


@contextmanager
def _client(
    tmp_path: Path,
    *,
    disabled: tuple[str, ...] = (),
    records: bool = True,
    options: dict[str, Any] | None = None,
) -> Iterator[tuple[TestClient, Any]]:
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=_library(tmp_path), state=tmp_path / "state"),
        registries=registries,
    )
    config = ModulesConfig(disabled=list(disabled), options=options or {})
    projects = ProjectsModule(versions=lambda _pid, _root: InMemoryVersionRepository())
    mods: list[Module] = [definitions, runs, runs_teams, definitions_teams, projects, module]
    if records:  # 실제 기록 공간 연동(폴더의 records.sqlite3)
        mods.append(projects_records)
    assembly = assemble(mods, config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _register(client: TestClient, folder: Path, project_id: str = "app") -> dict[str, Any]:
    created = client.post(f"{API}/projects", json={"folder": str(folder), "id": project_id})
    assert created.status_code == 201, created.text
    view: dict[str, Any] = created.json()
    return view


def _start(client: TestClient, graph_id: str, project_id: str | None, **extra: Any) -> Any:
    body: dict[str, Any] = {"graph_id": graph_id, "input": {"text": "안녕"}, **extra}
    if project_id is not None:
        body["project_id"] = project_id
    return client.post(f"{API}/runs", json=body)


def _wait(client: TestClient, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()["run"]
        if run["status"] in TERMINAL:
            events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
            return run, events
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _run(
    client: TestClient, graph_id: str, project_id: str | None, **extra: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    created = _start(client, graph_id, project_id, **extra)
    assert created.status_code == 202, created.text
    return _wait(client, created.json()["id"])


def _of(events: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == type_]


def _reply(events: list[dict[str, Any]]) -> str:
    [reply] = _of(events, "run.reply")
    return str(reply["payload"]["text"])


def _error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    error: dict[str, Any] = response.json()["error"]
    assert error["code"] == code, error
    return error


def _no_runs(client: TestClient, project_id: str | None = None) -> None:
    """앱 DB와 (등록된 프로젝트면) 그 프로젝트 기록 DB 모두 Run 0개."""
    assert client.get(f"{API}/runs").json() == []
    if project_id is not None:
        listed = client.get(f"{API}/runs", params={"project": project_id})
        assert listed.status_code != 200 or listed.json() == [], listed.text


# ---------------------------------------------------------------- 서버(조립)


def test_project_run_uses_project_copy_and_folder(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, assembly):
        assert assembly.status(MODULE_ID).state == "active"
        _register(client, folder)
        run, events = _run(client, "g1", "app")
        assert run["status"] == "completed", run
        assert run["project_id"] == "app"
        # 라이브러리 a1("라이브러리")이 아니라 프로젝트 사본 a1, 작업 폴더 = 프로젝트 폴더
        assert _reply(events) == f"cwd={folder} model=m-proj"
        [started] = _of(events, "run.started")
        assert started["payload"]["cwd"] == str(folder)
        assert _of(events, "log.warning") == []


def test_child_run_uses_same_space(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        run, events = _run(client, "parent", "app")
        assert run["status"] == "completed", run
        # 자식 팀 구성 child와 그 에이전트 a1 모두 프로젝트 공간에서(라이브러리에는 child가 없다)
        assert _reply(events) == f"cwd={folder} model=m-proj"


def test_required_project_on_by_default(tmp_path: Path) -> None:
    """0.3.0부터 기본 참(5.7R.33v 후속 ⑤): 설정 없이도 프로젝트 없는 실행을 막는다."""
    for options in (None, {MODULE_ID: {"require_project": True}}):
        with _client(tmp_path, options=options) as (client, _assembly):
            error = _error(_start(client, "g1", None), 422, "project.required")
            assert error["fix"]["actions"][0]["target"]["role"] == "projects"
            _no_runs(client)


def test_required_project_can_be_turned_off(tmp_path: Path) -> None:
    options = {MODULE_ID: {"require_project": False}}
    with _client(tmp_path, options=options) as (client, _assembly):
        run, events = _run(client, "g1", None)
        assert run["status"] == "completed"
        assert _reply(events) == "라이브러리"  # 프로젝트 없으면 라이브러리·서버 작업 폴더


def test_unknown_project(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _assembly):
        error = _error(_start(client, "g1", "ghost"), 404, "project.not_found")
        assert error["details"] == {"project_id": "ghost"}
        _no_runs(client)


def test_not_imported_reports_in_library(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        lib = _error(_start(client, "lib-only", "app"), 422, "project.not_imported")
        assert lib["details"] == {
            "project_id": "app",
            "kind": "graph",
            "id": "lib-only",
            "in_library": True,
        }
        nowhere = _error(_start(client, "ghost", "app"), 422, "project.not_imported")
        assert nowhere["details"]["in_library"] is False
        _no_runs(client, "app")


def test_reference_only_in_library_does_not_fall_back(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        created = _start(client, "uses-lib", "app")
        if created.status_code == 202:
            run, events = _wait(client, created.json()["id"])
            assert run["status"] == "failed", run
            assert not any("라이브러리" in str(e["payload"]) for e in _of(events, "run.reply"))
        else:  # 검사(팀 규칙)가 먼저 막는다
            assert created.status_code == 422, created.text


def test_folder_missing_and_manifest_invalid(tmp_path: Path) -> None:
    gone = _project_folder(tmp_path, "gone")
    broken = _project_folder(tmp_path, "broken")
    with _client(tmp_path) as (client, _assembly):
        _register(client, gone, "gone")
        _register(client, broken, "broken")
        shutil.rmtree(gone)
        error = _error(_start(client, "g1", "gone"), 409, "project.folder_missing")
        assert error["details"]["project_id"] == "gone"
        assert error["details"]["status"] == "folder_missing"
        (broken / CFG / "project.yaml").write_text("id: [깨짐", "utf-8")
        error = _error(_start(client, "g1", "broken"), 409, "project.manifest_invalid")
        assert error["details"]["status"] == "manifest_invalid"
        _no_runs(client)


def test_records_unavailable_blocks_start(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        (folder / CFG / "records.sqlite3").write_bytes(b"not a database" * 64)
        error = _error(_start(client, "g1", "app"), 409, "project.records_unavailable")
        assert error["details"]["project_id"] == "app"
        assert error["details"]["reason"] == "corrupt"
        _no_runs(client, "app")


def test_records_link_disabled_blocks_start(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path, records=False) as (client, _assembly):  # records.spaces 없음
        _register(client, folder)
        error = _error(_start(client, "g1", "app"), 409, "project.records_unavailable")
        assert error["details"]["reason"] == "link_disabled"
        _no_runs(client, "app")


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="권한 비트로 읽기 전용 폴더를 만들 수 없다",
)
def test_readonly_folder_blocks_start(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        config = folder / CFG
        modes = {p: p.stat().st_mode for p in [config, *config.rglob("*")] if p.is_dir()}
        try:
            for p in modes:
                p.chmod(0o555)
            if os.access(config, os.W_OK):
                pytest.skip("이 파일 시스템은 권한 비트를 따르지 않는다")
            error = _error(_start(client, "g1", "app"), 409, "project.records_unavailable")
            assert error["details"]["reason"] == "readonly"
            _no_runs(client, "app")
        finally:
            for p, mode in modes.items():
                p.chmod(mode)


def test_outside_folder_reports_paths_and_layers(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    outside = str(tmp_path / "elsewhere")
    _write(
        folder / CFG / "agents",
        "wander",
        _agent(
            "wander",
            working_directory=outside,
            limits={"directories": ["{workspace}/src", "../sibling"]},
        ),
    )
    _write(folder / CFG / "graphs", "wander", _graph("wander", "wander"))
    _write(
        folder / CFG / "agents",
        "inside",
        _agent("inside", working_directory="sub", limits={"directories": ["{workspace}"]}),
    )
    _write(folder / CFG / "graphs", "inside", _graph("inside", "inside"))
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        error = _error(_start(client, "wander", "app"), 422, "project.outside_folder")
        details = error["details"]
        assert (details["project_id"], details["folder"]) == ("app", str(folder))
        found = {(p["pointer"], p["value"], p["layer"], p["node_id"]) for p in details["paths"]}
        assert found == {
            ("/working_directory", outside, "에이전트", "a"),
            ("/limits/directories/1", "../sibling", "에이전트", "a"),
        }
        resolved = {p["value"]: p["resolved"] for p in details["paths"]}
        assert resolved["../sibling"] == str(tmp_path / "sibling")
        # 폴더 안 상대 경로·{workspace} 틀은 통과
        run, _events = _run(client, "inside", "app")
        assert run["status"] == "completed", run
        listed = client.get(f"{API}/runs", params={"project": "app"}).json()
        assert [r["graph_id"] for r in listed] == ["inside"]


def test_pinned_version_runs_from_space(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, assembly):
        _register(client, folder)
        [spaces] = assembly.ports(DEFINITIONS_SPACES)
        store = spaces.open("app")
        store.create("agent", _agent("old", "옛 응답"))
        first = store.create("graph", _graph("pin", "old"))
        store.save("graph", _graph("pin", "a1"), expected_version=first.version_hash)
        run, events = _run(client, "pin", "app", version_hash=first.version_hash)
        assert run["status"] == "completed", run
        assert run["graph_version"] == first.version_hash
        assert _reply(events) == "옛 응답"
        _run_now, now = _run(client, "pin", "app")
        assert _reply(now) == f"cwd={folder} model=m-proj"


def test_link_off_keeps_project_id_but_no_layer(tmp_path: Path) -> None:
    # 기록 연동도 끈다: 켜져 있으면 실행 모듈이 등록되지 않은 프로젝트를 404로 막는다(33y2)
    with _client(tmp_path, disabled=(MODULE_ID,), records=False) as (client, _assembly):
        run, events = _run(client, "g1", "app")
        assert run["project_id"] == "app"
        assert _reply(events) == "라이브러리"  # 연동이 꺼지면 정의 출처·층 없이
        listed = client.get(f"{API}/runs", params={"project": "app"}).json()
        assert [r["id"] for r in listed] == [run["id"]]
        body = client.get(
            f"{API}/graphs/g1/nodes/a/effective-settings", params={"project": "app"}
        ).json()
        assert body["value"].get("working_directory") is None


def test_projects_module_off_turns_link_off(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("mod-projects",)) as (client, assembly):
        report = assembly.status(MODULE_ID)
        assert report.state == "unsatisfied"
        assert report.missing == ("projects.lookup",)
        run, events = _run(client, "g1", None)  # 단독 mod-runs: 프로젝트 없이 그대로
        assert run["status"] == "completed"
        assert _reply(events) == "라이브러리"


def test_effective_settings_with_project(tmp_path: Path) -> None:
    folder = _project_folder(tmp_path)
    with _client(tmp_path) as (client, _assembly):
        _register(client, folder)
        url = f"{API}/graphs/g1/nodes/a/effective-settings"
        body = client.get(url, params={"project": "app"}).json()
        assert body["value"]["working_directory"] == str(folder)
        assert body["provenance"]["/working_directory"] == "project"
        ids = [layer["id"] for layer in body["layers"]]
        assert ids.index("project") == ids.index("common") + 1  # 공통 바로 아래
        plain = client.get(url).json()
        assert "project" not in [layer["id"] for layer in plain["layers"]]
        ghost = client.get(url, params={"project": "ghost"}).json()
        assert [w["code"] for w in ghost["warnings"]] == ["project.unknown"]


def test_ports_match_consumer_protocols(tmp_path: Path) -> None:
    with _client(tmp_path) as (_, assembly):
        [scoper] = assembly.ports(RUN_SCOPES)
        assert isinstance(scoper, RunScoper)
        assert isinstance(scoper, RunDefinitionsScoper)
        [source] = assembly.ports(SCOPE_LAYERS)
        assert hasattr(source, "scope_layers")


# ---------------------------------------------------------------- 단위(서버 없이)


def _scope(**options: Any) -> ProjectScope:
    projects_ = MemoryProjects(
        [
            Project(id="app", name="App", folder="/w/app"),
            Project(id="empty", name="빈 프로젝트", folder=None),
        ]
    )
    return ProjectScope(lambda: projects_, **options)


def _graph_model() -> Graph:
    return Graph.model_validate({"id": "g", "name": "g", "nodes": [], "edges": []})


def test_scope_run_puts_layer_into_services_and_keeps_existing() -> None:
    scope = _scope()
    assert scope.scope_run(_graph_model(), Services(), project_id=None) is None
    found = scope.scope_run(_graph_model(), Services(), project_id="app")
    assert found is not None
    assert list(found.errors) == []
    [layer] = found.services[SCOPE_LAYERS_SERVICE]
    assert (layer.id, dict(layer.value or {}), layer.source) == (
        "project",
        {"working_directory": "/w/app"},
        "project:app",
    )
    other = scope.layers("app").layers[0]
    services = Services({SCOPE_LAYERS_SERVICE: (other,)})
    again = scope.scope_run(_graph_model(), services, project_id="app")
    assert again is not None
    assert len(again.services[SCOPE_LAYERS_SERVICE]) == 2


def test_scope_run_requires_project_when_asked() -> None:
    found = _scope(require_project=True).scope_run(_graph_model(), Services(), project_id=None)
    assert found is not None
    assert [e.code for e in found.errors] == ["project.required"]
    # 프로젝트 읽기가 없으면(제공 모듈 없음) 요구하지 않는다
    none = ProjectScope(lambda: None, require_project=True)
    assert none.scope_run(_graph_model(), Services(), project_id=None) is None


def test_scope_layer_options_and_empty_project() -> None:
    scope = _scope(layer_id="proj", layer_label="P", unknown_message="없음: ${project}")
    [layer] = scope.layers("empty").layers
    assert (layer.id, layer.label, layer.value) == ("proj", "P", None)
    [issue] = scope.layers("nope").warnings
    assert isinstance(issue, Issue)
    assert (issue.code, issue.message) == ("project.unknown", "없음: nope")
    unknown = scope.scope_run(_graph_model(), Services(), project_id="nope")
    assert unknown is not None
    assert unknown.services == {}
    assert [w.code for w in unknown.warnings] == ["project.unknown"]


def test_lookup_missing_or_broken_is_ignored() -> None:
    assert ProjectScope(lambda: None).layers("app").warnings == ()

    class Broken:
        def get_project(self, project_id: str) -> Project | None:
            raise RuntimeError("고장")

    [issue] = ProjectScope(lambda: Broken()).layers("app").warnings
    assert issue.code == "project.unknown"


class _Store:
    def __init__(self, items: set[tuple[str, str]], error: Exception | None = None) -> None:
        self.items = items
        self.error = error

    def get(self, kind: str, item_id: str) -> Any:
        if self.error is not None:
            raise self.error
        if (kind, item_id) not in self.items:
            raise LookupError(item_id)
        return object()


class _Spaces:
    def __init__(self, stores: dict[str, Any]) -> None:
        self.stores = stores

    def open(self, project_id: str) -> Any:
        found = self.stores[project_id]
        if isinstance(found, Exception):
            raise found
        return found


class _CodedError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def test_run_definitions_unit() -> None:
    space = _Store({("graph", "g")})
    spaces = _Spaces(
        {
            "app": space,
            "empty": _CodedError("project.folder_missing"),
        }
    )
    library = _Store({("graph", "lib")})
    scope = _scope(spaces=lambda: spaces, library=lambda: library)
    assert scope.run_definitions("app", "g") is space
    lib = scope.run_definitions("app", "lib")
    assert (lib.code, lib.details["in_library"]) == ("project.not_imported", True)
    assert scope.run_definitions("app", "x").details["in_library"] is False
    assert scope.run_definitions("ghost", "g").code == "project.not_found"
    gone = scope.run_definitions("empty", "g")
    assert (gone.code, gone.details["status"]) == ("project.folder_missing", "folder_missing")
    broken = _Spaces({"app": _Store(set(), _CodedError("project.manifest_invalid"))})
    bad = _scope(spaces=lambda: broken).run_definitions("app", "g")
    assert bad.code == "project.manifest_invalid"
    # 공간 포트가 없으면 출처를 정하지 않는다
    assert _scope().run_definitions("app", "g") is None


def test_view_error_order() -> None:
    project = Project(id="app", name="App", folder="/w/app")
    ok = ProjectView(project=project, status="ready")
    assert view_error(ok) is None
    for status, code in (
        ("manifest_invalid", "project.manifest_invalid"),
        ("no_access", "project.folder_missing"),
        ("folder_conflict", "project.folder_missing"),
    ):
        err = view_error(ok.model_copy(update={"status": status, "records_writable": False}))
        assert err is not None
        assert (err.code, err.details["status"]) == (code, status)
    issue = Issue(
        severity="info",
        code="project.records_unavailable",
        message="x",
        details={"project_id": "app", "reason": "newer"},
    )
    err = view_error(ok.model_copy(update={"records_writable": False, "records_issue": issue}))
    assert err is not None
    assert err.details == {"project_id": "app", "reason": "newer"}
    readonly = view_error(ok.model_copy(update={"config_writable": False}))
    assert readonly is not None
    assert readonly.details["reason"] == "readonly"
    assert not_imported_error("app", "graph", "g", in_library=False).fix is None


def test_memory_projects_module_provides_lookup(tmp_path: Path) -> None:
    base = BaseServices(paths=Paths(base_dir=tmp_path, workspace=tmp_path, state=tmp_path))
    assembly = assemble(
        [memory_projects_module([Project(id="app", name="App", folder=None)]), module], base=base
    )
    [scope] = assembly.ports(SCOPE_LAYERS)
    assert [layer.id for layer in scope.scope_layers("app").layers] == ["project"]


def test_module_check_runs_without_with() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_projects_runs", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert MODULE_ID in done.stdout
