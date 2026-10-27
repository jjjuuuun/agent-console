"""백엔드 로그인 계약(0.8.0 F14, ux-overhaul §15.9-5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    BACKEND_LOGIN_TEXT_MAX_CHARS,
    HTTP_STATUS_BY_ERROR_CODE,
    BackendCapabilities,
    BackendDescriptor,
    BackendLoginInput,
    BackendLoginSession,
    BackendLoginStartRequest,
    BackendLogoutResult,
    BackendReadiness,
    ErrorCodes,
    LoginMethodInfo,
    ReadinessAction,
    build_schema,
)


def test_defaults_are_off_and_empty() -> None:
    caps = BackendCapabilities()
    assert (caps.login, caps.logout) == (False, False)
    desc = BackendDescriptor(id="b", title="B")
    assert desc.login_methods == []
    ready = BackendReadiness(backend_id="b", state="s", tone="ok", checked_at=1.0)
    assert ready.actions == []


def test_descriptor_with_methods_and_actions() -> None:
    desc = BackendDescriptor(
        id="b",
        title="B",
        capabilities=BackendCapabilities(login=True, logout=True),
        login_methods=[LoginMethodInfo(id="cli-login", label="구독으로 로그인", writes=["~/x"])],
    )
    assert desc.login_methods[0].needs_browser is True
    action = ReadinessAction(
        kind="login", method_id="cli-login", label="구독으로 로그인", primary=True
    )
    ready = BackendReadiness(
        backend_id="b", state="s", tone="warn", checked_at=1.0, actions=[action]
    )
    assert ready.model_dump(mode="json")["actions"][0]["kind"] == "login"


def test_input_one_of_and_limit() -> None:
    assert BackendLoginInput(text="abc").key is None
    assert BackendLoginInput(key="enter").text is None
    with pytest.raises(ValidationError):
        BackendLoginInput()
    with pytest.raises(ValidationError):
        BackendLoginInput(text="a", key="enter")
    with pytest.raises(ValidationError):
        BackendLoginInput(text="x" * (BACKEND_LOGIN_TEXT_MAX_CHARS + 1))


def test_session_phase_is_closed_vocabulary() -> None:
    base = {
        "session_id": "s",
        "backend_id": "b",
        "method_id": "m",
        "started_at": 1.0,
        "expires_at": 2.0,
    }
    assert BackendLoginSession.model_validate({**base, "phase": "waiting_user"}).needs_code is False
    with pytest.raises(ValidationError):
        BackendLoginSession.model_validate({**base, "phase": "weird"})


def test_request_and_logout_result() -> None:
    assert BackendLoginStartRequest().method_id is None
    with pytest.raises(ValidationError):
        BackendLoginStartRequest(timeout_s=0)
    result = BackendLogoutResult(backend_id="b", ok=True, finished_at=1.0)
    assert result.reason is None


def test_error_codes_and_schema() -> None:
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_LOGIN_BUSY] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_LOGIN_UNSUPPORTED] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_LOGOUT_UNSUPPORTED] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_SUBSCRIPTION_AUTH_DISABLED] == 409
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_LOGIN_SESSION_NOT_FOUND] == 404
    defs = build_schema()["$defs"]
    for name in (
        "BackendLoginSession",
        "BackendLoginInput",
        "BackendLoginStartRequest",
        "BackendLogoutResult",
        "LoginMethodInfo",
        "ReadinessAction",
    ):
        assert name in defs
    text = defs["BackendLoginInput"]["properties"]["text"]
    assert text["writeOnly"] is True
    assert text["x-secret"] is True
