"""mod-logs: 서술자·플러그인 로더·REST 전부·422·WS·경고·가리기·출처 실패 격리·런타임 출처·
배경 수집·보존·템플릿·끄기(design §4R.4·§4R.8·§4R.10, 작업 4R.10).

공개 저장소에는 로그 픽스처가 없어 픽스처를 읽는 테스트는 뺐다.
출처는 ac-logs 기본 플러그인(``normalized-v1``·``mapped-jsonl``)만 쓴다 — 이 패키지
단독 설치에서도 돈다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_contracts.logs import (
    LogClassifierDescriptor,
    LogSourceDescriptor,
)
from agent_console_logs import (
    ClassifyContext,
    Cursor,
    LogEventDraft,
    LogSourceContext,
    RawRecord,
    ReadResult,
    SourceRef,
)
from agent_console_mod_logs import (
    BRANCH,
    LOGS_INGEST,
    LOGS_QUERY,
    SECRET_RULES,
    SERVER_WARNINGS,
    WEB_ROLES,
    LogIngestPort,
    LogQueryPort,
    LogsModuleSettings,
    LogsService,
    module,
)
from agent_console_mod_logs.plugins import REPORT_GROUPS, load_plugins
from agent_console_mod_logs.testing import (
    RuntimeSource,
    runtime_sources_module,
    static_settings_module,
)
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ExtensionRegistries,
    Module,
    ModulesConfig,
    Paths,
    PluginLoadContext,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "t" * 32
QUIET = {"startup_scan": False, "scan_interval_seconds": 0}
"""배경 수집 없음(테스트가 직접 수집한다)."""
PROJECTS = {"groups": [{"id": "proj-a", "label": "프로젝트 A", "match": ["/work/proj-a/**"]}]}
FIXTURE_EVENTS = 9


# ---------------------------------------------------------------- 도우미


def _workspace(root: Path, *, extra: Sequence[Mapping[str, Any]] = (), **logs: Any) -> Any:
    sources = [{"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}, *extra]
    return WorkspaceSettings.model_validate(
        {"logs": {"sources": sources, "projects": PROJECTS, **logs}}
    )


def _assembly(
    tmp_path: Path,
    modules: Sequence[Module] = (),
    *,
    options: Mapping[str, Any] | None = None,
    database: bool = True,
    disabled: Sequence[str] = (),
    clock: Any = None,
) -> Assembly:
    db = SqliteDatabase.open(tmp_path / "host.sqlite3") if database else None
    services = BaseServices(
        database=db,
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        **({"clock": clock} if clock is not None else {}),
    )
    config = ModulesConfig(
        options={"mod-logs": {**QUIET, **(options or {})}}, disabled=list(disabled)
    )
    return assemble([module, *modules], config, base=services)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _warnings(assembly: Assembly) -> list[str]:
    return [i.code for source in assembly.ports(SERVER_WARNINGS) for i in source()]


def _service(assembly: Assembly) -> LogsService:
    found = assembly.port(LOGS_QUERY)
    assert isinstance(found, LogsService)
    return found


# ---------------------------------------------------------------- 서술자·로더


def test_descriptor_declares_ports_roles_and_lineage() -> None:
    d = module.descriptor
    assert d.id == "mod-logs"
    assert d.kind == "feature"
    assert {p.name for p in d.provides} == {"logs.query", "logs.ingest", "server.warnings"}
    assert {p.name for p in d.optional} == {
        "logs.sources",
        "workspace.settings",
        "secrets.rules",
        "logs.source_defaults",
        "logs.scope_kinds",
        "logs.filter_predicates",
        "projects.folders",
    }
    assert d.requires == ()
    assert d.web_roles == WEB_ROLES == ("logs",)
    assert d.migrations == (BRANCH,)
    assert d.settings_schema is LogsModuleSettings
    assert "logs" in d.contracts


def test_settings_defaults_match_design() -> None:
    cfg = LogsModuleSettings()
    assert cfg.scan_interval_seconds == 30
    assert cfg.startup_scan is True
    assert cfg.scan_budget_bytes == 8_000_000
    assert cfg.batch_size == 500
    assert cfg.retention_days is None
    assert cfg.index_path is None
    assert cfg.max_detail_bytes == 80_000
    assert cfg.dashboard_templates_dir is None
    with pytest.raises(ValueError, match="extra"):
        LogsModuleSettings.model_validate({"unknown": 1})


def test_plugin_loader_fills_bundle_extensions() -> None:
    bundle = ExtensionRegistries()
    reports = load_plugins(PluginLoadContext(registries=bundle))
    groups = {group for group, _ in reports}
    assert groups <= set(REPORT_GROUPS)
    assert {"log_sources", "log_classifiers"} <= groups
    sources = bundle.extension("log_sources")
    classifiers = bundle.extension("log_classifiers")
    assert "normalized-v1" in sources
    assert "mapped-jsonl" in sources
    assert "normalized-v1" in classifiers
    # plugins.enabled로 거른다(이름이 없으면 skipped)
    other = ExtensionRegistries()
    load_plugins(PluginLoadContext(registries=other, enabled=frozenset({"mapped-jsonl"})))
    assert "mapped-jsonl" in other.extension("log_sources")
    assert "normalized-v1" not in other.extension("log_sources")


def test_module_uses_host_bundle_when_present(tmp_path: Path) -> None:
    bundle = ExtensionRegistries()
    load_plugins(PluginLoadContext(registries=bundle, enabled=frozenset({"mapped-jsonl"})))
    services = BaseServices(registries=bundle)
    assembly = assemble([module], ModulesConfig(options={"mod-logs": QUIET}), base=services)
    ids = [s.descriptor.id for s in _service(assembly).sources()]
    assert ids == ["mapped-jsonl"]


# ---------------------------------------------------------------- REST


def test_dashboard_templates_have_size_and_no_period(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        templates = client.get(f"{API}/logs/dashboard-templates").json()
    assert templates, "패키지 기본 템플릿이 1개 이상"
    ids = [t["id"] for t in templates]
    assert len(ids) == len(set(ids))
    for template in templates:
        assert template["widgets"]
        for widget in template["widgets"]:
            assert isinstance(widget["options"]["w"], int)
            assert widget["options"]["w"] > 0
            assert isinstance(widget["options"]["h"], int)
            assert widget["options"]["h"] > 0
            assert not {"since", "until"} & set(widget["query"]["filter"])
    # 프로젝트 · 모델 토큰 위젯(§4R.0-4)이 기본 템플릿에 있다
    queries = [w["query"] for t in templates for w in t["widgets"]]
    assert {"group_by": ["project", "model"], "metric": "tokens.total", "filter": {}} in queries


def test_dashboard_templates_dir_option_and_deleted_templates(tmp_path: Path) -> None:
    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "mine.json").write_text(
        json.dumps({"id": "mine", "title": "내 것", "widgets": []}), encoding="utf-8"
    )
    (folder / "broken.yaml").write_text("id: [", encoding="utf-8")
    (folder / "notes.txt").write_text("무시", encoding="utf-8")
    assembly = _assembly(tmp_path, options={"dashboard_templates_dir": "templates"})
    with _client(assembly) as client:
        assert [t["id"] for t in client.get(f"{API}/logs/dashboard-templates").json()] == ["mine"]
    gone = _assembly(tmp_path / "x", options={"dashboard_templates_dir": str(tmp_path / "none")})
    with _client(gone) as client:
        assert client.get(f"{API}/logs/dashboard-templates").json() == []
        assert client.get(f"{API}/logs/sources").status_code == 200


# ---------------------------------------------------------------- WS·토픽


# ---------------------------------------------------------------- 저장·경고·가리기


def test_without_database_uses_memory_and_warns(tmp_path: Path) -> None:
    assembly = _assembly(tmp_path, database=False)
    codes = _warnings(assembly)
    assert "logs.storage_memory" in codes
    assert "logs.redaction_unavailable" in codes
    with _client(assembly) as client:
        assert client.get(f"{API}/logs/events").json()["items"] == []


class _Rules:
    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("sk-test-secret", "***")
        if isinstance(value, dict):
            return {k: self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact_value(v) for v in value]
        return value


def _rules_module() -> Module:
    rules = _Rules()
    return fake_module(
        "my-rules",
        provides=[SECRET_RULES],
        on_build=lambda ctx: ctx.provide(SECRET_RULES, lambda: rules),
    )


def _secret_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "secret-src"
    root.mkdir()
    row = {"schema_version": 1, "category": "input", "title": "키 sk-test-secret", "session": "s"}
    (root / "a.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return root


def test_redaction_applies_with_rules_port_and_respects_setting(tmp_path: Path) -> None:
    root = _secret_fixture(tmp_path)
    on = _assembly(tmp_path / "on", [static_settings_module(_workspace(root)), _rules_module()])
    assert "logs.redaction_unavailable" not in _warnings(on)
    with _client(on) as client:
        client.post(f"{API}/logs/scan")
        title = client.get(f"{API}/logs/events").json()["items"][0]["title"]
    assert "sk-test-secret" not in title
    assert "***" in title

    off_settings = _workspace(root, **{})
    off_settings = off_settings.model_copy(
        update={
            "secrets": off_settings.secrets.model_copy(update={"redact_suspected_in_logs": False})
        }
    )
    off = _assembly(tmp_path / "off", [static_settings_module(off_settings), _rules_module()])
    with _client(off) as client:
        client.post(f"{API}/logs/scan")
        title = client.get(f"{API}/logs/events").json()["items"][0]["title"]
    assert "sk-test-secret" in title
    # 규칙 포트가 없어도 설정이 가리기를 끄면 경고하지 않는다
    quiet = _assembly(tmp_path / "quiet", [static_settings_module(off_settings)])
    assert "logs.redaction_unavailable" not in _warnings(quiet)


# ---------------------------------------------------------------- 출처 실패 격리


# ---------------------------------------------------------------- 런타임 출처(X5r)


class _MemorySource:
    descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
        id="mem-runtime", title="메모리", format="mem", default_enabled=True, reads_paths=False
    )

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self.rows = list(rows)

    def discover(self, ctx: LogSourceContext) -> Iterator[SourceRef]:
        yield SourceRef(ref="r1", size=len(self.rows))

    def read(
        self, ref: SourceRef, cursor: Cursor, ctx: LogSourceContext, *, budget: int, final: bool
    ) -> ReadResult:
        records = [
            RawRecord(origin=ref.ref, offset=i, data=dict(row))
            for i, row in enumerate(self.rows)
            if i >= cursor.offset
        ]
        return ReadResult(
            records=records,
            cursor=Cursor(offset=len(self.rows)),
            read_bytes=len(records),
            exhausted=True,
        )


class _MemoryClassifier:
    descriptor: ClassVar[LogClassifierDescriptor] = LogClassifierDescriptor(
        id="mem", formats=["mem"], title="메모리"
    )

    def classify(self, record: RawRecord, ctx: ClassifyContext) -> list[LogEventDraft]:
        data = record.data
        assert isinstance(data, dict)
        return [LogEventDraft(category="run", title=str(data["title"]), session="rt")]


def test_runtime_sources_port_and_ingest_port(tmp_path: Path) -> None:
    source = _MemorySource([{"title": "하나"}, {"title": "둘"}])
    dup = RuntimeSource(source=_MemorySource([]), classifier=_MemoryClassifier())
    assembly = _assembly(
        tmp_path,
        [runtime_sources_module([RuntimeSource(source, _MemoryClassifier()), dup])],
    )
    ingest = assembly.port(LOGS_INGEST)
    query = assembly.port(LOGS_QUERY)
    assert isinstance(ingest, LogIngestPort)
    assert isinstance(query, LogQueryPort)
    with _client(assembly) as client:
        sources = {s["descriptor"]["id"]: s for s in client.get(f"{API}/logs/sources").json()}
        assert sources["mem-runtime"]["origin"] == "runtime"
        assert sources["mem-runtime"]["enabled"] is True
        report = client.post(f"{API}/logs/scan", json={"source_ids": ["mem-runtime"]}).json()
        assert report["new_events"] == 2
        titles = [e["title"] for e in client.get(f"{API}/logs/events").json()["items"]]
        assert titles == ["하나", "둘"]
    # 같은 id 두 번째 런타임 출처는 거절되고 경고로 남는다
    assert "logs.source_failed" in _warnings(assembly)


def test_add_runtime_source_rejects_plugin_id(tmp_path: Path) -> None:
    service = _service(_assembly(tmp_path))

    class _Clash(_MemorySource):
        descriptor = LogSourceDescriptor(id="normalized-v1", title="겹침", format="mem")

    with pytest.raises(ValueError, match="normalized-v1"):
        service.add_runtime_source(_Clash([]), classifier=_MemoryClassifier())


# ---------------------------------------------------------------- 배경 수집·예약·보존


def _wait(predicate: Any, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("시간 안에 조건이 맞지 않았다")


# ---------------------------------------------------------------- 끄기


def test_disabled_module_paths_are_404(tmp_path: Path) -> None:
    other = fake_module("mod-other")
    assembly = _assembly(tmp_path, [other], disabled=["mod-logs"])
    states = {r.id: r.state.value for r in assembly.report}
    assert states == {"mod-logs": "disabled", "mod-other": "active"}
    with _client(assembly) as client:
        assert client.get(f"{API}/health").status_code == 200
        for path in ("/logs/sources", "/logs/events", "/logs/schema"):
            assert client.get(f"{API}{path}").status_code == 404
        assert client.post(f"{API}/logs/scan").status_code == 404
