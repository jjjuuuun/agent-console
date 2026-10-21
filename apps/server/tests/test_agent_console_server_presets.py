"""프리셋 없이 동작(R0.2)과 시작 시 프리셋 적용(설정 `modules.options.mod-presets`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_mod_presets import PresetNotFoundError
from agent_console_server.testing import (
    API,
    agent_doc,
    make_settings,
    server,
    team_graph,
    wait_run,
)


def test_agent_console_server_runs_without_presets(tmp_path: Path) -> None:
    """빈 프리셋 경로로 기동 → 그래프 생성 → 실행. 서버는 어떤 정의도 가정하지 않는다."""
    empty = tmp_path / "no-presets"
    empty.mkdir()
    settings = make_settings(
        tmp_path, modules={"options": {"mod-presets": {"directories": [str(empty)]}}}
    )
    with server(settings) as client:
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


def test_agent_console_server_unknown_preset_fails_start(tmp_path: Path) -> None:
    options = {"directories": [str(tmp_path)], "apply_on_start": ["ghost"]}
    settings = make_settings(tmp_path, modules={"options": {"mod-presets": options}})
    with pytest.raises(PresetNotFoundError), server(settings):
        pass


def test_workspace_settings_keep_removed_console_keys(tmp_path: Path) -> None:
    """2R.20: 워크스페이스 `settings.yaml`의 `console`·`default_entry`는 모르는 키로 보존한다."""
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
