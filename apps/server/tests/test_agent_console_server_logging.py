"""토큰·비밀성 쿼리 값이 서버 로그에 남지 않는다(실제 `serve()` 경로 포함)."""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from websockets.sync.client import connect

from agent_console_server import QueryRedactingFilter, install_log_redaction

TOKEN = "serve-token-SHOULD-NOT-APPEAR-0123456789"
START_TIMEOUT = 90.0


def test_agent_console_server_query_redacting_filter() -> None:
    f = QueryRedactingFilter(values=["literal-secret-value"])
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", "/ws?a=1&token=abc123&Api_Key=k9&x=literal-secret-value"),
        None,
    )
    assert f.filter(record)
    message = record.getMessage()
    assert "abc123" not in message
    assert "k9" not in message
    assert "literal-secret-value" not in message
    assert "a=1" in message
    assert message.count("[REDACTED]") == 3
    plain = logging.LogRecord("x", logging.INFO, __file__, 1, "GET /?token=zz", None, None)
    f.filter(plain)
    assert plain.getMessage() == "GET /?token=[REDACTED]"


def test_agent_console_server_install_log_redaction_idempotent() -> None:
    f = QueryRedactingFilter()
    name = "agent_console_server.test.redaction"
    install_log_redaction(f, [name])
    install_log_redaction(f, [name])
    logger = logging.getLogger(name)
    assert logger.filters.count(f) == 1
    logger.removeFilter(f)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _wait_ready(port: int, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError("서버가 시작 중에 종료됐다")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/node-types", timeout=2):
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("서버가 시간 안에 준비되지 않았다")


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT 종료 경로는 POSIX에서 확인")
def test_agent_console_server_serve_logs_hide_token(tmp_path: Path) -> None:
    """실제 uvicorn(`python -m agent_console_server`)으로 띄워 쿼리 토큰이 출력에 없는지 본다."""
    port = _free_port()
    env = {
        **os.environ,
        "AGENT_CONSOLE_TOKEN": TOKEN,
        "AGENT_CONSOLE_WORKSPACE": str(tmp_path / "ws"),
        "AGENT_CONSOLE_LOG_LEVEL": "debug",
        "PYTHONUNBUFFERED": "1",
    }
    env.pop("AGENT_CONSOLE_CONFIG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "agent_console_server", "--port", str(port)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_ready(port, proc)
        with connect(f"ws://127.0.0.1:{port}/ws?token={TOKEN}") as ws:
            ws.send('{"type": "subscribe", "id": "s", "payload": {"topic": "interactions"}}')
        with (
            pytest.raises(Exception, match="4401"),
            connect(f"ws://127.0.0.1:{port}/ws?token=wrong-{TOKEN}") as bad,
        ):
            bad.recv(timeout=10)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/node-types?token={TOKEN}", timeout=5
        ):
            pass
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            output, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
    text = output.decode("utf-8", errors="replace")
    assert "WebSocket /ws" in text  # uvicorn이 WS 연결 줄을 남겼고
    assert "[REDACTED]" in text  # 쿼리 값은 가려졌다
    assert TOKEN not in text
    assert "KeyboardInterrupt" not in text  # SIGINT는 정상 종료
    assert proc.returncode == 0
