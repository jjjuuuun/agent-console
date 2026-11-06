"""테스트 지원 모듈 `testing`: WS 수신 도우미의 상한 시간(멈춘 테스트가 CI를 막지 않게)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_server.testing import (
    make_settings,
    receive_json,
    receive_until,
    server,
    ws_path,
)


def test_receive_json_returns_message(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client, client.websocket_connect(ws_path()) as ws:
        ws.send_json({"type": "subscribe", "id": "x", "payload": {"topic": "conversation:nope"}})
        message = receive_until(ws, lambda m: m.get("id") == "x" or "code" in m.get("payload", {}))
        assert message[-1]["payload"]["code"] == "not_found"


def test_receive_json_times_out_instead_of_hanging(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client, client.websocket_connect(ws_path()) as ws:
        with pytest.raises(AssertionError, match="초 안에 오지 않았다"):
            receive_until(ws, lambda _m: False, timeout=0.3)
        with pytest.raises(AssertionError, match="초 안에 오지 않았다"):
            receive_json(ws, timeout=0.2)
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:nope"}})
        assert receive_json(ws)["payload"]["code"] == "not_found"  # 시간 초과 뒤에도 수신이 된다
