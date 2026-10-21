"""호스트: 보안 미들웨어·토큰·/health·WS 다중화·오류 맵·설정 읽기."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_console_modkit import ModulesConfig, assemble
from agent_console_modkit.host import (
    TOKEN_HEADER,
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_UNAUTHORIZED,
    HostSettings,
    JsonWsCodec,
    QueryRedactingFilter,
    SecurityPolicy,
    WsCommand,
    WsInvalid,
    create_host_app,
    install_log_redaction,
    is_loopback_host,
    load_host_settings,
    resolve_token,
    route_topic,
)
from agent_console_modkit.testing import ECHO_SAID, ECHO_TRANSFORM, echo_module, fake_module

TOKEN = "test-token-0123456789"
API = "/api/v1"


def make_app(**policy_kw: Any) -> FastAPI:
    upper = fake_module(
        "mod-upper",
        provides=[ECHO_TRANSFORM],
        on_build=lambda ctx: ctx.provide(ECHO_TRANSFORM, str.upper),
    )
    assembly = assemble([echo_module, upper], ModulesConfig(options={"echo": {"prefix": "> "}}))
    # TestClient의 Host는 "testserver"다(허용 목록에 넣는다).
    policy = SecurityPolicy.for_bind(
        "127.0.0.1",
        0,
        token=TOKEN,
        max_request_bytes=2048,
        allowed_hosts=["testserver"],
        **policy_kw,
    )
    return create_host_app(assembly, policy=policy)


@pytest.fixture
def client() -> Any:
    with TestClient(make_app()) as c:
        yield c


def test_health_and_module_routes(client: TestClient) -> None:
    health = client.get(f"{API}/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "modules": {"echo": "active", "mod-upper": "active"}}
    assert health.headers["cache-control"] == "no-store"
    assert health.headers["x-frame-options"] == "DENY"
    assert client.get(f"{API}/echo", params={"text": "hi"}).json() == {"text": "> HI"}


def test_health_is_not_ready_before_start_and_after_stop() -> None:
    """3R.16: 모듈 시작 훅이 끝나기 전·종료 뒤 `/health`는 503 `not_ready`(200 = 준비)."""
    app = make_app()
    before = TestClient(app).get(f"{API}/health")
    assert before.status_code == 503
    assert before.json()["error"]["code"] == "not_ready"
    assert before.headers["retry-after"] == "1"
    with TestClient(app) as client:
        assert client.get(f"{API}/health").status_code == 200
        assert app.state.assembly.running is True
    assert app.state.assembly.running is False


def test_error_map_turns_module_exception_into_error_body(client: TestClient) -> None:
    response = client.get(f"{API}/echo/missing")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "없는 메아리", "details": {}}
    }


def test_token_host_origin_and_size_checks(client: TestClient) -> None:
    unauthorized = client.post(f"{API}/echo/c", json={"text": "x"})
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"
    ok = client.post(f"{API}/echo/c", json={"text": "x"}, headers={TOKEN_HEADER: TOKEN})
    assert ok.status_code == 200
    bad_host = client.get(f"{API}/health", headers={"host": "evil.example"})
    assert bad_host.status_code == 403
    cross = client.post(
        f"{API}/echo/c",
        json={"text": "x"},
        headers={TOKEN_HEADER: TOKEN, "origin": "http://evil.example"},
    )
    assert cross.status_code == 403
    big = client.post(f"{API}/echo/c", json={"text": "x" * 4096}, headers={TOKEN_HEADER: TOKEN})
    assert big.status_code == 413


def test_cors_only_for_listed_origins() -> None:
    app = make_app(allowed_origins=["http://localhost:5173"])
    with TestClient(app) as c:
        allowed = c.options(
            f"{API}/echo/c",
            headers={"origin": "http://localhost:5173", "access-control-request-method": "POST"},
        )
        assert allowed.status_code == 204
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        denied = c.options(
            f"{API}/echo/c",
            headers={"origin": "http://other:1", "access-control-request-method": "POST"},
        )
        assert denied.status_code == 403


def test_ws_auth_close_codes(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws") as ws:
        ws.receive_text()
    assert exc.value.code == WS_CLOSE_UNAUTHORIZED
    with (
        pytest.raises(WebSocketDisconnect) as exc2,
        client.websocket_connect(f"/ws?token={TOKEN}", headers={"origin": "http://evil"}) as ws,
    ):
        ws.receive_text()
    assert exc2.value.code == WS_CLOSE_FORBIDDEN


def test_ws_topics_are_multiplexed_to_module_handlers(client: TestClient) -> None:
    seen: list[str] = []
    assembly = client.app.state.assembly  # type: ignore[attr-defined]
    assembly.services.events.subscribe(ECHO_SAID, seen.append)
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        ws.send_json({"type": "subscribe", "id": "s1", "payload": {"topic": "echo:room"}})
        assert ws.receive_json() == {"type": "echo.ready", "channel": "room"}
        posted = client.post(
            f"{API}/echo/room", json={"text": "hello"}, headers={TOKEN_HEADER: TOKEN}
        )
        assert posted.json() == {"subscribers": 1}
        assert ws.receive_json() == {"type": "echo.said", "text": "hello"}
        ws.send_json({"type": "subscribe", "id": "s2", "payload": {"topic": "echo:forbidden"}})
        rejected = ws.receive_json()
        assert rejected["type"] == "error"
        assert rejected["id"] == "s2"
        assert rejected["payload"]["code"] == "forbidden"
        ws.send_json({"type": "subscribe", "id": "s3", "payload": {"topic": "nope:1"}})
        unknown = ws.receive_json()
        assert unknown["payload"]["details"] == {"reason": "unknown_topic"}
        ws.send_text('{"type": "subscribe", "id": "s4"}')
        invalid = ws.receive_json()
        assert invalid["id"] == "s4"
        assert invalid["payload"]["code"] == "bad_request"
        assert invalid["payload"]["details"]["issues"][0]["path"] == "payload"
        ws.send_text("x" * 5000)  # 기본 메시지 한도 1 MiB 이하라 형식 오류
        assert ws.receive_json()["payload"]["code"] == "bad_request"
        ws.send_json({"type": "unsubscribe", "payload": {"topic": "echo:room"}})
    assert seen == ["hello"]


def test_ws_subscription_limit_and_message_size() -> None:
    app = make_app(max_ws_subscriptions=1, max_ws_message_bytes=1024)
    with (
        TestClient(app) as c,
        c.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_json({"type": "subscribe", "payload": {"topic": "echo:a"}})
        assert ws.receive_json()["type"] == "echo.ready"
        ws.send_json({"type": "subscribe", "id": "2", "payload": {"topic": "echo:b"}})
        limit = ws.receive_json()
        assert limit["payload"]["details"] == {"reason": "subscription_limit"}
        ws.send_text("y" * 2000)
        assert ws.receive_json()["payload"]["code"] == "payload_too_large"


def test_route_topic_exact_and_prefix() -> None:
    async def h(_: Any) -> None:
        return None

    topics = {"run:": h, "interactions": h}
    assert route_topic(topics, "run:r1") == (h, "r1")
    assert route_topic(topics, "interactions") == (h, "")
    assert route_topic(topics, "run:") is None
    assert route_topic(topics, "interactions:x") is None
    assert route_topic(topics, "graph:g") is None


def test_json_codec_round_trip() -> None:
    codec = JsonWsCodec()
    assert codec.decode('{"type":"subscribe","payload":{"topic":"a:b","since_seq":3}}') == (
        WsCommand("subscribe", "a:b", 3, None)
    )
    invalid = codec.decode("not json")
    assert isinstance(invalid, WsInvalid)
    assert invalid.request_id is None
    assert codec.encode({"한": 1}) == '{"한": 1}'


def test_policy_token_and_loopback_helpers() -> None:
    settings = HostSettings.model_validate(
        {"port": 9000, "security": {"allowed_hosts": ["box.lan"]}}
    )
    policy = SecurityPolicy.from_settings(settings, "t")
    assert policy.host_ok("localhost:9000")
    assert not policy.host_ok("localhost:9001")
    assert policy.host_ok("box.lan")
    assert policy.token_ok("t")
    assert not policy.token_ok("u")
    assert not policy.token_ok(None)
    assert resolve_token("a", "b") == "a"
    assert resolve_token(None, "b") == "b"
    assert resolve_token(None, "", generate=lambda: "g") == "g"
    assert len(resolve_token()) >= 32
    assert is_loopback_host("127.0.0.2")
    assert is_loopback_host("[::1]")
    assert not is_loopback_host("0.0.0.0")
    assert HostSettings().host == "127.0.0.1"  # 기본은 루프백


def test_query_redacting_filter() -> None:
    log_filter = QueryRedactingFilter(values=["literal-secret"])
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "GET /ws?token=abc&x=1 %s", ("literal-secret",), None
    )
    log_filter.filter(record)
    assert record.getMessage() == "GET /ws?token=[REDACTED]&x=1 [REDACTED]"
    name = "agent_console_modkit.tests.redact"
    install_log_redaction(log_filter, [name])
    install_log_redaction(log_filter, [name])
    assert logging.getLogger(name).filters.count(log_filter) == 1


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("c.json", '{"port": 1, "modules": {"disabled": ["x"]}, "server_only": true}'),
        ("c.toml", 'port = 1\nserver_only = true\n[modules]\ndisabled = ["x"]\n'),
        ("c.yaml", "port: 1\nserver_only: true\nmodules:\n  disabled: [x]\n"),
    ],
)
def test_load_host_settings_formats(tmp_path: Path, name: str, text: str) -> None:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    settings = load_host_settings(path, overrides={"host": "::1"})
    assert settings.port == 1
    assert settings.host == "::1"
    assert settings.modules.disabled == ["x"]
    paths = settings.paths(tmp_path)
    assert paths.workspace == tmp_path / ".agent-console"


def test_load_host_settings_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("- a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="매핑"):
        load_host_settings(path)


def test_error_mapper_sets_details_message_and_headers() -> None:
    from fastapi import APIRouter

    from agent_console_modkit import ErrorReply, ModuleParts, assemble
    from agent_console_modkit.host import SecurityPolicy, create_host_app
    from agent_console_modkit.testing import fake_module

    class ClashError(Exception):
        pass

    router = APIRouter()

    @router.get("/clash")
    async def clash() -> None:
        raise ClashError("secret-ish")

    def mapper(exc: Exception) -> ErrorReply:
        return ErrorReply(
            code="already_exists", message="충돌", details={"paths": ["a"]}, headers={"ETag": '"x"'}
        )

    mod = fake_module(
        "clash", on_build=lambda ctx: ModuleParts(routers=[router], error_map={ClashError: mapper})
    )
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
    app = create_host_app(assemble([mod]), policy=policy, error_status={"already_exists": 409})
    with TestClient(app) as client:
        response = client.get("/api/v1/clash")
    assert response.status_code == 409
    assert response.headers["etag"] == '"x"'
    assert response.json() == {
        "error": {"code": "already_exists", "message": "충돌", "details": {"paths": ["a"]}}
    }


def test_error_reply_fix_is_in_body_only_when_given() -> None:
    """``ErrorReply.fix``(해결 버튼)는 주었을 때만 본문 ``error.fix``에 들어간다."""
    import json

    from agent_console_modkit.host import error_body

    plain = json.loads(error_body("x", "m", {"a": 1}))
    assert plain == {"error": {"code": "x", "message": "m", "details": {"a": 1}}}
    fix = {"actions": [{"label": "고치기", "target": {"role": "r"}}]}
    assert json.loads(error_body("x", "m", None, fix))["error"]["fix"] == fix
