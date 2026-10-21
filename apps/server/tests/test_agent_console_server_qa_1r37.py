"""1R.37 QA 탐침: 우회 경로·손으로 고친 파일·원문 안전성."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_console_server.testing import API, make_settings, server

PLAIN = "sk-live-123456"
MCP = {
    "id": "gh",
    "type": "mcp-server",
    "name": "gh",
    "config": {"name": "gh", "command": "npx", "env": {"API_KEY": PLAIN}},
}


def _preset(root: Path) -> Path:
    p = root / "presets" / "leaky"
    (p / "resources").mkdir(parents=True)
    (p / "preset.yaml").write_text(
        "kind: preset\nid: leaky\nschema_version: 1\nname: leaky\nitems:\n  - resources/gh.yaml\n",
        encoding="utf-8",
    )
    (p / "resources" / "gh.yaml").write_text(json.dumps(MCP), encoding="utf-8")
    return root / "presets"


def test_probe_preset_apply_with_plain_secret(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, options={"mod-presets": {"directories": [str(_preset(tmp_path))]}}
    )
    with server(settings) as client:
        client.post(f"{API}/presets/leaky/apply", json={})
        got = client.get(f"{API}/resources/gh")
        assert not (got.status_code == 200 and PLAIN in got.text), "프리셋 우회로 평문 저장됨"


def test_probe_hand_edited(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with server(settings) as client:
        client.post(f"{API}/agents", json={"id": "ok", "name": "ok", "backend": "fake"})
        client.post(f"{API}/resources", json={"id": "r1", "type": "instruction", "name": "x"})
        files = list(settings.workspace_path.rglob("ok.yaml")) + list(
            settings.workspace_path.rglob("r1.yaml")
        )
        for f in files:
            if f.name == "ok.yaml":
                bad = f.with_name("bad.yaml")
                bad.write_text("id: bad\nname: 1\nunknown_key: 3\nlimits: 7\n", encoding="utf-8")
            if f.name == "r1.yaml":
                f.with_name("leak.yaml").write_text(
                    json.dumps(MCP | {"id": "leak"}), encoding="utf-8"
                )
        lst = client.get(f"{API}/agents")
        assert [a["id"] for a in lst.json()] == ["ok"]  # 계약 위반 파일은 목록에서 뺀다
        one = client.get(f"{API}/agents/bad")
        assert one.status_code == 422
        leak = client.get(f"{API}/resources/leak")
        assert leak.status_code == 200  # 구형 평문은 그대로 읽힌다(알려진 한계)
        assert client.get(f"{API}/resources").status_code == 200
        c: Any = client.put(
            f"{API}/resources/leak/content", content="hi", headers={"If-Match": "x"}
        )
        assert c.status_code == 412


def test_probe_explicit_null_and_empty_roundtrip(tmp_path: Path) -> None:
    from agent_console_server.testing import team_graph

    g = team_graph()
    g["nodes"][0]["config"] = {}
    g["nodes"][0]["label"] = None
    s: dict[str, Any] = {
        "default_backend": None,
        "default_entry": None,
        "chat": {},
        "attachments": [],
    }
    r: dict[str, Any] = {
        "id": "n",
        "type": "instruction",
        "name": "n",
        "config": {},
        "labels": [],
        "content": None,
    }
    with server(make_settings(tmp_path)) as client:
        gp = client.post(f"{API}/graphs", json=g)
        assert gp.json()["graph"] == g, gp.json()["graph"]
        assert client.get(f"{API}/graphs/flow").json()["graph"] == g
        rp = client.post(f"{API}/resources", json=r)
        assert rp.json() == r, rp.text
        assert client.get(f"{API}/resources").status_code == 200
        sp = client.put(f"{API}/settings", json=s)
        assert sp.json() == s
        assert client.get(f"{API}/settings").json() == s
