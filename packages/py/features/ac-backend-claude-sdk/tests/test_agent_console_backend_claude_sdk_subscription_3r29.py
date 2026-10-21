"""3R.29 TM-2(E-13): 구독 자격(`auth.mode=subscription`)은 설치자 opt-in, 기본 꺼짐.

- 꺼짐(기본): 설정 검증 error `backend.subscription_auth_disabled`(이유 문장) + 실행 거부
  (비밀 해석·SDK 호출 전에).
- 켜짐: 강화된 경고 문장(검증 warning + 실행마다 `log.warning`).
- 이 패키지에는 OAuth 토큰을 받아 두거나 저장하는 경로가 없다.

가짜 SDK 클라이언트(`FakeSdkClient`)만 쓴다. 실제 SDK·자격 증명은 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, SystemMessage

import agent_console_backend_claude_sdk as pkg
from agent_console_backend_claude_sdk import (
    AUTH_ISSUES,
    SUBSCRIPTION_AUTH_DISABLED_MESSAGE,
    SUBSCRIPTION_AUTH_WARNING,
    ClaudeSdkAuth,
    ClaudeSdkBackend,
    ClaudeSdkErrorCodes,
    ClaudeSdkInstallOptions,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, AgentSettings, InteractionGrant
from agent_console_runtime import AgentRequest, CancelToken, EnvSecretProvider, SecretResolver

OAUTH = "oauth-fake-token-value-3r29-XYZ"
"""가짜 토큰 값(실제 자격 아님)."""

SUBSCRIPTION = {"mode": "subscription"}
WITH_TOKEN = {"mode": "subscription", "oauth_token": "secret://claude_oauth"}


class RecordingResolver(SecretResolver):
    """비밀 해석기 가짜: 어떤 공개 속성을 썼는지 기록한다(쓰기 경로가 없음을 확인)."""

    def __init__(self) -> None:
        super().__init__([EnvSecretProvider({"claude_oauth": OAUTH})])
        self.used: list[str] = []
        self.resolved: list[str] = []

    def __getattribute__(self, name: str) -> Any:
        if not name.startswith("_") and name not in {"used", "resolved"}:
            object.__getattribute__(self, "used").append(name)
        return object.__getattribute__(self, name)

    def resolve(self, ref: str) -> str:
        self.resolved.append(ref)
        return super().resolve(ref)


def _agent(**options: Any) -> Agent:
    return Agent(
        id="lead",
        name="Lead",
        model="lead-model",
        tools=["Read"],
        system_prompt="you lead",
        backend="claude-agent-sdk",
        backend_options=options,
    )


def _script() -> list[Any]:
    return [
        SystemMessage(subtype="init", data={"session_id": "sess-1", "model": "m"}),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sess-1",
            result="done",
            usage={"input_tokens": 1, "output_tokens": 1},
        ),
    ]


def _capture() -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, _script())
        clients.append(client)
        return client

    return clients, factory


# ---------------------------------------------------------------- 설치자 옵션


def test_allow_subscription_auth_defaults_to_true_5_2r79() -> None:
    """5.2R.79(F13): 기본은 구독(본인 책임). 설치자 허용도 기본 켜짐."""
    assert ClaudeSdkInstallOptions().allow_subscription_auth is True
    schema = ClaudeSdkInstallOptions.model_json_schema()
    assert schema["properties"]["allow_subscription_auth"]["default"] is True
    assert "본인 책임" in schema["properties"]["allow_subscription_auth"]["description"]


def test_auth_mode_defaults_to_subscription_and_api_key_stays_selectable_5_2r79() -> None:
    assert ClaudeSdkAuth().mode == "subscription"
    schema = ClaudeSdkAuth.model_json_schema()
    assert schema["properties"]["mode"]["default"] == "subscription"
    assert "API 키" in schema["properties"]["mode"]["description"]
    backend = ClaudeSdkBackend()  # 기본 설치 = 구독 허용
    # 인증 칸을 열고 방식을 고르지 않으면(빈 객체) 구독 — 본인 책임 경고가 붙는다.
    issues = backend.validate_settings(
        AgentSettings(backend_options={"auth": {}}), InteractionGrant()
    )
    assert [(i.severity, i.code) for i in issues] == [("warning", AUTH_ISSUES.SUBSCRIPTION_ENABLED)]
    # API 키 방식은 그대로 고를 수 있고 구독 경고가 없다.
    api_key = {"auth": {"mode": "api_key", "api_key": "secret://anthropic_api_key"}}
    assert (
        backend.validate_settings(AgentSettings(backend_options=api_key), InteractionGrant()) == []
    )


async def test_default_install_runs_empty_auth_as_subscription_with_warning_5_2r79() -> None:
    clients, factory = _capture()
    sink = ValidatingSink()
    backend = ClaudeSdkBackend(client_factory=factory, secrets=RecordingResolver(), environ={})
    result = await backend.run(AgentRequest(agent=_agent(auth={}), prompt="p"), sink, CancelToken())
    assert result.status == "succeeded"
    assert clients[0].options.env["ANTHROPIC_API_KEY"] == ""
    warnings = [w for w in sink.of("log.warning") if w["details"].get("option") == "auth.mode"]
    assert [w["message"] for w in warnings] == [SUBSCRIPTION_AUTH_WARNING]


def test_from_options_reads_allow_subscription_auth() -> None:
    resolver = SecretResolver([EnvSecretProvider({})])
    on = ClaudeSdkBackend.from_options(
        {"allow_subscription_auth": True}, secrets=resolver, environ={}
    )
    off = ClaudeSdkBackend.from_options(
        {"allow_subscription_auth": False}, secrets=resolver, environ={}
    )
    default = ClaudeSdkBackend.from_options({}, secrets=resolver, environ={})
    sub = AgentSettings(backend_options={"auth": SUBSCRIPTION})
    assert [i.code for i in on.validate_settings(sub, InteractionGrant())] == [
        AUTH_ISSUES.SUBSCRIPTION_ENABLED
    ]
    assert [i.code for i in off.validate_settings(sub, InteractionGrant())] == [
        AUTH_ISSUES.SUBSCRIPTION_DISABLED
    ]
    assert [i.code for i in default.validate_settings(sub, InteractionGrant())] == [
        AUTH_ISSUES.SUBSCRIPTION_ENABLED
    ]
    with pytest.raises(ValueError, match="allow_subscription_auth"):
        ClaudeSdkBackend.from_options(
            {"allow_subscription_auth": "maybe"}, secrets=resolver, environ={}
        )


# ---------------------------------------------------------------- 꺼짐(기본)


def test_disabled_subscription_is_validation_error_with_reason() -> None:
    issues = ClaudeSdkBackend(allow_subscription_auth=False).validate_settings(
        AgentSettings(backend_options={"auth": SUBSCRIPTION}), InteractionGrant()
    )
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "error"
    assert issue.code == "backend.subscription_auth_disabled"
    assert issue.message == SUBSCRIPTION_AUTH_DISABLED_MESSAGE
    assert "API 키 사용이 안내" in issue.message
    assert "allow_subscription_auth" in issue.message
    assert "본인 책임" in issue.message
    assert issue.details["install_option"] == "allow_subscription_auth"


def test_api_key_mode_and_no_auth_have_no_auth_issue() -> None:
    backend = ClaudeSdkBackend()
    for options in ({}, {"auth": {"mode": "api_key"}}):
        assert (
            backend.validate_settings(AgentSettings(backend_options=options), InteractionGrant())
            == []
        )


def test_auth_issue_combines_with_interaction_issue() -> None:
    settings = AgentSettings(backend_options={"auth": SUBSCRIPTION, "permission_mode": "default"})
    backend = ClaudeSdkBackend(allow_subscription_auth=False)
    codes = [i.code for i in backend.validate_settings(settings, InteractionGrant())]
    assert codes == [AUTH_ISSUES.SUBSCRIPTION_DISABLED, "interaction.no_path"]


async def test_disabled_subscription_run_is_refused_before_secrets_and_sdk() -> None:
    clients, factory = _capture()
    resolver = RecordingResolver()
    sink = ValidatingSink()
    backend = ClaudeSdkBackend(
        client_factory=factory, secrets=resolver, environ={}, allow_subscription_auth=False
    )
    result = await backend.run(
        AgentRequest(agent=_agent(auth=WITH_TOKEN), prompt="p"), sink, CancelToken()
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED
    assert result.error.code == "backend.subscription_auth_disabled"
    assert result.error.message == SUBSCRIPTION_AUTH_DISABLED_MESSAGE
    assert clients == []  # SDK를 부르지 않았다
    assert resolver.resolved == []  # 토큰 참조도 해석하지 않았다
    assert OAUTH not in repr(result.model_dump())


# ---------------------------------------------------------------- 켜짐


def test_enabled_subscription_is_strengthened_warning() -> None:
    issues = ClaudeSdkBackend(allow_subscription_auth=True).validate_settings(
        AgentSettings(backend_options={"auth": SUBSCRIPTION}), InteractionGrant()
    )
    assert [(i.severity, i.code) for i in issues] == [
        ("warning", "backend.subscription_auth_enabled")
    ]
    assert issues[0].message == SUBSCRIPTION_AUTH_WARNING
    assert "API 키 사용이 안내" in issues[0].message
    assert "본인 책임" in issues[0].message
    assert "미확인" not in issues[0].message


async def test_enabled_subscription_runs_with_strengthened_log_warning() -> None:
    clients, factory = _capture()
    sink = ValidatingSink()
    backend = ClaudeSdkBackend(
        client_factory=factory,
        secrets=RecordingResolver(),
        environ={},
        allow_subscription_auth=True,
    )
    result = await backend.run(
        AgentRequest(agent=_agent(auth=SUBSCRIPTION), prompt="p"), sink, CancelToken()
    )
    assert result.status == "succeeded"
    assert len(clients) == 1
    warnings = [w for w in sink.of("log.warning") if w["details"].get("option") == "auth.mode"]
    assert [w["message"] for w in warnings] == [SUBSCRIPTION_AUTH_WARNING]


# ---------------------------------------------------------------- 토큰을 받거나 저장하는 경로 없음


def test_no_install_option_or_public_api_accepts_tokens() -> None:
    install_fields = set(ClaudeSdkInstallOptions.model_fields)
    assert not {f for f in install_fields if "token" in f or "credential" in f or "oauth" in f}
    # 인증 설정의 토큰 칸은 참조 하나와 환경변수 이름뿐(값을 담는 다른 칸 없음).
    assert set(ClaudeSdkAuth.model_fields) == {
        "mode",
        "api_key",
        "oauth_token",
        "api_key_env",
        "oauth_token_env",
    }
    suspicious = ("login", "store", "save", "persist", "credential", "oauth", "token")
    assert not [n for n in pkg.__all__ if any(w in n.lower() for w in suspicious)]
    backend_methods = {n for n in dir(ClaudeSdkBackend) if not n.startswith("_")}
    assert not [n for n in backend_methods if any(w in n.lower() for w in suspicious)]


async def test_enabled_token_is_only_read_and_handed_to_cli_env(tmp_path: Path) -> None:
    clients, factory = _capture()
    resolver = RecordingResolver()
    sink = ValidatingSink()
    backend = ClaudeSdkBackend(
        client_factory=factory, secrets=resolver, environ={}, allow_subscription_auth=True
    )
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    result = await backend.run(
        AgentRequest(agent=_agent(auth=WITH_TOKEN), prompt="p", cwd=str(tmp_path)),
        sink,
        CancelToken(),
    )
    assert result.status == "succeeded"
    # 해석기는 읽기(resolve)와 가리기(redact)만 쓴다 — 저장·등록 호출 없음.
    assert set(resolver.used) <= {"resolve", "redact"}
    assert resolver.resolved == ["secret://claude_oauth"]
    # 토큰은 CLI 하위 프로세스 env로만 간다.
    assert clients[0].options.env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH
    # 이벤트·결과·경고 어디에도 값이 없다.
    assert OAUTH not in repr([(e.payload, e.raw) for e in sink.events])
    assert OAUTH not in repr(result.model_dump())
    # 실행 폴더에 아무것도 쓰지 않았다(토큰을 파일로 남기지 않음).
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before
