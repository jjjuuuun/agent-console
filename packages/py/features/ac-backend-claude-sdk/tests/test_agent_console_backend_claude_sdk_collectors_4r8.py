"""4R.8 관측 수집기(X7): 설정 해석, 옛 키 호환, 예외 격리, 설정 검증, entry point 확장."""

from __future__ import annotations

import inspect
import sys
import types
from collections.abc import Callable, Mapping
from importlib.metadata import EntryPoint
from typing import Any, ClassVar, cast

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookEventMessage,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

import agent_console_backend_claude_sdk._backend as backend_module
import agent_console_backend_claude_sdk._collector_run as run_module
from agent_console_backend_claude_sdk import COLLECTOR_ISSUES, ClaudeSdkBackend
from agent_console_backend_claude_sdk.collectors import (
    COLLECTOR_ERROR_MESSAGE,
    COLLECTORS_GROUP,
    BaseClaudeSdkCollector,
    ClaudeSdkCollector,
    CollectorContext,
    McpCallsCollector,
    ResolvedCollector,
    SdkHooksCollector,
    as_collector,
    default_collectors,
    discover_collectors,
    resolve_collector_settings,
    select_collectors,
)
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, AgentSettings, InteractionGrant, JsonObject, RunEvent
from agent_console_runtime import AgentRequest, CancelToken, SubagentSpec

# ------------------------------------------------------------------ 도우미


def _agent() -> Agent:
    return Agent(id="coder", name="Coder", backend="claude-agent-sdk", tools=["Read"])


def _init() -> SystemMessage:
    return SystemMessage(
        subtype="init",
        data={"session_id": "s1", "mcp_servers": [{"name": "wiki", "status": "connected"}]},
    )


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s1",
        result="ok",
    )


def _script() -> list[Any]:
    return [
        _init(),
        HookEventMessage(
            subtype="hook_response",
            data={"hook_event": "Stop", "hook_id": "h1", "exit_code": 0, "outcome": "success"},
            hook_event_name="Stop",
            session_id="s1",
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="t_m", name="mcp__wiki__search", input={"q": "x"})],
            model="m",
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="t_m", content="r", is_error=True)]),
        _result(),
    ]


HOOK_CALLS = [
    (
        "PostToolUse",
        {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Read"},
    )
]


def _capture(
    script: list[Any], **kw: Any
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script, **kw)
        clients.append(client)
        return client

    return clients, factory


async def _run(
    observe: Mapping[str, Any],
    *,
    collectors: list[Any] | None = None,
    script: list[Any] | None = None,
    **req: Any,
) -> tuple[ValidatingSink, FakeSdkClient, Any]:
    clock = iter(float(i) for i in range(100))
    clients, factory = _capture(script or _script(), hook_calls=HOOK_CALLS)
    backend = ClaudeSdkBackend(
        client_factory=factory, environ={}, clock=lambda: next(clock), collectors=collectors
    )
    sink = ValidatingSink()
    result = await backend.run(
        AgentRequest(agent=_agent(), prompt="p", observe=dict(observe), **req),
        sink,
        CancelToken(),
    )
    return sink, clients[0], result


def _observed(sink: ValidatingSink) -> list[tuple[str, dict[str, Any], Any]]:
    return [
        (e.type, dict(e.payload), e.raw)
        for e in sink.events
        if e.type.startswith(("hook.", "mcp."))
    ]


# ------------------------------------------------------------------ 설정 해석


def test_resolve_legacy_keys() -> None:
    got = resolve_collector_settings({"hooks": True, "mcp": False, "hook_events": ["Stop"]})
    assert got == {
        "sdk-hooks": ResolvedCollector(enabled=True, config={"events": ["Stop"]}),
        "mcp-calls": ResolvedCollector(enabled=False, config={}),
    }


def test_resolve_collectors_win_over_legacy() -> None:
    got = resolve_collector_settings(
        {
            "hooks": True,
            "hook_events": ["Stop"],
            "mcp": True,
            "collectors": {
                "sdk-hooks": {"enabled": False},  # enabled만 바꾸고 config는 옛 키 값 유지
                "mcp-calls": {"config": {}},  # enabled 생략 = 옛 키 값 유지
                "count": {"enabled": True, "config": {"x": 1}},
            },
        }
    )
    assert got["sdk-hooks"] == ResolvedCollector(enabled=False, config={"events": ["Stop"]})
    assert got["mcp-calls"] == ResolvedCollector(enabled=True, config={})
    assert got["count"] == ResolvedCollector(enabled=True, config={"x": 1})


def test_resolve_collectors_config_replaces_legacy_config() -> None:
    got = resolve_collector_settings(
        {"hook_events": ["Stop"], "collectors": {"sdk-hooks": {"config": {"events": ["X"]}}}}
    )
    assert got["sdk-hooks"] == ResolvedCollector(enabled=False, config={"events": ["X"]})


def test_resolve_ignores_malformed_and_empty() -> None:
    assert resolve_collector_settings(None) == {}
    assert resolve_collector_settings({}) == {}
    got = resolve_collector_settings(
        {"hooks": "yes", "collectors": {"a": "on", "b": {"enabled": "true", "config": 3}}}
    )
    assert got == {"b": ResolvedCollector(enabled=False, config={})}


def test_resolve_custom_legacy_table() -> None:
    got = resolve_collector_settings({"old": True}, legacy={"old": ("new-id", None)})
    assert got == {"new-id": ResolvedCollector(enabled=True)}


# ------------------------------------------------------------------ 옛 키 = 새 키(같은 이벤트)


async def test_collectors_setting_emits_same_events_as_legacy_keys() -> None:
    legacy, legacy_client, _ = await _run({"hooks": True, "mcp": True})
    new, new_client, _ = await _run(
        {"collectors": {"sdk-hooks": {"enabled": True}, "mcp-calls": {"enabled": True}}}
    )
    assert _observed(legacy) == _observed(new)
    types_ = [t for t, _, _ in _observed(new)]
    assert types_ == [
        "hook.invoked",
        "mcp.server_status",
        "hook.completed",
        "mcp.call_started",
        "mcp.call_completed",
    ]
    done = new.of("mcp.call_completed")[0]
    assert done == {
        "server": "wiki",
        "tool": "search",
        "tool_use_id": "t_m",
        "is_error": True,
        "duration_ms": 1000,
    }
    invoked = new.of("hook.invoked")[0]
    assert invoked == {
        "event": "PostToolUse",
        "hook_type": "sdk-callback",
        "session_id": "s1",
        "tool_name": "Read",
    }
    for client in (legacy_client, new_client):
        assert client.options.include_hook_events is True
        assert set(client.options.hooks or {}) >= {"PreToolUse", "PostToolUse", "Stop"}


async def test_collectors_off_wins_over_legacy_on() -> None:
    sink, client, _ = await _run(
        {
            "hooks": True,
            "mcp": True,
            "collectors": {"sdk-hooks": {"enabled": False}, "mcp-calls": {"enabled": False}},
        }
    )
    assert _observed(sink) == []
    assert client.options.include_hook_events is False
    assert set(client.options.hooks or {}) == {"PreToolUse"}


async def test_only_mcp_collector() -> None:
    sink, client, _ = await _run({"collectors": {"mcp-calls": {"enabled": True}}})
    assert {t for t, _, _ in _observed(sink)} == {
        "mcp.server_status",
        "mcp.call_started",
        "mcp.call_completed",
    }
    assert client.options.include_hook_events is False


async def test_hook_events_config_limits_callbacks() -> None:
    sink, client, _ = await _run(
        {"collectors": {"sdk-hooks": {"enabled": True, "config": {"events": ["Stop"]}}}}
    )
    assert set(client.options.hooks or {}) == {"PreToolUse", "Stop"}
    # PostToolUse 콜백을 걸지 않았으므로 sdk-callback 이벤트 없음, CLI 설정 hook 메시지만
    assert [p["hook_type"] for p in sink.of("hook.invoked") + sink.of("hook.completed")] == [
        "settings"
    ]


async def test_hook_callback_returns_empty_output() -> None:
    _, client, _ = await _run({"hooks": True})
    assert client.hook_outputs == [{}]


async def test_mcp_events_inside_subagent_are_attributed() -> None:
    delegate = AssistantMessage(
        content=[
            ToolUseBlock(
                id="toolu_agent",
                name="Agent",
                input={"subagent_type": "reviewer", "description": "d", "prompt": "p"},
            )
        ],
        model="m",
    )
    sub_call = AssistantMessage(
        content=[ToolUseBlock(id="t_s", name="mcp__gh__get", input={})],
        model="m",
        parent_tool_use_id="toolu_agent",
    )
    sub_result = UserMessage(
        content=[ToolResultBlock(tool_use_id="t_s", content="x", is_error=False)],
        parent_tool_use_id="toolu_agent",
    )
    sink, _, result = await _run(
        {"mcp": True},
        script=[_init(), delegate, sub_call, sub_result, _result()],
        subagents=[SubagentSpec(name="reviewer", description="d", prompt="p", actor="rev")],
    )
    assert result.status == "succeeded"
    started = [e for e in sink.events if e.type == "mcp.call_started"]
    done = [e for e in sink.events if e.type == "mcp.call_completed"]
    assert started[0].actor == "rev"
    assert started[0].node_path == ["n1", "reviewer"]
    assert done[0].actor == "rev"
    status = [e for e in sink.events if e.type == "mcp.server_status"]
    assert status[0].node_path == ["n1"]


# ------------------------------------------------------------------ 예외 격리


class _Exploding(BaseClaudeSdkCollector):
    id: ClassVar[str] = "explode"
    title: ClassVar[str] = "explode"
    default_backend: ClassVar[str] = "claude-agent-sdk"

    def hook_events(self, config: JsonObject) -> list[str]:
        return ["PostToolUse"]

    async def on_hook(
        self, event: str, data: Mapping[str, Any], tool_use_id: str | None, ctx: CollectorContext
    ) -> None:
        raise RuntimeError("secret-in-message")

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        ctx.emit("explode.before", {"n": 1})
        raise ValueError("boom")


class _BadSetup(BaseClaudeSdkCollector):
    id: ClassVar[str] = "bad-setup"
    title: ClassVar[str] = "bad"
    default_backend: ClassVar[str] = "claude-agent-sdk"

    def hook_events(self, config: JsonObject) -> list[str]:
        raise KeyError("x")


async def test_collector_exception_does_not_affect_run_one_warning() -> None:
    sink, _, result = await _run(
        {
            "mcp": True,
            "collectors": {"explode": {"enabled": True}, "bad-setup": {"enabled": True}},
        },
        collectors=[_Exploding(), *default_collectors(), _BadSetup()],
    )
    assert result.status == "succeeded"
    warnings = [p for p in sink.of("log.warning") if p["message"] == COLLECTOR_ERROR_MESSAGE]
    assert sorted((w["details"]["collector"], w["details"]["stage"]) for w in warnings) == [
        ("bad-setup", "setup"),
        ("explode", "on_hook"),
    ]
    assert all("secret" not in str(w) for w in warnings)
    # 예외 전 낸 이벤트는 나가고, 다른 수집기는 그대로 동작
    assert len(sink.of("explode.before")) == len(_script())
    assert sink.of("mcp.call_completed")


async def test_sink_failure_for_collector_event_is_swallowed() -> None:
    class FailingSink(ValidatingSink):
        async def emit(self, type: str, payload: Any = None, **kw: Any) -> RunEvent:
            if type.startswith("mcp."):
                raise RuntimeError("sink down")
            return await super().emit(type, payload, **kw)

    _clients, factory = _capture(_script())
    backend = ClaudeSdkBackend(client_factory=factory, environ={}, clock=lambda: 0.0)
    sink = FailingSink()
    result = await backend.run(
        AgentRequest(agent=_agent(), prompt="p", observe={"mcp": True}),
        cast("Any", sink),
        CancelToken(),
    )
    assert result.status == "succeeded"


# ------------------------------------------------------------------ 설정 검증


def _effective(collectors: dict[str, Any]) -> AgentSettings:
    return AgentSettings.model_validate({"observe": {"collectors": collectors}})


def test_validate_settings_unknown_collector_is_warning() -> None:
    backend = ClaudeSdkBackend(environ={})
    issues = backend.validate_settings(
        _effective({"nope": {"enabled": True}, "sdk-hooks": {"enabled": True}}),
        InteractionGrant(),
    )
    unknown = [i for i in issues if i.code == COLLECTOR_ISSUES.UNKNOWN]
    assert len(unknown) == 1
    assert unknown[0].severity == "warning"
    assert unknown[0].details["collector"] == "nope"
    assert unknown[0].details["known"] == ["mcp-calls", "sdk-hooks"]


def test_validate_settings_invalid_collector_config_is_warning() -> None:
    backend = ClaudeSdkBackend(environ={})
    issues = backend.validate_settings(
        _effective({"sdk-hooks": {"config": {"events": "Stop", "extra": 1}}}),
        InteractionGrant(),
    )
    bad = [i for i in issues if i.code == COLLECTOR_ISSUES.INVALID_CONFIG]
    assert len(bad) == 1
    assert bad[0].severity == "warning"
    assert bad[0].details["collector"] == "sdk-hooks"


def test_validate_settings_valid_collectors_no_issue() -> None:
    backend = ClaudeSdkBackend(environ={})
    issues = backend.validate_settings(
        _effective(
            {"sdk-hooks": {"enabled": True, "config": {"events": ["Stop"]}}, "mcp-calls": {}}
        ),
        InteractionGrant(),
    )
    assert issues == []


async def test_invalid_config_at_run_time_warns_and_skips() -> None:
    sink, _, result = await _run(
        {"collectors": {"sdk-hooks": {"enabled": True, "config": {"events": 3}}}}
    )
    assert result.status == "succeeded"
    warnings = [p for p in sink.of("log.warning") if p["message"] == COLLECTOR_ERROR_MESSAGE]
    assert [w["details"]["collector"] for w in warnings] == ["sdk-hooks"]


# ------------------------------------------------------------------ 디스크립터·등록


def test_descriptor_lists_default_collectors() -> None:
    backend = ClaudeSdkBackend(environ={})
    ids = [c.id for c in backend.descriptor.collectors]
    assert ids == ["sdk-hooks", "mcp-calls"]
    hooks = backend.descriptor.collectors[0]
    assert hooks.backend == "claude-agent-sdk"
    assert "events" in hooks.config_schema["properties"]
    assert hooks.emits == ["hook.invoked", "hook.completed"]


def test_backend_alias_gets_defaults_for_its_id() -> None:
    backend = ClaudeSdkBackend(environ={}, backend_id="claude-alt")
    assert [c.backend for c in backend.descriptor.collectors] == ["claude-alt", "claude-alt"]


def test_no_collector_ids_in_backend_or_dispatcher_code() -> None:
    """등록 목록에 switch가 없다: 백엔드·디스패처 코드는 수집기 id를 모른다."""
    for module in (backend_module, run_module):
        source = inspect.getsource(module)
        assert "sdk-hooks" not in source
        assert "mcp-calls" not in source


def test_as_collector_rejects_non_collectors() -> None:
    assert isinstance(as_collector(SdkHooksCollector), ClaudeSdkCollector)
    with pytest.raises(TypeError):
        as_collector(object())


def test_select_collectors_filters_backend_and_duplicates() -> None:
    other = McpCallsCollector(backend="other-backend")
    first = SdkHooksCollector()
    picked = select_collectors([other, first, SdkHooksCollector()], "claude-agent-sdk")
    assert picked == [first]


# ------------------------------------------------------------------ entry point 확장


class ToolCountCollector(BaseClaudeSdkCollector):
    """테스트 수집기: 도구 호출 수를 세어 결과 메시지에서 한 번 낸다."""

    id: ClassVar[str] = "tool-count"
    title: ClassVar[str] = "도구 호출 수"
    emits: ClassVar[tuple[str, ...]] = ("tool.count",)
    default_backend: ClassVar[str] = "claude-agent-sdk"

    def on_message(self, message: object, ctx: CollectorContext) -> None:
        if isinstance(message, AssistantMessage):
            n = sum(isinstance(b, ToolUseBlock) for b in message.content)
            ctx.state["n"] = ctx.state.get("n", 0) + n
        elif isinstance(message, ResultMessage):
            ctx.emit("tool.count", {"count": ctx.state.get("n", 0)})


class OtherBackendCollector(BaseClaudeSdkCollector):
    id: ClassVar[str] = "elsewhere"
    title: ClassVar[str] = "elsewhere"
    default_backend: ClassVar[str] = "another-backend"


@pytest.fixture
def plugin_module(monkeypatch: pytest.MonkeyPatch) -> str:
    module = types.ModuleType("ac_test_collector_plugin")
    module.ToolCountCollector = ToolCountCollector  # type: ignore[attr-defined]
    module.OtherBackendCollector = OtherBackendCollector  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module.__name__


def _ep(name: str, value: str) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=COLLECTORS_GROUP)


def test_discover_adds_entry_point_collector_and_filters_backend(plugin_module: str) -> None:
    eps = [
        _ep("tool-count", f"{plugin_module}:ToolCountCollector"),
        _ep("elsewhere", f"{plugin_module}:OtherBackendCollector"),
        _ep("broken", f"{plugin_module}:Missing"),
        EntryPoint(name="x", value=f"{plugin_module}:ToolCountCollector", group="other.group"),
    ]
    found, reports = discover_collectors(entry_points=eps)
    assert [c.descriptor.id for c in found] == ["tool-count", "sdk-hooks", "mcp-calls"]
    assert {r.key: r.status for r in reports} == {
        "broken": "failed",
        "elsewhere": "loaded",
        "tool-count": "loaded",
    }
    # 제거하면 사라진다
    gone, _ = discover_collectors(entry_points=[])
    assert [c.descriptor.id for c in gone] == ["sdk-hooks", "mcp-calls"]


def test_discover_installed_entry_points_include_defaults() -> None:
    found, reports = discover_collectors(include_defaults=False)
    assert {"sdk-hooks", "mcp-calls"} <= {c.descriptor.id for c in found}
    assert all(r.ok for r in reports if r.key in {"sdk-hooks", "mcp-calls"})


async def test_entry_point_collector_runs(plugin_module: str) -> None:
    found, _ = discover_collectors(entry_points=[_ep("t", f"{plugin_module}:ToolCountCollector")])
    sink, _, result = await _run(
        {"collectors": {"tool-count": {"enabled": True}}}, collectors=found
    )
    assert result.status == "succeeded"
    assert sink.of("tool.count") == [{"count": 1}]
    assert _observed(sink) == []  # 다른 수집기는 꺼져 있다


def test_from_options_discovers_entry_points() -> None:
    from agent_console_runtime import EnvSecretProvider, SecretResolver

    backend = ClaudeSdkBackend.from_options(
        {}, secrets=SecretResolver([EnvSecretProvider({})]), environ={}
    )
    assert {"sdk-hooks", "mcp-calls"} <= {c.id for c in backend.descriptor.collectors}
    assert backend.collector_reports
