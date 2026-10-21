"""준비 신호(3R.16, 3R.23 QA 관찰): `/health` 200은 모듈 시작 훅이 끝난 뒤에만.

lifespan을 돌리지 않은 앱(시작 전)에서는 다른 경로가 동작하지 않을 수 있으므로 `/health`도
503 `not_ready`다. 시작이 끝나면 200(준비 신호 계약 그대로), 종료 뒤에는 다시 준비되지 않은 상태다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ErrorCodes, ErrorResponse
from agent_console_server import create_app
from agent_console_server.testing import API, TEST_TOKEN, make_settings


def test_health_is_503_until_modules_started(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), environ={}, token=TEST_TOKEN)
    before = TestClient(app).get(f"{API}/health")  # 컨텍스트 없음 = lifespan 시작 안 함
    assert before.status_code == HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.NOT_READY] == 503
    assert ErrorResponse.model_validate(before.json()).error.code == ErrorCodes.NOT_READY
    assert before.headers["cache-control"] == "no-store"
    with TestClient(app) as client:
        ready = client.get(f"{API}/health")
        assert ready.status_code == 200
        assert ready.json()["contracts_version"]
    assert app.state.assembly.running is False  # 종료 뒤
    assert TestClient(app).get(f"{API}/health").status_code == 503


def test_modules_and_bootstrap_do_not_wait_for_ready(tmp_path: Path) -> None:
    """모듈 목록은 시작 전에도 읽힌다(웹이 상태를 보여 줄 수 있게)."""
    app = create_app(make_settings(tmp_path), environ={}, token=TEST_TOKEN)
    client = TestClient(app)
    assert client.get(f"{API}/modules").status_code == 200
