"""단독 실행 부품: mod-logs·mod-runs 없이 testing 모듈로 조립(``python -m … --check``와 같은
조합)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from agent_console_link_logs_runs import RUNS_EVENT, LogIngestLike, LogQueryLike, module
from agent_console_link_logs_runs.testing import (
    LocalLogs,
    MemoryRunRecords,
    local_logs_module,
    run_event,
    run_record,
    runs_module,
)
from agent_console_modkit import BaseServices, EventBus, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

TOKEN = "t" * 32


def test_local_modules_serve_run_logs(tmp_path: Path) -> None:
    logs = LocalLogs()
    assert isinstance(logs, LogIngestLike)
    assert isinstance(logs, LogQueryLike)
    records = MemoryRunRecords()
    records.runs.save(run_record("r1"))
    bus = EventBus()
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st"),
        events=bus,
    )
    assembly = assemble([local_logs_module(logs=logs), runs_module(records), module], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        first = run_event(1, "agent.session_started", {"session_id": "s1", "backend": "fake"})
        records.events.append(first)
        bus.publish(RUNS_EVENT, first)  # 루프 밖 발행 → 바로 수집 예약 → LocalLogs는 바로 수집
        body = client.get("/api/v1/runs/r1/logs", params={"source": "platform-runs"}).json()
        assert (body["total"], body["items"][0]["session"]) == (1, "s1")
        assert client.get("/api/v1/runs/r1/logs").json()["total"] == 0  # 외부 세션 이벤트 없음


def test_module_check_runs_without_with() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_logs_runs", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "link-logs-runs" in done.stdout
