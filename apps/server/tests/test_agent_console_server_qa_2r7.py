"""2R.7 QA: 초안 경로(POST)도 토큰·Origin 규칙을 따르고, 저장하지 않는다."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_server.testing import API, TEST_TOKEN, make_settings, server, team_graph

DRAFT_PATHS = ("plan", "effective-settings", "bundle-preview")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = make_settings(
        tmp_path,
        security={"allowed_hosts": ["testserver"], "allowed_origins": ["http://localhost:5173"]},
    )
    with server(settings, with_token=False) as c:
        yield c


def _body(path: str) -> dict[str, object]:
    graph = team_graph("qa-draft")
    return {"graph": graph} if path == "plan" else {"graph": graph, "node_id": "a"}


@pytest.mark.parametrize("path", DRAFT_PATHS)
def test_draft_posts_need_token_and_allowed_origin(client: TestClient, path: str) -> None:
    url = f"{API}/graphs/{path}"
    assert client.post(url, json=_body(path)).status_code == 401
    bad = client.post(
        url,
        json=_body(path),
        headers={"X-Console-Token": TEST_TOKEN, "Origin": "http://evil.example"},
    )
    assert bad.status_code == 403
    ok = client.post(
        url,
        json=_body(path),
        headers={"X-Console-Token": TEST_TOKEN, "Origin": "http://localhost:5173"},
    )
    assert ok.status_code in (200, 404, 422), ok.text  # 인증은 통과
    listed = client.get(f"{API}/graphs").json()
    assert all(g["id"] != "qa-draft" for g in listed)
