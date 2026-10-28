"""mod-memory 모듈·서비스: 포트·WS 알림·플러그인(X29)·도구 묶음·정리 스케줄·설정 해석·단독 실행.

범위 종류 이름은 테스트 데이터다(패키지 기본에 기대지 않는다).
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import WorkspaceSettings
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryAuthor,
    MemoryChanged,
    MemoryScopeAccess,
    MemoryScopeRef,
    MemoryWriteRequest,
)
from agent_console_memory import (
    MEMORY_SCOPE_KINDS_EXTENSION,
    EntryScanner,
    InMemoryMemoryStore,
    MemoryScopeKind,
    MemoryStore,
    ToolOutcome,
)
from agent_console_mod_memory import (
    MEMORY_SERVICE,
    MEMORY_TOPIC,
    LoopPublisher,
    MemoryModuleSettings,
    MemoryService,
    observe,
    parse_memory_settings,
)
from agent_console_mod_memory.module import run_retention_periodically
from agent_console_mod_memory.plugins import ensure_scope_kinds, load_plugins
from agent_console_mod_memory.standalone import main
from agent_console_modkit import Assembly, ExtensionRegistries, PluginLoadContext
from agent_console_modkit.host import HostSettings
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "m" * 32
NOTES = MemoryScopeRef(kind="notes", id="p1")
USER = MemoryAuthor(kind="user")

type MakeAssembly = Callable[..., Assembly]
type ClientOf = Callable[[Assembly], Any]


def _service(**kwargs: Any) -> tuple[MemoryService, list[MemoryChanged]]:
    changes: list[MemoryChanged] = []
    section = kwargs.pop("section", None)
    service = MemoryService(
        kwargs.pop("store", InMemoryMemoryStore()),
        section=lambda: section,
        on_change=changes.append,
        **kwargs,
    )
    return service, changes


# ---------------------------------------------------------------- 변경 알림 감싸개


def test_observed_store_notifies_each_versioned_change() -> None:
    service, changes = _service()
    store = service.store
    entry = store.write(NOTES, "a", "하나", author=USER).entry
    store.write(NOTES, "a", "둘", author=USER)
    store.archive(entry.id, author=USER)
    store.archive(entry.id, author=USER)  # 이미 보관 — 버전이 오르지 않아 알리지 않는다
    store.archive(entry.id, author=USER, archived=False)
    store.move(entry.id, author=USER, to_key="b")
    store.delete(entry.id, author=USER)
    store.restore(entry.id, author=USER)
    store.update(entry.id, author=MemoryAuthor(kind="system"), content="셋")
    store.purge(entry.id)
    assert [c.op for c in changes] == [
        "create",
        "update",
        "archive",
        "unarchive",
        "move",
        "delete",
        "restore",
        "update",
        "purge",
    ]
    assert changes[-2].author_kind == "system"
    assert changes[-1].author_kind == "user"
    assert changes[4].key == "b"
    assert "셋" not in repr(changes)  # 본문 없음


def test_observed_store_keeps_scan_capability() -> None:
    inner = InMemoryMemoryStore()
    assert isinstance(inner, EntryScanner)
    observed = observe(inner, lambda _c: None)
    assert isinstance(observed, EntryScanner)
    assert isinstance(observed, MemoryStore)

    class _NoScan:
        def __init__(self, inner: MemoryStore) -> None:
            self.inner = inner

        def __getattr__(self, name: str) -> Any:
            if name == "scan_entries":
                raise AttributeError(name)
            return getattr(self.inner, name)

    plain = observe(_NoScan(inner), lambda _c: None)
    assert not isinstance(plain, EntryScanner)


def test_sink_failure_does_not_break_writes() -> None:
    def boom(_changed: MemoryChanged) -> None:
        raise RuntimeError("허브 없음")

    service = MemoryService(InMemoryMemoryStore(), on_change=boom)
    entry = service.create(MemoryWriteRequest(scope=NOTES, key="a", content="x"))
    assert entry.version == 1


def test_loop_publisher_moves_calls_to_the_loop_thread() -> None:
    seen: list[tuple[str, int]] = []
    publisher = LoopPublisher(lambda c: seen.append((threading.current_thread().name, c.version)))
    sample = MemoryChanged(
        scope=NOTES, key="k", entry_id="e", version=1, op="create", author_kind="user"
    )
    publisher(sample)  # 루프를 묶기 전에는 바로 부른다
    assert seen == [(threading.current_thread().name, 1)]

    async def scenario() -> None:
        publisher.bind(asyncio.get_running_loop())
        worker = threading.Thread(target=publisher, args=(sample,), name="worker")
        worker.start()
        worker.join()
        await asyncio.sleep(0.01)
        publisher(sample)  # 루프 스레드에서는 바로

    asyncio.run(scenario())
    names = [name for name, _ in seen[1:]]
    assert "worker" not in names
    assert len(names) == 2


# ---------------------------------------------------------------- 포트·WS


def test_port_toolkit_writes_and_announces(
    database: SqliteDatabase, make_assembly: MakeAssembly, client_of: ClientOf
) -> None:
    section = {
        "memory": {
            "include_default_scope_kinds": False,
            "scope_kinds": {"notes": {"label": "노트", "id": "{/project_id}"}},
        }
    }
    assembly = make_assembly(database=database, settings=section, options={"max_search_results": 3})
    port = assembly.port(MEMORY_SERVICE)
    assert port is not None
    access = MemoryAccessConfig(
        scopes=[MemoryScopeAccess(kind="notes", access=["read", "search", "write"])]
    )
    kit = port.toolkit(access, MemoryAccessContext(project_id="p1", run_id="r1", agent_id="a"))
    assert kit.max_search_results == 3
    specs = {spec.op: spec for spec in kit.specs()}
    assert set(specs) == {"read", "search", "write"}
    with client_of(assembly) as client, client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "subscribe", "payload": {"topic": MEMORY_TOPIC}})
        client.get(f"{API}/memory/scope-kinds")  # 구독이 자리 잡을 시간

        async def write() -> ToolOutcome:
            return await specs["write"].call({"key": "결정/api", "content": "v2"}, "t1")

        outcome = asyncio.run(write())
        assert not outcome.is_error, outcome.text
        message = ws.receive_json()
        assert message["type"] == "memory.changed"
        assert message["payload"]["scope"] == {"kind": "notes", "id": "p1"}
        assert message["payload"]["author_kind"] == "agent"
        listed = client.get(f"{API}/memory/entries").json()["items"]
        assert listed[0]["updated_by"]["run_id"] == "r1"


def test_scope_kind_plugins_from_host_registries(
    make_assembly: MakeAssembly, client_of: ClientOf
) -> None:
    registries = ExtensionRegistries()
    registry = registries.extension(MEMORY_SCOPE_KINDS_EXTENSION, validator=ensure_scope_kinds)
    week = MemoryScopeKind(
        id="week",
        label="주차",
        resolver=lambda _ctx: "2026-W44",
        origin="plugin:example-dist",
    )
    registry.register("week", (week,), source="test")
    with client_of(make_assembly(registries=registries)) as client:
        kinds = {k["kind"]: k for k in client.get(f"{API}/memory/scope-kinds").json()["kinds"]}
    assert kinds["week"]["origin"] == "plugin:example-dist"
    assert kinds["week"]["context_fields"] == []
    with pytest.raises(TypeError):
        ensure_scope_kinds(["not", "kinds"])


def test_host_plugin_loader_reads_entry_points_into_registries() -> None:
    registries = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=registries, enabled=None))
    assert all(group == MEMORY_SCOPE_KINDS_EXTENSION for group, _ in reports)
    assert MEMORY_SCOPE_KINDS_EXTENSION in registries.extensions


# ---------------------------------------------------------------- 설정 해석


def test_settings_from_workspace_model_extra(
    make_assembly: MakeAssembly, client_of: ClientOf, warning_codes: Callable[[Assembly], list[str]]
) -> None:
    """공통 설정 모델은 섹션을 모르는 키로 보존한다(모델 그대로 받아도 읽힌다)."""
    document = WorkspaceSettings.model_validate(
        {"memory": {"include_default_scope_kinds": False, "secrets": "nope"}}
    )
    assembly = make_assembly(settings=document)
    with client_of(assembly) as client:
        assert client.get(f"{API}/memory/scope-kinds").json()["kinds"] == []
    assert KnownIssueCodes.MEMORY_SETTINGS_INVALID in warning_codes(assembly)


def test_parse_keeps_valid_parts() -> None:
    raw = {
        "secrets": "redact",
        "max_versions_per_entry": 0,
        "scope_kinds": {"ok": {"label": "좋음", "id": ""}, "Bad Id": {"label": "x"}, "off": None},
        "retention": {"rules": [{"id": "r", "when": {}, "action": "archive"}, {"nope": 1}]},
        "future_key": 1,
    }
    settings, issues = parse_memory_settings(raw)
    assert settings.secrets == "redact"
    assert settings.max_versions_per_entry == 50
    assert set(settings.scope_kinds) == {"ok", "off"}
    assert [r.id for r in settings.retention.rules] == ["r"]
    paths = sorted(i.path or "" for i in issues)
    assert "/memory/max_versions_per_entry" in paths
    assert "/memory/scope_kinds/Bad Id" in paths
    assert "/memory/retention/rules/1" in paths
    assert all(i.severity == "warning" for i in issues)
    assert parse_memory_settings("text")[1][0].path == "/memory"
    assert parse_memory_settings(None) == (parse_memory_settings({})[0], [])


def test_policy_follows_user_settings() -> None:
    section: dict[str, Any] = {}
    store = InMemoryMemoryStore()
    service = MemoryService(store, section=lambda: section)

    def mode() -> str:
        return store.policy.secrets.mode

    assert mode() == "reject"
    section.update({"secrets": "redact", "max_versions_per_entry": 3})
    assert service.settings().secrets == "redact"
    assert mode() == "redact"
    assert store.policy.max_versions_per_entry == 3


def test_installer_limits_reach_store_and_transfer() -> None:
    options = MemoryModuleSettings(max_entry_bytes=10, max_import_files=7)
    assert options.limits().max_entry_bytes == 10
    assert options.transfer_limits().max_files == 7
    defaults = MemoryModuleSettings()
    assert defaults.retention_interval_seconds > 0
    assert defaults.store_path is None


# ---------------------------------------------------------------- 정리 스케줄


def test_periodic_retention_applies_saved_rules() -> None:
    rule = {
        "id": "temp",
        "when": {"all": [{"path": "/tags", "op": "contains", "value": "임시"}]},
        "action": "delete",
    }
    from agent_console_conditions import default_operators

    operators, _ = default_operators()
    service, _changes = _service(
        section={"retention": {"rules": [rule]}}, operators=lambda: operators
    )
    entry = service.create(MemoryWriteRequest(scope=NOTES, key="a", content="x", tags=["임시"]))
    assert service.has_retention_rules()

    async def scenario() -> None:
        task = asyncio.create_task(run_retention_periodically(service, 0.01))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if service.store.get(entry.id) is None:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    gone = service.store.get(entry.id, include_deleted=True)
    assert gone is not None
    assert gone.deleted_at is not None
    assert gone.updated_by.label == "temp"


def test_module_skips_scheduler_when_interval_zero(make_assembly: MakeAssembly) -> None:
    assembly = make_assembly(options={"retention_interval_seconds": 0})
    assert assembly.parts["mod-memory"].background == []
    assembly = make_assembly()
    assert len(assembly.parts["mod-memory"].background) == 1


# ---------------------------------------------------------------- 단독 실행


def test_standalone_serves_memory_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    config = tmp_path / "standalone.json"
    config.write_text(
        json.dumps({"port": 0, "workspace": "ws", "state": "state", "security": {"token": TOKEN}}),
        encoding="utf-8",
    )
    seen: dict[str, Any] = {}

    def serve(app: Any, settings: HostSettings) -> None:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            client.headers["X-Console-Token"] = TOKEN
            created = client.post(
                f"{API}/memory/entries",
                json={"scope": {"kind": "notes", "id": ""}, "key": "a", "content": "x"},
            )
            seen["created"] = created.status_code
            seen["modules"] = [m["id"] for m in client.get(f"{API}/modules").json()]

    out = io.StringIO()
    code = main(["--config", str(config)], serve=serve, out=out, environ={})
    assert code == 0, out.getvalue()
    assert seen["created"] == 201
    assert "mod-memory" in seen["modules"]
    assert (tmp_path / "state" / "console.sqlite3").is_file()
