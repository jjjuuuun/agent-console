"""시험 도우미: 워크스페이스(노트 리소스를 붙인 에이전트·팀), Run 실행·이벤트 고르기.

``test_assembly.py``(테스트 호스트)와 ``test_server.py``(통합 서버)가 함께 쓴다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_example_link import NotesRunsSettings, load_resource_type
from agent_console_resources import SLOT_UNSUPPORTED

API = "/api/v1"
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
TEXT = NotesRunsSettings().text()
RTYPE = load_resource_type()
NOTE = "점심 회의는 12시"


def _write(folder: Path, item_id: str, document: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item_id}.yaml").write_text(json.dumps(document, ensure_ascii=False), "utf-8")


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
        "config": {},
    }


def write_workspace(ws: Path) -> None:
    """노트 리소스를 붙인 에이전트 하나와 팀 ``solo``(사람 → 에이전트 → 사람)."""
    _write(ws / "resources", "notes", {"id": "notes", "type": RTYPE.id, "name": "노트"})
    _write(
        ws / "agents",
        "reader",
        {
            "id": "reader",
            "name": "읽는 이",
            "backend": "fake-agent",
            "backend_options": {
                "default": {
                    "response": "[$host_1_status]$host_1",
                    "host_tool_calls": [{"tool": TEXT.name, "input": {}, "append": False}],
                }
            },
            "resources": [{"ref": "notes"}],
        },
    )
    _write(
        ws / "graphs",
        "solo",
        {
            "id": "solo",
            "name": "혼자",
            "nodes": [
                {"id": "you", "type": "user", "label": "나"},
                {"id": "r", "type": "agent", "label": "r", "config": {"agent_ref": "reader"}},
            ],
            "edges": [
                _edge("m1", "you", "says", "r", "in", "message"),
                _edge("r1", "r", "out", "you", "hears", "reply"),
            ],
        },
    )


def run_team(
    client: TestClient, graph_id: str = "solo", *, project_id: str | None = None
) -> tuple[dict[str, Any], list[Any]]:
    """팀을 실행하고 끝날 때까지 기다린다(Run, 이벤트)."""
    body: dict[str, Any] = {"graph_id": graph_id, "input": {"text": "시작"}}
    if project_id is not None:
        body["project_id"] = project_id
    created = client.post(f"{API}/runs", json=body)
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run: dict[str, Any] = client.get(f"{API}/runs/{run_id}").json()["run"]
        if run["status"] in TERMINAL:
            events: list[Any] = client.get(f"{API}/runs/{run_id}/events").json()
            return run, events
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def of(events: list[Any], prefix: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"].startswith(prefix)]


def slot_warnings(events: list[Any]) -> list[dict[str, Any]]:
    return [
        e["payload"]["details"]
        for e in of(events, "log.warning")
        if e["payload"]["details"].get("code") == SLOT_UNSUPPORTED
    ]
