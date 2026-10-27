"""단독 실행 부품: mod-logs·mod-architecture 없이 testing 모듈로 조립(``python -m … --check``와 같은
조합). 포트 모양 검사."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from agent_console_link_logs_architecture import (
    ArchitectureCatalogReader,
    LogQueryReader,
    module,
)
from agent_console_link_logs_architecture.testing import (
    IndexLogQuery,
    StaticCatalog,
    demo_profiles,
    local_catalog_module,
    local_logs_module,
)
from agent_console_logs import IndexBatch
from agent_console_logs.testing import MemoryLogIndex, make_record
from agent_console_modkit import BaseServices, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app

TOKEN = "t" * 32


def test_port_shapes() -> None:
    assert isinstance(IndexLogQuery(MemoryLogIndex()), LogQueryReader)
    assert isinstance(StaticCatalog({}), ArchitectureCatalogReader)


def test_local_modules_serve_architecture(tmp_path: Path) -> None:
    index = MemoryLogIndex()
    index.write(
        IndexBatch(
            records=[
                make_record("tool", source="a1", session="s1", tool="Read", tags=("tool_call",)),
                make_record("input", source="a1", session="s1"),
            ]
        )
    )
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "st")
    )
    assembly = assemble(
        [
            local_logs_module(index=index),
            local_catalog_module(profiles=demo_profiles()),
            module,
        ],
        base=base,
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    with TestClient(create_host_app(assembly, policy=policy)) as client:
        client.headers["X-Console-Token"] = TOKEN
        body = client.get("/api/v1/logs/architecture", params={"session": "s1"}).json()
        counts = {c["id"]: c["metrics"]["count"]["value"] for c in body["cells"]}
        assert (counts["tools"], counts["input"], body["event_total"]) == (1, 1, 2)
        call = next(e for e in body["edges"] if e["id"] == "call")
        assert call["metrics"]["count"]["value"] == 1
        assert call["from"] == "model"


def test_module_check_runs_without_with() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_logs_architecture", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "link-logs-architecture" in done.stdout
