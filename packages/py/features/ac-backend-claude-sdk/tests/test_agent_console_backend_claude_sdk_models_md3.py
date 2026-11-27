"""MD.3(design §1.1-MB MD-4): Claude SDK 백엔드 계정 모델 조회(X54) — 대역만 쓴다.

- 구독(``sdk_init``): 가짜 SDK 클라이언트 — ``query`` 호출 0, ``disconnect`` 항상 호출, 시간 초과,
  ``models`` 키 없음 → ``unsupported``(``cli_no_models``), 모양 틀림, 응답 항목 → ``ModelInfo``.
- API 키(``models_api``): ``httpx.MockTransport`` — 쪽 넘김 2쪽, 401 → ``auth_failed``, 연결 오류 →
  ``network``, 모양 틀림 → ``invalid_response``, 헤더에 키가 실리되 결과·``details``·로그에 없음.
- 구독 끔·키 없음·로그인 없음: CLI·HTTP 호출 0. 실제 Claude·네트워크 호출은 하지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from claude_agent_sdk import ClaudeAgentOptions, CLIConnectionError

from agent_console_backend_claude_sdk import (
    METHOD_MODELS_API,
    METHOD_SDK_INIT,
    ClaudeSdkBackend,
    ClaudeSdkInstallOptions,
    ClaudeSdkModelDiscoveryOptions,
    api_base_url,
    models_from_api_page,
    models_from_server_info,
)
from agent_console_contracts import ModelInfo
from agent_console_runtime import (
    BackendCheckContext,
    BackendModelCatalogService,
    EnvSecretProvider,
    ModelDiscoveryReasons,
    SecretResolver,
    supports_model_discovery,
)

KEY = "sk-test-SECRET-md3-models-key-77"
"""가짜 키 값(실제 자격 아님)."""

FAKE_CLI = "/fake/bin/claude"
INFO_MODELS = [
    {
        "value": "zz-alias",
        "displayName": "Zz Alias",
        "description": "pick me",
        "supportsEffort": True,
    },
    {"value": "zz-full-1", "displayName": "Zz Full", "description": "", "resolvedModel": "zz-x"},
    {"displayName": "no value"},
]


class InfoClient:
    """``connect``·``get_server_info``·``disconnect``만 쓰는 가짜(``query`` 호출을 센다)."""

    def __init__(
        self,
        options: ClaudeAgentOptions,
        info: Any,
        *,
        connect_error: Exception | None = None,
        hang: bool = False,
    ) -> None:
        self.options = options
        self.info = info
        self.connect_error = connect_error
        self.hang = hang
        self.queries = 0
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        if self.hang:
            await asyncio.sleep(30)
        self.connected = True

    async def get_server_info(self) -> Any:
        return self.info

    async def query(self, prompt: str) -> None:  # pragma: no cover - 불리면 안 된다
        self.queries += 1

    def receive_response(self) -> Any:  # pragma: no cover - 불리면 안 된다
        self.queries += 1
        raise AssertionError("receive_response must not be called")

    async def interrupt(self) -> None:  # pragma: no cover
        pass

    async def disconnect(self) -> None:
        self.disconnected = True


class Factory:
    def __init__(self, info: Any = None, **kwargs: Any) -> None:
        self.info = {"commands": [], "models": INFO_MODELS} if info is None else info
        self.kwargs = kwargs
        self.clients: list[InfoClient] = []

    def __call__(self, options: ClaudeAgentOptions) -> Any:
        client = InfoClient(options, self.info, **self.kwargs)
        self.clients.append(client)
        return client


class Http:
    """``httpx.MockTransport`` 처리기(요청을 기록한다)."""

    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def factory(self) -> httpx.AsyncClient:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            result: httpx.Response = self.handler(request)
            return result

        return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _never(_request: httpx.Request) -> httpx.Response:  # pragma: no cover - 불리면 안 된다
    raise AssertionError("HTTP must not be called")


def _backend(
    factory: Factory | None = None,
    *,
    http: Http | None = None,
    auth: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    allow_subscription_auth: bool = True,
    cli: str | None = FAKE_CLI,
    files: frozenset[str] = frozenset({"/home/u/.claude/.credentials.json"}),
    discovery: dict[str, Any] | None = None,
    workspace: Path | None = None,
) -> tuple[ClaudeSdkBackend, SecretResolver]:
    secrets = SecretResolver([EnvSecretProvider(env or {})])
    backend = ClaudeSdkBackend(
        client_factory=factory or Factory(),
        secrets=secrets,
        environ={"HOME": "/home/u", **(env or {})},
        readiness={"auth": auth or {"mode": "subscription"}},
        allow_subscription_auth=allow_subscription_auth,
        cli_locator=lambda _p: cli,
        path_exists=lambda p: p in files,
        model_discovery=discovery,
        http_client_factory=(http or Http(_never)).factory,
        workspace=workspace,
        auth_dir=None if workspace is not None else {"config_dir": None},
    )
    return backend, secrets


def _ctx(secrets: SecretResolver) -> BackendCheckContext:
    return BackendCheckContext("claude-agent-sdk", clock=lambda: 7.0, has_secret=secrets.has)


API_KEY_AUTH = {"mode": "api_key", "api_key": "secret://anthropic_api_key"}


# ---------------------------------------------------------------- 능력·설정


def test_capability_declared_and_settings_default() -> None:
    backend, _ = _backend()
    assert backend.descriptor.capabilities.model_discovery is True
    assert supports_model_discovery(backend)
    parsed = ClaudeSdkInstallOptions.model_validate({})
    assert parsed.model_discovery == ClaudeSdkModelDiscoveryOptions()
    assert parsed.model_discovery.method == "auto"
    assert parsed.model_discovery.page_limit == 1000
    with pytest.raises(ValueError, match="model_discovery"):
        ClaudeSdkBackend.from_options(
            {"model_discovery": {"zz": 1}}, secrets=SecretResolver(), environ={}
        )


def test_from_options_passes_model_discovery() -> None:
    backend = ClaudeSdkBackend.from_options(
        {"model_discovery": {"method": "models_api", "api_base_url": "http://gw.invalid"}},
        secrets=SecretResolver(),
        environ={},
    )
    assert backend._model_discovery.method == "models_api"


def test_api_base_url_order() -> None:
    opts = ClaudeSdkModelDiscoveryOptions(api_base_url="http://set.invalid/")
    assert api_base_url(opts, {"ANTHROPIC_BASE_URL": "http://env.invalid"}) == "http://set.invalid"
    env = {"ANTHROPIC_BASE_URL": "http://env.invalid"}
    assert api_base_url(ClaudeSdkModelDiscoveryOptions(), env) == "http://env.invalid"


# ---------------------------------------------------------------- 응답 해석


def test_server_info_mapping() -> None:
    parsed = models_from_server_info({"models": INFO_MODELS})
    assert parsed is not None
    assert parsed.skipped == 1
    first, second = (ModelInfo.model_validate(m) for m in parsed.models)
    assert (first.id, first.title, first.description) == ("zz-alias", "Zz Alias", "pick me")
    assert first.attributes == {"supportsEffort": True}
    assert second.description is None  # 빈 설명은 없음
    assert second.attributes == {"resolvedModel": "zz-x"}
    assert models_from_server_info({"commands": []}) is None
    assert models_from_server_info(None) is None
    with pytest.raises(ValueError, match="models"):
        models_from_server_info({"models": {"value": "x"}})


def test_api_page_mapping() -> None:
    page = models_from_api_page(
        {
            "data": [
                {
                    "type": "model",
                    "id": "zz-a",
                    "display_name": "A",
                    "max_input_tokens": 5,
                    "line": "z",
                },
                {"type": "model", "display_name": "no id"},
                "junk",
            ],
            "has_more": True,
            "last_id": "zz-a",
        }
    )
    assert page.has_more
    assert page.last_id == "zz-a"
    assert page.parsed.skipped == 2
    (only,) = (ModelInfo.model_validate(m) for m in page.parsed.models)
    assert (only.id, only.title, only.context_window) == ("zz-a", "A", 5)
    assert only.attributes == {"line": "z"}
    with pytest.raises(ValueError, match="data"):
        models_from_api_page({"models": []})


# ---------------------------------------------------------------- 구독: CLI 초기화 응답


async def test_sdk_init_lists_models_without_query() -> None:
    factory = Factory()
    backend, secrets = _backend(factory)
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.ok
    assert result.method == METHOD_SDK_INIT
    assert [ModelInfo.model_validate(m).id for m in result.models] == ["zz-alias", "zz-full-1"]
    assert result.details == {"skipped": 1}
    (client,) = factory.clients
    assert client.queries == 0
    assert client.connected
    assert client.disconnected
    opts = client.options
    assert opts.model is None
    assert opts.tools == []
    assert opts.setting_sources == []
    assert opts.extra_args.get("no-session-persistence", "missing") is None
    assert opts.cwd
    assert Path(opts.cwd).name.startswith("ac-models-")
    assert not Path(opts.cwd).exists()  # 임시 작업 폴더는 지웠다


async def test_sdk_init_without_models_key_is_unsupported() -> None:
    factory = Factory(info={"commands": [], "output_style": "x"})
    backend, secrets = _backend(factory)
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert not result.ok
    assert result.unsupported
    assert result.reason == ModelDiscoveryReasons.CLI_NO_MODELS
    assert factory.clients[0].disconnected


async def test_sdk_init_bad_shape_is_invalid_response() -> None:
    factory = Factory(info={"models": "nope"})
    backend, secrets = _backend(factory)
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.reason == ModelDiscoveryReasons.INVALID_RESPONSE
    assert factory.clients[0].disconnected


async def test_sdk_init_timeout_and_errors_still_disconnect() -> None:
    hanging = Factory(hang=True)
    backend, secrets = _backend(hanging)
    timed = await backend.discover_models(_ctx(secrets), 0.2)
    assert timed.reason == ModelDiscoveryReasons.TIMEOUT
    assert hanging.clients[0].disconnected
    broken = Factory(connect_error=CLIConnectionError(f"boom {KEY}"))
    backend, secrets = _backend(broken)
    failed = await backend.discover_models(_ctx(secrets), 5.0)
    assert failed.reason == ModelDiscoveryReasons.NETWORK
    assert KEY not in json.dumps(failed.details)
    assert broken.clients[0].disconnected
    assert broken.clients[0].queries == 0


async def test_subscription_disabled_and_missing_login_call_nothing() -> None:
    factory = Factory()
    backend, secrets = _backend(factory, allow_subscription_auth=False)
    off = await backend.discover_models(_ctx(secrets), 5.0)
    assert off.reason == ModelDiscoveryReasons.SUBSCRIPTION_DISABLED
    no_cli, secrets = _backend(factory, cli=None)
    missing_cli = await no_cli.discover_models(_ctx(secrets), 5.0)
    assert missing_cli.reason == ModelDiscoveryReasons.CLI_MISSING
    assert factory.clients == []


async def test_app_auth_dir_without_login_is_auth_missing(tmp_path: Path) -> None:
    factory = Factory()
    backend, secrets = _backend(factory, workspace=tmp_path, files=frozenset())
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.reason == ModelDiscoveryReasons.AUTH_MISSING
    assert factory.clients == []


async def test_sdk_init_forced_with_api_key_auth_uses_cli() -> None:
    factory = Factory()
    backend, secrets = _backend(
        factory,
        auth=API_KEY_AUTH,
        env={"anthropic_api_key": KEY},
        discovery={"method": "sdk_init"},
    )
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.ok
    assert factory.clients[0].options.env.get("ANTHROPIC_API_KEY") == KEY  # CLI 환경으로만
    assert KEY not in json.dumps([dict(m) for m in result.models])


# ---------------------------------------------------------------- API 키: Models API


def _page(ids: list[str], *, more: bool) -> dict[str, Any]:
    return {
        "data": [{"type": "model", "id": i, "display_name": i.upper()} for i in ids],
        "has_more": more,
        "first_id": ids[0] if ids else None,
        "last_id": ids[-1] if ids else None,
    }


async def test_models_api_two_pages(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "after_id" not in request.url.params:
            return httpx.Response(200, json=_page(["zz-a", "zz-b"], more=True))
        assert request.url.params["after_id"] == "zz-b"
        return httpx.Response(200, json=_page(["zz-c"], more=False))

    http = Http(handler)
    factory = Factory()
    backend, secrets = _backend(
        factory,
        http=http,
        auth=API_KEY_AUTH,
        env={"anthropic_api_key": KEY, "ANTHROPIC_BASE_URL": "http://gw.invalid/"},
        discovery={"page_limit": 2, "api_version": "zz-version"},
    )
    service = BackendModelCatalogService(
        lambda: {"claude-agent-sdk": backend}, has_secret=secrets.has
    )
    with caplog.at_level(logging.DEBUG):
        catalog = await service.catalog("claude-agent-sdk")
    assert catalog.discovery.state == "ok"
    assert [m.id for m in catalog.models] == ["zz-a", "zz-b", "zz-c"]
    assert catalog.models[0].title == "ZZ-A"
    assert len(http.requests) == 2
    first = http.requests[0]
    assert str(first.url).startswith("http://gw.invalid/v1/models")
    assert first.url.params["limit"] == "2"
    assert first.headers["x-api-key"] == KEY  # 키는 헤더에만
    assert first.headers["anthropic-version"] == "zz-version"
    assert KEY not in catalog.model_dump_json()
    assert KEY not in caplog.text
    assert factory.clients == []  # CLI를 띄우지 않는다


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda r: httpx.Response(401, json={"error": {"message": KEY}}), "auth_failed"),
        (lambda r: httpx.Response(403, json={}), "auth_failed"),
        (lambda r: httpx.Response(500, text="oops"), "error"),
        (lambda r: httpx.Response(200, json={"models": []}), "invalid_response"),
        (lambda r: httpx.Response(200, text="not json"), "invalid_response"),
    ],
)
async def test_models_api_failures(handler: Any, reason: str) -> None:
    backend, secrets = _backend(
        http=Http(handler), auth=API_KEY_AUTH, env={"anthropic_api_key": KEY}
    )
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert not result.ok
    assert result.method == METHOD_MODELS_API
    assert result.reason == reason
    assert KEY not in json.dumps(result.details)


async def test_models_api_network_and_timeout() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    for handler, reason in ((refuse, "network"), (slow, "timeout")):
        backend, secrets = _backend(
            http=Http(handler), auth=API_KEY_AUTH, env={"anthropic_api_key": KEY}
        )
        result = await backend.discover_models(_ctx(secrets), 5.0)
        assert result.reason == reason


async def test_models_api_without_key_calls_nothing() -> None:
    http = Http(_never)
    factory = Factory()
    backend, secrets = _backend(factory, http=http, auth=API_KEY_AUTH)
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.reason == ModelDiscoveryReasons.AUTH_MISSING
    assert http.requests == []
    assert factory.clients == []


async def test_models_api_forced_in_subscription_mode_needs_key() -> None:
    http = Http(_never)
    backend, secrets = _backend(http=http, discovery={"method": "models_api"})
    result = await backend.discover_models(_ctx(secrets), 5.0)
    assert result.reason == ModelDiscoveryReasons.AUTH_MISSING
    assert http.requests == []


async def test_catalog_merges_configured_list_first() -> None:
    factory = Factory()
    secrets = SecretResolver()
    backend = ClaudeSdkBackend(
        client_factory=factory,
        secrets=secrets,
        environ={"HOME": "/home/u"},
        models=[{"id": "zz-full-1", "title": "Mine"}, {"id": "zz-only-config"}],
        cli_locator=lambda _p: FAKE_CLI,
        path_exists=lambda p: p == "/home/u/.claude/.credentials.json",
        auth_dir={"config_dir": None},
    )
    service = BackendModelCatalogService(lambda: {"claude-agent-sdk": backend})
    catalog = await service.catalog("claude-agent-sdk")
    assert [(m.id, m.title, m.sources) for m in catalog.models] == [
        ("zz-full-1", "Mine", ["config", "discovered"]),
        ("zz-only-config", None, ["config"]),
        ("zz-alias", "Zz Alias", ["discovered"]),
    ]
    assert factory.clients[0].queries == 0
