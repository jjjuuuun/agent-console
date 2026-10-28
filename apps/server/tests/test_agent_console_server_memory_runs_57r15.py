"""5.7R.15: 설치된 서버에서 메모리·실행 연동(`link-memory-runs`) 모듈 매트릭스(design §5.7R.2 표).

- 전부 켜짐: 연동이 active·웹 역할 `memory:runs`, 메모리 리소스를 붙인 에이전트가 fake-agent
  실행에서 도구로 쓰고 읽는다(`memory.*` 이벤트, 본문 없음), 메모리 REST에 쓴 주체(실행)가 보인다.
- `mod-memory` 끔(연동 unsatisfied)·연동 끔: 실행은 정상, "적용하지 못한 칸" 경고(R13.5) 1건.

범위 종류는 이 테스트의 사용자 설정 데이터(`notes`)이고 패키지 기본 범위 종류를 끈다. 리소스 종류
id·칸 이름은 연동 패키지 데이터에서 읽는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_link_memory_runs import load_memory_resource_type, memory_slot
from agent_console_server.testing import API, agent_doc, make_settings, server, wait_run

LINK = "link-memory-runs"
RTYPE = load_memory_resource_type()
BODY = "결정: 응답 형식은 JSON v2"
QUIET = {"mod-logs": {"startup_scan": False, "scan_interval_seconds": 0}}


def _settings_file(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    section = {
        "include_default_scope_kinds": False,
        "scope_kinds": {"notes": {"label": "노트", "id": "{/graph_id}"}},
    }
    (ws / "settings.yaml").write_text(json.dumps({"memory": section}, ensure_ascii=False), "utf-8")


def _seed(client: Any) -> None:
    resource = {
        "id": "mem",
        "type": RTYPE.id,
        "name": "노트 접근",
        "config": {"scopes": [{"kind": "notes", "access": ["read", "search", "write"]}]},
    }
    assert client.post(f"{API}/resources", json=resource).status_code == 201
    calls = [
        {"tool": "memory_write", "input": {"key": "결정/형식", "content": BODY}, "append": False},
        {"tool": "memory_read", "input": {"key": "결정/형식"}, "append": False},
    ]
    writer = agent_doc("writer", "$host_1_status|$host_2", resources=[{"ref": "mem"}])
    writer["backend_options"]["default"]["host_tool_calls"] = calls
    assert client.post(f"{API}/agents", json=writer).status_code == 201
    graph = {
        "id": "g1",
        "name": "팀",
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "w", "type": "agent", "label": "w", "config": {"agent_ref": "writer"}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "w", "port": "in"},
                "kind": "message",
                "config": {},
            },
            {
                "id": "r1",
                "source": {"node": "w", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }
    assert client.post(f"{API}/graphs", json=graph).status_code == 201


def _run(client: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    created = client.post(f"{API}/runs", json={"graph_id": "g1", "input": {"text": "시작"}})
    assert created.status_code == 202, created.text
    run = wait_run(client, created.json()["id"])["run"]
    events: list[dict[str, Any]] = client.get(f"{API}/runs/{run['id']}/events").json()
    return run, events


def _slot_warnings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e["payload"]["details"]
        for e in events
        if e["type"] == "log.warning"
        and e["payload"]["details"].get("code") == "resource.slot_unsupported"
    ]


def test_all_on_agent_uses_memory_tools(tmp_path: Path) -> None:
    _settings_file(tmp_path)
    with server(make_settings(tmp_path, options=QUIET)) as client:
        infos = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert infos[LINK]["status"] == "active"
        assert infos[LINK]["web_roles"] == ["memory:runs"]
        assert RTYPE.id in {t["id"] for t in client.get(f"{API}/resource-types").json()}
        _seed(client)
        run, events = _run(client)
        assert run["status"] == "completed", run
        mem = [e for e in events if e["type"].startswith("memory.")]
        assert [(e["type"], e["payload"]["status"]) for e in mem] == [
            ("memory.write", "ok"),
            ("memory.read", "ok"),
        ]
        assert mem[0]["payload"]["scope"] == {"kind": "notes", "id": "g1"}
        assert all(BODY not in json.dumps(e["payload"], ensure_ascii=False) for e in mem)
        assert _slot_warnings(events) == []
        page = client.get(f"{API}/memory/entries", params={"author_run": run["id"]}).json()
        [item] = page["items"]
        assert (item["key"], item["updated_by"]["run_id"]) == ("결정/형식", run["id"])


@pytest.mark.parametrize(("off", "state"), [("mod-memory", "unsatisfied"), (LINK, "disabled")])
def test_off_runs_normally_with_one_warning(tmp_path: Path, off: str, state: str) -> None:
    _settings_file(tmp_path)
    settings = make_settings(tmp_path, options=QUIET, modules={"disabled": [off]})
    with server(settings) as client:
        statuses = {m["id"]: m["status"] for m in client.get(f"{API}/modules").json()}
        assert statuses[LINK] == state
        _seed(client)  # 리소스 종류는 연동을 꺼도 등록돼 있다
        run, events = _run(client)
        assert run["status"] == "completed", run
        assert [e for e in events if e["type"].startswith("memory.")] == []
        [warning] = _slot_warnings(events)
        assert (warning["slot"], warning["resources"]) == (memory_slot(RTYPE), ["mem"])
