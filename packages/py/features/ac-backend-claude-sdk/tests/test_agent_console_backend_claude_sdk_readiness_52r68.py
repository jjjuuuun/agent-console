"""5.2R.68(ux-overhaul §15.8 F8): Claude SDK 백엔드 준비 상태(`status`)·연결 테스트(`probe`).

- `status`: 모델을 부르지 않는다(SDK 클라이언트 생성 0회). 인증 해석 결과 → 상태·해결 버튼.
- `probe`: 막힌 경우(실행 파일 없음·구독 꺼짐·키 없음) 호출 없이 거부, 시간 상한, 실패 사유 분류.
- 비밀 값은 응답·로그·예외 어디에도 나오지 않는다.

가짜 SDK 클라이언트(`FakeSdkClient`)만 쓴다. 실제 Claude 호출은 하지 않는다(실제 클라이언트 생성
수 0을 단언한다).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    TextBlock,
)

import agent_console_backend_claude_sdk._backend as backend_module
from agent_console_backend_claude_sdk import (
    PROBE_COST_NOTE,
    ClaudeSdkBackend,
    ClaudeSdkInstallOptions,
    ClaudeSdkReadinessOptions,
    ProbeReasonCodes,
    ReadinessStates,
    assess_readiness,
    classify_probe_error,
    classify_probe_messages,
    expand_path,
    find_claude_cli,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient
from agent_console_contracts import BackendProbeResult, BackendReadiness
from agent_console_runtime import (
    BackendCheckContext,
    BackendReadinessService,
    EnvSecretProvider,
    SecretResolver,
    supports_probe,
    supports_status,
)

KEY = "sk-test-SECRET-123-readiness-5x"
"""가짜 키 값(실제 자격 아님). 응답·로그에 이 값과 그 일부가 나오면 안 된다."""

OAUTH = "oauth-test-SECRET-456-readiness"
FAKE_CLI = "/fake/bin/claude"
SECRET_FRAGMENTS = (KEY, "SECRET-123", "sk-test-S", OAUTH, "SECRET-456")


def _found(_path: str | None) -> str | None:
    return FAKE_CLI


def _missing(_path: str | None) -> str | None:
    return None


def _result(**extra: Any) -> ResultMessage:
    fields: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "probe-sess",
        "result": "OK",
    }
    fields.update(extra)
    return ResultMessage(**fields)


def _ok_script() -> list[Any]:
    return [
        AssistantMessage(content=[TextBlock(text="OK")], model="claude-test-model"),
        _result(),
    ]


class Factory:
    """가짜 SDK 클라이언트 생성기(생성 수·옵션 기록)."""

    def __init__(
        self,
        script: Callable[[], list[Any]] = _ok_script,
        **client_kwargs: Any,
    ) -> None:
        self.script = script
        self.kwargs = client_kwargs
        self.clients: list[FakeSdkClient] = []

    def __call__(self, options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, self.script(), **self.kwargs)
        self.clients.append(client)
        return client


API_KEY_AUTH: dict[str, Any] = {"mode": "api_key", "api_key": "secret://anthropic_api_key"}


def _resolver(env: dict[str, str]) -> SecretResolver:
    return SecretResolver([EnvSecretProvider(env)])


def _backend(
    factory: Factory,
    *,
    env: dict[str, str] | None = None,
    readiness: dict[str, Any] | None = None,
    allow_subscription_auth: bool = False,
    cli: Callable[[str | None], str | None] = _found,
    files: frozenset[str] = frozenset(),
) -> tuple[ClaudeSdkBackend, SecretResolver]:
    secrets = _resolver(env or {})
    backend = ClaudeSdkBackend(
        client_factory=factory,
        secrets=secrets,
        environ={"HOME": "/home/u", **(env or {})},
        # 5.2R.79부터 기본 인증은 구독이다. 이 파일의 기존 시나리오는 API 키 경로를 명시해 고른다.
        readiness={"auth": API_KEY_AUTH, **(readiness or {})},
        allow_subscription_auth=allow_subscription_auth,
        cli_locator=cli,
        path_exists=lambda p: p in files,
    )
    return backend, secrets


def _ctx(secrets: SecretResolver) -> BackendCheckContext:
    return BackendCheckContext("claude-agent-sdk", clock=lambda: 7.0, has_secret=secrets.has)


SUBSCRIPTION = {"auth": {"mode": "subscription"}}
LOGIN_FILE = "/home/u/.claude/.credentials.json"


# ---------------------------------------------------------------- 능력 선언


def test_descriptor_declares_status_and_probe() -> None:
    backend, _ = _backend(Factory())
    caps = backend.descriptor.capabilities
    assert (caps.status, caps.probe) == (True, True)
    assert backend.descriptor.probe_cost_note == PROBE_COST_NOTE
    assert supports_status(backend)
    assert supports_probe(backend)


# ---------------------------------------------------------------- status: 모델 호출 없음


async def test_api_key_missing_then_ready_without_model_calls() -> None:
    factory = Factory()
    backend, secrets = _backend(factory)
    missing = await backend.status(_ctx(secrets))
    assert (missing.state, missing.tone) == (ReadinessStates.AUTH_MISSING, "error")
    assert missing.summary.startswith("키 없음")
    assert missing.short_summary == "키 없음"
    assert "anthropic_api_key" in missing.detail
    assert missing.fixes
    assert all(f.label and f.target.role for f in missing.fixes)
    assert missing.checked_at == 7.0
    key_check = next(c for c in missing.checks if c.id == "api_key")
    assert key_check.ok is False

    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY})
    ready = await backend.status(_ctx(secrets))
    assert (ready.state, ready.tone) == (ReadinessStates.AUTH_READY, "ok")
    assert ready.summary == "인증 설정됨 (API 키)"
    assert ready.fixes == []
    assert factory.clients == []  # 모델(SDK) 호출 0회


async def test_api_key_env_name_is_used_when_no_reference() -> None:
    readiness = {"auth": {"mode": "api_key", "api_key_env": "MY_KEY"}}
    backend, secrets = _backend(Factory(), env={"MY_KEY": KEY}, readiness=readiness)
    assert (await backend.status(_ctx(secrets))).state == ReadinessStates.AUTH_READY


async def test_subscription_disabled_then_enabled() -> None:
    factory = Factory()
    backend, secrets = _backend(factory, readiness=SUBSCRIPTION)
    off = await backend.status(_ctx(secrets))
    assert (off.state, off.tone) == (ReadinessStates.SUBSCRIPTION_DISABLED, "warn")
    assert off.summary == "구독 방식 꺼짐 — 설치자 설정에서 켜야 합니다"
    assert off.fixes

    backend, secrets = _backend(
        factory,
        readiness=SUBSCRIPTION,
        allow_subscription_auth=True,
        files=frozenset({LOGIN_FILE}),
    )
    on = await backend.status(_ctx(secrets))
    assert (on.state, on.tone) == (ReadinessStates.SUBSCRIPTION_READY, "warn")
    assert on.summary == "구독 방식으로 인증됨 (본인 책임)"
    assert "본인 책임" in on.detail
    assert factory.clients == []


async def test_subscription_login_file_missing_or_token_missing() -> None:
    backend, secrets = _backend(Factory(), readiness=SUBSCRIPTION, allow_subscription_auth=True)
    unverified = await backend.status(_ctx(secrets))
    assert (unverified.state, unverified.tone) == (ReadinessStates.SUBSCRIPTION_UNVERIFIED, "warn")
    token = {"auth": {"mode": "subscription", "oauth_token": "secret://claude_oauth"}}
    backend, secrets = _backend(Factory(), readiness=token, allow_subscription_auth=True)
    missing = await backend.status(_ctx(secrets))
    assert (missing.state, missing.tone) == (ReadinessStates.SUBSCRIPTION_TOKEN_MISSING, "error")
    backend, secrets = _backend(
        Factory(), env={"claude_oauth": OAUTH}, readiness=token, allow_subscription_auth=True
    )
    assert (await backend.status(_ctx(secrets))).state == ReadinessStates.SUBSCRIPTION_READY


async def test_cli_missing_is_error_and_probe_is_refused() -> None:
    factory = Factory()
    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY}, cli=_missing)
    status = await backend.status(_ctx(secrets))
    assert (status.state, status.tone) == (ReadinessStates.CLI_MISSING, "error")
    assert status.fixes
    probe = await backend.probe(_ctx(secrets), 5.0)
    assert (probe.ok, probe.reason) == (False, ProbeReasonCodes.CLI_MISSING)
    assert factory.clients == []


# ---------------------------------------------------------------- probe: 막힌 경우 호출 없음


async def test_probe_refused_without_call_when_subscription_disabled() -> None:
    factory = Factory()
    backend, secrets = _backend(factory, readiness=SUBSCRIPTION)
    result = await backend.probe(_ctx(secrets), 5.0)
    assert result.ok is False
    assert result.reason == "backend.subscription_auth_disabled"
    assert result.details["category"] == "auth"
    assert result.message
    assert result.fixes
    assert factory.clients == []


async def test_probe_refused_without_call_when_key_missing() -> None:
    factory = Factory()
    backend, secrets = _backend(factory)
    result = await backend.probe(_ctx(secrets), 5.0)
    assert (result.ok, result.reason) == (False, ProbeReasonCodes.AUTH_MISSING)
    assert result.fixes
    assert factory.clients == []


# ---------------------------------------------------------------- probe: 짧은 호출


async def test_probe_success_uses_minimal_call() -> None:
    factory = Factory()
    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY, "OTHER_SECRET": "x" * 9})
    result = await backend.probe(_ctx(secrets), 5.0)
    assert result.ok is True
    assert result.reason is None
    assert result.message == "연결됨"
    assert result.details == {"model": "claude-test-model"}
    assert result.latency_ms is not None
    assert len(factory.clients) == 1
    client = factory.clients[0]
    options = client.options
    assert options.tools == []
    assert options.max_turns == 1
    assert options.setting_sources == []
    assert options.strict_mcp_config is True
    assert options.cli_path == FAKE_CLI
    assert "no-session-persistence" in options.extra_args
    assert options.env["ANTHROPIC_API_KEY"] == KEY  # CLI 하위 프로세스에만 간다
    assert options.env["OTHER_SECRET"] == ""  # 허용 목록 밖 환경은 가린다
    assert client.prompts == [ClaudeSdkReadinessOptions().probe_prompt]
    assert client.disconnected is True
    assert not Path(str(options.cwd)).exists()  # 임시 폴더는 지운다


async def test_probe_model_and_prompt_are_data() -> None:
    factory = Factory()
    readiness = {"probe_model": "m-small", "probe_prompt": "ping", "probe_extra_args": {}}
    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY}, readiness=readiness)
    assert (await backend.probe(_ctx(secrets), 5.0)).ok is True
    assert factory.clients[0].options.model == "m-small"
    assert factory.clients[0].options.extra_args == {}
    assert factory.clients[0].prompts == ["ping"]


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        (
            lambda: [
                AssistantMessage(
                    content=[TextBlock(text=f"Invalid API key {KEY}")],
                    model="m",
                    error="authentication_failed",
                ),
                _result(is_error=True, result=f"Invalid API key {KEY}"),
            ],
            ProbeReasonCodes.AUTH_FAILED,
        ),
        (lambda: [_result(is_error=True, api_error_status=401)], ProbeReasonCodes.AUTH_FAILED),
        (lambda: [_result(is_error=True, api_error_status=529)], ProbeReasonCodes.ERROR),
        (lambda: [], ProbeReasonCodes.ERROR),
    ],
)
async def test_probe_classifies_sdk_responses(script: Callable[[], list[Any]], reason: str) -> None:
    backend, secrets = _backend(Factory(script), env={"ANTHROPIC_API_KEY": KEY})
    result = await backend.probe(_ctx(secrets), 5.0)
    assert (result.ok, result.reason) == (False, reason)
    assert KEY not in result.model_dump_json()


@pytest.mark.parametrize(
    ("error", "reason", "category"),
    [
        (CLIConnectionError(f"connect failed {KEY}"), ProbeReasonCodes.NETWORK, "network"),
        (ConnectionResetError("reset"), ProbeReasonCodes.NETWORK, "network"),
        (CLINotFoundError("no cli"), ProbeReasonCodes.CLI_MISSING, "other"),
        (ProcessError(f"exit 1 {KEY}", exit_code=1), ProbeReasonCodes.ERROR, "other"),
        (RuntimeError(KEY), ProbeReasonCodes.ERROR, "other"),
    ],
)
async def test_probe_classifies_exceptions(error: Exception, reason: str, category: str) -> None:
    factory = Factory(connect_error=error)
    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY})
    result = await backend.probe(_ctx(secrets), 5.0)
    assert (result.ok, result.reason, result.details["category"]) == (False, reason, category)
    assert result.details["error"] == type(error).__name__
    assert KEY not in result.model_dump_json()
    assert factory.clients[0].disconnected is True


async def test_probe_times_out_within_budget() -> None:
    factory = Factory(lambda: [], block=True, ignore_interrupt=True)
    backend, secrets = _backend(factory, env={"ANTHROPIC_API_KEY": KEY})
    result = await backend.probe(_ctx(secrets), 0.3)
    assert (result.ok, result.reason) == (False, ProbeReasonCodes.TIMEOUT)
    assert result.details["category"] == "timeout"
    assert "0.3초" in result.message
    assert factory.clients[0].disconnected is True


# ---------------------------------------------------------------- 실제 SDK 호출 0회


async def test_real_sdk_client_is_never_created_by_status_or_refused_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Any] = []

    class CountingClient:
        def __init__(self, options: Any) -> None:
            created.append(options)
            raise AssertionError("실제 SDK 클라이언트를 만들면 안 된다")

    monkeypatch.setattr(backend_module, "ClaudeSDKClient", CountingClient)
    for readiness, env in (
        ({"auth": API_KEY_AUTH}, {}),
        (SUBSCRIPTION, {"ANTHROPIC_API_KEY": KEY}),
    ):
        secrets = _resolver(env)
        backend = ClaudeSdkBackend(
            secrets=secrets,
            environ=env,
            readiness=readiness,
            allow_subscription_auth=False,
            cli_locator=_found,
            path_exists=lambda _p: False,
        )
        await backend.status(_ctx(secrets))
        assert (await backend.probe(_ctx(secrets), 1.0)).ok is False
    # 실행 파일이 없으면 키가 있어도 부르지 않는다.
    secrets = _resolver({"ANTHROPIC_API_KEY": KEY})
    backend = ClaudeSdkBackend(
        secrets=secrets,
        environ={},
        readiness={"auth": API_KEY_AUTH},
        cli_locator=_missing,
        path_exists=lambda _p: False,
    )
    assert (await backend.probe(_ctx(secrets), 1.0)).reason == ProbeReasonCodes.CLI_MISSING
    assert created == []


# ---------------------------------------------------------------- 비밀 비노출


async def test_secrets_never_appear_in_responses_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    env = {"ANTHROPIC_API_KEY": KEY, "claude_oauth": OAUTH}

    def leaky() -> list[Any]:
        return [
            AssistantMessage(content=[TextBlock(text=f"echo {KEY} {OAUTH}")], model="m"),
            _result(result=f"{KEY} {OAUTH}"),
        ]

    outputs: list[str] = []
    for readiness, allow in (
        (None, False),
        ({"auth": {"mode": "subscription", "oauth_token": "secret://claude_oauth"}}, True),
    ):
        backend, secrets = _backend(
            Factory(leaky), env=env, readiness=readiness, allow_subscription_auth=allow
        )
        registered: dict[str, Any] = {"claude-agent-sdk": backend}
        service = BackendReadinessService(
            registered.copy,
            redact=secrets.redact,
            has_secret=secrets.has,
        )
        status = await service.status("claude-agent-sdk")
        probe = await service.probe("claude-agent-sdk", 5.0)
        assert probe.ok is True
        failing, failing_secrets = _backend(
            Factory(connect_error=RuntimeError(f"boom {KEY} {OAUTH}")),
            env=env,
            readiness=readiness,
            allow_subscription_auth=allow,
        )
        failed = await failing.probe(_ctx(failing_secrets), 5.0)
        outputs += [status.model_dump_json(), probe.model_dump_json(), failed.model_dump_json()]
    text = "\n".join([*outputs, caplog.text])
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in text


def test_response_models_have_no_value_fields() -> None:
    for model in (BackendReadiness, BackendProbeResult):
        schema = json.dumps(model.model_json_schema())
        for word in ('"api_key"', '"token"', '"secret"', '"value"'):
            assert word not in schema


# ---------------------------------------------------------------- 설치자 설정·부품


def test_install_options_accept_readiness() -> None:
    parsed = ClaudeSdkInstallOptions.model_validate(
        {"readiness": {"auth": {"mode": "subscription"}, "cli_path": "/x/claude"}}
    )
    assert parsed.readiness.auth.mode == "subscription"
    backend = ClaudeSdkBackend.from_options(
        {"readiness": {"probe_model": "m"}}, secrets=_resolver({}), environ={}
    )
    assert backend.descriptor.capabilities.probe is True
    with pytest.raises(ValueError, match="readiness"):
        ClaudeSdkBackend.from_options({"readiness": {"nope": 1}}, secrets=_resolver({}), environ={})


def test_default_readiness_checks_subscription_login_5_2r79() -> None:
    """5.2R.79(F13): 상태 점검 기본 인증은 구독이다. API 키는 명시해서 고른다."""
    opts = ClaudeSdkReadinessOptions()
    assert opts.auth.mode == "subscription"
    assert opts.auth.api_key is None
    chosen = ClaudeSdkReadinessOptions.model_validate({"auth": API_KEY_AUTH})
    assert (chosen.auth.mode, chosen.auth.api_key) == ("api_key", "secret://anthropic_api_key")


async def test_default_status_is_subscription_with_responsibility_warning_5_2r79() -> None:
    """기본 설치(설정 없음)의 상태 카드: 구독 허용(기본 켜짐) + 로그인 파일 → 본인 책임 경고."""
    secrets = _resolver({})
    backend = ClaudeSdkBackend(
        client_factory=Factory(),
        secrets=secrets,
        environ={"HOME": "/home/u"},
        cli_locator=_found,
        path_exists=lambda p: p == "/home/u/.claude/.credentials.json",
    )
    status = await backend.status(_ctx(secrets))
    assert (status.state, status.tone) == (ReadinessStates.SUBSCRIPTION_READY, "warn")
    assert "본인 책임" in status.summary


def test_assess_readiness_is_usable_alone() -> None:
    a = assess_readiness(
        ClaudeSdkReadinessOptions.model_validate({"auth": API_KEY_AUTH}),
        allow_subscription_auth=False,
        has_secret=lambda name: name == "anthropic_api_key",
        cli_found=True,
        environ={},
    )
    assert (a.state, a.tone, a.probe_block) == (ReadinessStates.AUTH_READY, "ok", None)
    assert [c.id for c in a.checks] == ["cli", "auth_mode", "api_key"]


def test_expand_path() -> None:
    env = {"HOME": "/h", "CLAUDE_CONFIG_DIR": "/cfg"}
    assert expand_path("~/.claude/x", env) == "/h/.claude/x"
    assert expand_path("${CLAUDE_CONFIG_DIR}/x", env) == "/cfg/x"
    assert expand_path("${NOPE}/x", env) is None
    assert expand_path("~/x", {}) is None


def test_find_claude_cli_explicit_path(tmp_path: Path) -> None:
    cli = tmp_path / "claude"
    cli.write_text("")
    assert find_claude_cli(str(cli)) == str(cli)
    assert find_claude_cli(str(tmp_path / "missing")) is None


def test_classifiers_are_usable_alone() -> None:
    ok = classify_probe_messages(_ok_script())
    assert (ok.ok, ok.details) == (True, {"model": "claude-test-model"})
    assert classify_probe_error(TimeoutError()).reason == ProbeReasonCodes.ERROR
