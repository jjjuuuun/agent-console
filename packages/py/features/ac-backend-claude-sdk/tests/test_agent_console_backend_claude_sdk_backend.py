"""ClaudeSdkBackend: 주입한 가짜 SDK 클라이언트로 메시지 → 이벤트, 결과, 취소, 오류, 관측을 검사."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookEventMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_console_backend_claude_sdk import ClaudeSdkBackend
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent, Limits, ModelInfo
from agent_console_runtime import (
    BACKENDS_GROUP,
    REDACTED,
    AgentRequest,
    CancelToken,
    EnvSecretProvider,
    ExecutionBackend,
    Registries,
    SecretResolver,
    SessionRef,
    load_registries,
)

SECRET = "sk-ant-api-THISISASECRETVALUE123"


def _agent(**options: Any) -> Agent:
    return Agent(
        id="coder",
        name="Coder",
        model="model-from-definition",
        tools=["Read", "Bash(git:*)"],
        system_prompt="be brief",
        backend="claude-agent-sdk",
        backend_options=options,
    )


def _init(session: str = "sess-1", **extra: Any) -> SystemMessage:
    return SystemMessage(
        subtype="init", data={"session_id": session, "model": "model-reported", **extra}
    )


def _delta(text: str, parent: str | None = None) -> StreamEvent:
    return StreamEvent(
        uuid="u",
        session_id="sess-1",
        event={
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": text},
        },
        parent_tool_use_id=parent,
    )


def _result(**kw: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 10,
        "duration_api_ms": 8,
        "is_error": False,
        "num_turns": 1,
        "session_id": "sess-1",
        "result": "Hello world",
        "usage": {"input_tokens": 30, "output_tokens": 12, "cache_read_input_tokens": 5},
        "total_cost_usd": 0.01,
    }
    base.update(kw)
    return ResultMessage(**base)


def _script() -> list[Any]:
    usage = {"input_tokens": 10, "output_tokens": 4}
    return [
        _init(),
        StreamEvent(
            uuid="u0",
            session_id="sess-1",
            event={"type": "message_start", "message": {"id": "msg_1"}},
        ),
        _delta("Hello "),
        _delta("sub-agent text", parent="toolu_task"),
        _delta("world"),
        AssistantMessage(
            content=[TextBlock("Hello world")], model="m", usage=usage, message_id="msg_1"
        ),
        # 같은 message_id의 다음 블록(같은 usage) → 사용량 중복 집계 없음
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="toolu_1", name="Read", input={"file_path": "a.txt", "api_key": SECRET}
                )
            ],
            model="m",
            usage=usage,
            message_id="msg_1",
        ),
        UserMessage(
            content=[
                ToolResultBlock(tool_use_id="toolu_1", content=f"key={SECRET}", is_error=False)
            ]
        ),
        TaskStartedMessage(
            subtype="task_started",
            data={},
            task_id="t1",
            description="explore",
            uuid="u",
            session_id="sess-1",
        ),
        TaskNotificationMessage(
            subtype="task_notification",
            data={},
            task_id="t1",
            status="completed",
            output_file="",
            summary="",
            uuid="u",
            session_id="sess-1",
            usage={"total_tokens": 99, "tool_uses": 2, "duration_ms": 5},
        ),
        _result(structured_output={"ok": True}),
    ]


def _backend(factory: Callable[[ClaudeAgentOptions], Any], **kw: Any) -> ClaudeSdkBackend:
    kw.setdefault("environ", {})
    return ClaudeSdkBackend(client_factory=factory, **kw)


def _capture(script: list[Any], **kw: Any) -> tuple[list[Any], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[Any] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script, **kw)
        clients.append(client)
        return client

    return clients, factory


async def test_messages_become_contract_events_and_result() -> None:
    sink = ValidatingSink()
    clients, factory = _capture(_script())
    req = AgentRequest(agent=_agent(env={"ANTHROPIC_API_KEY": SECRET}), prompt="hi", cwd="/work")
    result = await _backend(factory).run(req, sink, CancelToken())

    assert result.status == "succeeded", result.error
    assert result.text == "Hello world"
    assert result.structured == {"ok": True}
    assert result.session == SessionRef(backend="claude-agent-sdk", session_id="sess-1")
    assert result.usage.input_tokens == 30
    assert result.usage.cache_read_tokens == 5
    assert result.usage.cost_usd == 0.01
    assert clients[0].prompts == ["hi"]
    assert clients[0].disconnected

    assert sink.types == [
        "agent.session_started",
        "agent.text_delta",
        "agent.text_delta",
        "agent.message",
        "agent.usage",
        "agent.tool_call",
        "agent.tool_result",
        "agent.subagent_started",
        "agent.subagent_stopped",
        "agent.usage",
    ]
    assert sink.of("agent.session_started")[0] == {
        "session_id": "sess-1",
        "backend": "claude-agent-sdk",
        "model": "model-reported",
    }
    assert [p["text"] for p in sink.of("agent.text_delta")] == ["Hello ", "world"]
    assert all(p["message_id"] == "msg_1" for p in sink.of("agent.text_delta"))
    usages = [p["usage"] for p in sink.of("agent.usage")]
    assert usages[0]["input_tokens"] == 10  # 같은 message_id 두 번 → 한 번만
    assert usages[-1]["input_tokens"] == 30  # 최종은 ResultMessage 누적값
    assert sink.of("agent.subagent_stopped")[0]["usage"]["total_tokens"] == 99

    # 비밀은 payload·raw 어디에도 없다
    dumped = repr([(e.payload, e.raw) for e in sink.events])
    assert SECRET not in dumped
    assert sink.of("agent.tool_call")[0]["input"]["api_key"] == REDACTED
    deltas = [e for e in sink.events if e.type == "agent.text_delta"]
    assert all(e.raw is None for e in deltas)
    assert sink.events[0].raw["_type"] == "SystemMessage"


async def test_options_mapping_reaches_client() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(
        agent=_agent(max_turns=3),
        prompt="p",
        cwd="/work",
        limits=Limits(directories=["/work", "/shared"], commands=["git status"], network="deny"),
        session=SessionRef(backend="claude-agent-sdk", session_id="prev"),
    )
    await _backend(factory).run(req, sink, CancelToken())
    opts = clients[0].options
    assert opts.cwd == "/work"
    assert opts.model == "model-from-definition"
    assert opts.tools == ["Bash", "Read"]
    assert opts.allowed_tools == ["Read", "Bash(git:*)"]
    assert "WebFetch" in opts.disallowed_tools
    assert opts.permission_mode == "dontAsk"
    assert opts.setting_sources == ["project"]
    assert opts.strict_mcp_config is True
    assert opts.add_dirs == ["/shared"]
    assert opts.resume == "prev"
    assert opts.max_turns == 3
    assert opts.system_prompt == "be brief"
    assert opts.include_partial_messages is True
    assert opts.can_use_tool is None  # dontAsk는 묻지 않는다
    assert "PreToolUse" in (opts.hooks or {})


async def test_guard_hook_denies_out_of_scope_commands() -> None:
    sink = ValidatingSink()
    calls = [
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status -s"},
                "tool_use_id": "t1",
            },
        ),
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status; rm -rf /"},
                "tool_use_id": "t2",
            },
        ),
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/etc/passwd"},
                "tool_use_id": "t3",
            },
        ),
    ]
    clients, factory = _capture([_init(), _result()], hook_calls=calls)
    req = AgentRequest(
        agent=_agent(), prompt="p", cwd="/work", limits=Limits(commands=["git status"])
    )
    await _backend(factory).run(req, sink, CancelToken())
    outs = clients[0].hook_outputs
    assert outs[0] == {}
    assert outs[1]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert outs[2]["hookSpecificOutput"]["permissionDecision"] == "deny"


async def test_can_use_tool_set_for_asking_modes() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(agent=_agent(permission_mode="default"), prompt="p", cwd="/w")
    await _backend(factory).run(req, sink, CancelToken())
    can_use = clients[0].options.can_use_tool
    assert can_use is not None
    denied = await can_use("Bash", {"command": "ls"}, None)
    assert denied.behavior == "deny"
    other = await can_use("Read", {"file_path": "/w/x"}, None)
    assert other.behavior == "deny"  # unmatched_permission 기본 deny


async def test_cancel_interrupts_and_returns_cancelled() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init(), _delta("partial")], block=True)
    cancel = CancelToken()
    req = AgentRequest(agent=_agent(), prompt="p", cwd="/w")
    task = asyncio.create_task(_backend(factory).run(req, sink, cancel))
    while "agent.text_delta" not in sink.types:
        await asyncio.sleep(0.01)
    cancel.cancel()
    result = await asyncio.wait_for(task, 2)
    assert result.status == "cancelled"
    assert clients[0].interrupted.is_set()
    assert clients[0].disconnected
    assert result.session is not None


async def test_cancel_gives_up_after_grace() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init()], block=True, ignore_interrupt=True)
    cancel = CancelToken()
    task = asyncio.create_task(
        _backend(factory, cancel_grace=0.05).run(
            AgentRequest(agent=_agent(), prompt="p"), sink, cancel
        )
    )
    await asyncio.sleep(0.05)
    cancel.cancel()
    result = await asyncio.wait_for(task, 2)
    assert result.status == "cancelled"
    assert clients[0].disconnected


async def test_error_result_becomes_failed() -> None:
    sink = ValidatingSink()
    script = [
        _init(),
        _result(is_error=True, subtype="error_max_turns", result=None, errors=["too many turns"]),
    ]
    _, factory = _capture(script)
    result = await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken()
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "agent_error"
    assert result.error.message == "too many turns"
    assert result.error.details["subtype"] == "error_max_turns"


async def test_sdk_exception_is_failed_and_masked() -> None:
    sink = ValidatingSink()
    _, factory = _capture([], connect_error=RuntimeError(f"bad key {SECRET}"))
    req = AgentRequest(agent=_agent(env={"ANTHROPIC_API_KEY": SECRET}), prompt="p")
    result = await _backend(factory).run(req, sink, CancelToken())
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "backend_error"
    assert SECRET not in result.error.message


async def test_stream_without_result_fails() -> None:
    sink = ValidatingSink()
    _, factory = _capture([_init()])
    result = await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken()
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "backend_no_result"


async def test_invalid_options_fail_without_client() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([])
    for options in (
        {"permission_mode": "yolo"},
        {"sdk_options": {"cwd": "/x"}},
        {"sdk_options": {"nope": 1}},
    ):
        result = await _backend(factory).run(
            AgentRequest(agent=_agent(**options), prompt="p"), sink, CancelToken()
        )
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "validation_failed"
    assert clients == []


async def test_secret_refs_in_env() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(
        agent=_agent(env={"ANTHROPIC_API_KEY": "secret://anthropic_api_key"}), prompt="p"
    )
    unresolved = await _backend(factory).run(req, sink, CancelToken())
    assert unresolved.error is not None
    assert unresolved.error.code == "secret_unresolved"

    resolver = SecretResolver([EnvSecretProvider({"ANTHROPIC_API_KEY": SECRET})])
    ok = await _backend(factory, secrets=resolver).run(req, sink, CancelToken())
    assert ok.status == "succeeded"
    assert clients[-1].options.env == {"ANTHROPIC_API_KEY": SECRET}


async def test_observe_hooks_and_mcp() -> None:
    sink = ValidatingSink()
    times = iter([1.0, 1.25])
    script = [
        _init(mcp_servers=[{"name": "wiki", "status": "connected"}]),
        HookEventMessage(
            subtype="hook_response",
            data={
                "hook_event": "PreToolUse",
                "hook_id": "h1",
                "exit_code": 0,
                "outcome": "success",
                "stdout": "x",
            },
            hook_event_name="PreToolUse",
            session_id="sess-1",
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="toolu_m", name="mcp__wiki__search", input={"q": "x"})],
            model="m",
        ),
        UserMessage(
            content=[ToolResultBlock(tool_use_id="toolu_m", content="found", is_error=False)]
        ),
        _result(),
    ]
    calls = [
        (
            "PostToolUse",
            {
                "hook_event_name": "PostToolUse",
                "session_id": "sess-1",
                "tool_name": "Read",
                "tool_use_id": "t9",
            },
        )
    ]
    clients, factory = _capture(script, hook_calls=calls)
    req = AgentRequest(agent=_agent(), prompt="p", observe={"hooks": True, "mcp": True})
    await _backend(factory, clock=lambda: next(times)).run(req, sink, CancelToken())

    assert clients[0].options.include_hook_events is True
    assert sink.of("mcp.server_status")[0] == {"servers": [{"name": "wiki", "status": "connected"}]}
    assert sink.of("hook.completed")[0]["hook_id"] == "h1"
    invoked = sink.of("hook.invoked")
    assert invoked[0]["hook_type"] == "sdk-callback"
    assert invoked[0]["tool_use_id"] == "t9"
    assert sink.of("mcp.call_started")[0] == {
        "server": "wiki",
        "tool": "search",
        "tool_use_id": "toolu_m",
    }
    done = sink.of("mcp.call_completed")[0]
    assert done["duration_ms"] == 250
    assert done["is_error"] is False


async def test_observe_off_emits_no_hook_or_mcp_events() -> None:
    sink = ValidatingSink()
    script = [
        _init(mcp_servers=[{"name": "wiki", "status": "connected"}]),
        AssistantMessage(
            content=[ToolUseBlock(id="toolu_m", name="mcp__wiki__search", input={})], model="m"
        ),
        _result(),
    ]
    clients, factory = _capture(script)
    await _backend(factory).run(AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken())
    assert not [t for t in sink.types if t.startswith(("hook.", "mcp."))]
    assert set(clients[0].options.hooks or {}) == {"PreToolUse"}
    assert clients[0].options.include_hook_events is False


async def test_list_models_from_injected_data() -> None:
    assert await ClaudeSdkBackend().list_models() == []
    backend = ClaudeSdkBackend(models=[{"id": "configured-model"}])
    assert await backend.list_models() == [ModelInfo(id="configured-model")]


def test_descriptor_declares_enforcement_honestly() -> None:
    backend = ClaudeSdkBackend()
    caps = backend.descriptor.capabilities
    assert backend.descriptor.id == "claude-agent-sdk"
    assert caps.enforce.commands is True
    assert caps.enforce.directories is False
    assert caps.enforce.network is False
    assert all([caps.streaming, caps.cancel, caps.resume, caps.hooks, caps.mcp])
    assert isinstance(backend, ExecutionBackend)


def test_registered_as_entry_point() -> None:
    eps = [ep for ep in entry_points(group=BACKENDS_GROUP) if ep.name == "claude-agent-sdk"]
    assert len(eps) == 1
    regs = Registries()
    load_registries(regs, enabled={"claude-agent-sdk"}, entry_points=eps)
    assert isinstance(regs.backends.get("claude-agent-sdk"), ClaudeSdkBackend)


async def test_invalid_option_errors_do_not_echo_input() -> None:
    sink = ValidatingSink()
    _, factory = _capture([])
    req = AgentRequest(agent=_agent(max_turns=SECRET), prompt="p")
    result = await _backend(factory).run(req, sink, CancelToken())
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert SECRET not in repr(result.error.model_dump())
    assert "input" not in result.error.details["errors"][0]


async def test_parent_env_is_allowlisted() -> None:
    sink = ValidatingSink()
    parent = {
        "PATH": "/usr/bin",
        "HOME": "/home/u",
        "LC_ALL": "C.UTF-8",
        "SystemRoot": "C:\\Windows",
        "AGENT_CONSOLE_TOKEN": "server-only-fake-value",
        "OTHER_API_KEY": "fake-other-key",
        "ANTHROPIC_API_KEY": "parent-fake-key",
    }
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(agent=_agent(env={"ANTHROPIC_API_KEY": SECRET}), prompt="p")
    await _backend(factory, environ=parent).run(req, sink, CancelToken())
    env = clients[0].options.env
    # SDK는 부모 환경 위에 options.env를 덮어쓰므로 최종 환경 = parent | env
    final = {**parent, **env}
    assert final["PATH"] == "/usr/bin"
    assert final["HOME"] == "/home/u"
    assert final["LC_ALL"] == "C.UTF-8"
    assert final["SystemRoot"] == "C:\\Windows"
    assert final["AGENT_CONSOLE_TOKEN"] == ""
    assert final["OTHER_API_KEY"] == ""
    assert final["ANTHROPIC_API_KEY"] == SECRET  # 명시 env가 우선
    assert "server-only-fake-value" not in final.values()
    assert not sink.of("log.warning")


async def test_env_policy_is_configurable_and_inherit_all_warns() -> None:
    sink = ValidatingSink()
    parent = {"PATH": "/bin", "CUSTOM_CA": "x", "HIDDEN": "y"}
    clients, factory = _capture([_init(), _result()])
    backend = _backend(factory, environ=parent, env_policy={"allow": ["PATH", "CUSTOM_*"]})
    await backend.run(AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken())
    assert clients[0].options.env == {"HIDDEN": ""}

    all_backend = _backend(factory, environ=parent, env_policy={"inherit": "all"})
    await all_backend.run(AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken())
    assert clients[1].options.env == {}
    assert any("env_policy" in w["message"] for w in sink.of("log.warning"))


async def test_risky_options_emit_warnings() -> None:
    sink = ValidatingSink()
    clients, factory = _capture([_init(), _result()])
    agent = _agent(
        setting_sources=["user", "project"],
        sdk_options={"permission_mode": "bypassPermissions"},
    )
    result = await _backend(factory).run(AgentRequest(agent=agent, prompt="p"), sink, CancelToken())
    assert result.status == "succeeded"
    options = [w["details"]["option"] for w in sink.of("log.warning")]
    assert options == ["permission_mode", "setting_sources"]
    assert clients[0].options.can_use_tool is None
    assert "PreToolUse" in (clients[0].options.hooks or {})  # 범위 검사는 유지


async def test_sdk_options_env_override_warns_with_key_names_only() -> None:
    sink = ValidatingSink()
    _, factory = _capture([_init(), _result()])
    agent = _agent(sdk_options={"env": {"MY_KEY": "value-should-not-appear"}})
    await _backend(factory).run(AgentRequest(agent=agent, prompt="p"), sink, CancelToken())
    warnings = [w for w in sink.of("log.warning") if w["details"]["option"] == "sdk_options.env"]
    assert len(warnings) == 1
    assert warnings[0]["details"]["keys"] == ["MY_KEY"]
    assert "value-should-not-appear" not in repr(sink.of("log.warning"))


async def test_from_options_hook_builds_configured_backend() -> None:
    """`ConfigurableBackend` 훅: 설치자 설정(models·env_policy)·공용 해석기·주입 환경으로 만든다."""
    from agent_console_runtime import ConfigurableBackend, EnvSecretProvider, SecretResolver

    resolver = SecretResolver([EnvSecretProvider({})])
    parent = {"PATH": "/bin", "CUSTOM_CA": "x", "HIDDEN": "y"}
    backend = ClaudeSdkBackend.from_options(
        {"models": [{"id": "m1"}], "env_policy": {"allow": ["PATH", "CUSTOM_*"]}},
        secrets=resolver,
        environ=parent,
    )
    assert isinstance(backend, ConfigurableBackend)
    assert [m.id for m in await backend.list_models()] == ["m1"]
    clients, factory = _capture([_init(), _result()])
    backend._client_factory = factory  # 테스트: SDK 클라이언트만 가짜로 바꾼다
    await backend.run(AgentRequest(agent=_agent(), prompt="p"), ValidatingSink(), CancelToken())
    assert clients[0].options.env == {"HIDDEN": ""}  # 주입한 environ + 설정한 정책

    default = ClaudeSdkBackend.from_options({}, secrets=resolver, environ={})
    assert await default.list_models() == []


def test_from_options_rejects_unknown_keys_without_values() -> None:
    from agent_console_runtime import EnvSecretProvider, SecretResolver

    resolver = SecretResolver([EnvSecretProvider({})])
    with pytest.raises(ValueError, match="nope") as exc:
        ClaudeSdkBackend.from_options(
            {"nope": "secret-looking-value"}, secrets=resolver, environ={}
        )
    assert "secret-looking-value" not in str(exc.value)
    with pytest.raises(ValueError, match="cancel_grace"):
        ClaudeSdkBackend.from_options({"cancel_grace": -1}, secrets=resolver, environ={})
