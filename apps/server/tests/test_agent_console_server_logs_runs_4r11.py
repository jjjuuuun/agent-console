"""4R.11(R8.1·R8.4): 서버 조립 수준에서 fake 실행 → 로그.

- 플랫폼 실행 이벤트가 `platform-runs` 출처로 로그 검색에 보이고, fake `observe` 규칙의 hook·MCP
  이벤트가 범주 `hook`·`mcp`와 소요 시간으로 세션 타임라인에 보인다.
- 실행 상세 "세션 로그"(`GET /runs/{id}/logs`)는 그 Run 세션의 외부 세션 이벤트(fake가 흉내 낸
  hook probe 기록)를 `total`과 함께 돌려준다.
- 연동을 끄면 `/runs/{id}/logs`가 404이고 출처 목록에 `platform-runs`가 없다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server, wait_run

OBSERVE_RULES: list[dict[str, Any]] = [
    {"type": "hook.invoked", "payload": {"event": "PreToolUse", "hook_type": "sdk-callback"}},
    {
        "type": "hook.finished",
        "after": "tool",
        "payload": {"event": "PreToolUse", "name": "guard", "exit_code": 0, "duration_ms": 40},
    },
    {
        "type": "mcp.call_started",
        "after": "tool",
        "payload": {"server": "docs", "tool": "lookup", "tool_use_id": "$session_id:tool0"},
    },
    {
        "type": "mcp.call_completed",
        "after": "tool",
        "payload": {"server": "docs", "tool": "lookup", "tool_use_id": "$session_id:tool0"},
    },
]
PROBE_RULE: list[dict[str, Any]] = [{"event": "Stop", "after": "end", "duration_ms": 5}]


def _graph() -> dict[str, Any]:
    return {
        "id": "g-logs",
        "name": "로그",
        "inputs": [{"name": "request"}],
        "nodes": [
            {"id": "you", "type": "user"},
            {"id": "a", "type": "agent", "config": {"agent_ref": "watcher"}},
        ],
        "edges": [
            {
                "id": "m",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "a", "port": "in"},
                "kind": "message",
                "config": {"input_key": "request"},
            },
            {
                "id": "r",
                "source": {"node": "a", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
                "config": {},
            },
        ],
    }


def _run(client: Any) -> dict[str, Any]:
    agent = {
        "id": "watcher",
        "name": "watcher",
        "backend": "fake-agent",
        "backend_options": {
            "default": {
                "response": "ok",
                "tool_calls": [{"name": "mcp__docs__lookup", "input": {"q": "x"}}],
                "observe": OBSERVE_RULES,
                "hook_probe": PROBE_RULE,
            }
        },
        "observe": {"hooks": True, "mcp": True, "hook_probe": True},
    }
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    assert client.post(f"{API}/graphs", json=_graph()).status_code == 201
    run = client.post(f"{API}/runs", json={"graph_id": "g-logs", "input": {"request": "go"}})
    snap = wait_run(client, run.json()["id"])
    assert snap["run"]["status"] == "completed", snap["run"]
    return snap


def _until(client: Any, path: str, params: dict[str, str], count: int) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    body: dict[str, Any] = {}
    while time.monotonic() < deadline:
        body = client.get(f"{API}{path}", params=params).json()
        if len(body.get("items", [])) >= count:
            return body
        time.sleep(0.1)
    raise AssertionError(f"{path} {params}: {body}")


def test_fake_run_events_show_in_logs_with_hook_mcp_and_session_logs(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        snap = _run(client)
        run_id = snap["run"]["id"]
        (session,) = {n["backend_session_id"] for n in snap["node_runs"] if n["node_id"] == "a"}
        # runs.event 구독(디바운스) → 수집 예약: 수동 수집 없이도 색인된다
        query = {"source": "platform-runs", "category": "mcp"}
        mcp = _until(client, "/logs/events", query, 2)["items"]
        assert {e["stage"] for e in mcp} == {"start", "complete"}
        assert all(e["session"] == session and e["run_id"] == run_id for e in mcp)
        assert client.post(f"{API}/logs/scan").status_code == 202
        timeline = client.get(f"{API}/logs/sessions/{session}/timeline").json()
        events = timeline["events"]
        hooks = [e for e in events if e["category"] == "hook" and e["source"] == "platform-runs"]
        spans = [e for e in hooks if e["stage"] in ("start", "complete")]
        assert [e["stage"] for e in spans] == ["start", "complete"]
        assert all(abs(e["duration_ms"] - 40) < 1e-3 for e in spans)
        assert any(e["category"] == "mcp" and e["duration_ms"] is not None for e in events)
        # 실행 상세 "세션 로그": 외부 세션 이벤트(hook probe 기록)만, total 채움
        logs = _until(client, f"/runs/{run_id}/logs", {}, 1)
        assert logs["total"] == len(logs["items"]) >= 1
        assert {e["source"] for e in logs["items"]} == {"hook-probe-jsonl"}
        assert {e["session"] for e in logs["items"]} == {session}
        assert client.get(f"{API}/runs/missing/logs").status_code == 404


def test_link_off_hides_session_logs_and_platform_source(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["link-logs-runs"]})
    with server(settings) as client:
        snap = _run(client)
        assert client.get(f"{API}/runs/{snap['run']['id']}/logs").status_code == 404
        ids = [s["descriptor"]["id"] for s in client.get(f"{API}/logs/sources").json()]
        assert "platform-runs" not in ids
        modules = {m["id"]: m for m in client.get(f"{API}/modules").json()}
        assert modules["link-logs-runs"]["status"] == "disabled"
        assert modules["mod-logs"]["status"] == "active"
