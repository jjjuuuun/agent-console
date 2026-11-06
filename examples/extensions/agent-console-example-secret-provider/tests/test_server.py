"""통합 서버 시험(agent-console-server — 기본 모듈 전부): 설치하지 않고 설정
`plugins.modules`로 이 공급자를 등록한다(설치한 서버가 entry point로 로드하는 것과 같은
레지스트리에 들어간다).

- 팀 실행: 에이전트의 `backend_options`에 둔 비밀 참조가 이 파일의 값으로 풀려 가짜
  백엔드가 답에 그대로 쓰지만, 저장·응답 이벤트에는 가려져 나온다.
- `/server-info`·로그에 값이 없다. 파일이 없어도 서버는 시작하고 경고만 남는다.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_example_secret_provider import default_settings_data
from agent_console_server import create_app, load_settings
from agent_console_server.testing import register_project

API = "/api/v1"
TOKEN = "test-token-0123456789abcdef"
VALUE = "file-value-zz53"
PLUGIN = "agent_console_example_secret_provider:register"
PROJECT = "p1"
TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})
AGENT = {
    "id": "bot",
    "name": "봇",
    "backend": "fake-agent",
    "backend_options": {"default": {"response": "secret://example_token"}},
}
GRAPH = {
    "id": "flow",
    "name": "흐름",
    "nodes": [
        {"id": "you", "type": "user", "label": "나"},
        {"id": "a", "type": "agent", "label": "응답자", "config": {"agent_ref": "bot"}},
    ],
    "edges": [
        {
            "id": "m1",
            "source": {"node": "you", "port": "says"},
            "target": {"node": "a", "port": "in"},
            "kind": "message",
            "config": {},
        },
        {
            "id": "r1",
            "source": {"node": "a", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "reply",
            "config": {},
        },
    ],
}


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))  # 실제 ~/.claude를 읽지 않게
    monkeypatch.setenv(default_settings_data()["path_env"], str(tmp_path / "secrets.env"))


@contextmanager
def _server(tmp_path: Path) -> Iterator[TestClient]:
    config = tmp_path / "agent-console.yaml"
    config.write_text("workspace: ws\n", encoding="utf-8")
    environ = {"CLAUDE_CONFIG_DIR": str(tmp_path / "claude")}
    overrides: dict[str, Any] = {
        "security": {"allowed_hosts": ["testserver"]},
        "plugins": {"modules": [PLUGIN]},
    }
    settings = load_settings(config, environ=environ, overrides=overrides)
    app = create_app(settings, environ=environ, token=TOKEN)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client


def _seed(client: TestClient, tmp_path: Path) -> None:
    """실행은 프로젝트 폴더에서만 한다 — 프로젝트를 등록하고 그 안에 정의를 만든다."""
    folder = tmp_path / "proj"
    folder.mkdir()
    register_project(client, PROJECT, folder)
    assert client.post(f"{API}/agents?project={PROJECT}", json=AGENT).status_code == 201
    created = client.post(f"{API}/graphs?project={PROJECT}", json=GRAPH)
    assert created.status_code == 201, created.text


def _start(client: TestClient) -> str:
    body = {"graph_id": "flow", "input": {"text": "안녕"}, "project_id": PROJECT}
    started = client.post(f"{API}/runs", json=body)
    assert started.status_code == 202, started.text
    run_id: str = started.json()["id"]
    return run_id


def _wait(client: TestClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snap: dict[str, Any] = client.get(f"{API}/runs/{run_id}?project={PROJECT}").json()
        if snap["run"]["status"] in TERMINAL:
            return snap
        time.sleep(0.02)
    raise AssertionError("Run이 끝나지 않았다")


def test_value_is_used_but_never_shown(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "secrets.env").write_text(f"EXAMPLE_TOKEN={VALUE}\n", encoding="utf-8")
    with caplog.at_level(logging.DEBUG), _server(tmp_path) as client:
        _seed(client, tmp_path)
        info = client.get(f"{API}/server-info")
        assert info.status_code == 200
        mine = [p for p in info.json()["plugins"] if p["group"] == "plugins.modules"]
        assert [(p["name"], p["status"]) for p in mine] == [("register", "loaded")]

        run_id = _start(client)
        snap = _wait(client, run_id)
        assert snap["run"]["status"] == "completed", snap
        events = client.get(f"{API}/runs/{run_id}/events?project={PROJECT}").json()
        replies = [e["payload"]["text"] for e in events if e["type"] == "run.reply"]
        assert replies == [
            "[REDACTED]"
        ]  # 값이 풀려 쓰였고(참조 문자열이 아니다), 기록에는 가려졌다

        shown = info.text + json.dumps(snap) + json.dumps(events)
        shown += client.get(f"{API}/server-info").text
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert VALUE not in shown
    assert VALUE not in logs


def test_missing_file_only_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), _server(tmp_path) as client:
        assert client.get(f"{API}/health").status_code == 200
        _seed(client, tmp_path)
        snap = _wait(client, _start(client))
        # 값이 없으면 그 노드만 "비밀을 찾을 수 없음"으로 실패한다(오류 문장에 값·경로가 없다).
        assert snap["run"]["status"] == "failed"
        assert "secrets.env" not in json.dumps(snap)
    assert any("비밀 파일이 없습니다" in r.getMessage() for r in caplog.records)
