"""5.7R.33x: 정의 경로의 공간 선택(``?project=``) — 선택 포트 ``definitions.spaces``.

가짜 제공자는 공간마다 폴더 하나(정의 YAML) + 그 폴더의 기록 DB(버전)를 쓴다. 정의 모듈은 공간
이름이 무엇을 가리키는지 모른다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_mod_definitions import DEFINITIONS_SPACES, module
from agent_console_mod_definitions.store import definition_kinds
from agent_console_modkit import Assembly, BaseServices, ModuleContext, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    DefinitionKind,
    DefinitionSpaces,
    DefinitionStore,
    FileDefinitionStore,
    RecordsDb,
    RecordsVersionRepository,
    StoreError,
    VersionWriteCheck,
    open_records_db,
)

TOKEN = "t" * 32
API = "/api/v1"
AGENT = {"id": "rev", "name": "리뷰어", "backend": "fake-agent"}
GRAPH = {"id": "g1", "name": "팀", "nodes": [], "edges": []}
PLAIN = "ghp_PlainToken123456"


class PlainSecretError(StoreError):
    """예제 공간의 평문 비밀 거부(필드 위치 이슈)."""

    code = "validation_failed"

    def __init__(self, paths: list[str]) -> None:
        super().__init__("plain secret")
        self.paths = paths

    def field_issues(self) -> list[Issue]:
        return [
            Issue(severity="error", code="secret.plain_found", message="secret://", path=p)
            for p in self.paths
        ]


def _guard(
    versions: VersionWriteCheck,
) -> Any:
    def guard(
        kind: DefinitionKind, id: str, document: Mapping[str, Any], put: Mapping[str, bytes]
    ) -> None:
        found = [f"/{k}" for k, v in document.items() if isinstance(v, str) and v == PLAIN]
        if found:
            raise PlainSecretError(found)
        versions.ensure_writable()

    return guard


class FolderSpaces:
    """``definitions.spaces`` 예제 구현: 공간 이름 → 폴더(정의 YAML + 기록 DB 버전)."""

    def __init__(self, folders: Mapping[str, Path]) -> None:
        self.folders = dict(folders)
        self.dbs: dict[str, RecordsDb] = {}
        self.stores: dict[str, FileDefinitionStore] = {}

    def open(self, space: str) -> DefinitionStore:
        folder = self.folders[space]  # 모르면 KeyError → 404
        if space not in self.stores:
            root = folder / ".cfg"
            db = open_records_db(root / "records.sqlite3", (), backup_dir=root / "backups")
            self.dbs[space] = db
            repo = RecordsVersionRepository(lambda: db)
            kinds = [k for k in definition_kinds() if k.is_portable]
            self.stores[space] = FileDefinitionStore(
                root, kinds, versions=repo, write_guard=_guard(repo)
            )
        return self.stores[space]

    def close(self) -> None:
        for db in self.dbs.values():
            db.close()
        self.dbs.clear()
        self.stores.clear()


def _spaces_module(spaces: DefinitionSpaces) -> Any:
    def build(ctx: ModuleContext) -> None:
        ctx.provide(DEFINITIONS_SPACES, spaces)

    return fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build)


def _assembly(tmp_path: Path, *extra: Any) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, *extra], base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


@pytest.fixture
def spaces(tmp_path: Path) -> Any:
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    found = FolderSpaces({"pa": a, "pb": b})
    yield found
    found.close()


def test_two_spaces_and_library_are_separate(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _client(_assembly(tmp_path, _spaces_module(spaces))) as client:
        lib = client.post(f"{API}/agents", json=AGENT)
        in_a = client.post(f"{API}/agents?project=pa", json={**AGENT, "name": "A의 리뷰어"})
        in_b = client.post(f"{API}/agents?project=pb", json={**AGENT, "name": "B의 리뷰어"})
        assert [lib.status_code, in_a.status_code, in_b.status_code] == [201, 201, 201]
        assert client.get(f"{API}/agents/rev").json()["name"] == "리뷰어"
        assert client.get(f"{API}/agents/rev?project=pa").json()["name"] == "A의 리뷰어"
        assert client.get(f"{API}/agents/rev?project=pb").json()["name"] == "B의 리뷰어"
        # 저장(If-Match)·버전 기록은 그 공간에만.
        etag = in_a.headers["etag"]
        saved = client.put(
            f"{API}/agents/rev?project=pa",
            json={**AGENT, "name": "A2"},
            headers={"If-Match": etag},
        )
        assert saved.status_code == 200
        assert len(spaces.stores["pa"].list_versions("agent", "rev")) == 2
        assert len(spaces.stores["pb"].list_versions("agent", "rev")) == 1
        # 팀 구성도: 목록·만들기·복제·삭제가 그 공간에서만.
        assert client.post(f"{API}/graphs?project=pa", json=GRAPH).status_code == 201
        dup = client.post(f"{API}/graphs/g1/duplicate?project=pa", json={"id": "g2", "name": "c"})
        assert dup.status_code == 201
        assert [g["id"] for g in client.get(f"{API}/graphs?project=pa").json()] == ["g1", "g2"]
        assert client.get(f"{API}/graphs").json() == []
        assert client.get(f"{API}/graphs?project=pb").json() == []
        assert client.delete(f"{API}/graphs/g2?project=pa").status_code == 204
        assert client.get(f"{API}/graphs/g2?project=pa").status_code == 404
        assert client.delete(f"{API}/agents/rev?project=pb").status_code == 204
        assert client.get(f"{API}/agents/rev?project=pb").status_code == 404
        assert client.get(f"{API}/agents/rev").status_code == 200
    # 공간마다 다른 기록 DB 파일, 라이브러리 폴더에는 공간 정의가 없다.
    assert (tmp_path / "A" / ".cfg" / "records.sqlite3").exists()
    assert (tmp_path / "B" / ".cfg" / "records.sqlite3").exists()
    assert not (tmp_path / "ws" / "graphs" / "g1.yaml").exists()


def test_unknown_space_is_404(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _client(_assembly(tmp_path, _spaces_module(spaces))) as client:
        got = client.get(f"{API}/agents?project=nope")
        assert got.status_code == 404
        assert got.json()["error"]["code"] == "project.not_found"
        assert client.post(f"{API}/agents?project=nope", json=AGENT).status_code == 404


def test_without_port_library_works_and_project_query_is_refused(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        assert client.post(f"{API}/agents", json=AGENT).status_code == 201
        assert client.get(f"{API}/agents").json() == [AGENT]
        refused = client.get(f"{API}/agents?project=pa")
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"
        # 질의를 무시하고 라이브러리에 쓰지 않는다.
        assert client.post(f"{API}/graphs?project=pa", json=GRAPH).status_code == 409
        assert client.get(f"{API}/graphs").json() == []


def test_space_write_refusals_map_to_contract_errors(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _client(_assembly(tmp_path, _spaces_module(spaces))) as client:
        bad = client.post(f"{API}/agents?project=pa", json={**AGENT, "system_prompt": PLAIN})
        assert bad.status_code == 422
        [issue] = bad.json()["error"]["details"]["issues"]
        assert issue["path"] == "/system_prompt"
        assert PLAIN not in bad.text
        created = client.post(f"{API}/agents?project=pa", json=AGENT)
        assert created.status_code == 201
    # 기록 DB가 앞선 리비전이면 사본 저장은 409이고 정의 파일은 그대로.
    spaces.close()
    raw = sqlite3.connect(tmp_path / "A" / ".cfg" / "records.sqlite3")
    raw.execute("UPDATE alembic_version SET version_num = 'legacy_9999'")
    raw.commit()
    raw.close()
    agent_file = tmp_path / "A" / ".cfg" / "agents" / "rev.yaml"
    before = agent_file.read_bytes()
    with _client(_assembly(tmp_path, _spaces_module(spaces))) as client:
        current = client.get(f"{API}/agents/rev?project=pa")
        refused = client.put(
            f"{API}/agents/rev?project=pa",
            json={**AGENT, "name": "바뀜"},
            headers={"If-Match": current.headers["etag"]},
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "project.records_unavailable"
    assert agent_file.read_bytes() == before


def test_copied_folder_keeps_version_history(tmp_path: Path, spaces: FolderSpaces) -> None:
    with _client(_assembly(tmp_path, _spaces_module(spaces))) as client:
        created = client.post(f"{API}/agents?project=pa", json=AGENT)
        client.put(
            f"{API}/agents/rev?project=pa",
            json={**AGENT, "name": "둘"},
            headers={"If-Match": created.headers["etag"]},
        )
    spaces.close()
    moved = tmp_path / "moved"
    moved.mkdir()
    for src in (tmp_path / "A" / ".cfg").rglob("*"):
        dst = moved / ".cfg" / src.relative_to(tmp_path / "A" / ".cfg")
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    again = FolderSpaces({"other-name": moved})
    try:
        store = again.open("other-name")
        assert [v.version_hash for v in store.list_versions("agent", "rev")] == [
            v.version_hash
            for v in FolderSpaces({"x": tmp_path / "A"}).open("x").list_versions("agent", "rev")
        ]
        assert len(store.list_versions("agent", "rev")) == 2
    finally:
        again.close()


def test_space_graph_list_has_no_validation(tmp_path: Path, spaces: FolderSpaces) -> None:
    from agent_console_mod_definitions import GRAPH_VALIDATION

    class Validation:
        def summaries(self, graph_ids: Any) -> Mapping[str, Any]:
            raise AssertionError("공간 목록에서는 라이브러리 검증을 부르지 않는다")

    validation = fake_module(
        "validation",
        provides=[GRAPH_VALIDATION],
        on_build=lambda ctx: ctx.provide(GRAPH_VALIDATION, Validation()),
    )
    with _client(_assembly(tmp_path, _spaces_module(spaces), validation)) as client:
        client.post(f"{API}/graphs?project=pa", json=GRAPH)
        [row] = client.get(f"{API}/graphs?project=pa").json()
        assert row["validation"] is None


def test_openapi_lists_project_query(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        schema = client.app.openapi()  # type: ignore[attr-defined]
        params = schema["paths"][f"{API}/agents/{{agent_id}}"]["get"]["parameters"]
        assert any(p["name"] == "project" and p["in"] == "query" for p in params)
