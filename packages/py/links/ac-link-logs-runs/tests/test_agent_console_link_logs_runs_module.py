"""link-logs-runs 모듈: 실제 mod-logs와 조립, runs.event 구독 → 수집, /runs/{id}/logs, 끄기,
포트 계약."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, NodeRun, WorkspaceSettings
from agent_console_contracts.logs import LogSettings
from agent_console_link_logs_runs import (
    LOG_SOURCES,
    LOGS_INGEST,
    LOGS_QUERY,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    EventReader,
    LogIngestLike,
    LogQueryLike,
    RunReader,
    module,
)
from agent_console_link_logs_runs.testing import (
    MemoryRunRecords,
    run_event,
    run_record,
    runs_module,
)
from agent_console_mod_logs import RuntimeLogSource
from agent_console_mod_logs import module as logs_module
from agent_console_mod_logs.testing import static_settings_module
from agent_console_mod_runs import module as runs_feature
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    EventBus,
    Module,
    ModulesConfig,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app

API = "/api/v1"
TOKEN = "t" * 32
OPTIONS: dict[str, dict[str, Any]] = {
    "mod-logs": {"scan_interval_seconds": 0, "startup_scan": False},
    "link-logs-runs": {"debounce_seconds": 0},
}


def _records() -> MemoryRunRecords:
    records = MemoryRunRecords()
    records.runs.save(run_record("r1"))
    records.runs.save(run_record("r2", created_at=2.0))
    records.runs.save_node_run(
        NodeRun(run_id="r1", node_id="b", status="succeeded", backend_session_id="s2")
    )
    records.events.append(
        run_event(1, "agent.session_started", {"session_id": "s1", "backend": "fake-agent"}),
        run_event(2, "agent.message", {"role": "assistant", "text": "안녕"}),
        run_event(1, "node.started", {"status": "running"}, ("x",), run_id="r2"),
    )
    return records


def _external_logs(folder: Path) -> WorkspaceSettings:
    rows = [
        {"schema_version": 1, "category": "llm", "title": "외부 s1", "session": "s1"},
        {"schema_version": 1, "category": "tool", "title": "외부 s2", "session": "s2"},
        {"schema_version": 1, "category": "llm", "title": "다른 세션", "session": "zz"},
    ]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    source = {"id": "normalized-v1", "enabled": True, "config": {"roots": [str(folder)]}}
    return WorkspaceSettings(logs=LogSettings.model_validate({"sources": [source]}))


@contextmanager
def _client(
    tmp_path: Path,
    records: MemoryRunRecords,
    *,
    disabled: tuple[str, ...] = (),
    bus: EventBus | None = None,
) -> Iterator[tuple[TestClient, Assembly]]:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        events=bus or EventBus(),
    )
    modules: list[Module] = [
        logs_module,
        static_settings_module(_external_logs(tmp_path / "ext")),
        runs_module(records),
        module,
    ]
    config = ModulesConfig(options=OPTIONS, disabled=list(disabled))
    assembly = assemble(modules, config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, assembly


def _titles(body: dict[str, Any]) -> list[str]:
    return [item["title"] for item in body["items"]]


def test_run_logs_are_external_session_events_with_total(tmp_path: Path) -> None:
    with _client(tmp_path, _records()) as (client, assembly):
        assert all(r.state.value == "active" for r in assembly.report), assembly.report
        assert client.post(f"{API}/logs/scan").status_code == 202
        body = client.get(f"{API}/runs/r1/logs").json()
        # 세션 s1(알린 이벤트) + s2(NodeRun) — 플랫폼 실행 이벤트 자체는 빠진다
        assert sorted(_titles(body)) == ["외부 s1", "외부 s2"]
        assert body["total"] == 2
        narrowed = client.get(f"{API}/runs/r1/logs", params={"category": "tool"}).json()
        assert (_titles(narrowed), narrowed["total"]) == (["외부 s2"], 1)
        platform = client.get(f"{API}/runs/r1/logs", params={"source": "platform-runs"}).json()
        assert _titles(platform) == ["세션 시작 s1", "안녕"]
        assert platform["total"] == 2
        none = client.get(f"{API}/runs/r2/logs").json()
        assert none == {"items": [], "total": 0, "next_cursor": None}


def test_run_logs_errors(tmp_path: Path) -> None:
    with _client(tmp_path, _records()) as (client, _assembly):
        missing = client.get(f"{API}/runs/nope/logs")
        assert missing.status_code == 404
        bad = client.get(f"{API}/runs/r1/logs", params={"bogus": "1"})
        assert bad.status_code == 422
        details = bad.json()["error"]["details"]
        assert details["path"] == "bogus"
        assert details["issues"][0]["code"] == "logs.invalid_query"


def test_platform_runs_listed_and_runs_event_schedules_scan(tmp_path: Path) -> None:
    records = _records()
    bus = EventBus()
    with _client(tmp_path, records, bus=bus) as (client, _assembly):
        sources = {s["descriptor"]["id"]: s for s in client.get(f"{API}/logs/sources").json()}
        assert sources["platform-runs"]["origin"] == "runtime"
        assert sources["platform-runs"]["enabled"] is True
        assert sources["platform-runs"]["descriptor"]["reads_paths"] is False
        assert (
            client.get(f"{API}/logs/events", params={"source": "platform-runs"}).json()["items"]
            == []
        )
        records.events.append(run_event(3, "mcp.call_started", {"server": "d", "tool": "t"}))
        bus.publish(RUNS_EVENT, records.events.list("r1", since_seq=2)[0])
        deadline = time.monotonic() + 10
        items: list[Any] = []
        while time.monotonic() < deadline and not items:
            items = client.get(
                f"{API}/logs/events", params={"source": "platform-runs", "category": "mcp"}
            ).json()["items"]
            time.sleep(0.05)
        assert [i["title"] for i in items] == ["MCP d/t"]


def test_disabled_link_hides_route_and_runtime_source(tmp_path: Path) -> None:
    with _client(tmp_path, _records(), disabled=("link-logs-runs",)) as (client, assembly):
        assert assembly.status("link-logs-runs") is not None
        assert client.get(f"{API}/runs/r1/logs").status_code == 404
        ids = [s["descriptor"]["id"] for s in client.get(f"{API}/logs/sources").json()]
        assert "platform-runs" not in ids
        assert "normalized-v1" in ids
        assert client.post(f"{API}/logs/scan").status_code == 202  # 로그는 그대로 동작


def test_requires_logs_and_runs_ports() -> None:
    assembly = assemble([module])
    [report] = assembly.report
    assert report.state.value == "unsatisfied"
    assert set(report.missing) == {"logs.ingest", "logs.query", "runs.reader", "runs.events"}
    assert module.descriptor.web_roles == ("logs:runs",)


def test_real_providers_satisfy_consumer_protocols(tmp_path: Path) -> None:
    """포트 계약: mod-logs·mod-runs의 제공 구현 ↔ 이 연동의 소비 프로토콜, 이 연동의 항목 ↔
    mod-logs의 ``logs.sources`` 소비 프로토콜."""
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble(
        [logs_module, runs_feature, local_definitions_module(), module],
        ModulesConfig(options=OPTIONS),
        base=base,
    )
    assert all(r.state.value == "active" for r in assembly.report), assembly.report
    assert isinstance(assembly.port(LOGS_INGEST), LogIngestLike)
    assert isinstance(assembly.port(LOGS_QUERY), LogQueryLike)
    assert isinstance(assembly.port(RUNS_READER), RunReader)
    assert isinstance(assembly.port(RUNS_EVENTS), EventReader)
    [item] = assembly.ports(LOG_SOURCES)
    assert isinstance(item, RuntimeLogSource)
