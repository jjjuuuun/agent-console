"""5.7R.33x 통합: 정의·리소스·버전 경로의 ``?project=`` + 실제 프로젝트 공간(``ac-project-space``)
+ 그 폴더의 기록 DB 버전(``RecordsVersionRepository``).

공간 제공자는 이 테스트 안의 작은 모듈이다(``mod-projects``의 ``definitions.spaces``와 같은 모양).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_definitions import DEFINITIONS_SPACES
from agent_console_mod_definitions import module as definitions
from agent_console_mod_definitions.store import definition_kinds
from agent_console_mod_resources import module as resources
from agent_console_mod_versions import module as versions
from agent_console_modkit import Assembly, BaseServices, ModuleContext, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_project_space import ProjectSpace, open_space
from agent_console_project_space.testing import ReadOnlyFiles
from agent_console_store import (
    DefinitionStore,
    RecordsDb,
    RecordsVersionRepository,
    open_records_db,
)

TOKEN = "t" * 32
API = "/api/v1"
AGENT = {"id": "rev", "name": "리뷰어", "backend": "fake-agent"}


class FolderSpaces:
    """등록 id → 폴더. 공간마다 그 폴더 기록 DB에 버전을 남긴다(공간 캐시 = 이 객체)."""

    def __init__(self, folders: dict[str, Path], *, readonly: set[str] | None = None) -> None:
        self.folders = folders
        self.readonly = readonly or set()
        self.dbs: dict[str, RecordsDb] = {}
        self.spaces: dict[str, ProjectSpace] = {}

    def open(self, space: str) -> DefinitionStore:
        if space not in self.spaces:
            folder = self.folders[space]
            root = folder / ".agent-console"
            db = open_records_db(
                root / "records.sqlite3", (), backup_dir=root / ".state" / "backups"
            )
            self.dbs[space] = db
            options: dict[str, Any] = {}
            if space in self.readonly:
                options["files"] = ReadOnlyFiles()
            self.spaces[space] = open_space(
                folder,
                kinds=definition_kinds(),
                versions=RecordsVersionRepository(lambda: db),
                **options,
            )
        return self.spaces[space].definitions

    def close(self) -> None:
        for db in self.dbs.values():
            db.close()
        self.dbs.clear()
        self.spaces.clear()


def _app(tmp_path: Path, spaces: FolderSpaces) -> TestClient:
    def build(ctx: ModuleContext) -> None:
        ctx.provide(DEFINITIONS_SPACES, spaces)

    provider = fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly: Assembly = assemble([definitions, resources, versions, provider], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    client = TestClient(
        create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    )
    client.headers["X-Console-Token"] = TOKEN
    return client


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[FolderSpaces]:
    for name in ("A", "B", "R"):
        (tmp_path / name).mkdir()
    found = FolderSpaces(
        {"pa": tmp_path / "A", "pb": tmp_path / "B", "pr": tmp_path / "R", "gone": tmp_path / "X"},
        readonly={"pr"},
    )
    yield found
    found.close()


def test_project_spaces_end_to_end(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _app(tmp_path, spaces) as client:
        a = client.post(f"{API}/agents?project=pa", json={**AGENT, "name": "A"})
        b = client.post(f"{API}/agents?project=pb", json={**AGENT, "name": "B"})
        assert (a.status_code, b.status_code) == (201, 201)
        client.put(
            f"{API}/agents/rev?project=pa",
            json={**AGENT, "name": "A2"},
            headers={"If-Match": a.headers["etag"]},
        )
        va = client.get(f"{API}/agents/rev/versions?project=pa").json()
        vb = client.get(f"{API}/agents/rev/versions?project=pb").json()
        assert (len(va), len(vb)) == (2, 1)
        assert client.get(f"{API}/agents/rev/versions").json() == []
        # 사본은 그 폴더의 구성 폴더에, 버전은 그 폴더의 기록 DB에.
        assert (tmp_path / "A" / ".agent-console" / "agents" / "rev.yaml").exists()
        assert (tmp_path / "A" / ".agent-console" / "records.sqlite3").exists()
        assert (tmp_path / "B" / ".agent-console" / "records.sqlite3").exists()
        assert not (tmp_path / "ws" / "agents").exists()

        # 리소스도 같은 공간.
        doc = {"id": "g", "type": "instruction", "name": "지침", "content": {"file": "a.md"}}
        assert client.post(f"{API}/resources?project=pa", json=doc).status_code == 201
        assert (tmp_path / "A" / ".agent-console" / "resources" / "g.yaml").exists()

        # 평문 비밀 → 422 + 필드 위치(값 없음).
        plain = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        bad = client.post(
            f"{API}/agents?project=pa", json={"id": "s", "name": "s", "attributes": {"k": plain}}
        )
        assert bad.status_code == 422
        assert [i["path"] for i in bad.json()["error"]["details"]["issues"]] == ["/attributes/k"]
        assert plain not in bad.text

        # 쓸 수 없는 폴더 → 409 project.config_readonly, 폴더 없음 → 409 project.folder_missing.
        ro = client.post(f"{API}/agents?project=pr", json=AGENT)
        assert (ro.status_code, ro.json()["error"]["code"]) == (409, "project.config_readonly")
        gone = client.get(f"{API}/agents?project=gone")
        assert (gone.status_code, gone.json()["error"]["code"]) == (409, "project.folder_missing")
        unknown = client.get(f"{API}/agents?project=zzz")
        assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "project.not_found")


def test_newer_records_db_blocks_copy_save(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _app(tmp_path, spaces) as client:
        assert client.post(f"{API}/agents?project=pa", json=AGENT).status_code == 201
    spaces.close()
    raw = sqlite3.connect(tmp_path / "A" / ".agent-console" / "records.sqlite3")
    raw.execute("UPDATE alembic_version SET version_num = 'legacy_9999'")
    raw.commit()
    raw.close()
    target = tmp_path / "A" / ".agent-console" / "agents" / "rev.yaml"
    before = target.read_bytes()
    with _app(tmp_path, spaces) as client:
        etag = client.get(f"{API}/agents/rev?project=pa").headers["etag"]
        refused = client.put(
            f"{API}/agents/rev?project=pa", json={**AGENT, "name": "x"}, headers={"If-Match": etag}
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "project.records_unavailable"
        # 읽기(버전 목록)는 된다.
        assert len(client.get(f"{API}/agents/rev/versions?project=pa").json()) == 1
    assert target.read_bytes() == before


def test_app_assembly_versions_go_to_project_records_db(tmp_path: Path) -> None:
    """mod-projects(`definitions.spaces`) + link-projects-records: 사본 버전이 그 폴더 기록 DB에."""
    from agent_console_link_projects_records import RECORDS_SPACES, RecordsSpacePool
    from agent_console_link_projects_records import module as records_link
    from agent_console_mod_projects import module as projects

    folder = tmp_path / "proj"
    folder.mkdir()
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble([definitions, versions, projects, records_link], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    client = TestClient(
        create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    )
    client.headers["X-Console-Token"] = TOKEN
    try:
        with client:
            registered = client.post(f"{API}/projects", json={"folder": str(folder)})
            assert registered.status_code == 201, registered.text
            pid = registered.json()["project"]["id"]
            created = client.post(f"{API}/agents?project={pid}", json=AGENT)
            assert created.status_code == 201, created.text
            client.put(
                f"{API}/agents/rev?project={pid}",
                json={**AGENT, "name": "둘"},
                headers={"If-Match": created.headers["etag"]},
            )
            listed = client.get(f"{API}/agents/rev/versions?project={pid}").json()
            assert len(listed) == 2
            assert client.get(f"{API}/agents/rev/versions").json() == []
            assert client.get(f"{API}/agents").json() == []
        db = folder / ".agent-console" / "records.sqlite3"
        assert db.exists()
        raw = sqlite3.connect(db)
        try:
            count = raw.execute(
                "SELECT COUNT(*) FROM definition_versions WHERE def_id = 'rev'"
            ).fetchone()[0]
        finally:
            raw.close()
        assert count == 2
    finally:
        pool = assembly.port(RECORDS_SPACES)
        if isinstance(pool, RecordsSpacePool):
            pool.close_all()


def test_app_assembly_secret_rejection_has_field_issues(tmp_path: Path) -> None:
    """mod-projects의 SecretRejected 처리기(앱 전체)도 정의 경로 모양의 details.issues를 싣는다."""
    from agent_console_mod_projects import module as projects

    folder = tmp_path / "proj"
    folder.mkdir()
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble([definitions, projects], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    client = TestClient(
        create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    )
    client.headers["X-Console-Token"] = TOKEN
    plain = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    with client:
        pid = client.post(f"{API}/projects", json={"folder": str(folder)}).json()["project"]["id"]
        bad = client.post(
            f"{API}/agents?project={pid}", json={"id": "s", "name": "s", "attributes": {"k": plain}}
        )
    assert bad.status_code == 422
    details = bad.json()["error"]["details"]
    assert [i["path"] for i in details["issues"]] == ["/attributes/k"]
    assert plain not in bad.text


def _team_graph(edge_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "team",
        "name": "팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "lead", "type": "agent", "label": "리더", "config": {}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "lead", "port": "in"},
                "kind": "message",
                "config": edge_config,
            }
        ],
    }


def test_team_graph_with_input_key_saves_to_space_57r33y2(
    tmp_path: Path, spaces: FolderSpaces
) -> None:
    """5.7R.33y2 결함: 연결 config의 ``input_key``가 평문 비밀로 잡혀 422가 나던 것."""
    with _app(tmp_path, spaces) as client:
        ok = client.post(f"{API}/graphs?project=pa", json=_team_graph({"input_key": "message"}))
        assert ok.status_code == 201, ok.text
        assert (tmp_path / "A" / ".agent-console" / "graphs" / "team.yaml").exists()

        secret = "sk-ant-" + "abcdef123456"
        bad = client.post(
            f"{API}/graphs?project=pb",
            json=_team_graph({"input_key": "message", "api_key": secret}),
        )
        assert bad.status_code == 422
        paths = [i["path"] for i in bad.json()["error"]["details"]["issues"]]
        assert paths == ["/edges/0/config/api_key"]
        assert secret not in bad.text
