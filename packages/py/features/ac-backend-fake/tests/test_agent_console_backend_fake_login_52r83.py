"""fake 대본 로그인(5.2R.83, ux-overhaul §15.9): PTY·네트워크 없이 로그인 흐름 전체를 재현한다."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import pytest

from agent_console_backend_fake import (
    FAKE_LOGIN_METHOD_ID,
    FAKE_LOGIN_REQUIRED_STATE,
    FAKE_READY_STATE,
    FakeBackend,
)
from agent_console_contracts import BackendLoginSession
from agent_console_runtime import (
    BackendCheckContext,
    BackendLoginContext,
    BackendLoginService,
    LoginRefusedError,
    SecretResolver,
    supports_login,
    supports_logout,
)

SECRET = "CODE-SECRET-12345"


def _service(backend: FakeBackend, **kwargs: Any) -> BackendLoginService:
    return BackendLoginService(lambda: {"fake": backend}, tick_s=0.02, **kwargs)


async def _until(
    service: BackendLoginService,
    sid: str,
    pred: Callable[[BackendLoginSession], bool],
    timeout: float = 5.0,
) -> BackendLoginSession:
    deadline = time.monotonic() + timeout
    while True:
        view = service.get(sid)
        if pred(view):
            return view
        assert time.monotonic() < deadline, view
        await asyncio.sleep(0.02)


def _done(view: BackendLoginSession) -> bool:
    return view.phase in {"succeeded", "failed", "cancelled", "expired"}


def _logged_in(backend: FakeBackend) -> bool:
    return backend.login_state.logged_in


def _ctx() -> BackendCheckContext:
    return BackendCheckContext("fake", clock=lambda: 1.0)


def test_no_login_by_default() -> None:
    backend = FakeBackend()
    assert backend.descriptor.capabilities.login is False
    assert backend.descriptor.login_methods == []
    assert not supports_login(backend)
    disabled = FakeBackend(login={"enabled": False})
    assert disabled.descriptor.capabilities.login is False


async def test_declares_and_status_follows_memory_state() -> None:
    backend = FakeBackend(login={})
    assert supports_login(backend)
    assert supports_logout(backend)
    assert [m.id for m in backend.descriptor.login_methods] == [FAKE_LOGIN_METHOD_ID]
    status = await backend.status(_ctx())
    assert (status.state, status.tone) == (FAKE_LOGIN_REQUIRED_STATE, "warn")
    assert [(a.kind, a.primary) for a in status.actions] == [("login", True)]
    backend.login_state.logged_in = True
    status = await backend.status(_ctx())
    assert (status.state, status.tone) == (FAKE_READY_STATE, "ok")
    assert [(a.kind, a.primary) for a in status.actions] == [("login", False), ("logout", False)]


async def test_code_ok_succeeds_then_logout() -> None:
    backend = FakeBackend(login={})
    service = _service(backend)
    view = await service.start("fake")
    view = await _until(service, view.session_id, lambda v: v.needs_code)
    assert view.phase == "waiting_user"
    assert view.open_url == "https://login.example.com/oauth/authorize?fake=1"
    assert view.screen
    await service.send_input(view.session_id, text=" ok ")
    final = await _until(service, view.session_id, _done)
    assert final.phase == "succeeded"
    assert _logged_in(backend) is True
    result = await service.logout("fake")
    assert result.ok is True
    assert _logged_in(backend) is False
    await service.aclose()


async def test_wrong_code_fails_and_is_masked(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    backend = FakeBackend(login={"verify_delay_s": 0.05})
    service = _service(backend)
    sid = (await service.start("fake")).session_id
    await _until(service, sid, lambda v: v.needs_code)
    await service.send_input(sid, text=SECRET)
    mid = service.get(sid)
    assert mid.phase in {"verifying", "failed"}
    final = await _until(service, sid, _done)
    assert (final.phase, final.reason) == ("failed", "verify_failed")
    assert _logged_in(backend) is False
    dumped = json.dumps(final.model_dump(mode="json"))
    assert SECRET[:5] not in dumped
    assert SECRET[:5] not in caplog.text
    await service.aclose()


async def test_cancel_while_waiting() -> None:
    backend = FakeBackend(login={})
    service = _service(backend)
    sid = (await service.start("fake")).session_id
    await _until(service, sid, lambda v: v.needs_code)
    final = await service.cancel(sid)
    assert final.phase == "cancelled"
    assert _logged_in(backend) is False
    await service.aclose()


async def test_timeout_expires() -> None:
    backend = FakeBackend(login={})
    service = _service(backend, timeout_default_s=0.2, timeout_max_s=0.2)
    sid = (await service.start("fake")).session_id
    final = await _until(service, sid, _done)
    assert final.phase == "expired"
    assert final.reason == "timeout"
    await service.aclose()


async def test_callback_path_and_delays() -> None:
    backend = FakeBackend(
        login={"needs_code": False, "callback_after_s": 0.05, "start_delay_s": 0.05}
    )
    service = _service(backend)
    view = await service.start("fake")
    assert view.phase == "starting"
    final = await _until(service, view.session_id, _done)
    assert final.phase == "succeeded"
    await service.aclose()


async def test_custom_script_data() -> None:
    backend = FakeBackend(
        login={
            "success_code": "let-me-in",
            "fail_reason": "bad_code",
            "open_url": None,
            "start_logged_in": True,
            "logout_ok": False,
            "texts": {"label": "대본 로그인"},
        }
    )
    assert backend.descriptor.login_methods[0].label == "대본 로그인"
    assert backend.descriptor.login_methods[0].needs_browser is False
    assert _logged_in(backend) is True
    service = _service(backend)
    sid = (await service.start("fake")).session_id
    await _until(service, sid, lambda v: v.needs_code)
    assert service.get(sid).open_url is None
    await service.send_input(sid, text="ok")
    final = await _until(service, sid, _done)
    assert final.reason == "bad_code"
    result = await service.logout("fake")
    assert (result.ok, result.reason) == (False, "logout_failed")
    await service.aclose()


async def test_unknown_method_refused() -> None:
    backend = FakeBackend(login={})
    with pytest.raises(LoginRefusedError):
        await backend.start_login(BackendLoginContext("fake"), "other")


def test_from_options_reads_login() -> None:
    backend = FakeBackend.from_options(
        {"login": {"success_code": "x"}}, secrets=SecretResolver([]), environ={}
    )
    assert backend.descriptor.capabilities.login is True
    with pytest.raises(ValueError, match="login"):
        FakeBackend.from_options({"login": {"nope": 1}}, secrets=SecretResolver([]), environ={})
