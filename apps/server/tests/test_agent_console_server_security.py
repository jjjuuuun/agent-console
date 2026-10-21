"""보안(design §9.1, R10.3): Host·Origin·토큰 검사, 요청 크기 제한, 바인딩, 비밀 값 비노출."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_console_server import (
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    ConfigError,
    SecurityPolicy,
    create_app,
)
from agent_console_server.testing import (
    API,
    SECRET_NAME,
    SECRET_VALUE,
    TEST_TOKEN,
    agent_doc,
    make_settings,
    receive_until,
    server,
    team_graph,
    wait_run,
    ws_path,
)

MAX_BODY = 2048


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = make_settings(
        tmp_path,
        security={
            "allowed_hosts": ["testserver"],
            "allowed_origins": ["http://localhost:5173"],
            "max_request_bytes": MAX_BODY,
        },
    )
    with server(settings, with_token=False) as c:
        yield c


def _auth(**extra: str) -> dict[str, str]:
    return {"X-Console-Token": TEST_TOKEN, **extra}


def test_agent_console_server_token_required_for_writes(client: TestClient) -> None:
    doc = agent_doc("a1", "hi")
    missing = client.post(f"{API}/agents", json=doc)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"
    wrong = client.post(f"{API}/agents", json=doc, headers={"X-Console-Token": "nope"})
    assert wrong.status_code == 401
    assert client.delete(f"{API}/agents/a1").status_code == 401
    assert client.put(f"{API}/settings", json={}).status_code == 401
    # 읽기는 토큰 없이 된다(같은 출처 화면이 부트스트랩 전에 쓰는 경로는 없지만 CLI·curl 조회용)
    assert client.get(f"{API}/agents").status_code == 200
    assert client.post(f"{API}/agents", json=doc, headers=_auth()).status_code == 201


def test_agent_console_server_origin_check(client: TestClient) -> None:
    doc = agent_doc("a1", "hi")
    evil = client.post(f"{API}/agents", json=doc, headers=_auth(Origin="http://evil.example"))
    assert evil.status_code == 403
    assert evil.json()["error"]["code"] == "forbidden"
    same = client.post(f"{API}/agents", json=doc, headers=_auth(Origin="http://testserver"))
    assert same.status_code == 201
    dev = client.put(f"{API}/agents/a1", json=doc, headers=_auth(Origin="http://localhost:5173"))
    assert dev.status_code == 200


def test_agent_console_server_bootstrap_same_origin_only(client: TestClient) -> None:
    assert client.get(f"{API}/bootstrap").json()["token"] == TEST_TOKEN
    ok = client.get(f"{API}/bootstrap", headers={"Origin": "http://testserver"})
    assert ok.status_code == 200
    evil = client.get(f"{API}/bootstrap", headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403
    cross = client.get(f"{API}/bootstrap", headers={"Sec-Fetch-Site": "cross-site"})
    assert cross.status_code == 403
    assert TEST_TOKEN not in cross.text


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8765", "localhost:9999", "127.0.0.1.evil.example", ""]
)
def test_agent_console_server_host_check(client: TestClient, host: str) -> None:
    """DNS 리바인딩 차단: 루프백 이름 + 바인딩 포트, 또는 allowed_hosts만."""
    response = client.get(f"{API}/bootstrap", headers={"Host": host})
    assert response.status_code == 403
    assert TEST_TOKEN not in response.text


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "[::1]:8765", "testserver"])
def test_agent_console_server_host_allowed(client: TestClient, host: str) -> None:
    assert client.get(f"{API}/node-types", headers={"Host": host}).status_code == 200


def test_agent_console_server_request_size_limit(client: TestClient) -> None:
    big = agent_doc("big", "x" * (MAX_BODY * 2))
    declared = client.post(f"{API}/agents", json=big, headers=_auth())
    assert declared.status_code == 413
    assert declared.json()["error"]["code"] == "payload_too_large"

    def chunks() -> Iterator[bytes]:  # Content-Length 없이(chunked) 보내도 센다
        body = json.dumps(big).encode()
        for i in range(0, len(body), 512):
            yield body[i : i + 512]

    chunked = client.post(
        f"{API}/agents",
        content=chunks(),
        headers=_auth(**{"Content-Type": "application/json"}),
    )
    assert chunked.status_code == 413
    small = client.post(f"{API}/agents", json=agent_doc("small", "x"), headers=_auth())
    assert small.status_code == 201


def test_agent_console_server_security_headers(client: TestClient) -> None:
    response = client.get(f"{API}/node-types")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_agent_console_server_ws_auth_close_codes(client: TestClient) -> None:
    for path in (ws_path(None), ws_path("wrong")):
        with client.websocket_connect(path) as ws, pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == WS_CLOSE_UNAUTHORIZED == 4401
    with (
        client.websocket_connect(ws_path(), headers={"Origin": "http://evil.example"}) as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == WS_CLOSE_FORBIDDEN == 4403
    with (
        client.websocket_connect(ws_path(), headers={"Host": "evil.example"}) as ws,
        pytest.raises(WebSocketDisconnect) as exc,
    ):
        ws.receive_text()
    assert exc.value.code == WS_CLOSE_FORBIDDEN


def test_agent_console_server_remote_bind_requires_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        create_app(make_settings(tmp_path, host="0.0.0.0"), environ={})
    app = create_app(
        make_settings(tmp_path, host="0.0.0.0", security={"allow_remote": True}), environ={}
    )
    assert app.state.settings.host == "0.0.0.0"
    assert make_settings(tmp_path).host == "127.0.0.1"  # 기본은 루프백


def test_agent_console_server_random_token_when_unset(tmp_path: Path) -> None:
    first = create_app(make_settings(tmp_path), environ={}).state.policy
    second = create_app(make_settings(tmp_path), environ={}).state.policy
    assert isinstance(first, SecurityPolicy)
    assert len(first.token) >= 32
    assert first.token != second.token
    configured = create_app(
        make_settings(tmp_path, security={"token": "configured-token-123"}), environ={}
    )
    assert configured.state.policy.token == "configured-token-123"


def test_agent_console_server_secrets_not_in_responses_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """비밀 참조로 해석한 값은 응답(Run·스냅샷·WS)·로그 어디에도 원문으로 나오지 않는다."""
    caplog.set_level(logging.DEBUG)
    with server(make_settings(tmp_path)) as client:
        client.post(f"{API}/agents", json=agent_doc("fast", f"secret://{SECRET_NAME}"))
        client.post(f"{API}/agents", json=agent_doc("slow", f"키는 secret://{SECRET_NAME}"))
        client.post(f"{API}/graphs", json=team_graph())
        run = client.post(
            f"{API}/runs", json={"graph_id": "flow", "input": {"request": "? 키 알려줘"}}
        ).json()
        snap = wait_run(client, run["id"])
        assert snap["run"]["status"] == "completed"
        text = json.dumps(snap, ensure_ascii=False)
        assert SECRET_VALUE not in text
        assert "[REDACTED]" in text
        with client.websocket_connect(ws_path()) as ws:
            ws.send_json({"type": "subscribe", "payload": {"topic": f"run:{run['id']}"}})
            events = receive_until(ws, lambda m: m["payload"].get("type") == "run.completed")
        assert SECRET_VALUE not in json.dumps(events, ensure_ascii=False)
        # 입력에 비밀 값이 섞여도 저장·응답본은 가려진다(§4.8)
        echoed = client.post(
            f"{API}/runs", json={"graph_id": "flow", "input": {"request": f"? {SECRET_VALUE}"}}
        ).json()
        assert SECRET_VALUE not in json.dumps(wait_run(client, echoed["id"]), ensure_ascii=False)
        for path in ("/runs", "/agents", "/settings", "/bootstrap"):
            assert SECRET_VALUE not in client.get(f"{API}{path}").text
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET_VALUE not in logged
    assert TEST_TOKEN not in logged  # WS ?token= 포함 어떤 요청에서도 토큰을 남기지 않는다
