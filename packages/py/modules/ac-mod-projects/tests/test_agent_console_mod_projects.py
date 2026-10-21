"""mod-projects: CRUD·옮기기·삭제 계획·범위 검사 포트·선택 포트가 없을 때(design §UX-P.5).

참조 추출은 테스트용 규칙(문서의 ``uses: [[kind, id], ...]``)을 ``definitions.references``로 준다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, KnownIssueCodes, Project
from agent_console_mod_projects import (
    CODE_DEFINITIONS_UNAVAILABLE,
    DEFINITION_CHECKS,
    DEFINITIONS_STORE,
    PROJECTS_LOOKUP,
    DefinitionSnapshot,
    ProjectLookup,
    ProjectRepository,
    ProjectService,
    module,
    project_kind,
)
from agent_console_mod_projects.testing import (
    Saved,
    local_definitions_module,
    references_module,
)
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import RecordingDatabase
from agent_console_store import FileDefinitionStore, InMemoryVersionRepository

TOKEN = "t" * 32
API = "/api/v1"


def uses(kind: str, document: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """테스트 참조 규칙: 문서 ``uses``의 ``[종류, id]`` 목록(종류 이름은 보지 않는다)."""
    return [(k, i) for k, i in document.get("uses", [])]


def _assembly(tmp_path: Path, *, definitions: bool = True, refs: bool = True) -> Assembly:
    extra: list[Any] = []
    if definitions:
        extra.append(local_definitions_module(workspace=tmp_path / "ws"))
    if refs:
        extra.append(references_module(uses))
    config = ModulesConfig(options={"mod-projects": {"snapshot_ttl_seconds": 0}})
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, *extra], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _store(assembly: Assembly) -> Any:
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    return store


def _agent(agent_id: str, project: str | None = None, **extra: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {"id": agent_id, "name": agent_id, "backend": "fake", **extra}
    if project is not None:
        doc["project"] = project
    return doc


def _resource(res_id: str, project: str | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {"id": res_id, "name": res_id, "type": "instructions", "config": {}}
    if project is not None:
        doc["project"] = project
    return doc


# ---------------------------------------------------------------- CRUD


def test_crud_round_trip_stores_projects_yaml(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        assert client.get(f"{API}/projects").json() == []
        created = client.post(
            f"{API}/projects",
            json={"id": "app", "name": "앱", "working_directory": "/work/app"},
        )
        assert created.status_code == 201, created.text
        assert created.json() == {"id": "app", "name": "앱", "working_directory": "/work/app"}
        etag = created.headers["etag"]
        assert (tmp_path / "ws" / "projects" / "app.yaml").is_file()
        dup = client.post(f"{API}/projects", json={"id": "app", "name": "x"})
        assert dup.status_code == 409
        assert client.get(f"{API}/projects/app").headers["etag"] == etag

        put = client.put(
            f"{API}/projects/app",
            json={"description": "설명", "working_directory": None, "name": None},
            headers={"If-Match": etag},
        )
        assert put.status_code == 200, put.text
        assert put.json() == {"id": "app", "name": "앱", "description": "설명"}
        stale = client.put(f"{API}/projects/app", json={"name": "y"}, headers={"If-Match": etag})
        assert stale.status_code == 412
        assert [p["id"] for p in client.get(f"{API}/projects").json()] == ["app"]

        assert client.get(f"{API}/projects/ghost").status_code == 404
        assert client.put(f"{API}/projects/ghost", json={"name": "g"}).status_code == 404
        assert client.delete(f"{API}/projects/app").status_code == 204
        assert client.get(f"{API}/projects/app").status_code == 404
        assert client.delete(f"{API}/projects/app").status_code == 404
        bad = client.post(f"{API}/projects", json={"id": "bad id", "name": "x"})
        assert bad.status_code == 422


def test_projects_lookup_port(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    lookup = assembly.port(PROJECTS_LOOKUP)
    assert isinstance(lookup, ProjectLookup)
    with _client(assembly) as client:
        client.post(f"{API}/projects", json={"id": "b", "name": "B"})
        client.post(f"{API}/projects", json={"id": "a", "name": "A"})
    assert [p.id for p in lookup.list_projects()] == ["a", "b"]
    project = lookup.get_project("a")
    assert isinstance(project, Project)
    assert project.name == "A"
    assert lookup.get_project("zz") is None
    assert lookup.get_project("../x") is None


# ---------------------------------------------------------------- 옮기기


def _seed(assembly: Assembly, client: TestClient) -> Any:
    """프로젝트 app·web, app 전용 coder(→ app 전용 리소스 guide), 공용 lead(→ coder)."""
    for pid in ("app", "web"):
        assert client.post(f"{API}/projects", json={"id": pid, "name": pid}).status_code == 201
    store = _store(assembly)
    store.create("resource", _resource("guide", "app"))
    store.create("agent", _agent("coder", "app", uses=[["resource", "guide"]]))
    store.create("agent", _agent("lead", uses=[["agent", "coder"]]))
    return store


def test_move_plan_and_apply(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        store = _seed(assembly, client)
        plan = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "coder", "to": None}
        )
        assert plan.status_code == 200, plan.text
        body = plan.json()
        assert [(m["kind"], m["id"], m["from"], m["to"], m["required"]) for m in body["moves"]] == [
            ("agent", "coder", "app", None, True),
            ("resource", "guide", "app", None, False),
        ]
        assert body["warnings"] == []

        applied = client.post(f"{API}/projects/move", json=body)
        assert applied.status_code == 200, applied.text
        assert [m["id"] for m in applied.json()["moves"]] == ["coder", "guide"]
        assert "project" not in store.get("agent", "coder").document
        assert "project" not in store.get("resource", "guide").document
        again = client.post(f"{API}/projects/move", json=body).json()
        assert again["moves"] == []  # 이미 공용

        to_web = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "coder", "to": "web"}
        ).json()
        codes = {w["code"] for w in to_web["warnings"]}
        assert codes == {"project.shared_uses_project"}  # 공용 lead가 web 전용 coder를 쓴다
        done = client.post(f"{API}/projects/move", json=to_web).json()
        assert store.get("agent", "coder").document["project"] == "web"
        assert {w["code"] for w in done["warnings"]} == {"project.shared_uses_project"}

        missing = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "coder", "to": "nope"}
        )
        assert missing.status_code == 404
        ghost = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "ghost", "to": None}
        )
        assert ghost.status_code == 404
        issues = client.post(f"{API}/projects/scope-issues").json()
        assert [i["code"] for i in issues] == ["project.shared_uses_project"]


# ---------------------------------------------------------------- 삭제


@pytest.mark.parametrize(
    ("mode", "kept"),
    [(None, True), ("move_to_shared", True), ("delete_definitions", False)],
)
def test_delete_plan_and_both_delete_paths(tmp_path: Path, mode: str | None, kept: bool) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        store = _seed(assembly, client)
        plan = client.post(f"{API}/projects/app/delete-plan").json()
        assert plan["default_mode"] == "move_to_shared"
        assert sorted((d["kind"], d["id"]) for d in plan["definitions"]) == [
            ("agent", "coder"),
            ("resource", "guide"),
        ]
        assert client.post(f"{API}/projects/ghost/delete-plan").status_code == 404
        etag = client.get(f"{API}/projects/app").headers["etag"]
        stale = client.delete(f"{API}/projects/app", headers={"If-Match": '"nope"'})
        assert stale.status_code == 412
        assert store.get("agent", "coder").document["project"] == "app"  # 412면 정의는 그대로
        url = f"{API}/projects/app" + (f"?mode={mode}" if mode else "")
        assert client.delete(url, headers={"If-Match": etag}).status_code == 204
        assert client.get(f"{API}/projects/app").status_code == 404
        assert client.get(f"{API}/projects/web").status_code == 200
    ids = store.list_ids("agent")
    if kept:
        assert "project" not in store.get("agent", "coder").document
        assert "project" not in store.get("resource", "guide").document
    else:
        assert "coder" not in ids
        assert store.list_ids("resource") == []
    assert "lead" in ids


# ---------------------------------------------------------------- 저장 전 범위 검사


def test_definition_check_reports_scope_issues_for_saved_document(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        _seed(assembly, client)
    (check,) = assembly.ports(DEFINITION_CHECKS)
    # 공용 에이전트가 app 전용 리소스를 쓴다 → 경고 + [공용으로 옮기기]
    issues = check.issues("agent", _agent("helper", uses=[["resource", "guide"]]))
    assert [(i.severity, i.code) for i in issues] == [("warning", "project.shared_uses_project")]
    assert issues[0].details is not None
    assert (issues[0].details["kind"], issues[0].details["id"]) == ("resource", "guide")
    assert [s.id for s in issues[0].suggestions or []] == ["project.move_to_shared"]
    # web 전용 에이전트가 app 전용 리소스를 쓴다 → 다른 프로젝트 경고
    cross = check.issues("agent", _agent("w", "web", uses=[["resource", "guide"]]))
    assert [i.code for i in cross] == ["project.cross_project"]
    # 없는 프로젝트 → 정보(공용으로 봄)
    unknown = check.issues("agent", _agent("u", "gone"))
    assert [(i.severity, i.code) for i in unknown] == [("info", "project.unknown")]
    # 다른 정의끼리의 이슈는 이 문서 저장에 붙이지 않는다
    assert check.issues("agent", _agent("plain")) == []
    # 리소스를 web으로 옮기려 하면 그것을 쓰는 app 전용 coder가 경고
    moved = check.issues("resource", _resource("guide", "web"))
    assert [i.code for i in moved] == ["project.cross_project"]
    # 공통 설정처럼 id가 없는 문서는 검사하지 않는다
    assert check.issues("settings", {"secrets": {}}) == []


def test_without_references_check_says_cannot_check(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, refs=False)
    with _client(assembly) as client:
        _seed(assembly, client)
        plan = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "coder", "to": None}
        ).json()
        assert [m["id"] for m in plan["moves"]] == ["coder"]
        assert [w["code"] for w in plan["warnings"]] == ["project.references_unavailable"]
    (check,) = assembly.ports(DEFINITION_CHECKS)
    scoped = check.issues("agent", _agent("x", "app"))
    assert [(i.severity, i.code) for i in scoped] == [("info", "project.references_unavailable")]
    assert check.issues("agent", _agent("y")) == []  # 공용 문서에는 안내를 달지 않는다


def test_without_definitions_crud_works_and_rest_is_info_or_409(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, definitions=False, refs=False)
    assert assembly.status("mod-projects") is not None
    (check,) = assembly.ports(DEFINITION_CHECKS)
    assert check.issues("agent", _agent("x", "app")) == []
    with _client(assembly) as client:
        assert client.post(f"{API}/projects", json={"id": "app", "name": "앱"}).status_code == 201
        plan = client.post(f"{API}/projects/app/delete-plan").json()
        assert plan["definitions"] == []
        assert [w["code"] for w in plan["warnings"]] == ["project.definitions_unavailable"]
        move = client.post(
            f"{API}/projects/move-plan", json={"kind": "agent", "id": "a", "to": "app"}
        ).json()
        assert [w["code"] for w in move["warnings"]] == ["project.definitions_unavailable"]
        apply = client.post(
            f"{API}/projects/move",
            json={"target": {"kind": "agent", "id": "a"}, "moves": [{"kind": "agent", "id": "a"}]},
        )
        assert apply.status_code == 409
        assert apply.json()["error"]["code"] == "feature_unavailable"
        issues = client.post(f"{API}/projects/scope-issues").json()
        assert [i["code"] for i in issues] == ["project.definitions_unavailable"]
        assert client.delete(f"{API}/projects/app").status_code == 204


# ---------------------------------------------------------------- 단독 부품


def test_service_without_server(tmp_path: Path) -> None:
    """서버·호스트 없이 저장소 + 서비스만으로 쓴다."""
    repo = ProjectRepository(
        FileDefinitionStore(tmp_path, [project_kind()], versions=InMemoryVersionRepository())
    )
    service = ProjectService(repo, snapshot=DefinitionSnapshot(lambda: None))
    assert service.scope_issues()[0].code == "project.definitions_unavailable"
    assert repo.list_projects() == []


def test_snapshot_invalidated_by_saved_topic(tmp_path: Path) -> None:
    calls: list[int] = []

    class Reader:
        def kinds(self) -> list[str]:
            calls.append(1)
            return []

        def list_ids(self, kind: str) -> list[str]:
            return []

        def get(self, kind: str, id: str) -> Any:
            raise AssertionError

    reader = Reader()
    snap = DefinitionSnapshot(lambda: reader, ttl=60, clock=lambda: 0.0)
    snap.get()
    snap.get()
    assert len(calls) == 1
    snap.invalidate()
    snap.get()
    assert len(calls) == 2
    assert Saved("agent", "a", "h").kind == "agent"


def test_python_m_check_passes(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_CONSOLE_")}
    result = subprocess.run(
        [sys.executable, "-m", "agent_console_mod_projects", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "/health → 200" in result.stdout


def test_definitions_unavailable_code_is_contract_constant() -> None:
    """모듈 정보 코드는 계약 문서 상수를 그대로 쓴다(다시 정의하지 않음, 5.2R.3 후속)."""
    assert CODE_DEFINITIONS_UNAVAILABLE is KnownIssueCodes.PROJECT_DEFINITIONS_UNAVAILABLE


def test_database_opened_only_when_projects_are_used(tmp_path: Path) -> None:
    """DB를 쓰는 다른 모듈이 모두 꺼진 서버에서 시작만으로는 DB를 열지 않는다(처음 쓸 때 연다)."""
    database = RecordingDatabase(tmp_path / "db.sqlite3")
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=database,
    )
    assembly = assemble([module], base=base)
    lookup = assembly.port(PROJECTS_LOOKUP)
    assert lookup is not None
    with _client(assembly) as client:  # 시작 훅까지 돈다
        assert lookup.list_projects() == []
        assert client.get(f"{API}/projects").json() == []
        assert database.upgraded == []
        assert client.post(f"{API}/projects", json={"id": "a", "name": "A"}).status_code == 201
        assert database.upgraded == [[]]  # legacy 계보(정의 버전 표) 한 번
        client.put(f"{API}/projects/a", json={"name": "B"})
    assert database.upgraded == [[]]
