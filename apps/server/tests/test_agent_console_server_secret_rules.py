"""2R.4 비밀 규칙: 사용자 규칙(더하기만, 위험 정규식 422), 실행 기록 의심 가림,
평문 점검 경고(`ServerInfo.warnings`, 캐시 무효화), 선언형 `x-secret` 평문 거부, `expose_paths`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_server.testing import (
    API,
    make_settings,
    seed,
    server,
    wait_run,
)

TOKEN = "ghp_PlainToken123456"


def _settings_put(client: TestClient, body: dict[str, Any]) -> Any:
    current = client.get(f"{API}/settings")
    headers = {"If-Match": current.headers["etag"]} if "etag" in current.headers else {}
    return client.put(f"{API}/settings", json=body, headers=headers)


def _run(client: TestClient, text: str) -> tuple[dict[str, Any], str]:
    created = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": text}})
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    snap = wait_run(client, run_id)
    events = client.get(f"{API}/runs/{run_id}/events").text
    return snap, events


def test_suspected_values_are_redacted_in_run_records_and_toggle(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        seed(client)
        snap, events = _run(client, f"키는 {TOKEN} 입니다")
        assert snap["run"]["status"] == "completed"
        assert TOKEN not in json.dumps(snap, ensure_ascii=False)
        assert TOKEN not in events
        assert "[REDACTED]" in json.dumps(snap["node_runs"], ensure_ascii=False)

        # 끄면(디버깅용) 원문 그대로 남는다
        assert (
            _settings_put(client, {"secrets": {"redact_suspected_in_logs": False}}).status_code
            == 200
        )
        snap, events = _run(client, f"키는 {TOKEN} 입니다")
        assert TOKEN in json.dumps(snap["node_runs"], ensure_ascii=False)
        assert TOKEN in events


def test_user_rules_only_add_and_dangerous_patterns_rejected(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        bad = _settings_put(client, {"secrets": {"extra_value_patterns": ["ok_[0-9]+", "(a+)+$"]}})
        assert bad.status_code == 422, bad.text
        issues = bad.json()["error"]["details"]["issues"]
        assert [(i["code"], i["path"]) for i in issues] == [
            ("secret.invalid_rule", "/secrets/extra_value_patterns/1")
        ]
        assert client.get(f"{API}/settings").json() == {}

        # 사용자 키 이름: 리소스가 없는 첨부 덮어쓰기 검사에 더해진다
        doc = {
            "id": "a",
            "name": "a",
            "resources": [{"ref": "later", "config_override": {"corp": "v"}}],
        }
        assert client.post(f"{API}/agents", json=doc).status_code == 201
        ok = _settings_put(client, {"secrets": {"extra_key_names": ["corp"]}})
        assert ok.status_code == 200, ok.text
        doc2 = {**doc, "id": "b", "name": "b"}
        rejected = client.post(f"{API}/agents", json=doc2)
        assert rejected.status_code == 422
        paths = [i["path"] for i in rejected.json()["error"]["details"]["issues"]]
        assert "/resources/0/config_override/corp" in paths


def test_plain_found_warnings_cache_and_invalidation(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    resources = settings.workspace_path / "resources"
    resources.mkdir(parents=True)
    legacy: dict[str, Any] = {
        "id": "gh",
        "type": "mcp-server",
        "name": "gh",
        "config": {"name": "gh", "command": "npx", "env": {"API_KEY": "plain-legacy-1"}},
    }
    (resources / "gh.yaml").write_text(json.dumps(legacy), encoding="utf-8")
    with server(settings) as client:
        info = client.get(f"{API}/server-info")
        assert info.status_code == 200
        assert "plain-legacy-1" not in info.text
        warnings = info.json()["warnings"]
        assert [(w["code"], w["path"], w["details"]) for w in warnings] == [
            ("secret.plain_found", "/config/env/API_KEY", {"kind": "resource", "id": "gh"})
        ]
        assert all(w["severity"] == "warning" for w in warnings)
        assert info.json()["attributes"]["workspace"] == str(settings.workspace_path)

        # 고치면(정의 쓰기) 캐시가 무효화되어 경고가 사라진다
        current = client.get(f"{API}/resources/gh")
        fixed = {**legacy, "config": {**legacy["config"], "env": {"API_KEY": "secret://GH"}}}
        put = client.put(
            f"{API}/resources/gh", json=fixed, headers={"If-Match": current.headers["etag"]}
        )
        assert put.status_code == 200, put.text
        assert client.get(f"{API}/server-info").json()["warnings"] == []


def test_expose_paths_false_hides_workspace(tmp_path: Path) -> None:
    with server(make_settings(tmp_path, security={"expose_paths": False})) as client:
        attributes = client.get(f"{API}/server-info").json()["attributes"]
        assert "workspace" not in attributes
        assert str(tmp_path) not in json.dumps(attributes)


def test_declarative_x_secret_plain_rejected(tmp_path: Path) -> None:
    """선언형 종류는 `pattern` 없이 `x-secret`만 달아도 평문이 거부된다."""
    settings = make_settings(tmp_path)
    types_dir = settings.workspace_path / "resource-types"
    types_dir.mkdir(parents=True)
    (types_dir / "api-token.yaml").write_text(
        "id: api-token\n"
        "title: API 토큰\n"
        "config_schema:\n"
        "  type: object\n"
        "  properties:\n"
        "    token: {type: string, x-secret: true}\n"
        "contributes:\n"
        "  - slot: notes\n"
        "    template: '{name}'\n",
        encoding="utf-8",
    )
    with server(settings) as client:
        doc = {"id": "t", "type": "api-token", "name": "t", "config": {"token": "plain-x-1"}}
        rejected = client.post(f"{API}/resources", json=doc)
        assert rejected.status_code == 422, rejected.text
        assert "plain-x-1" not in rejected.text
        [issue] = rejected.json()["error"]["details"]["issues"]
        assert (issue["code"], issue["path"]) == ("resource.plain_secret", "/config/token")
        ok = {**doc, "config": {"token": "secret://T"}}
        assert client.post(f"{API}/resources", json=ok).status_code == 201
