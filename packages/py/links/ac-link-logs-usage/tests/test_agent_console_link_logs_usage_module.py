"""link-logs-usage 모듈: 포트 계약·끄기·설정·logs.ingested 무효화·실제 mod-logs/mod-usage 연결."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, WorkspaceSettings
from agent_console_contracts.logs import TokenSample
from agent_console_contracts.modules import LogsIngestedPayload
from agent_console_link_logs_usage import (
    LOGS_INGESTED,
    LocalLogsUsageSource,
    LogTokenQuery,
    module,
)
from agent_console_link_logs_usage.testing import (
    SampleQuery,
    local_logs_query_module,
    local_usage_module,
)
from agent_console_mod_logs import LOGS_INGEST, LOGS_QUERY
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_mod_usage import USAGE_SERVICE, UsageReportService
from agent_console_mod_usage import module as usage_module
from agent_console_modkit import Assembly, BaseServices, Module, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

H0 = 1_800_000_000.0
NOW = datetime.fromtimestamp(H0 + 3600.0, tz=UTC)
TOKEN = "t" * 32
MY = {"filter": {"source": "my-logs"}}


def _workspace(config: dict[str, Any] | None = None, **extra: Any) -> WorkspaceSettings:
    return WorkspaceSettings.model_validate(
        {"usage": {"sources": [{"id": "local-logs", "config": config or MY}]}, **extra}
    )


def _samples(*tokens: int) -> list[TokenSample]:
    return [
        TokenSample(message_id=f"m{i}", time=H0 + 60 * (i + 1), input_tokens=t)
        for i, t in enumerate(tokens)
    ]


def _assemble(
    modules: Sequence[Module],
    *,
    disabled: Sequence[str] = (),
    options: dict[str, Any] | None = None,
    tmp_path: Path | None = None,
) -> Assembly:
    paths = (
        Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
        if tmp_path is not None
        else None
    )
    base = BaseServices(clock=lambda: NOW, paths=paths)
    return assemble(
        list(modules),
        ModulesConfig(disabled=list(disabled), options=options or {}),
        base=base,
    )


def _usage(assembly: Assembly) -> UsageReportService:
    service = assembly.port(USAGE_SERVICE)
    assert isinstance(service, UsageReportService)
    return service


def _windows(assembly: Assembly) -> dict[str, Any]:
    report = asyncio.run(_usage(assembly).report(["windows"]))
    assert report.windows is not None
    return {w.window: w for w in report.windows if w.source == "local-logs"}


def _stack(query: SampleQuery, settings: WorkspaceSettings | None = None) -> list[Module]:
    return [
        usage_module,
        local_logs_query_module(query=query),
        static_settings_module(settings or _workspace()),
        module,
    ]


def test_descriptor_ports() -> None:
    d = module.descriptor
    assert d.kind == "link"
    assert {p.name for p in d.requires} == {"logs.query", "usage.service"}
    assert [(p.name, p.multi) for p in d.provides] == [
        ("usage.sources", True),
        ("logs.source_defaults", True),
    ]
    assert [p.name for p in d.optional] == ["logs.ingest"]
    assert d.web_roles == ()


def test_port_contract_with_real_mod_logs(tmp_path: Path) -> None:
    assembly = _assemble([logs_module], tmp_path=tmp_path)
    assert isinstance(assembly.port(LOGS_QUERY), LogTokenQuery)


def test_local_logs_source_is_listed_and_estimates_windows() -> None:
    assembly = _assemble(_stack(SampleQuery(_samples(5, 6), source="my-logs")))
    assert assembly.status("link-logs-usage").state.value == "active"  # type: ignore[union-attr]
    infos = {i.descriptor.id: i for i in _usage(assembly).sources()}
    assert infos["local-logs"].descriptor.trust == "estimated"
    windows = _windows(assembly)
    assert {k: w.used_tokens for k, w in windows.items()} == {
        "local_five_hour": 11,
        "local_seven_day": 11,
    }
    assert all(w.used_ratio is None for w in windows.values())


def test_link_off_or_usage_off_means_no_local_source() -> None:
    query = SampleQuery(_samples(5), source="my-logs")
    off = _assemble(_stack(query), disabled=["link-logs-usage"])
    ids = {i.descriptor.id for i in _usage(off).sources()}
    assert "local-logs" not in ids
    assert _windows(off) == {}
    no_usage = _assemble(_stack(query), disabled=["mod-usage"])
    assert no_usage.status("link-logs-usage").state.value == "unsatisfied"  # type: ignore[union-attr]


def test_logs_ingested_topic_invalidates_cache() -> None:
    query = SampleQuery(_samples(5), source="my-logs")
    assembly = _assemble(_stack(query))
    assert _windows(assembly)["local_five_hour"].used_tokens == 5
    query.samples.append(TokenSample(message_id="late", time=H0 + 600, input_tokens=2))
    assert _windows(assembly)["local_five_hour"].used_tokens == 5  # 캐시
    assembly.services.events.publish(
        LOGS_INGESTED, LogsIngestedPayload(source_ids=["my-logs"], count=1, max_seq=9)
    )
    assert _windows(assembly)["local_five_hour"].used_tokens == 7


def test_options_source_id_and_defaults_file(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.json"
    defaults.write_text(
        json.dumps(
            {"windows": [{"id": "my_day", "kind": "rolling", "days": 1}], "filter": MY["filter"]}
        ),
        encoding="utf-8",
    )
    query = SampleQuery(_samples(3), source="my-logs")
    settings = WorkspaceSettings.model_validate({"usage": {"sources": []}})
    assembly = _assemble(
        _stack(query, settings),
        options={"link-logs-usage": {"source_id": "mine", "defaults_file": "defaults.json"}},
        tmp_path=tmp_path,
    )
    report = asyncio.run(_usage(assembly).report(["windows"]))
    assert report.windows is not None
    assert [(w.source, w.window, w.used_tokens) for w in report.windows] == [("mine", "my_day", 3)]
    bad = _assemble(_stack(query), options={"link-logs-usage": {"nope": 1}})
    assert bad.status("link-logs-usage").state.value == "failed"  # type: ignore[union-attr]


def test_standalone_helpers_satisfy_requirements() -> None:
    assembly = _assemble([module, local_logs_query_module(), local_usage_module()])
    assert assembly.status("link-logs-usage").state.value == "active"  # type: ignore[union-attr]
    placeholder = assembly.port(USAGE_SERVICE)
    sources = placeholder.sources()  # type: ignore[union-attr]
    assert [type(s) for s in sources] == [LocalLogsUsageSource]


def test_with_real_mod_logs_scan_and_http(tmp_path: Path) -> None:
    root = tmp_path / "logs"
    root.mkdir()
    log = root / "s.jsonl"

    def line(mid: str, t: float, tokens: int) -> str:
        row = {
            "schema_version": 1,
            "category": "llm",
            "title": "답변",
            "session": "s1",
            "thread": "main",
            "message_id": mid,
            "time": t,
            "usage": {"input_tokens": tokens, "output_tokens": 1},
        }
        return json.dumps(row) + "\n"

    # 같은 message_id 두 행은 한 번만 센다(마지막 값)
    log.write_text(line("a", H0 + 60, 10) + line("a", H0 + 61, 10) + line("b", H0 + 120, 4))
    settings = WorkspaceSettings.model_validate(
        {
            "logs": {
                "sources": [
                    {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(root)]}}
                ]
            },
            "usage": {
                "sources": [{"id": "local-logs", "config": {"filter": {"source": "normalized-v1"}}}]
            },
        }
    )
    assembly = _assemble(
        [logs_module, usage_module, static_settings_module(settings), module],
        options={"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}},
        tmp_path=tmp_path,
    )
    ingest = assembly.port(LOGS_INGEST)
    assert ingest is not None
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        assert client.post("/api/v1/logs/scan", json={}).status_code == 202
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        local = {w["window"]: w for w in body["windows"] if w["source"] == "local-logs"}
        assert local["local_five_hour"]["used_tokens"] == 16
        assert local["local_five_hour"]["used_ratio"] is None
        # 새 줄 → 수집(logs.ingested 발행) → 캐시 무효화 → 새 합
        with log.open("a", encoding="utf-8") as f:
            f.write(line("c", H0 + 180, 100))
        assert client.post("/api/v1/logs/scan", json={}).status_code == 202
        body = client.get("/api/v1/usage", params={"parts": "windows"}).json()
        local = {w["window"]: w for w in body["windows"] if w["source"] == "local-logs"}
        assert local["local_five_hour"]["used_tokens"] == 117
        sources = client.get("/api/v1/usage/sources").json()
        assert "local-logs" in [s["descriptor"]["id"] for s in sources]
