"""1R.37 후속: 리소스 첨부 `config_override` 평문 비밀 거부(에이전트·팀 구성·공통 설정)와
유효 설정·묶음 미리보기의 `x-secret` 평문 가리기(이전 데이터 안전망)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import API, make_settings, server, team_graph

PLAIN = "sk-live-123456"
MCP = {
    "id": "gh",
    "type": "mcp-server",
    "name": "gh",
    "config": {"name": "gh", "command": "npx", "env": {"API_KEY": "secret://T"}},
}


def _att(value: str = PLAIN) -> dict[str, Any]:
    return {"ref": "gh", "config_override": {"env": {"API_KEY": value}}}


def _paths(response: Any) -> list[str]:
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert PLAIN not in response.text
    return [i["path"] for i in error["details"]["issues"] if i["severity"] == "error"]


def _seed(client: TestClient) -> None:
    assert client.post(f"{API}/resources", json=MCP).status_code == 201


def test_agent_override_plain_secret_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        doc = {"id": "a", "name": "a", "backend": "fake", "resources": [{"ref": "gh"}, _att()]}
        assert _paths(client.post(f"{API}/agents", json=doc)) == [
            "/resources/1/config_override/env/API_KEY"
        ]
        ok = {**doc, "resources": [_att("secret://OTHER")]}
        created = client.post(f"{API}/agents", json=ok)
        assert created.status_code == 201
        put = client.put(f"{API}/agents/a", json=doc, headers={"If-Match": created.headers["etag"]})
        assert _paths(put) == ["/resources/1/config_override/env/API_KEY"]
        assert client.get(f"{API}/agents/a").json() == ok


def test_suspicion_rule_covers_non_string_values_and_nested_names(tmp_path: Path) -> None:
    """4R.18(1R.37d 후속 확인): 비문자열 값(`{"API_KEY": 12345}`)과 비밀 이름 아래 하위 객체(가장
    가까운 비밀 이름을 이어받음)도 저장 경로에서 거부된다."""
    override = {
        "env": {"API_KEY": 12345},
        "credentials": {"user": "u", "nested": {"value": "v"}},
        "auth": {"mode": "oauth"},  # 예외 단어(mode)는 이어받지 않는다
    }
    with server(make_settings(tmp_path)) as client:
        doc = {"id": "a", "name": "a", "resources": [{"ref": "later", "config_override": override}]}
        assert sorted(_paths(client.put(f"{API}/agents/a", json=doc))) == [
            "/resources/0/config_override/credentials/nested/value",
            "/resources/0/config_override/credentials/user",
            "/resources/0/config_override/env/API_KEY",
        ]
        assert client.get(f"{API}/agents/a").status_code == 404


def test_override_of_missing_resource_uses_secret_suspicion_rule(tmp_path: Path) -> None:
    """ref 리소스가 없으면 스키마를 모르므로 공용 비밀 의심 규칙으로 검사한다(1R.36 QA).

    의심되면 422(원문 GET으로 평문이 새지 않게), 아니면 warning만 내고 저장한다(리소스를 나중에
    만드는 흐름은 허용)."""
    with server(make_settings(tmp_path)) as client:
        doc = {"id": "a", "name": "a", "resources": [_att()]}
        assert _paths(client.put(f"{API}/agents/a", json=doc)) == [
            "/resources/0/config_override/env/API_KEY"
        ]
        assert client.get(f"{API}/agents/a").status_code == 404
        token = {"ref": "later", "config_override": {"args": ["--x", "ghp_abcdefghijk"]}}
        assert _paths(client.post(f"{API}/agents", json={**doc, "resources": [token]})) == [
            "/resources/0/config_override/args/1"
        ]
        ok = {
            "id": "a",
            "name": "a",
            "resources": [
                _att("secret://LATER"),
                {"ref": "later", "config_override": {"name": "x", "max_tokens": 5}},
            ],
        }
        created = client.post(f"{API}/agents", json=ok)
        assert created.status_code == 201
        assert client.get(f"{API}/agents/a").json() == ok


def test_graph_team_node_and_edge_overrides_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        team = {**team_graph(), "settings": {"resources": [_att()]}}
        assert _paths(client.post(f"{API}/graphs", json=team)) == [
            "/settings/resources/0/config_override/env/API_KEY"
        ]
        node = team_graph()
        node["nodes"][1]["config"]["settings"] = {"resources": [_att()]}
        assert _paths(client.post(f"{API}/graphs", json=node)) == [
            "/nodes/1/config/settings/resources/0/config_override/env/API_KEY"
        ]
        edge = team_graph()
        edge["nodes"].append({"id": "res", "type": "resource", "config": {"resource_ref": "gh"}})
        edge["edges"].append(
            {
                "id": "u1",
                "source": {"node": "res", "port": "provides"},
                "target": {"node": "a", "port": "resources"},
                "kind": "uses",
                "config": {"config_override": {"env": {"API_KEY": PLAIN}}},
            }
        )
        index = len(edge["edges"]) - 1
        assert _paths(client.post(f"{API}/graphs", json=edge)) == [
            f"/edges/{index}/config/config_override/env/API_KEY"
        ]
        edge["edges"][index]["config"] = {"config_override": {"env": {"API_KEY": "secret://X"}}}
        assert client.post(f"{API}/graphs", json=edge).status_code == 201


def test_settings_agent_defaults_override_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        _seed(client)
        body = {"agent_defaults": {"resources": [_att()]}}
        assert _paths(client.put(f"{API}/settings", json=body)) == [
            "/agent_defaults/resources/0/config_override/env/API_KEY"
        ]
        assert client.get(f"{API}/settings").json() == {}


def test_effective_settings_and_bundle_preview_mask_legacy_plain(tmp_path: Path) -> None:
    """검사 전에 저장된(손으로 고친) 평문 덮어쓰기·리소스는 응답에서 가린다."""
    settings = make_settings(tmp_path)
    with server(settings) as client:
        _seed(client)
        assert client.post(f"{API}/agents", json={"id": "a", "name": "a"}).status_code == 201
        graph = team_graph()
        graph["nodes"][1]["config"]["settings"] = {"resources": [_att("secret://OK")]}
        assert client.post(f"{API}/graphs", json=graph).status_code == 201
        # 손으로 고친 파일(검사를 거치지 않은 이전 데이터)
        [agent_file] = settings.workspace_path.rglob("a.yaml")
        agent_file.write_text(
            json.dumps({"id": "a", "name": "a", "resources": [_att()]}), encoding="utf-8"
        )
        [res_file] = settings.workspace_path.rglob("gh.yaml")
        res_file.write_text(
            json.dumps({**MCP, "config": {**MCP["config"], "env": {"API_KEY": PLAIN}}}),  # type: ignore[dict-item]
            encoding="utf-8",
        )
        graph["nodes"][1]["config"]["settings"] = {"resources": [_att()]}
        [graph_file] = settings.workspace_path.rglob("flow.yaml")
        graph_file.write_text(json.dumps(graph), encoding="utf-8")

        effective = client.get(f"{API}/agents/a/effective-settings")
        assert effective.status_code == 200
        assert PLAIN not in effective.text
        [att] = effective.json()["value"]["resources"]
        assert att["config_override"]["env"]["API_KEY"] == "***"

        node = client.get(f"{API}/graphs/flow/nodes/a/effective-settings")
        assert node.status_code == 200
        assert PLAIN not in node.text
        preview = client.get(f"{API}/graphs/flow/nodes/a/bundle-preview")
        assert preview.status_code == 200
        assert PLAIN not in preview.text
