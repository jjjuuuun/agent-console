"""백엔드 로그인 서비스(5.2R.80, ux-overhaul §15.9 F14).

세션 하나(busy), 시간 상한 자르기·만료, 하트비트, 취소, 종료 훅, 입력 검사(키·글자), 가림(입력값·
부분 문자열·주입 redact), 로그 규칙(값·URL 없음), 능력 없음, 로그아웃.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any, cast

import pytest

from agent_console_contracts import (
    BackendLoginSession,
    BackendLogoutResult,
    FixAction,
    FixTarget,
)
from agent_console_runtime import (
    REDACTED,
    BackendLoginContext,
    BackendLoginService,
    ExecutionBackend,
    LoginBusyError,
    LoginInputError,
    LoginProgress,
    LoginReasons,
    LoginRefusedError,
    LoginSessionNotFoundError,
    LoginUnsupportedError,
    LogoutUnsupportedError,
    UnknownBackendError,
    mask_values,
    supports_login,
    supports_logout,
)
from agent_console_runtime.testing_login import LoginBackendStub, ManualLoginDriver

CODE = "CODE-SECRET-12345"
NOW = 1_700_000_000.0


class Clock:
    def __init__(self) -> None:
        self.mono = 100.0

    def monotonic(self) -> float:
        return self.mono


def make_service(
    *backends: Any, clock: Clock | None = None, **kwargs: Any
) -> tuple[BackendLoginService, Clock]:
    clk = clock or Clock()
    table = {b.descriptor.id: b for b in backends}
    options: dict[str, Any] = {
        "clock": lambda: NOW,
        "monotonic": clk.monotonic,
        "tick_s": 0.01,
        "id_factory": iter(f"s{i}" for i in range(100)).__next__,
    }
    options.update(kwargs)
    service = BackendLoginService(lambda: cast(Mapping[str, ExecutionBackend], table), **options)
    return service, clk


async def until(cond: Any, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not cond():
        if loop.time() > end:
            raise AssertionError("조건을 기다리다 시간 초과")
        await asyncio.sleep(0.01)


def dump(session: BackendLoginSession) -> str:
    return json.dumps(session.model_dump(mode="json"), ensure_ascii=False)


# ---------------------------------------------------------------- 능력


def test_supports_flags() -> None:
    assert supports_login(LoginBackendStub())
    assert supports_logout(LoginBackendStub())
    assert not supports_login(LoginBackendStub(login=False))
    assert not supports_logout(LoginBackendStub(logout=False))
    assert not supports_login(object())


async def test_unknown_and_unsupported() -> None:
    service, _ = make_service(LoginBackendStub("a", login=False, logout=False))
    with pytest.raises(UnknownBackendError):
        await service.start("missing")
    with pytest.raises(LoginUnsupportedError):
        await service.start("a")
    with pytest.raises(LogoutUnsupportedError):
        await service.logout("a")
    assert service.login_supported("a") is False
    assert service.logout_supported("a") is False


async def test_unknown_method_rejected() -> None:
    service, _ = make_service(LoginBackendStub("a"))
    with pytest.raises(LoginUnsupportedError) as info:
        await service.start("a", "nope")
    assert info.value.method_id == "nope"


# ---------------------------------------------------------------- 흐름


async def test_start_poll_code_success() -> None:
    def on_text(d: ManualLoginDriver, text: str) -> None:
        d.update(phase="verifying", needs_code=False, screen=[f"> {text}"])

    backend = LoginBackendStub("a", make_driver=lambda ctx, m: ManualLoginDriver(on_text=on_text))
    service, _ = make_service(backend, environ=lambda: {"HOME": "/h"})
    session = await service.start("a")
    assert session.phase == "waiting_user"
    assert session.method_id == "m1"
    assert session.needs_code
    assert session.accepts_keys == ["enter", "up", "down", "escape"]
    assert session.expires_at == NOW + 300
    assert backend.contexts[0].environ == {"HOME": "/h"}
    assert service.current() is not None

    await service.send_input(session.session_id, text=f"  {CODE}\n")
    driver = backend.drivers[0]
    assert driver.texts == [CODE]  # 앞뒤 공백 자름
    polled = service.get(session.session_id)
    assert polled.phase == "verifying"
    assert CODE not in dump(polled)
    assert polled.screen == [f"> {REDACTED}"]

    driver.update(phase="succeeded", message="로그인됨", screen=[f"code {CODE[:8]} ok"])
    await until(lambda: service.get(session.session_id).phase == "succeeded")
    done = service.get(session.session_id)
    assert done.finished_at == NOW
    assert done.accepts_keys == []
    assert CODE[:8] not in dump(done)
    assert service.current() is None


async def test_second_start_is_busy_and_same_session_visible() -> None:
    service, _ = make_service(LoginBackendStub("a"), LoginBackendStub("b"))
    first = await service.start("a")
    with pytest.raises(LoginBusyError) as info:
        await service.start("b")
    assert info.value.session_id == first.session_id
    assert info.value.backend_id == "a"
    current = service.current()
    assert current is not None
    assert current.session_id == first.session_id
    await service.cancel(first.session_id)
    second = await service.start("b")  # 끝나면 다시 시작할 수 있다
    assert second.backend_id == "b"


async def test_concurrent_starts_only_one_wins() -> None:
    service, _ = make_service(LoginBackendStub("a"))
    results = await asyncio.gather(service.start("a"), service.start("a"), return_exceptions=True)
    assert sum(isinstance(r, BackendLoginSession) for r in results) == 1
    assert sum(isinstance(r, LoginBusyError) for r in results) == 1


async def test_cancel_calls_driver_and_keeps_session_for_retain() -> None:
    backend = LoginBackendStub("a")
    service, clk = make_service(backend, retain_s=60)
    session = await service.start("a")
    cancelled = await service.cancel(session.session_id)
    assert cancelled.phase == "cancelled"
    assert cancelled.reason is None
    assert "취소" in cancelled.message
    assert backend.drivers[0].cancel_calls == 1
    assert (await service.cancel(session.session_id)).phase == "cancelled"  # 두 번째는 그대로
    assert backend.drivers[0].cancel_calls == 1
    clk.mono += 61
    with pytest.raises(LoginSessionNotFoundError):
        service.get(session.session_id)


async def test_timeout_is_clamped_and_expires() -> None:
    backend = LoginBackendStub("a")
    service, clk = make_service(backend, timeout_max_s=100, heartbeat_s=10_000)
    session = await service.start("a", timeout_s=5000)
    assert session.expires_at == NOW + 100
    clk.mono += 101
    await until(lambda: service.get(session.session_id).phase == "expired")
    expired = service.get(session.session_id)
    assert expired.reason == LoginReasons.TIMEOUT
    assert expired.details == {"timeout_s": 100}
    assert backend.drivers[0].cancelled


async def test_heartbeat_lost_cancels() -> None:
    backend = LoginBackendStub("a")
    service, clk = make_service(backend, heartbeat_s=30)
    session = await service.start("a")
    clk.mono += 31  # 조회 없이 시간이 지남
    await until(lambda: backend.drivers[0].cancelled)
    view = service.get(session.session_id)
    assert view.phase == "cancelled"
    assert view.reason == LoginReasons.HEARTBEAT


async def test_polling_keeps_session_alive() -> None:
    backend = LoginBackendStub("a")
    service, clk = make_service(backend, heartbeat_s=30)
    session = await service.start("a")
    for _ in range(5):
        clk.mono += 20
        service.get(session.session_id)
        await asyncio.sleep(0.03)
    assert service.get(session.session_id).phase == "waiting_user"
    assert not backend.drivers[0].cancelled


async def test_success_before_cancel_is_kept() -> None:
    backend = LoginBackendStub("a")
    service, _ = make_service(backend, tick_s=10)  # 감시가 아직 못 봄
    session = await service.start("a")
    backend.drivers[0].update(phase="succeeded", message="ok")
    result = await service.cancel(session.session_id)
    assert result.phase == "succeeded"


async def test_aclose_cancels_active() -> None:
    backend = LoginBackendStub("a")
    service, _ = make_service(backend)
    session = await service.start("a")
    await service.aclose()
    view = service.get(session.session_id)
    assert view.phase == "cancelled"
    assert view.reason == LoginReasons.SHUTDOWN
    assert backend.drivers[0].cancelled
    with pytest.raises(LoginRefusedError):
        await service.start("a")
    await service.aclose()  # 여러 번


async def test_driver_cancel_failure_still_finishes(caplog: pytest.LogCaptureFixture) -> None:
    backend = LoginBackendStub("a", make_driver=lambda c, m: ManualLoginDriver(fail_cancel=True))
    service, _ = make_service(backend)
    session = await service.start("a")
    with caplog.at_level(logging.WARNING, logger="agent_console_runtime.login"):
        assert (await service.cancel(session.session_id)).phase == "cancelled"
    assert "RuntimeError" in caplog.text


async def test_start_exception_becomes_failed_session() -> None:
    def boom(ctx: BackendLoginContext, method: str) -> Any:
        raise OSError(f"spawn failed with {CODE}")

    service, _ = make_service(LoginBackendStub("a", make_driver=boom))
    session = await service.start("a")
    assert session.phase == "failed"
    assert session.reason == LoginReasons.START_FAILED
    assert session.details == {"error": "OSError"}
    assert CODE not in dump(session)
    assert service.current() is None


async def test_refused_propagates_without_session() -> None:
    def refuse(ctx: BackendLoginContext, method: str) -> Any:
        raise LoginRefusedError("backend.subscription_auth_disabled", "구독 인증이 꺼져 있습니다")

    service, _ = make_service(LoginBackendStub("a", make_driver=refuse))
    with pytest.raises(LoginRefusedError) as info:
        await service.start("a")
    assert info.value.code == "backend.subscription_auth_disabled"
    assert service.current() is None


# ---------------------------------------------------------------- 입력


async def test_input_validation() -> None:
    backend = LoginBackendStub(
        "a",
        make_driver=lambda c, m: ManualLoginDriver(
            LoginProgress(phase="waiting_user", accepts_keys=["enter"])
        ),
    )
    service, _ = make_service(backend)
    session = await service.start("a")
    sid = session.session_id
    with pytest.raises(LoginInputError) as info:
        await service.send_input(sid, key="up")
    assert info.value.reason == LoginInputError.KEY_NOT_ACCEPTED
    await service.send_input(sid, key="enter")
    assert backend.drivers[0].keys == ["enter"]
    for bad in ("   ", "a\x1bb", "line\nbreak"):
        with pytest.raises(LoginInputError) as info:
            await service.send_input(sid, text=bad)
        assert info.value.reason == LoginInputError.TEXT_INVALID
        assert bad.strip() not in str(info.value) or not bad.strip()
    with pytest.raises(LoginInputError):
        await service.send_input(sid)
    await service.cancel(sid)
    with pytest.raises(LoginInputError) as info:
        await service.send_input(sid, text=CODE)
    assert info.value.reason == LoginInputError.SESSION_FINISHED
    with pytest.raises(LoginSessionNotFoundError):
        await service.send_input("nope", text="x")


async def test_driver_send_failure_hides_value(caplog: pytest.LogCaptureFixture) -> None:
    def explode(d: ManualLoginDriver, text: str) -> None:
        raise OSError(f"write failed: {text}")

    backend = LoginBackendStub("a", make_driver=lambda c, m: ManualLoginDriver(on_text=explode))
    service, _ = make_service(backend)
    session = await service.start("a")
    with caplog.at_level(logging.DEBUG), pytest.raises(LoginInputError) as info:
        await service.send_input(session.session_id, text=CODE)
    assert CODE not in str(info.value)
    assert info.value.__cause__ is None
    assert CODE not in caplog.text


# ---------------------------------------------------------------- 가림·로그


async def test_masking_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    redacted: list[Any] = []

    def redact(value: Any) -> Any:
        redacted.append(value)
        text = json.dumps(value).replace("sk-env-777", REDACTED)
        return json.loads(text)

    backend = LoginBackendStub("a")
    service, _ = make_service(backend, redact=redact)
    with caplog.at_level(logging.DEBUG):
        session = await service.start("a")
        await service.send_input(session.session_id, text=CODE)
        driver = backend.drivers[0]
        driver.update(
            phase="failed",
            message=f"bad code {CODE}",
            screen=["head", f"...{CODE[3:]}", f"{CODE[:6]}", "key sk-env-777"],
            details={"echo": CODE, "exit_code": 1},
            reason="verify_failed",
            fixes=[FixAction(label=f"retry {CODE}", target=FixTarget(role="settings"))],
            open_url="https://login.example/authorize?x=1",
        )
        await until(lambda: service.get(session.session_id).phase == "failed")
        view = service.get(session.session_id)
    text = dump(view)
    for part in (CODE, CODE[:5], CODE[3:], CODE[-5:], "sk-env-777"):
        assert part not in text
    assert view.screen[0] == "head"
    assert view.details["exit_code"] == 1
    assert redacted, "주입 redact가 불렸다"
    assert CODE[:5] not in caplog.text
    assert "login.example" not in caplog.text
    assert "session=s0" in caplog.text
    assert "phase=failed" in caplog.text
    assert "reason=verify_failed" in caplog.text


async def test_screen_is_limited() -> None:
    backend = LoginBackendStub(
        "a",
        make_driver=lambda c, m: ManualLoginDriver(
            LoginProgress(phase="waiting_user", screen=[str(i) for i in range(100)])
        ),
    )
    service, _ = make_service(backend, screen_max_lines=3)
    session = await service.start("a")
    assert session.screen == ["97", "98", "99"]


def test_mask_values_short_and_parts() -> None:
    assert mask_values("a abc b", ["abc"]) == f"a {REDACTED} b"
    assert mask_values("xx12345yy", ["0123456789"]) == f"xx{REDACTED}yy"
    assert mask_values("xx1234yy", ["0123456789"]) == "xx1234yy"
    assert mask_values("", ["abc"]) == ""
    assert mask_values("abc", []) == "abc"


def test_invalid_options() -> None:
    with pytest.raises(ValueError, match="0보다"):
        BackendLoginService(dict, heartbeat_s=0)
    with pytest.raises(ValueError, match="0 이상"):
        BackendLoginService(dict, retain_s=-1)


def test_clamp_timeout() -> None:
    service = BackendLoginService(dict, timeout_default_s=300, timeout_max_s=900)
    assert service.clamp_timeout(None) == 300
    assert service.clamp_timeout(10) == 10
    assert service.clamp_timeout(5000) == 900
    assert service.clamp_timeout(-1) == 300


# ---------------------------------------------------------------- 로그아웃


async def test_logout_ok_and_busy() -> None:
    backend = LoginBackendStub("a")
    service, _ = make_service(backend, LoginBackendStub("b"))
    result = await service.logout("a")
    assert result.ok
    assert backend.logout_calls == 1
    session = await service.start("a")
    with pytest.raises(LoginBusyError):
        await service.logout("a")
    assert (await service.logout("b")).ok  # 다른 백엔드는 막지 않는다
    await service.cancel(session.session_id)


async def test_logout_errors_are_results() -> None:
    def bad(ctx: BackendLoginContext) -> BackendLogoutResult:
        raise RuntimeError(f"secret {CODE}")

    service, _ = make_service(LoginBackendStub("a", logout_result=bad))
    result = await service.logout("a")
    assert not result.ok
    assert result.reason == LoginReasons.ERROR
    assert CODE not in result.model_dump_json()


async def test_logout_timeout() -> None:
    class Slow(LoginBackendStub):
        async def logout(
            self, ctx: BackendLoginContext, method_id: str | None
        ) -> BackendLogoutResult:
            await asyncio.sleep(10)
            raise AssertionError  # pragma: no cover

    service, _ = make_service(Slow("a"), logout_timeout_s=0.05)
    result = await service.logout("a")
    assert result.reason == LoginReasons.TIMEOUT
