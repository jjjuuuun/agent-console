"""구독 로그인 ``cli-login``(5.2R.82, ux-overhaul §15.9) — 스텁 CLI로만, 실제 CLI·로그인 없음.

스텁은 ``tests/claude_cli_stub.py``이고 임시 ``CLAUDE_CONFIG_DIR``에만 쓴다. POSIX에서 실제 PTY로
돈다(PTY가 없는 환경은 건너뛴다).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from agent_console_backend_claude_sdk import (
    CLI_LOGIN_METHOD_ID,
    ClaudeSdkBackend,
    ClaudeSdkLoginOptions,
    ClaudeSdkLoginRules,
    EnvPolicy,
    PtySupport,
    ReadinessStates,
    allowed_open_url,
    login_env,
    parse_auth_method,
    writes_lines,
)
from agent_console_contracts import BackendLoginSession, ErrorCodes
from agent_console_pty_session import FakePty, pty_available
from agent_console_runtime import (
    BackendCheckContext,
    BackendLoginContext,
    BackendLoginService,
    LoginRefusedError,
    SecretResolver,
    supports_login,
    supports_logout,
)

STUB = str(Path(__file__).with_name("claude_cli_stub.py"))
SECRET_CODE = "CODE-SECRET-12345"
needs_pty = pytest.mark.skipif(
    sys.platform == "win32" or not pty_available(), reason="POSIX PTY가 필요하다"
)


def _cmd(scenario: str, verb: str) -> list[str]:
    return [sys.executable, STUB, scenario, "auth", verb]


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "claude-config"
    folder.mkdir()
    return folder


def _environ(config_dir: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(config_dir.parent),
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "ANTHROPIC_API_KEY": "sk-ant-should-not-pass",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-should-not-pass",
        "SECRET_OTHER": "other-should-not-pass",
    }


def _backend(
    config_dir: Path,
    scenario: str = "code",
    *,
    status_scenario: str | None = None,
    allow: bool = True,
    login: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ClaudeSdkBackend:
    opts: dict[str, Any] = {
        "command": _cmd(scenario, "login"),
        "status_command": _cmd(status_scenario or scenario, "status"),
        "logout_command": _cmd(scenario, "logout"),
        "terminate_grace_s": 0.5,
        "exit_wait_s": 3.0,
        "status_timeout_s": 10.0,
    }
    opts.update(login or {})
    environ = _environ(config_dir)
    return ClaudeSdkBackend(
        environ=environ,
        allow_subscription_auth=allow,
        cli_locator=lambda _p: "/stub/claude",
        path_exists=lambda p: Path(p).exists(),
        login=opts,
        **kwargs,
    )


def _service(backend: ClaudeSdkBackend, **kwargs: Any) -> BackendLoginService:
    return BackendLoginService(
        lambda: {backend.descriptor.id: backend},
        tick_s=0.05,
        **kwargs,
    )


async def _until(
    service: BackendLoginService,
    sid: str,
    pred: Callable[[BackendLoginSession], bool],
    timeout: float = 15.0,
) -> BackendLoginSession:
    deadline = time.monotonic() + timeout
    while True:
        view = service.get(sid)
        if pred(view):
            return view
        if time.monotonic() > deadline:
            raise AssertionError(f"시간 초과: phase={view.phase} screen={view.screen}")
        await asyncio.sleep(0.05)


def _done(view: BackendLoginSession) -> bool:
    return view.phase in {"succeeded", "failed", "cancelled", "expired"}


def _gone(pid: int | None) -> bool:
    """프로세스가 없다(거두지 않은 좀비도 남은 것으로 본다)."""
    return pid is None or not Path(f"/proc/{pid}").exists()


def _driver_pid(backend: ClaudeSdkBackend, service: BackendLoginService) -> int | None:
    rec = next(iter(service._sessions.values()))
    return getattr(rec.driver, "pid", None)


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """실제 ~/.claude를 건드리지 않게 테스트 프로세스 환경도 비운다(스텁은 주입 환경만 본다)."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


# ---------------------------------------------------------------- 디스크립터·상태


def test_descriptor_declares_login_when_enabled(config_dir: Path) -> None:
    b = _backend(config_dir, pty_support=PtySupport(True))
    caps = b.descriptor.capabilities
    assert caps.login is True
    assert caps.logout is True
    assert [m.id for m in b.descriptor.login_methods] == [CLI_LOGIN_METHOD_ID]
    method = b.descriptor.login_methods[0]
    assert method.label == "구독으로 로그인"
    assert "본인 책임" in method.notice
    assert "claude auth logout" in method.notice
    assert method.writes[0].endswith(str(config_dir / ".credentials.json"))
    assert supports_login(b)
    assert supports_logout(b)


@pytest.mark.parametrize(
    ("allow", "enabled", "pty"),
    [(False, True, True), (True, False, True), (True, True, False)],
)
def test_no_capability_when_disabled(
    config_dir: Path, allow: bool, enabled: bool, pty: bool
) -> None:
    b = _backend(
        config_dir,
        allow=allow,
        login={"enabled": enabled},
        pty_support=PtySupport(pty, None if pty else "missing_package"),
    )
    assert b.descriptor.capabilities.login is False
    assert b.descriptor.capabilities.logout is False
    assert b.descriptor.login_methods == []
    assert not supports_login(b)


def _check_ctx() -> BackendCheckContext:
    return BackendCheckContext(backend_id="claude-agent-sdk", clock=lambda: 1.0)


async def test_status_actions_follow_login_file(config_dir: Path) -> None:
    b = _backend(config_dir, pty_support=PtySupport(True))
    r = await b.status(_check_ctx())
    assert r.state == ReadinessStates.SUBSCRIPTION_UNVERIFIED
    assert [(a.kind, a.primary, a.method_id) for a in r.actions] == [
        ("login", True, CLI_LOGIN_METHOD_ID)
    ]
    (config_dir / ".credentials.json").write_text("{}")
    r = await b.status(_check_ctx())
    assert r.state == ReadinessStates.SUBSCRIPTION_READY
    assert [(a.kind, a.primary) for a in r.actions] == [("login", False), ("logout", False)]


async def test_status_without_pty_has_note_not_failure(config_dir: Path) -> None:
    b = _backend(config_dir, pty_support=PtySupport(False, "missing_package"))
    r = await b.status(_check_ctx())
    assert r.state == ReadinessStates.SUBSCRIPTION_UNVERIFIED
    assert r.actions == []
    assert "[login]" in r.detail


async def test_status_no_actions_when_disallowed_or_token(config_dir: Path) -> None:
    b = _backend(config_dir, allow=False, pty_support=PtySupport(True))
    assert (await b.status(_check_ctx())).actions == []
    b = _backend(
        config_dir,
        pty_support=PtySupport(True),
        readiness={"auth": {"mode": "subscription", "oauth_token": "secret://tok"}},
    )
    r = await b.status(
        BackendCheckContext(
            backend_id="claude-agent-sdk", clock=lambda: 1.0, has_secret=lambda n: True
        )
    )
    assert r.state == ReadinessStates.SUBSCRIPTION_READY
    assert r.actions == []


async def test_start_refused_when_subscription_disabled(config_dir: Path) -> None:
    b = _backend(config_dir, allow=False, pty_support=PtySupport(True))
    with pytest.raises(LoginRefusedError) as info:
        await b.start_login(BackendLoginContext("claude-agent-sdk"), CLI_LOGIN_METHOD_ID)
    assert info.value.code == ErrorCodes.BACKEND_SUBSCRIPTION_AUTH_DISABLED


def test_from_options_reads_login(config_dir: Path) -> None:
    b = ClaudeSdkBackend.from_options(
        {"login": {"enabled": False}}, secrets=SecretResolver([]), environ={}
    )
    assert b.descriptor.capabilities.login is False
    with pytest.raises(ValueError, match="login"):
        ClaudeSdkBackend.from_options(
            {"login": {"rules": {"success": ["(a+)+$"]}}}, secrets=SecretResolver([]), environ={}
        )


# ---------------------------------------------------------------- 부품


def test_rules_are_safe_checked() -> None:
    with pytest.raises(ValueError, match="needs_code"):
        ClaudeSdkLoginOptions.model_validate({"rules": {"needs_code": ["(a+)+$"]}})
    assert ClaudeSdkLoginRules().named()[0] == ("open_url", r"https://\S+/oauth/authorize\S*")


def test_open_url_https_and_hosts_only() -> None:
    hosts = ClaudeSdkLoginOptions().allowed_url_hosts
    assert allowed_open_url("https://claude.ai/oauth/authorize?a=1", hosts)
    assert allowed_open_url("https://www.claude.com/cai/oauth/authorize", hosts)
    assert allowed_open_url("http://claude.ai/oauth/authorize", hosts) is None
    assert allowed_open_url("https://claude.ai.evil.example/oauth/authorize", hosts) is None
    assert allowed_open_url("https://user:pw@claude.ai/oauth/authorize", hosts) is None
    assert allowed_open_url("javascript:alert(1)", hosts) is None


def test_login_env_blanks_keys_and_drops_unlisted() -> None:
    env = login_env(
        {"PATH": "/bin", "ANTHROPIC_API_KEY": "k", "SECRET_OTHER": "x", "XDG_RUNTIME_DIR": "/r"},
        EnvPolicy(),
        ClaudeSdkLoginOptions(),
    )
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == ""
    assert "SECRET_OTHER" not in env
    assert env["XDG_RUNTIME_DIR"] == "/r"


def test_writes_first_resolved_only() -> None:
    opts = ClaudeSdkLoginOptions()
    assert writes_lines(opts, {"HOME": "/h"})[0].endswith("/h/.claude/.credentials.json")
    lines = writes_lines(opts, {"HOME": "/h", "CLAUDE_CONFIG_DIR": "/c"})
    assert lines[0].endswith("/c/.credentials.json")
    assert not any("/h/" in line for line in lines)


def test_parse_auth_method() -> None:
    assert parse_auth_method('noise {"authMethod": "claude.ai"}') == "claude.ai"
    assert parse_auth_method("[1,2]") is None


# ---------------------------------------------------------------- 스텁 CLI 시나리오(실제 PTY)


@needs_pty
async def test_code_paste_success_and_secret_masked(
    config_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    backend = _backend(config_dir, "code", login={"submit_keys": ["enter"]})
    service = _service(backend)
    view = await service.start(backend.descriptor.id)
    sid = view.session_id
    view = await _until(service, sid, lambda v: v.needs_code)
    assert view.phase == "waiting_user"
    assert view.open_url is not None
    assert view.open_url.startswith("https://claude.ai/oauth/authorize")
    assert view.code_label
    # 코드가 틀리면(스텁은 GOOD-CODE만 받는다) 실패 — 먼저 비밀 문자열로 가림 확인
    await service.send_input(sid, text=f"  {SECRET_CODE}  ")
    final = await _until(service, sid, _done)
    assert final.phase == "failed"
    assert final.reason == "exited"
    dumped = json.dumps(final.model_dump(mode="json"))
    for part in (SECRET_CODE, SECRET_CODE[:5], SECRET_CODE[-6:]):
        assert part not in dumped
        assert part not in caplog.text
    assert not (config_dir / ".credentials.json").exists()
    await service.aclose()


@needs_pty
async def test_code_paste_good_code_succeeds(config_dir: Path) -> None:
    backend = _backend(config_dir, "code")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    await _until(service, sid, lambda v: v.needs_code)
    pid = _driver_pid(backend, service)
    await service.send_input(sid, text="GOOD-CODE")
    final = await _until(service, sid, _done)
    assert final.phase == "succeeded", final
    assert final.details.get("status_exit_code") == 0
    assert final.details.get("auth_method") == "claude.ai"
    assert (config_dir / ".credentials.json").exists()
    assert _gone(pid)
    # 하위 프로세스 환경: 키·토큰은 빈 값, 목록 밖 변수는 없음
    seen = json.loads((config_dir / "env.json").read_text())
    assert seen == {
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "CLAUDE_CODE_OAUTH_TOKEN": "",
        "SECRET_OTHER": None,
    }
    await service.aclose()


@needs_pty
async def test_callback_success_without_code(config_dir: Path) -> None:
    backend = _backend(config_dir, "callback")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    final = await _until(service, sid, _done)
    assert final.phase == "succeeded"
    assert (config_dir / ".credentials.json").exists()
    await service.aclose()


@needs_pty
async def test_no_url_then_cancel_leaves_nothing(config_dir: Path) -> None:
    backend = _backend(config_dir, "nourl")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    view = await _until(service, sid, lambda v: any("Starting" in line for line in v.screen))
    assert view.phase == "starting"
    assert view.open_url is None
    pid = _driver_pid(backend, service)
    final = await service.cancel(sid)
    assert final.phase == "cancelled"
    assert _gone(pid)
    assert not (config_dir / ".credentials.json").exists()
    await service.aclose()


@needs_pty
async def test_silent_exit_with_status_zero_succeeds(config_dir: Path) -> None:
    backend = _backend(config_dir, "silent")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    final = await _until(service, sid, _done)
    assert final.phase == "succeeded"
    await service.aclose()


@needs_pty
async def test_success_text_but_status_one_is_verify_failed(config_dir: Path) -> None:
    backend = _backend(config_dir, "false_success")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    final = await _until(service, sid, _done)
    assert final.phase == "failed"
    assert final.reason == "verify_failed"
    assert final.details.get("status_exit_code") == 1
    await service.aclose()


@needs_pty
async def test_cancel_kills_process_ignoring_sigterm(config_dir: Path) -> None:
    backend = _backend(config_dir, "ignore_term", login={"terminate_grace_s": 0.3})
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    await _until(service, sid, lambda v: v.open_url is not None)
    pid = _driver_pid(backend, service)
    assert pid is not None
    assert not _gone(pid)
    final = await service.cancel(sid)
    assert final.phase == "cancelled"
    assert _gone(pid)
    await service.aclose()


@needs_pty
async def test_timeout_expires_and_kills(config_dir: Path) -> None:
    backend = _backend(config_dir, "nourl")
    service = _service(backend, timeout_default_s=0.6, timeout_max_s=0.6)
    sid = (await service.start(backend.descriptor.id)).session_id
    await asyncio.sleep(0.2)
    pid = _driver_pid(backend, service)
    final = await _until(service, sid, _done)
    assert final.phase == "expired"
    assert _gone(pid)
    await service.aclose()


@needs_pty
async def test_disallowed_url_not_offered(config_dir: Path) -> None:
    backend = _backend(config_dir, "bad_url")
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    view = await _until(service, sid, lambda v: any("evil" in line for line in v.screen))
    assert view.open_url is None
    await service.cancel(sid)
    await service.aclose()


@needs_pty
async def test_logout_runs_logout_command(config_dir: Path) -> None:
    (config_dir / ".credentials.json").write_text("{}")
    backend = _backend(config_dir, "code")
    service = _service(backend)
    result = await service.logout(backend.descriptor.id)
    assert result.ok is True
    assert not (config_dir / ".credentials.json").exists()
    status = await backend.status(_check_ctx())
    assert status.state == ReadinessStates.SUBSCRIPTION_UNVERIFIED


async def test_cli_missing_is_failed_session(config_dir: Path) -> None:
    backend = ClaudeSdkBackend(
        environ=_environ(config_dir),
        cli_locator=lambda _p: None,
        pty_support=PtySupport(True),
        pty_spawner=FakePty().spawn,
    )
    service = _service(backend)
    view = await service.start(backend.descriptor.id)
    assert view.phase == "failed"
    assert view.reason == "cli_missing"
    assert view.fixes
    result = await service.logout(backend.descriptor.id)
    assert result.ok is False
    assert result.reason == "cli_missing"


async def test_fake_pty_flow_with_osc8_link(config_dir: Path) -> None:
    """FakePty로 OSC 8 링크만 있는 화면 → open_url, 성공 문구 → Enter 자동 전송."""
    url = "https://claude.com/cai/oauth/authorize?x=1"

    def script(pty: FakePty, text: str) -> None:
        if text == "\r" and pty.inputs.count("\r") == 1:
            (config_dir / ".credentials.json").write_text("{}")
            pty.emit("Login successful\r\n")
        elif text == "\r":
            pty.exit(0)

    fake = FakePty(
        output=f"\x1b]8;;{url}\x1b\\sign in\x1b]8;;\x1b\\\r\nPaste code here > ", on_input=script
    )
    backend = _backend(config_dir, "code", pty_spawner=fake.spawn, pty_support=PtySupport(True))
    service = _service(backend)
    sid = (await service.start(backend.descriptor.id)).session_id
    view = await _until(service, sid, lambda v: v.needs_code and v.open_url is not None)
    assert view.open_url == url
    await service.send_input(sid, text="abc")
    final = await _until(service, sid, _done)
    assert final.phase == "succeeded"
    assert fake.inputs[:2] == ["abc", "\r"]
    assert fake.inputs.count("\r") >= 2  # 성공 뒤 on_success_keys
    await service.aclose()
