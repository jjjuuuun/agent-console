"""빈 워크스페이스에서 동작(R0.2): 서버는 어떤 정의도 가정하지 않는다."""

from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    server,
    team_graph,
    wait_run,
)


def test_agent_console_server_runs_from_empty_workspace(tmp_path: Path) -> None:
    """빈 워크스페이스로 기동 → 사용자가 정의를 만들고 → 실행."""
    with server(make_settings(tmp_path)) as client:
        assert client.get(f"{API}/graphs").json() == []
        assert client.get(f"{API}/agents").json() == []
        assert client.get(f"{API}/settings").json().get("default_entry") is None
        client.post(f"{API}/agents", json=agent_doc("fast", "답: $prompt"))
        client.post(f"{API}/agents", json=agent_doc("slow", "깊은 답"))
        assert client.post(f"{API}/graphs", json=team_graph()).status_code == 201
        run = client.post(
            f"{API}/runs", json={"graph_id": "flow", "input": {"request": "? 안녕"}}
        ).json()
        assert wait_run(client, run["id"])["run"]["status"] == "completed"


def test_workspace_settings_keep_removed_console_keys(tmp_path: Path) -> None:
    """워크스페이스 `settings.yaml`의 모르는 옛 키(`console`·`default_entry`)는 보존한다."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "settings.yaml").write_text(
        "default_entry: old-graph\nconsole: {command_prefix: '!'}\n", encoding="utf-8"
    )
    with server(make_settings(tmp_path)) as client:
        got = client.get(f"{API}/settings")
        assert got.status_code == 200
        assert got.json()["default_entry"] == "old-graph"
        assert got.json()["console"] == {"command_prefix": "!"}
        saved = client.put(
            f"{API}/settings",
            json={**got.json(), "default_backend": "fake"},
            headers={"If-Match": got.headers["etag"]},
        )
        assert saved.status_code == 200
    text = (ws / "settings.yaml").read_text(encoding="utf-8")
    assert "old-graph" in text
    assert "command_prefix" in text
