from __future__ import annotations

from pathlib import Path

from agent_console_server.testing import API, make_settings, server

PLAIN = "sk-live-123456"


def test_override_bypass(tmp_path: Path) -> None:
    mcp = {
        "id": "gh",
        "type": "mcp-server",
        "name": "gh",
        "config": {"name": "gh", "command": "npx", "env": {"API_KEY": "secret://T"}},
    }
    att = {"ref": "gh", "config_override": {"env": {"API_KEY": PLAIN}}}
    with server(make_settings(tmp_path)) as client:
        assert client.post(f"{API}/resources", json=mcp).status_code == 201
        a = client.post(
            f"{API}/agents",
            json={"id": "a", "name": "a", "backend": "fake-agent", "resources": [att]},
        )
        assert a.status_code == 422
        assert PLAIN not in a.text
