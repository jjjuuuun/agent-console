"""1R.37b QA: 첨부 config_override 평문 비밀이 모든 층에서 막히는지."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

PLAIN = "sk-live-123456"
OVR = {"env": {"API_KEY": PLAIN}}
MCP: dict[str, Any] = {
    "id": "gh",
    "type": "mcp-server",
    "name": "gh",
    "config": {"name": "gh", "command": "npx", "env": {"API_KEY": "secret://T"}},
}


def _graph(**node_extra: Any) -> dict[str, Any]:
    return {
        "id": "g",
        "name": "g",
        "nodes": [
            {"id": "ag", "type": "agent", "config": {"agent_ref": "x"}, **node_extra},
            {"id": "rs", "type": "resource", "config": {"resource_ref": "gh"}},
        ],
        "edges": [
            {
                "id": "u1",
                "source": {"node": "rs", "port": "provides"},
                "target": {"node": "ag", "port": "resources"},
                "kind": "uses",
                "config": {"config_override": OVR},
            }
        ],
    }


def _paths(r: Any) -> list[str]:
    assert r.status_code == 422, (r.status_code, r.text)
    assert PLAIN not in r.text
    return [i["path"] for i in r.json()["error"]["details"]["issues"] if i.get("path")]


def test_override_rejected_in_every_layer(tmp_path: Path) -> None:
    att = {"ref": "gh", "config_override": OVR}
    with server(make_settings(tmp_path)) as client:
        assert client.post(f"{API}/resources", json=MCP).status_code == 201
        out: dict[str, list[str]] = {}
        out["agent"] = _paths(
            client.post(f"{API}/agents", json={"id": "a", "name": "a", "resources": [att]})
        )
        out["settings.defaults"] = _paths(
            client.put(f"{API}/settings", json={"agent_defaults": {"resources": [att]}})
        )
        out["graph.uses"] = _paths(client.post(f"{API}/graphs", json=_graph()))
        out["graph.node"] = _paths(
            client.post(
                f"{API}/graphs",
                json={**_graph(config={"agent_ref": "x"}), "edges": []}
                | {
                    "nodes": [
                        {
                            "id": "ag",
                            "type": "agent",
                            "config": {"agent_ref": "x", "settings": {"resources": [att]}},
                        }
                    ]
                },
            )
        )
        out["graph.team"] = _paths(
            client.post(
                f"{API}/graphs",
                json={"id": "g2", "name": "g2", "settings": {"resources": [att]}},
            )
        )
        print(json.dumps(out, ensure_ascii=False, indent=1))
        # 저장 안 됨
        assert client.get(f"{API}/agents/a").status_code == 404
        assert client.get(f"{API}/graphs/g").status_code == 404
        assert client.get(f"{API}/settings").json() == {}
        # PUT 경로(기존 문서 유지)
        ok = client.post(f"{API}/agents", json={"id": "b", "name": "b"})
        assert (
            client.put(
                f"{API}/agents/b",
                json={"id": "b", "name": "b", "resources": [att]},
                headers={"If-Match": ok.headers["etag"].strip('"')},
            ).status_code
            == 422
        )
        assert client.get(f"{API}/agents/b").json() == {"id": "b", "name": "b"}
        # 정상 override(비밀 아님)는 통과
        fine = client.post(
            f"{API}/agents",
            json={
                "id": "c",
                "name": "c",
                "resources": [{"ref": "gh", "config_override": {"command": "uvx"}}],
            },
        )
        assert fine.status_code == 201, fine.text
        sec = client.post(
            f"{API}/agents",
            json={
                "id": "d",
                "name": "d",
                "resources": [{"ref": "gh", "config_override": {"env": {"API_KEY": "secret://Z"}}}],
            },
        )
        assert sec.status_code == 201, sec.text


def test_legacy_plain_resource_is_not_blamed_on_attachment(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        client.post(f"{API}/resources", json={"id": "tip", "type": "instruction", "name": "t"})
        legacy = {**MCP, "id": "old", "config": {**MCP["config"], "env": {"API_KEY": PLAIN}}}
        (settings.workspace_path / "resources" / "old.yaml").write_text(
            json.dumps(legacy), encoding="utf-8"
        )
        r = client.post(
            f"{API}/agents", json={"id": "a", "name": "a", "resources": [{"ref": "old"}]}
        )
        assert r.status_code == 201, r.text
        eff = client.get(f"{API}/agents/a/effective-settings")
        assert PLAIN not in eff.text
