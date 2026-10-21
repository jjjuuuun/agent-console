"""5R.10 백엔드 능력 `host_tools`: in-process SDK MCP 서버, 사전 승인 이름 규칙, 핸들러 호출·오류·
취소, `mcp-calls` 수집기 이벤트. 실호출 없음 — SDK 클라이언트는 가짜, 도구 서버는 설치 SDK의
`create_sdk_mcp_server`를 그대로 쓰고 CLI가 보내는 JSON-RPC로 부른다(`testing.SdkToolCall`)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)

from agent_console_backend_claude_sdk import (
    DEFAULT_HOST_TOOL_SERVER,
    ClaudeSdkBackend,
    ClaudeSdkBackendOptions,
    ClaudeSdkErrorCodes,
    build_host_tool_server,
    host_tool_rule,
)
from agent_console_backend_claude_sdk.testing import (
    FakeSdkClient,
    SdkToolCall,
    ValidatingSink,
    call_sdk_mcp_tool,
)
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken, HostTool, HostToolResult

SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "enum": ["reviewer", "writer"]},
        "task": {"type": "string"},
    },
    "required": ["target", "task"],
}


def test_installed_sdk_has_in_process_mcp_api() -> None:
    """설치 SDK에 `create_sdk_mcp_server`·`tool`이 있고 설정 모양이
    `{type: sdk, name, instance}`다."""

    @tool("t", "d", {"type": "object", "properties": {}})
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": []}

    config = create_sdk_mcp_server(name="s", tools=[handler])
    assert config["type"] == "sdk"
    assert config["name"] == "s"
    assert config["instance"] is not None


def _host(name: str = "delegate", handler: Any = None, calls: list[Any] | None = None) -> HostTool:
    async def default(args: dict[str, Any]) -> HostToolResult:
        if calls is not None:
            calls.append(args)
        return HostToolResult(text=f"{args['target']} 결과: {args['task']}")

    return HostTool(
        name=name,
        description="다른 에이전트에게 맡긴다",
        input_schema=SCHEMA,
        handler=handler or default,
    )


def _agent(**options: Any) -> Agent:
    return Agent(
        id="lead", name="Lead", backend="claude-agent-sdk", tools=["Read"], backend_options=options
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


def _script(call: SdkToolCall, rule: str) -> list[Any]:
    return [
        SystemMessage(
            subtype="init",
            data={
                "session_id": "s1",
                "mcp_servers": [{"name": call.server, "status": "connected"}],
            },
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="tu1", name=rule, input=call.arguments)], model="m"
        ),
        call,
        UserMessage(content=[ToolResultBlock(tool_use_id="tu1", content="r", is_error=False)]),
        _result(),
    ]


def _factory(
    script: list[Any], **kw: Any
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def make(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script, **kw)
        clients.append(client)
        return client

    return clients, make


def test_descriptor_declares_host_tools() -> None:
    assert ClaudeSdkBackend(environ={}).descriptor.capabilities.host_tools is True


def test_server_name_is_option_schema_default() -> None:
    schema = ClaudeSdkBackendOptions.model_json_schema()
    assert schema["properties"]["host_tool_server"]["default"] == DEFAULT_HOST_TOOL_SERVER
    with pytest.raises(ValueError, match="__"):
        ClaudeSdkBackendOptions(host_tool_server="a__b")


async def test_options_add_server_and_preapprove_rule() -> None:
    calls: list[Any] = []
    call = SdkToolCall(
        server="platform", tool="delegate", arguments={"target": "reviewer", "task": "검토"}
    )
    rule = host_tool_rule("platform", "delegate")
    clients, make = _factory(_script(call, rule))
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    sink = ValidatingSink()
    result = await backend.run(
        AgentRequest(
            agent=_agent(host_tool_server="platform"),
            prompt="p",
            host_tools=[_host(calls=calls)],
        ),
        sink,
        CancelToken(),
    )
    assert result.status == "succeeded"
    options = clients[0].options
    assert rule == "mcp__platform__delegate"
    assert rule in (options.allowed_tools or [])
    assert options.mcp_servers["platform"]["type"] == "sdk"
    # 핸들러가 모델 입력 그대로 불렸고 결과가 MCP 도구 결과로 돌아갔다.
    assert calls == [{"target": "reviewer", "task": "검토"}]
    assert call.results == [
        {"content": [{"type": "text", "text": "reviewer 결과: 검토"}], "isError": False}
    ]


async def test_no_host_tools_means_no_server() -> None:
    clients, make = _factory([_result()])
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    await backend.run(AgentRequest(agent=_agent(), prompt="p"), ValidatingSink(), CancelToken())
    options = clients[0].options
    assert DEFAULT_HOST_TOOL_SERVER not in options.mcp_servers
    assert not any(r.startswith("mcp__") for r in options.allowed_tools or [])


async def test_handler_error_and_schema_rejection_are_error_results() -> None:
    async def failing(args: dict[str, Any]) -> HostToolResult:
        return HostToolResult(text="대상 실패", is_error=True)

    async def raising(args: dict[str, Any]) -> HostToolResult:
        raise RuntimeError("sk-secret")

    mapping = build_host_tool_server(
        [_host("fail", failing), _host("boom", raising), _host("ok")], server="p"
    )
    assert mapping is not None
    fail = await call_sdk_mcp_tool(mapping.config, "fail", {"target": "writer", "task": "x"})
    assert fail["isError"] is True
    assert fail["content"][0]["text"] == "대상 실패"
    boom = await call_sdk_mcp_tool(mapping.config, "boom", {"target": "writer", "task": "x"})
    assert boom["isError"] is True
    assert "RuntimeError" in boom["content"][0]["text"]
    assert "sk-secret" not in boom["content"][0]["text"]
    # 대상 값 목록(enum) 밖이면 SDK가 핸들러 전에 거부한다.
    bad = await call_sdk_mcp_tool(mapping.config, "ok", {"target": "nobody", "task": "x"})
    assert bad["isError"] is True


async def test_cancel_stops_running_handler() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def slow(args: dict[str, Any]) -> HostToolResult:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return HostToolResult(text="never")

    call = SdkToolCall(
        server=DEFAULT_HOST_TOOL_SERVER,
        tool="delegate",
        arguments={"target": "writer", "task": "t"},
    )
    _clients, make = _factory(
        _script(call, host_tool_rule(DEFAULT_HOST_TOOL_SERVER, "delegate"))[:-1], block=True
    )
    backend = ClaudeSdkBackend(client_factory=make, environ={}, cancel_grace=2)
    cancel = CancelToken()
    run = asyncio.ensure_future(
        backend.run(
            AgentRequest(agent=_agent(), prompt="p", host_tools=[_host(handler=slow)]),
            ValidatingSink(),
            cancel,
        )
    )
    await asyncio.wait_for(started.wait(), 5)
    cancel.cancel()
    result = await asyncio.wait_for(run, 10)
    assert result.status == "cancelled"
    assert stopped.is_set()
    assert call.results[0]["isError"] is True


async def test_tool_call_recorded_by_mcp_calls_collector() -> None:
    call = SdkToolCall(
        server=DEFAULT_HOST_TOOL_SERVER,
        tool="delegate",
        arguments={"target": "reviewer", "task": "검토"},
    )
    clock = iter(float(i) for i in range(100))
    _clients, make = _factory(_script(call, host_tool_rule(DEFAULT_HOST_TOOL_SERVER, "delegate")))
    backend = ClaudeSdkBackend(client_factory=make, environ={}, clock=lambda: next(clock))
    sink = ValidatingSink()
    result = await backend.run(
        AgentRequest(
            agent=_agent(),
            prompt="p",
            host_tools=[_host()],
            observe={"collectors": {"mcp-calls": {"enabled": True}}},
        ),
        sink,
        CancelToken(),
    )
    assert result.status == "succeeded"
    mcp = [(e.type, dict(e.payload)) for e in sink.events if e.type.startswith("mcp.")]
    types = [t for t, _ in mcp]
    assert types == ["mcp.server_status", "mcp.call_started", "mcp.call_completed"]
    started = mcp[1][1]
    assert started["server"] == DEFAULT_HOST_TOOL_SERVER
    assert started["tool"] == "delegate"
    assert mcp[2][1]["is_error"] is False
    tool_calls = [dict(e.payload) for e in sink.events if e.type == "agent.tool_call"]
    assert tool_calls[0]["name"] == "mcp__agent-console__delegate"


@pytest.mark.parametrize(
    ("tools", "options", "message"),
    [
        ([_host("a"), _host("a")], {}, "겹칩니다"),
        ([_host("a b")], {}, "영문"),
        ([_host()], {"mcp_servers": {DEFAULT_HOST_TOOL_SERVER: {"type": "stdio"}}}, "서버 이름"),
    ],
)
async def test_invalid_host_tools_fail_before_sdk(
    tools: list[HostTool], options: dict[str, Any], message: str
) -> None:
    clients, make = _factory([_result()])
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    result = await backend.run(
        AgentRequest(agent=_agent(**options), prompt="p", host_tools=tools),
        ValidatingSink(),
        CancelToken(),
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == ClaudeSdkErrorCodes.INVALID_OPTIONS
    assert message in result.error.message
    assert clients == []


async def test_disallowed_rule_is_not_preapproved() -> None:
    rule = host_tool_rule(DEFAULT_HOST_TOOL_SERVER, "delegate")
    clients, make = _factory([_result()])
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    await backend.run(
        AgentRequest(agent=_agent(disallowed_tools=[rule]), prompt="p", host_tools=[_host()]),
        ValidatingSink(),
        CancelToken(),
    )
    assert rule not in (clients[0].options.allowed_tools or [])


async def test_long_name_and_sdk_override_warn() -> None:
    _clients, make = _factory([_result()])
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    sink = ValidatingSink()
    await backend.run(
        AgentRequest(
            agent=_agent(sdk_options={"allowed_tools": ["Read"]}),
            prompt="p",
            host_tools=[_host("x" * 60)],
        ),
        sink,
        CancelToken(),
    )
    warnings = [dict(e.payload) for e in sink.events if e.type == "log.warning"]
    options = {w["details"].get("option") for w in warnings}
    assert {"host_tool_server", "sdk_options"} <= options
