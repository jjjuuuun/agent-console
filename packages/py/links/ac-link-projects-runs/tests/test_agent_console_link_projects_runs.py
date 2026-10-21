"""link-projects-runs: 실행의 project_id → 프로젝트 층(작업 폴더·설정), 없는 프로젝트, 연동 끄기,
유효 설정 ``?project=``, 단독 실행(design §UX-P.5·§5.2R.6, 5.2R.34).

정의·실행·프로젝트 모듈과 다른 연동은 dev 의존이다(이 패키지는 import하지 않는다). 노드·백엔드는
설치된 entry point(``ac-nodes-core``·``ac-backend-fake``)에서 읽는다. fake 응답 틀 ``$cwd``·
``$model``로 실제 요청(``AgentRequest.cwd``·모델)에 들어간 값을 본다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Graph, Issue, Project
from agent_console_link_definitions_teams import module as definitions_teams
from agent_console_link_projects_runs import (
    MODULE_ID,
    RUN_SCOPES,
    SCOPE_LAYERS,
    ProjectScope,
    module,
)
from agent_console_link_projects_runs.testing import MemoryProjects, memory_projects_module
from agent_console_link_runs_teams import module as runs_teams
from agent_console_mod_definitions import module as definitions
from agent_console_mod_projects import module as projects
from agent_console_mod_runs import RunScoper
from agent_console_mod_runs import module as runs
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_nodes_core import SCOPE_LAYERS as SCOPE_LAYERS_SERVICE
from agent_console_runtime import Registries, Services, load_registries

API = "/api/v1"
TOKEN = "t" * 32
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
RESPONSE = "cwd=$cwd model=$model"


def _write(folder: Path, item_id: str, document: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item_id}.yaml").write_text(json.dumps(document, ensure_ascii=False), "utf-8")


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    _write(
        ws / "agents",
        "a1",
        {
            "id": "a1",
            "name": "응답자",
            "backend": "fake",
            "backend_options": {"default": {"response": RESPONSE}},
        },
    )
    _write(
        ws / "graphs",
        "g1",
        {
            "id": "g1",
            "name": "팀",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": "a1"}},
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
        },
    )
    _write(
        ws / "projects",
        "app",
        {
            "kind": "project",
            "id": "app",
            "name": "App",
            "working_directory": str(tmp_path / "proj"),
            "settings": {"model": "m-proj"},
        },
    )
    return ws


@contextmanager
def _client(tmp_path: Path, *, disabled: tuple[str, ...] = ()) -> Iterator[tuple[TestClient, Any]]:
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=_workspace(tmp_path), state=tmp_path / "state"),
        registries=registries,
    )
    config = ModulesConfig(disabled=list(disabled))
    assembly = assemble(
        [definitions, runs, runs_teams, definitions_teams, projects, module], config, base=base
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _run(client: TestClient, project_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    body: dict[str, Any] = {"graph_id": "g1", "input": {"text": "안녕"}}
    if project_id is not None:
        body["project_id"] = project_id
    created = client.post(f"{API}/runs", json=body)
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()["run"]
        if run["status"] in TERMINAL:
            events: list[dict[str, Any]] = client.get(f"{API}/runs/{run_id}/events").json()
            return run, events
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def _of(events: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == type_]


def _reply(events: list[dict[str, Any]]) -> str:
    [reply] = _of(events, "run.reply")
    return str(reply["payload"]["text"])


def test_project_layer_sets_working_directory_and_settings(tmp_path: Path) -> None:
    proj = str(tmp_path / "proj")
    with _client(tmp_path) as (client, assembly):
        assert assembly.status(MODULE_ID).state == "active"
        run, events = _run(client, "app")
        assert run["status"] == "completed", run
        assert run["project_id"] == "app"
        # fake 실행 요청에 프로젝트 작업 폴더·설정(model)이 들어갔다
        assert _reply(events) == f"cwd={proj} model=m-proj"
        # Run 유효 작업 폴더가 run.started payload cwd로 남는다(로그 프로젝트 묶기 재료)
        [started] = _of(events, "run.started")
        assert started["payload"]["cwd"] == proj
        assert _of(events, "log.warning") == []
        # 프로젝트 없이 돌리면 서버 작업 폴더·에이전트 설정 그대로
        _run_plain, plain = _run(client, None)
        assert _reply(plain) == f"cwd={tmp_path} model="
        assert _of(plain, "run.started")[0]["payload"]["cwd"] == str(tmp_path)


def test_unknown_project_warns_and_runs_without_layer(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _assembly):
        run, events = _run(client, "ghost")
        assert run["status"] == "completed", run
        assert run["project_id"] == "ghost"  # 기록은 그대로(불투명 문자열)
        [warning] = _of(events, "log.warning")
        assert warning["payload"]["details"] == {"code": "project.unknown", "project": "ghost"}
        assert "ghost" in warning["payload"]["message"]
        assert _reply(events) == f"cwd={tmp_path} model="


def test_link_off_keeps_project_id_but_no_layer(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=(MODULE_ID,)) as (client, _assembly):
        run, events = _run(client, "app")
        assert run["project_id"] == "app"
        assert _reply(events) == f"cwd={tmp_path} model="
        listed = client.get(f"{API}/runs", params={"project": "app"}).json()
        assert [r["id"] for r in listed] == [run["id"]]
        # 유효 설정 ?project=는 공급자가 없으니 무시된다
        body = client.get(
            f"{API}/graphs/g1/nodes/a/effective-settings", params={"project": "app"}
        ).json()
        assert body["value"].get("working_directory") is None


def test_projects_module_off_turns_link_off(tmp_path: Path) -> None:
    with _client(tmp_path, disabled=("mod-projects",)) as (client, assembly):
        report = assembly.status(MODULE_ID)
        assert report.state == "unsatisfied"
        assert report.missing == ("projects.lookup",)
        run, events = _run(client, "app")
        assert run["status"] == "completed"
        assert _reply(events) == f"cwd={tmp_path} model="


def test_effective_settings_with_project(tmp_path: Path) -> None:
    proj = str(tmp_path / "proj")
    with _client(tmp_path) as (client, _assembly):
        url = f"{API}/graphs/g1/nodes/a/effective-settings"
        body = client.get(url, params={"project": "app"}).json()
        assert body["value"]["working_directory"] == proj
        assert body["value"]["model"] == "m-proj"
        assert body["provenance"]["/working_directory"] == "project"
        assert body["provenance"]["/model"] == "project"
        ids = [layer["id"] for layer in body["layers"]]
        assert ids.index("project") == ids.index("common") + 1  # 공통 바로 아래
        plain = client.get(url).json()
        assert "project" not in [layer["id"] for layer in plain["layers"]]
        ghost = client.get(url, params={"project": "ghost"}).json()
        assert [w["code"] for w in ghost["warnings"]] == ["project.unknown"]
        draft = client.post(
            f"{API}/graphs/effective-settings",
            params={"project": "app"},
            json={"graph": client.get(f"{API}/graphs/g1").json()["graph"], "node_id": "a"},
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["value"]["working_directory"] == proj
        agent = client.get(f"{API}/agents/a1/effective-settings", params={"project": "app"})
        assert agent.json()["value"]["model"] == "m-proj"


def test_ports_match_consumer_protocols(tmp_path: Path) -> None:
    with _client(tmp_path) as (_, assembly):
        [scoper] = assembly.ports(RUN_SCOPES)
        assert isinstance(scoper, RunScoper)
        [source] = assembly.ports(SCOPE_LAYERS)
        assert hasattr(source, "scope_layers")


# ---------------------------------------------------------------- 단위(서버 없이)


def _scope(**options: Any) -> ProjectScope:
    projects_ = MemoryProjects(
        [
            Project(id="app", name="App", working_directory="/w/app"),
            Project(id="empty", name="빈 프로젝트"),
        ]
    )
    return ProjectScope(lambda: projects_, **options)


def _graph() -> Graph:
    return Graph.model_validate({"id": "g", "name": "g", "nodes": [], "edges": []})


def test_scope_run_puts_layer_into_services_and_keeps_existing() -> None:
    scope = _scope()
    assert scope.scope_run(_graph(), Services(), project_id=None) is None
    first = scope.layers("x")  # 없는 프로젝트
    assert first.layers == () or list(first.layers) == []
    found = scope.scope_run(_graph(), Services(), project_id="app")
    assert found is not None
    [layer] = found.services[SCOPE_LAYERS_SERVICE]
    assert (layer.id, dict(layer.value or {}), layer.source) == (
        "project",
        {"working_directory": "/w/app"},
        "project:app",
    )
    # 다른 공급자가 넣은 범위 층은 앞에 남는다
    other = scope.layers("app").layers[0]
    services = Services({SCOPE_LAYERS_SERVICE: (other,)})
    again = scope.scope_run(_graph(), services, project_id="app")
    assert again is not None
    assert len(again.services[SCOPE_LAYERS_SERVICE]) == 2


def test_scope_layer_options_and_empty_project() -> None:
    scope = _scope(layer_id="proj", layer_label="P", unknown_message="없음: ${project}")
    [layer] = scope.layers("empty").layers
    assert (layer.id, layer.label, layer.value) == ("proj", "P", None)  # 비어 있으면 값 None
    [issue] = scope.layers("nope").warnings
    assert isinstance(issue, Issue)
    assert (issue.code, issue.message) == ("project.unknown", "없음: nope")
    unknown = scope.scope_run(_graph(), Services(), project_id="nope")
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


def test_memory_projects_module_provides_lookup(tmp_path: Path) -> None:
    base = BaseServices(paths=Paths(base_dir=tmp_path, workspace=tmp_path, state=tmp_path))
    assembly = assemble(
        [memory_projects_module([Project(id="app", name="App")]), module], base=base
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
