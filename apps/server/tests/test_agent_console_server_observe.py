"""2R.5(R8.4): fake 규칙 `observe`의 hook·MCP 이벤트가 실행 이벤트 API로 조회된다(플러그인 없이)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server, wait_run

OBSERVE_RULES: list[dict[str, Any]] = [
    {"type": "hook.invoked", "payload": {"event": "PreToolUse", "hook_type": "sdk-callback"}},
    {"type": "mcp.server_status", "payload": {"servers": [{"name": "docs", "status": "ok"}]}},
    {
        "type": "mcp.call_completed",
        "after": "end",
        "payload": {"server": "docs", "tool": "lookup", "tool_use_id": "t1", "is_error": False},
    },
]


def _graph(agent_id: str) -> dict[str, Any]:
    return {
        "id": f"g-{agent_id}",
        "name": "관측",
        "inputs": [{"name": "request"}],
        "nodes": [
            {"id": "you", "type": "user"},
            {"id": "a", "type": "agent", "config": {"agent_ref": agent_id}},
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


def _run(client: Any, agent_id: str, observe: dict[str, Any] | None) -> str:
    agent: dict[str, Any] = {
        "id": agent_id,
        "name": agent_id,
        "backend": "fake-agent",
        "backend_options": {"default": {"response": "ok", "observe": OBSERVE_RULES}},
    }
    if observe is not None:
        agent["observe"] = observe
    assert client.post(f"{API}/agents", json=agent).status_code == 201
    created = client.post(f"{API}/graphs", json=_graph(agent_id))
    assert created.status_code == 201, created.text
    run = client.post(
        f"{API}/runs", json={"graph_id": f"g-{agent_id}", "input": {"request": "go"}}
    ).json()
    assert wait_run(client, run["id"])["run"]["status"] == "completed"
    run_id: str = run["id"]
    return run_id


def _events(client: Any, run_id: str, prefix: str) -> list[dict[str, Any]]:
    response = client.get(f"{API}/runs/{run_id}/events", params={"type_prefix": prefix})
    assert response.status_code == 200
    body: list[dict[str, Any]] = response.json()
    return body


def test_fake_observe_events_are_queryable_by_type_prefix(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        run_id = _run(client, "watcher", {"hooks": True, "mcp": True})
        hooks = _events(client, run_id, "hook.")
        assert [e["type"] for e in hooks] == ["hook.invoked"]
        assert hooks[0]["payload"]["event"] == "PreToolUse"
        assert hooks[0]["node_path"] == ["a"]
        mcp = _events(client, run_id, "mcp.")
        assert [e["type"] for e in mcp] == ["mcp.server_status", "mcp.call_completed"]
        assert mcp[1]["payload"]["server"] == "docs"


def test_fake_observe_events_need_observe_setting(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        off = _run(client, "quiet", None)
        assert _events(client, off, "hook.") == []
        assert _events(client, off, "mcp.") == []
        hooks_only = _run(client, "half", {"hooks": True})
        assert [e["type"] for e in _events(client, hooks_only, "hook.")] == ["hook.invoked"]
        assert _events(client, hooks_only, "mcp.") == []
