"""5.7R.33x: 리소스 경로의 공간 선택(``?project=``) — 선택 포트 ``definitions.spaces``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, DefinitionReference
from agent_console_mod_resources import DEFINITION_USAGES, DEFINITIONS_SPACES, module
from agent_console_mod_resources.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModuleContext, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore, MappedSpaces

TOKEN = "t" * 32
API = "/api/v1"
DOC = {"id": "guide", "type": "instruction", "name": "지침", "content": {"file": "a.md"}}


def _assembly(tmp_path: Path, *extra: Any) -> Assembly:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    return assemble([module, local_definitions_module(), *extra], base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _spaces(tmp_path: Path) -> tuple[Any, FileDefinitionStore]:
    store = FileDefinitionStore(
        tmp_path / "A" / ".cfg", [k for k in DEFAULT_KINDS if k.is_portable]
    )
    spaces = MappedSpaces({"pa": store})

    def build(ctx: ModuleContext) -> None:
        ctx.provide(DEFINITIONS_SPACES, spaces)

    return fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build), store


class _Usages:
    def references(self, kind: str, id: str) -> list[DefinitionReference]:
        return [DefinitionReference(kind="graph", id="g", name="g")]


def test_resource_paths_follow_project_query(tmp_path: Path) -> None:
    spaces, store = _spaces(tmp_path)
    usages = fake_module(
        "usages",
        provides=[DEFINITION_USAGES],
        on_build=lambda ctx: ctx.provide(DEFINITION_USAGES, _Usages()),
    )
    with _client(_assembly(tmp_path, spaces, usages)) as client:
        lib = client.post(f"{API}/resources", json=DOC)
        assert lib.status_code == 201
        created = client.post(f"{API}/resources?project=pa", json={**DOC, "name": "프로젝트 지침"})
        assert created.status_code == 201
        etag = created.headers["etag"]
        put = client.put(
            f"{API}/resources/guide/content?project=pa",
            content=b"# project",
            headers={"If-Match": etag, "Content-Type": "text/markdown"},
        )
        assert put.status_code == 200
        assert client.get(f"{API}/resources/guide/content?project=pa").text == "# project"
        assert client.get(f"{API}/resources/guide/content").status_code == 404
        assert client.get(f"{API}/resources/guide").json()["name"] == "지침"
        assert client.get(f"{API}/resources/guide?project=pa").json()["name"] == "프로젝트 지침"
        # 목록: 공간의 사용 수는 라이브러리 기준이라 계산하지 않는다(null).
        [lib_row] = client.get(f"{API}/resources").json()
        [space_row] = client.get(f"{API}/resources?project=pa").json()
        assert lib_row["usage_count"] == 1
        assert space_row["usage_count"] is None
        assert space_row["name"] == "프로젝트 지침"
        # 여러 파일 경로도 그 공간.
        assert client.get(f"{API}/resources/guide/files?project=pa").status_code == 200
        latest = client.get(f"{API}/resources/guide?project=pa").headers["etag"]
        assert (
            client.delete(
                f"{API}/resources/guide?project=pa", headers={"If-Match": latest}
            ).status_code
            == 204
        )
        assert client.get(f"{API}/resources/guide?project=pa").status_code == 404
        assert client.get(f"{API}/resources/guide").status_code == 200
        unknown = client.get(f"{API}/resources?project=nope")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
    assert store.list_ids("resource") == []


def test_without_port_project_query_is_refused(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        assert client.get(f"{API}/resources").json() == []
        refused = client.post(f"{API}/resources?project=pa", json=DOC)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"
        assert client.get(f"{API}/resources").json() == []
        # 종류 목록은 공간과 무관.
        assert client.get(f"{API}/resource-types?project=pa").status_code == 200
