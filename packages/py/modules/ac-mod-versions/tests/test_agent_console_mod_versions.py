"""mod-versions: 목록·비교·되돌리기·보존 개수(D3)·검사 포트·끄기(design §3R.1.3)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Issue
from agent_console_mod_versions import (
    DEFINITION_CHECKS,
    DEFINITIONS_STORE,
    DefinitionCheck,
    SavedDefinition,
    VersionService,
    module,
)
from agent_console_mod_versions.testing import Saved, local_definitions_module
from agent_console_modkit import Assembly, ModulesConfig, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore, InMemoryVersionRepository

TOKEN = "t" * 32


def _agent(name: str, **extra: Any) -> dict[str, Any]:
    return {"id": "a", "name": name, "backend": "fake", **extra}


def _assembly(tmp_path: Path, *extra: Any, **options: Any) -> Assembly:
    config = ModulesConfig(options={"mod-versions": options}) if options else None
    return assemble([module, local_definitions_module(workspace=tmp_path / "ws"), *extra], config)


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


def test_list_diff_restore_over_http(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    store = _store(assembly)
    first = store.create("agent", _agent("하나"))
    second = store.save("agent", _agent("둘"), expected_version=first.version_hash)
    with _client(assembly) as client:
        listed = client.get("/api/v1/agents/a/versions").json()
        assert [v["version_hash"] for v in listed] == [second.version_hash, first.version_hash]
        diff = client.get(f"/api/v1/agents/a/versions/{first.version_hash}/diff").json()
        assert [(c["op"], c["path"]) for c in diff["changes"]] == [("replace", "/name")]
        url = f"/api/v1/agents/a/versions/{first.version_hash}/restore"
        assert client.post(url).status_code == 428
        wrong = client.post(url, headers={"If-Match": '"nope"'})
        assert wrong.status_code == 412
        assert wrong.headers["etag"] == f'"{second.version_hash}"'
        restored = client.post(url, headers={"If-Match": f'"{second.version_hash}"'})
        assert restored.status_code == 200, restored.text
        assert restored.json()["message"] == f"restored from {first.version_hash}"
        assert client.get("/api/v1/agents/ghost/versions/x").status_code == 404
        assert client.get("/api/v1/settings/versions").json() == []
    assert store.get("agent", "a").document["name"] == "하나"


def test_diff_masks_suspected_secrets_with_default_rules(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    store = _store(assembly)
    first = store.create("agent", _agent("a", env={"API_KEY": "plain-one"}))
    store.save(
        "agent", _agent("a", env={"API_KEY": "plain-two"}), expected_version=first.version_hash
    )
    with _client(assembly) as client:
        diff = client.get(f"/api/v1/agents/a/versions/{first.version_hash}/diff").json()
    [change] = diff["changes"]
    assert change["secret"] is True
    assert (change["before"], change["after"]) == ("***", "***")


class _RejectAll:
    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        return [Issue(severity="error", code="test.bad", message="안 됨", path="/name")]


def test_checks_reject_restore_with_issues(tmp_path: Path) -> None:
    checks = fake_module(
        "checks",
        provides=[DEFINITION_CHECKS],
        on_build=lambda ctx: ctx.provide(DEFINITION_CHECKS, _RejectAll()),
    )
    assembly = _assembly(tmp_path, checks)
    store = _store(assembly)
    first = store.create("agent", _agent("하나"))
    with _client(assembly) as client:
        response = client.post(
            f"/api/v1/agents/a/versions/{first.version_hash}/restore",
            headers={"If-Match": f'"{first.version_hash}"'},
        )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert [i["code"] for i in error["details"]["issues"]] == ["test.bad"]
    assert isinstance(_RejectAll(), DefinitionCheck)


def test_max_per_definition_trims_on_save(tmp_path: Path) -> None:
    """D3: 저장할 때마다 정의당 버전 수를 설정 값으로 줄인다(현재 버전은 항상 남는다)."""
    assembly = _assembly(tmp_path, max_per_definition=2)
    store = _store(assembly)
    current = store.create("agent", _agent("0"))
    for i in range(1, 5):
        current = store.save("agent", _agent(str(i)), expected_version=current.version_hash)
    versions = store.list_versions("agent", "a")
    assert len(versions) == 2
    assert versions[0].version_hash == current.version_hash


def test_max_per_definition_applies_at_start(tmp_path: Path) -> None:
    store = FileDefinitionStore(
        tmp_path / "ws", DEFAULT_KINDS, versions=InMemoryVersionRepository()
    )
    current = store.create("agent", _agent("0"))
    for i in range(1, 4):
        current = store.save("agent", _agent(str(i)), expected_version=current.version_hash)
    provider = fake_module(
        "definitions",
        provides=[DEFINITIONS_STORE],
        on_build=lambda ctx: ctx.provide(DEFINITIONS_STORE, store),
    )
    config = ModulesConfig(options={"mod-versions": {"max_per_definition": 1}})
    assembly = assemble([module, provider], config)
    asyncio.run(assembly.start(fail_fast=True))
    asyncio.run(assembly.stop())
    [kept] = store.list_versions("agent", "a")
    assert kept.version_hash == current.version_hash


def test_without_limit_keeps_everything_and_service_retain_is_noop(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    store = _store(assembly)
    current = store.create("agent", _agent("0"))
    for i in range(1, 4):
        current = store.save("agent", _agent(str(i)), expected_version=current.version_hash)
    assert len(store.list_versions("agent", "a")) == 4
    service = VersionService(store)
    assert service.retain("agent", "a") == 0
    saved: SavedDefinition = Saved("agent", "a", current.version_hash)
    assert isinstance(saved, SavedDefinition)


def test_custom_collections_and_disabled_is_404(tmp_path: Path) -> None:
    custom = [{"path": "/team-members", "kind": "agent", "id_param": "member_id", "label": "멤버"}]
    assembly = _assembly(tmp_path, collections=custom)
    _store(assembly).create("agent", _agent("하나"))
    with _client(assembly) as client:
        assert len(client.get("/api/v1/team-members/a/versions").json()) == 1
        assert client.get("/api/v1/agents/a/versions").status_code == 404
    off = assemble(
        [module, local_definitions_module(workspace=tmp_path / "ws")],
        ModulesConfig(disabled=["mod-versions"]),
    )
    with _client(off) as client:
        assert client.get("/api/v1/agents/a/versions").status_code == 404
    alone = assemble([module])
    assert alone.report[0].missing == ("definitions.store",)
