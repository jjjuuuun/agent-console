"""5.7R.33x: 버전 경로의 공간 선택(``?project=``)과 공간 저장 알림의 보존 개수."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_versions import DEFINITIONS_SAVED, DEFINITIONS_SPACES, module
from agent_console_mod_versions.testing import local_definitions_module
from agent_console_modkit import Assembly, ModuleContext, ModulesConfig, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    DEFAULT_KINDS,
    FileDefinitionStore,
    InMemoryVersionRepository,
    MappedSpaces,
    ObservedVersionRepository,
)

TOKEN = "t" * 32


@dataclass(frozen=True)
class SpaceSaved:
    kind: str
    id: str
    version_hash: str
    space: str | None = None


def _agent(name: str) -> dict[str, Any]:
    return {"id": "a", "name": name, "backend": "fake-agent"}


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _setup(tmp_path: Path, **options: Any) -> tuple[Assembly, dict[str, FileDefinitionStore]]:
    made: dict[str, FileDefinitionStore] = {}

    def build(ctx: ModuleContext) -> None:
        def saved(kind: str, item_id: str, version_hash: str) -> None:
            ctx.publish(DEFINITIONS_SAVED, SpaceSaved(kind, item_id, version_hash, "pa"))

        made["pa"] = FileDefinitionStore(
            tmp_path / "A",
            [k for k in DEFAULT_KINDS if k.is_portable],
            versions=ObservedVersionRepository(InMemoryVersionRepository(), saved),
        )
        ctx.provide(DEFINITIONS_SPACES, MappedSpaces(made))

    spaces = fake_module("spaces", provides=[DEFINITIONS_SPACES], on_build=build)
    config = ModulesConfig(options={"mod-versions": options}) if options else None
    assembly = assemble(
        [module, local_definitions_module(workspace=tmp_path / "ws"), spaces], config
    )
    return assembly, made


def test_version_paths_follow_project_query(tmp_path: Path) -> None:
    assembly, made = _setup(tmp_path)
    space = made["pa"]
    first = space.create("agent", _agent("하나"))
    second = space.save("agent", _agent("둘"), expected_version=first.version_hash)
    with _client(assembly) as client:
        assert client.get("/api/v1/agents/a/versions").status_code == 200
        assert client.get("/api/v1/agents/a/versions").json() == []
        listed = client.get("/api/v1/agents/a/versions?project=pa").json()
        assert [v["version_hash"] for v in listed] == [second.version_hash, first.version_hash]
        one = client.get(f"/api/v1/agents/a/versions/{first.version_hash}?project=pa")
        assert one.json()["content"]["name"] == "하나"
        diff = client.get(f"/api/v1/agents/a/versions/{first.version_hash}/diff?project=pa")
        assert diff.status_code == 200
        restored = client.post(
            f"/api/v1/agents/a/versions/{first.version_hash}/restore?project=pa",
            headers={"If-Match": f'"{second.version_hash}"'},
        )
        assert restored.status_code == 200
        assert space.get("agent", "a").document["name"] == "하나"
        missing = client.get("/api/v1/agents/a/versions?project=nope")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "project.not_found"


def test_without_port_project_query_is_refused(tmp_path: Path) -> None:
    assembly = assemble([module, local_definitions_module(workspace=tmp_path / "ws")])
    with _client(assembly) as client:
        refused = client.get("/api/v1/agents/a/versions?project=pa")
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"


def test_space_saved_items_trim_that_space(tmp_path: Path) -> None:
    assembly, made = _setup(tmp_path, max_per_definition=2)
    library = assembly.port(DEFINITIONS_SPACES)
    assert library is not None
    space = made["pa"]
    current = space.create("agent", _agent("0"))
    for i in range(1, 5):
        current = space.save("agent", _agent(str(i)), expected_version=current.version_hash)
    versions = space.list_versions("agent", "a")
    assert len(versions) == 2
    assert versions[0].version_hash == current.version_hash
