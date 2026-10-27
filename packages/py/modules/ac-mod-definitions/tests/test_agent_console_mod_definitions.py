"""mod-definitions: CRUD·검사·목록 요약 포트·저장 알림·평문 점검·버전 기록·포트 계약(3R.12)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Graph,
    GraphValidationSummary,
    Issue,
    WorkspaceSettings,
)
from agent_console_mod_definitions import (
    DEFINITION_CHECKS,
    DEFINITIONS_LOOKUP,
    DEFINITIONS_SAVED,
    DEFINITIONS_STORE,
    GRAPH_ENTRY_LABELS,
    GRAPH_VALIDATION,
    SECRET_RULES,
    SERVER_WARNINGS,
    VERSIONS_MEMORY,
    WORKSPACE_SETTINGS,
    DefinitionCheck,
    GraphEntryLabels,
    GraphValidationSource,
    SavedDefinition,
    module,
)
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ModuleContext,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_secret_rules import SecretRules
from agent_console_store import ContentTooLarge, DefinitionStore, SqliteDatabase

TOKEN = "t" * 32
API = "/api/v1"
AGENT = {"id": "rev", "name": "리뷰어", "backend": "fake"}
GRAPH = {"id": "g1", "name": "팀", "nodes": [], "edges": []}
PLAIN = "ghp_PlainToken123456"


def _base(tmp_path: Path, database: Any = None) -> BaseServices:
    return BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=database,
    )


def _assembly(tmp_path: Path, *extra: Any, database: Any = None, **options: Any) -> Assembly:
    config = ModulesConfig(options={"mod-definitions": options}) if options else None
    return assemble([module, *extra], config, base=_base(tmp_path, database))


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


class _RejectAgentNamed:
    """``name == "bad"``인 에이전트를 막는 검사(``definitions.checks`` 예)."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        if kind == "agent" and document.get("name") == "bad":
            return [Issue(severity="error", code="x.bad", message="안 됨", path="/name")]
        if kind == "agent" and document.get("system_prompt") == "plain":
            return [Issue(severity="warning", code="resource.plain_secret", message="p", path="/x")]
        return []


def _checks_module() -> Any:
    return fake_module(
        "checks",
        provides=[DEFINITION_CHECKS],
        on_build=lambda ctx: ctx.provide(DEFINITION_CHECKS, _RejectAgentNamed()),
    )


def test_agent_crud_etag_if_match_and_id_mismatch(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/agents", json=AGENT)
        assert created.status_code == 201
        etag = created.headers["etag"]
        assert created.json() == AGENT  # 저장 원문(기본값을 채우지 않는다)
        assert client.get(f"{API}/agents").json() == [AGENT]
        assert client.get(f"{API}/agents/rev").headers["etag"] == etag
        mismatch = client.put(f"{API}/agents/other", json=AGENT)
        assert mismatch.status_code == 400
        assert mismatch.json()["error"]["details"] == {"path_id": "other", "body_id": "rev"}
        stale = client.delete(f"{API}/agents/rev", headers={"If-Match": '"nope"'})
        assert stale.status_code == 412
        assert stale.headers["etag"] == etag
        assert client.delete(f"{API}/agents/rev", headers={"If-Match": etag}).status_code == 204
        assert client.get(f"{API}/agents/rev").status_code == 404
        assert client.post(f"{API}/agents", json={"id": "!"}).status_code == 422


def test_graph_crud_duplicate_and_list_without_providers(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        created = client.post(f"{API}/graphs", json=GRAPH)
        assert created.status_code == 201
        etag = created.headers["etag"]
        assert created.json()["graph"] == GRAPH
        assert client.put(f"{API}/graphs/g1", json=GRAPH).status_code == 428
        renamed = {**GRAPH, "name": "새 이름"}
        saved = client.put(f"{API}/graphs/g1", json=renamed, headers={"If-Match": etag})
        assert saved.status_code == 200
        dup = client.post(f"{API}/graphs/g1/duplicate", json={"id": "g2", "name": "복사"})
        assert dup.status_code == 201
        conflict = client.post(f"{API}/graphs/g1/duplicate", json={"id": "g2", "name": "복사"})
        assert conflict.status_code == 409
        listed = client.get(f"{API}/graphs").json()
        assert [g["id"] for g in listed] == ["g1", "g2"]
        # 검증 요약·입구 이름 제공자가 없으면 null(연동이 꺼진 동작)
        assert all(g["validation"] is None and g["entry_labels"] is None for g in listed)


def test_graph_list_carries_attributes_and_saved_at(tmp_path: Path) -> None:
    """목록 요약 ``attributes``·``saved_at``(5.2R.64). 폴더 저장은 기존 ``PUT /graphs/{id}``."""
    with _client(_assembly(tmp_path)) as client:
        etag = client.post(f"{API}/graphs", json=GRAPH).headers["etag"]
        row = client.get(f"{API}/graphs").json()[0]
        assert row["attributes"] == {}
        assert isinstance(row["saved_at"], float)
        attrs = {"ui": {"folder": "개발팀/백엔드"}, "team_tag": "a"}
        saved = client.put(
            f"{API}/graphs/g1", json={**GRAPH, "attributes": attrs}, headers={"If-Match": etag}
        )
        assert saved.status_code == 200, saved.text
        row = client.get(f"{API}/graphs").json()[0]
        assert row["attributes"] == attrs
        assert row["saved_at"] >= saved.json()["saved_at"] - 1e-6


class _Validation:
    def summaries(self, graph_ids: Sequence[str]) -> Mapping[str, GraphValidationSummary | None]:
        return {gid: GraphValidationSummary(blocks_run=True, error_count=1) for gid in graph_ids}


class _Labels:
    def entry_labels(self, graph: Graph) -> list[str] | None:
        return [f"입구-{graph.id}"]


def test_graph_list_uses_optional_providers(tmp_path: Path) -> None:
    validation, labels = _Validation(), _Labels()
    assert isinstance(validation, GraphValidationSource)
    assert isinstance(labels, GraphEntryLabels)

    def build(ctx: ModuleContext) -> None:
        ctx.provide(GRAPH_VALIDATION, validation)
        ctx.provide(GRAPH_ENTRY_LABELS, labels)

    provider = fake_module(
        "graph-extras", provides=[GRAPH_VALIDATION, GRAPH_ENTRY_LABELS], on_build=build
    )
    with _client(_assembly(tmp_path, provider)) as client:
        client.post(f"{API}/graphs", json=GRAPH)
        item = client.get(f"{API}/graphs").json()[0]
        assert item["entry_labels"] == ["입구-g1"]
        assert item["validation"]["error_count"] == 1
        assert (
            client.get(f"{API}/graphs", params={"validate": "false"}).json()[0]["validation"]
            is None
        )


def test_checks_reject_and_settings_rule_check(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path, _checks_module())) as client:
        rejected = client.post(f"{API}/agents", json={**AGENT, "name": "bad"})
        assert rejected.status_code == 422
        assert rejected.json()["error"]["details"]["issues"][0]["code"] == "x.bad"
        bad = client.put(
            f"{API}/settings", json={"secrets": {"extra_value_patterns": ["ok", "(a+)+$"]}}
        )
        assert bad.status_code == 422
        issues = bad.json()["error"]["details"]["issues"]
        assert [(i["code"], i["path"]) for i in issues] == [
            ("secret.invalid_rule", "/secrets/extra_value_patterns/1")
        ]
        assert client.get(f"{API}/settings").json() == {}
        ok = client.put(f"{API}/settings", json={"default_backend": "fake"})
        assert ok.status_code == 200
        assert client.get(f"{API}/settings").json() == {"default_backend": "fake"}


def test_saved_topic_and_ports(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    got: list[SavedDefinition] = []
    assembly.services.events.subscribe(DEFINITIONS_SAVED, got.append)
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    assert store is assembly.port(DEFINITIONS_LOOKUP)
    saved = store.create("agent", AGENT)
    assert [(s.kind, s.id, s.version_hash) for s in got] == [("agent", "rev", saved.version_hash)]
    read = assembly.port(WORKSPACE_SETTINGS)
    rules = assembly.port(SECRET_RULES)
    assert read is not None
    assert rules is not None
    assert read() == WorkspaceSettings()
    store.save("settings", {"secrets": {"extra_key_names": ["corp"]}})
    assert read().secrets.extra_key_names == ["corp"]
    assert isinstance(rules(), SecretRules)
    assert rules().find_suspected({"corp": "v"})  # 사용자 키 이름이 규칙에 들어갔다


def test_plain_scan_warnings_cache_and_invalidation(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, _checks_module())
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    [source] = assembly.ports(SERVER_WARNINGS)

    def warnings() -> list[Issue]:
        return [w for w in source() if w.code != VERSIONS_MEMORY]  # DB 없음 경고는 따로 본다

    assert warnings() == []
    store.create("agent", {**AGENT, "system_prompt": "plain"})  # 검사의 평문 이슈 코드
    found = warnings()  # 저장 알림이 캐시를 버렸다
    assert [(w.code, w.path, w.details) for w in found] == [
        ("secret.plain_found", "/x", {"kind": "agent", "id": "rev"})
    ]
    assert PLAIN not in str(found)
    store.create("agent", {"id": "b", "name": "b", "backend_options": {"token": PLAIN}})
    assert {w.details["id"] for w in warnings()} == {"rev", "b"}  # 규칙의 의심 값
    store.delete("agent", "b")  # 삭제도 캐시를 버린다
    assert {w.details["id"] for w in warnings()} == {"rev"}


def test_memory_versions_warn_in_server_warnings(tmp_path: Path) -> None:
    """DB 핸들이 없으면 버전 기록이 메모리로 떨어지고 ``server.warnings``에 경고를 낸다."""
    [source] = _assembly(tmp_path).ports(SERVER_WARNINGS)
    assert [w.code for w in source()] == [VERSIONS_MEMORY]
    db = SqliteDatabase.open(tmp_path / "state" / "w.sqlite3")
    try:
        [with_db] = _assembly(tmp_path, database=db).ports(SERVER_WARNINGS)
        assert with_db() == []
    finally:
        db.close()


def test_versions_go_to_database_handle_and_persist(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "c.sqlite3"
    db = SqliteDatabase.open(db_path)
    try:
        assembly = _assembly(tmp_path, database=db)
        with _client(assembly) as client:  # 시작 훅이 legacy 계보를 올린다
            first = client.post(f"{API}/agents", json=AGENT).headers["etag"]
            client.put(
                f"{API}/agents/rev", json={**AGENT, "name": "둘"}, headers={"If-Match": first}
            )
        store = assembly.port(DEFINITIONS_STORE)
        assert store is not None
        assert len(store.list_versions("agent", "rev")) == 2
    finally:
        db.close()
    db = SqliteDatabase.open(db_path)
    try:
        again = _assembly(tmp_path, database=db).port(DEFINITIONS_STORE)
        assert again is not None
        assert len(again.list_versions("agent", "rev")) == 2  # 재시작 뒤에도 남는다
    finally:
        db.close()


def test_max_content_bytes_option(tmp_path: Path) -> None:
    store = _assembly(tmp_path, max_content_bytes=4).port(DEFINITIONS_STORE)
    assert store is not None
    saved = store.create("resource", {"id": "r", "type": "instruction", "name": "r", "config": {}})
    with pytest.raises(ContentTooLarge):
        store.write_content(
            "resource",
            "r",
            b"0123456789",
            file="content.txt",
            expected_version=saved.version_hash,
        )


def test_port_contracts() -> None:
    """제공 구현 ↔ 소비 프로토콜(이 모듈이 정한 모양과 ac-store ``DefinitionStore``)."""
    assembly = assemble([module], base=BaseServices())
    store: DefinitionStore | None = assembly.port(DEFINITIONS_STORE)  # 정적 모양 검사
    for name in ("get", "create", "save", "delete", "list_ids", "summaries", "list_versions"):
        assert callable(getattr(store, name))
    [own_check] = assembly.ports(DEFINITION_CHECKS)
    assert isinstance(own_check, DefinitionCheck)
    assert callable(assembly.port(WORKSPACE_SETTINGS))
    assert callable(assembly.port(SECRET_RULES))


def test_disabled_is_404(tmp_path: Path) -> None:
    config = ModulesConfig(disabled=["mod-definitions"])
    assembly = assemble([module], config, base=_base(tmp_path))
    with _client(assembly) as client:
        assert client.get(f"{API}/agents").status_code == 404


def test_settings_compat_rejects_removed_preset_keys() -> None:
    """삭제된 프리셋 기능의 설정 키는 지우라는 이유로 거부한다(옛 ``resources``는 새 위치 안내)."""
    from agent_console_mod_definitions.settings import PRESETS_REMOVED_REASON, SETTINGS_COMPAT
    from agent_console_modkit import removed_settings

    assert module.descriptor.settings_compat is SETTINGS_COMPAT
    compat = {"mod-definitions": SETTINGS_COMPAT}
    data = {
        "presets": {"directories": ["p"]},
        "modules": {"options": {"mod-presets": {"apply_on_start": ["x"]}}},
        "resources": {},
    }
    found = {r.path: r for r in removed_settings(data, compat)}
    assert set(found) == {"presets", "modules.options.mod-presets", "resources"}
    assert found["presets"].message() == PRESETS_REMOVED_REASON
    assert found["modules.options.mod-presets"].new is None
    assert found["resources"].new == "modules.options.mod-definitions"
    assert removed_settings({"modules": {"options": {"mod-definitions": {}}}}, compat) == []
