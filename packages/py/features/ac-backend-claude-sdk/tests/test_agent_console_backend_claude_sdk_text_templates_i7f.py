"""I.7f(design §I18N.13 I-15·I-16): 값이 섞인 상태·연결 테스트·로그인·로그아웃 문구의 원문 틀 + 값.

각 응답의 ``text_templates``: 포인터마다 틀을 채워 공백 하나로 이은 값 == 칸 값. 설치자가
``texts``를 바꾸면 틀도 바뀐 문구, 가림 대상 값은 params에서도 가려진다. 가짜 SDK 클라이언트·
가짜 PTY만 쓴다(실제 Claude 호출·로그인 없음).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from claude_agent_sdk import ClaudeAgentOptions

from agent_console_backend_claude_sdk import (
    AuthDirView,
    ClaudeSdkBackend,
    ClaudeSdkReadinessOptions,
    PtySupport,
    ReadinessStates,
    assess_readiness,
    env_warning_templates,
    env_warnings,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient
from agent_console_contracts import BackendReadiness, TextTemplate, render_text_parts
from agent_console_pty_session import FakePty
from agent_console_runtime import (
    REDACTED,
    BackendCheckContext,
    BackendLoginService,
    BackendReadinessService,
    EnvSecretProvider,
    ExecutionBackend,
    SecretResolver,
)

API_KEY_AUTH: dict[str, Any] = {"mode": "api_key", "api_key": "secret://zz_key_name"}


def assert_consistent(response: Any) -> None:
    """모든 포인터: 틀을 채워 공백 하나로 이은 값 == 칸 값."""
    dumped = response.model_dump(mode="json")
    assert response.text_templates
    for pointer, parts in response.text_templates.items():
        node: Any = dumped
        for key in pointer[1:].split("/"):
            node = node[int(key)] if isinstance(node, list) else node[key]
        assert " ".join(render_text_parts([p]) for p in parts) == node, pointer


class Factory:
    def __init__(self, **client_kwargs: Any) -> None:
        self.kwargs = client_kwargs
        self.clients: list[FakeSdkClient] = []

    def __call__(self, options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, [], **self.kwargs)
        self.clients.append(client)
        return client


def backend(
    *,
    env: Mapping[str, str] | None = None,
    readiness: Mapping[str, Any] | None = None,
    factory: Factory | None = None,
    **kwargs: Any,
) -> tuple[ClaudeSdkBackend, BackendCheckContext]:
    secrets = SecretResolver([EnvSecretProvider(dict(env or {}))])
    b = ClaudeSdkBackend(
        client_factory=factory or Factory(),
        secrets=secrets,
        environ={"HOME": "/home/u", **(env or {})},
        readiness={"auth": API_KEY_AUTH, **(readiness or {})},
        cli_locator=lambda _p: "/fake/bin/claude",
        **kwargs,
    )
    ctx = BackendCheckContext("claude-agent-sdk", clock=lambda: 7.0, has_secret=secrets.has)
    return b, ctx


# ---------------------------------------------------------------- 상태(detail·checks[].note)


async def test_api_key_missing_detail_and_note_have_templates() -> None:
    b, ctx = backend()
    r = await b.status(ctx)
    assert r.state == ReadinessStates.AUTH_MISSING
    detail = r.text_templates["/detail"]
    assert detail[0].params == {"name": "zz_key_name"}
    index = next(i for i, c in enumerate(r.checks) if c.id == "api_key")
    note = r.text_templates[f"/checks/{index}/note"][0]
    assert note.template == "비밀 '{name}': {state}"
    assert note.params["state"] == TextTemplate(template="없음")
    assert r.checks[index].note == "비밀 'zz_key_name': 없음"
    assert_consistent(r)
    # 고정 문구 칸(점검 항목 이름, 실행 파일 있음 등)에는 항목이 없다
    assert all(p == "/detail" or p.endswith("/note") for p in r.text_templates)
    assert "/checks/0/note" not in r.text_templates


async def test_ready_api_key_has_found_note_and_no_detail_entry() -> None:
    b, ctx = backend(env={"ZZ_KEY_NAME": "sk-value-0001"})
    r = await b.status(ctx)
    assert r.state == ReadinessStates.AUTH_READY
    assert "/detail" not in r.text_templates  # 빈 detail
    (pointer,) = r.text_templates
    assert r.text_templates[pointer][0].params["state"] == TextTemplate(template="있음")
    assert_consistent(r)


async def test_unverified_detail_lists_each_sentence_and_login_note() -> None:
    b, ctx = backend(
        readiness={"auth": {"mode": "subscription"}},
        allow_subscription_auth=True,
        path_exists=lambda _p: False,
        pty_support=PtySupport(False, "missing_package"),
    )
    r = await b.status(ctx)
    assert r.state == ReadinessStates.SUBSCRIPTION_UNVERIFIED
    t = ClaudeSdkReadinessOptions().texts
    parts = r.text_templates["/detail"]
    assert [p.template for p in parts][:2] == [
        t.subscription_unverified_detail,
        t.subscription_ready_detail,
    ]
    assert len(parts) == 3  # + 앱 화면 로그인 설치 안내(고정 문장)
    assert all(p.params == {} for p in parts)
    assert_consistent(r)


def test_auth_dir_detail_and_loose_permissions() -> None:
    view = AuthDirView(
        display=".state/claude",
        files=("/w/.state/claude/.credentials.json",),
        permissions_ok=False,
        loose=("folder", ".credentials.json"),
    )
    options = ClaudeSdkReadinessOptions.model_validate({"auth": {"mode": "subscription"}})
    for exists in (True, False):
        a = assess_readiness(
            options,
            allow_subscription_auth=True,
            has_secret=lambda _n: False,
            cli_found=True,
            environ={},
            path_exists=lambda _p, e=exists: e,  # type: ignore[misc]
            auth_dir=view,
        )
        r = BackendReadiness(
            backend_id="b",
            state=a.state,
            tone=a.tone,
            detail=a.detail,
            checked_at=1.0,
            checks=a.checks,
            text_templates=a.text_templates(),
        )
        params = [p.params for p in r.text_templates["/detail"]]
        assert {"names": "folder, .credentials.json"} in params
        if exists:
            assert a.state == ReadinessStates.SUBSCRIPTION_READY
            assert {"path": ".state/claude"} in params
        else:
            assert a.state == ReadinessStates.SUBSCRIPTION_LOGIN_REQUIRED
            assert r.text_templates["/detail"][0].template == options.texts.login_required_detail
        index = next(i for i, c in enumerate(r.checks) if c.id == "auth_dir_permissions")
        assert r.text_templates[f"/checks/{index}/note"][0].params == {
            "names": "folder, .credentials.json"
        }
        assert_consistent(r)


async def test_installer_texts_become_the_templates() -> None:
    texts = {"auth_missing_detail": "Key {name} is missing.", "note_secret": "{name} = {state}"}
    b, ctx = backend(readiness={"texts": texts})
    r = await b.status(ctx)
    assert r.detail == "Key zz_key_name is missing."
    assert r.text_templates["/detail"][0].template == "Key {name} is missing."
    assert any(v[0].template == "{name} = {state}" for v in r.text_templates.values())
    assert_consistent(r)


async def test_masked_values_are_masked_in_params_too() -> None:
    b, _ctx = backend()

    def redact(value: Any) -> Any:
        return json.loads(json.dumps(value).replace("zz_key_name", REDACTED))

    service = BackendReadinessService(
        lambda: cast(Mapping[str, ExecutionBackend], {"claude-agent-sdk": b}), redact=redact
    )
    r = await service.status("claude-agent-sdk")
    assert "zz_key_name" not in json.dumps(r.model_dump(mode="json"))
    assert r.text_templates["/detail"][0].params == {"name": REDACTED}
    assert_consistent(r)


# ---------------------------------------------------------------- 연결 테스트 시간 초과


async def test_probe_timeout_message_has_template() -> None:
    factory = Factory(block=True, ignore_interrupt=True)
    b, ctx = backend(env={"ZZ_KEY_NAME": "sk-value-0001"}, factory=factory)
    result = await b.probe(ctx, 0.3)
    assert result.reason == "timeout"
    assert result.message == "0.3초 안에 응답이 없었습니다."
    assert result.text_templates == {
        "/message": [
            TextTemplate(template="{seconds}초 안에 응답이 없었습니다.", params={"seconds": 0.3})
        ]
    }
    assert_consistent(result)


async def test_refused_probe_has_no_templates() -> None:
    b, ctx = backend()
    result = await b.probe(ctx, 1.0)
    assert result.reason == "auth_missing"
    assert result.text_templates == {}


# ---------------------------------------------------------------- 로그인 경고·로그아웃


def login_backend(spawner: Callable[..., Any], **login: Any) -> ClaudeSdkBackend:
    return ClaudeSdkBackend(
        environ={"HOME": "/home/u", "PATH": "", "ANTHROPIC_API_KEY": "sk-ant-should-not-pass"},
        allow_subscription_auth=True,
        cli_locator=lambda _p: "/stub/claude",
        path_exists=lambda _p: False,
        pty_support=PtySupport(True),
        pty_spawner=spawner,
        login={"terminate_grace_s": 0.1, "exit_wait_s": 0.5, **login},
    )


def service_of(b: ClaudeSdkBackend) -> BackendLoginService:
    return BackendLoginService(
        lambda: cast(Mapping[str, ExecutionBackend], {b.descriptor.id: b}), tick_s=0.05
    )


async def test_login_env_warning_has_template() -> None:
    fake = FakePty(output="Paste code here > ")
    b = login_backend(fake.spawn)
    service = service_of(b)
    view = await service.start(b.descriptor.id)
    index = next(i for i, w in enumerate(view.warnings) if "ANTHROPIC_API_KEY" in w)
    part = view.text_templates[f"/warnings/{index}"][0]
    assert part.params == {"name": "ANTHROPIC_API_KEY"}
    assert_consistent(view)
    await service.aclose()


def test_env_warning_templates_match_strings() -> None:
    b = login_backend(FakePty().spawn)
    options = b._login.options
    parent = {"ANTHROPIC_API_KEY": "x", "CLAUDE_CODE_OAUTH_TOKEN": "y"}
    templates = env_warning_templates(parent, options)
    assert [render_text_parts([t]) for t in templates] == env_warnings(parent, options)
    assert {t.params["name"] for t in templates} == {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}


async def test_logout_failed_has_template() -> None:
    fake = FakePty(exit_code=3)
    b = login_backend(fake.spawn)
    result = await service_of(b).logout(b.descriptor.id)
    assert (result.ok, result.reason) == (False, "logout_failed")
    assert result.message == "로그아웃하지 못했습니다(종료 코드 3)."
    assert result.text_templates["/message"][0].params == {"code": 3}
    assert_consistent(result)


async def test_logout_timeout_has_template() -> None:
    fake = FakePty(output="waiting")
    b = login_backend(fake.spawn, logout_timeout_s=0.2)
    result = await service_of(b).logout(b.descriptor.id)
    assert result.reason == "timeout"
    assert result.message == "로그아웃이 0.2초 안에 끝나지 않았습니다."
    template = result.text_templates["/message"][0].template
    assert template == "로그아웃이 {seconds}초 안에 끝나지 않았습니다."
    assert_consistent(result)


async def test_logout_ok_has_no_templates() -> None:
    fake = FakePty(exit_code=0)
    b = login_backend(fake.spawn)
    result = await service_of(b).logout(b.descriptor.id)
    assert result.ok is True
    assert result.text_templates == {}
