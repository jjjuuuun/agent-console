"""WebSocket `/ws`(design §5.3): run 구독 `since_seq` 재생, 오류 상관 id, 콘솔 보류."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_console_modkit import (
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
    WsForward,
    WsReject,
    WsSubscribeRequest,
)
from agent_console_server import create_app, installed_modules
from agent_console_server.testing import (
    API,
    TEST_TOKEN,
    make_settings,
    receive_until,
    seed,
    server,
    wait_run,
    ws_path,
)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with server(make_settings(tmp_path)) as c:
        yield c


def test_agent_console_server_ws_run_replay_since_seq(client: TestClient) -> None:
    """끝난 Run을 `since_seq`로 구독: since_seq 다음부터 빠짐없이 재생되고 `run.completed`로 끝난다.

    스냅샷의 `last_seq`는 기준으로 쓰지 않는다. 기록기는 최종 Run(status)을 저장한 뒤
    `run.completed` 이벤트를 저장하므로, status가 끝났어도 그 순간 `last_seq`에는 마지막
    이벤트가 빠져 있을 수 있다(스냅샷 + `since_seq` 구독으로 보완되는 정상 동작).
    그래서 `run.completed`를 받을 때까지 기다린다.
    """
    seed(client)
    run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "? a"}}).json()
    assert wait_run(client, run["id"])["run"]["status"] == "completed"
    with client.websocket_connect(ws_path()) as ws:
        ws.send_json(
            {"type": "subscribe", "payload": {"topic": f"run:{run['id']}", "since_seq": 2}}
        )
        events = receive_until(ws, lambda m: m["payload"].get("type") == "run.completed")
    assert all(m["type"] == "run.event" for m in events)
    seqs = [m["payload"]["seq"] for m in events]
    assert seqs == list(range(3, 3 + len(seqs)))
    assert len(seqs) > 1
    final = client.get(f"{API}/runs/{run['id']}").json()
    assert final["last_seq"] == seqs[-1]  # run.completed를 받았으면 저장소도 그 seq까지 있다


def test_agent_console_server_ws_run_live_then_no_duplicates(client: TestClient) -> None:
    """실행 중 구독: 재생과 실시간이 겹쳐도 seq가 1..n 연속(중복·누락 없음)."""
    seed(client, delay_ms=20, chunk_chars=2)
    run = client.post(f"{API}/runs", json={"graph_id": "flow", "input": {"request": "깊게"}}).json()
    with client.websocket_connect(ws_path()) as ws:
        ws.send_json({"type": "subscribe", "payload": {"topic": f"run:{run['id']}"}})
        events = receive_until(ws, lambda m: m["payload"].get("type") == "run.completed")
    seqs = [m["payload"]["seq"] for m in events]
    assert seqs == list(range(1, len(seqs) + 1))
    assert any(m["payload"]["type"] == "agent.text_delta" for m in events)


def test_agent_console_server_ws_errors_echo_request_id(client: TestClient) -> None:
    with client.websocket_connect(ws_path()) as ws:
        ws.send_json({"type": "subscribe", "id": "r1", "payload": {"topic": "run:missing"}})
        error = ws.receive_json()
        assert error == {
            "type": "error",
            "id": "r1",
            "payload": {"code": "not_found", "message": error["payload"]["message"], "details": {}},
        }
        ws.send_json({"type": "subscribe", "id": "r2", "payload": {"topic": "weird"}})
        assert ws.receive_json()["payload"]["details"]["reason"] == "unknown_topic"
        ws.send_json({"type": "no-such-type", "id": "r3", "payload": {}})
        bad = ws.receive_json()
        assert bad["id"] == "r3"
        assert bad["payload"]["code"] == "bad_request"
        ws.send_text("{not json")
        assert ws.receive_json()["payload"]["code"] == "bad_request"


def test_agent_console_server_ws_message_size_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, security={"max_ws_message_bytes": 1024})
    with server(settings) as client, client.websocket_connect(ws_path()) as ws:
        ws.send_text('{"type":"console.open","payload":{},"pad":"' + "x" * 2048 + '"}')
        assert ws.receive_json()["payload"]["code"] == "payload_too_large"


class _QuietTopicModule:
    """구독을 받아 두기만 하는 WS 토픽 `quiet:<id>`(구독 한도 시험용)."""

    descriptor = ModuleDescriptor(id="mod-quiet", version="0", kind="feature", title="Quiet")

    def build(self, ctx: ModuleContext) -> ModuleParts:
        async def quiet(_: WsSubscribeRequest) -> WsForward | WsReject | None:
            return None

        return ModuleParts(ws_topics={"quiet:": quiet})


def test_agent_console_server_ws_subscription_limit(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, security={"max_ws_subscriptions": 2})
    modules = [*installed_modules(), _QuietTopicModule()]
    app = create_app(settings, environ={}, token=TEST_TOKEN, modules=modules)
    with TestClient(app) as client, client.websocket_connect(ws_path()) as ws:
        for i in range(2):
            ws.send_json({"type": "subscribe", "payload": {"topic": f"quiet:g{i}"}})
        ws.send_json({"type": "subscribe", "id": "over", "payload": {"topic": "quiet:g9"}})
        error = ws.receive_json()
        assert error["id"] == "over"
        assert error["payload"]["details"]["reason"] == "subscription_limit"
