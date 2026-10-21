"""플랫폼 도구(`HostTool`, design §5R.6) 런타임 타입·공용 부품 테스트(5R.10)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_console_contracts import Agent
from agent_console_runtime import (
    AgentRequest,
    CancelToken,
    HostTool,
    HostToolResult,
    call_host_tool,
    duplicate_host_tool_names,
    object_input_schema,
)


def _tool(name: str = "delegate", handler: Any = None) -> HostTool:
    async def echo(args: dict[str, Any]) -> HostToolResult:
        return HostToolResult(text=f"got {args.get('task')}")

    return HostTool(
        name=name,
        description="위임",
        input_schema={"type": "object", "properties": {"task": {"type": "string"}}},
        handler=handler or echo,
    )


def test_agent_request_keeps_host_tools_runtime_only() -> None:
    tool = _tool()
    req = AgentRequest(agent=Agent(id="a", name="a"), prompt="p", host_tools=[tool])
    assert req.host_tools[0] is tool
    assert "host_tools" not in req.model_dump()
    assert "host_tools" not in req.model_dump_json()
    assert req.model_copy(update={"prompt": "q"}).host_tools[0] is tool
    assert AgentRequest(agent=Agent(id="a", name="a"), prompt="p").host_tools == []


async def test_call_host_tool_runs_handler() -> None:
    result = await call_host_tool(_tool(), {"task": "x"})
    assert result == HostToolResult(text="got x")


async def test_call_host_tool_turns_exception_into_error_without_message() -> None:
    async def boom(args: dict[str, Any]) -> HostToolResult:
        raise RuntimeError("secret-value-123")

    result = await call_host_tool(_tool(handler=boom), {})
    assert result.is_error
    assert "RuntimeError" in result.text
    assert "secret-value-123" not in result.text


async def test_call_host_tool_rejects_wrong_return_type() -> None:
    async def wrong(args: dict[str, Any]) -> Any:
        return "text"

    result = await call_host_tool(_tool(handler=wrong), {}, error_template="E:{tool}:{error}")
    assert result == HostToolResult(text="E:delegate:str", is_error=True)


async def test_call_host_tool_cancel_token_stops_handler() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def slow(args: dict[str, Any]) -> HostToolResult:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return HostToolResult(text="never")

    cancel = CancelToken()
    call = asyncio.ensure_future(
        call_host_tool(_tool(handler=slow), {}, cancel=cancel, cancelled_text="C:{tool}")
    )
    await started.wait()
    cancel.cancel()
    result = await asyncio.wait_for(call, 2)
    assert result == HostToolResult(text="C:delegate", is_error=True)
    assert stopped.is_set()


async def test_call_host_tool_already_cancelled_skips_handler() -> None:
    calls: list[int] = []

    async def handler(args: dict[str, Any]) -> HostToolResult:
        calls.append(1)
        return HostToolResult(text="x")

    cancel = CancelToken()
    cancel.cancel()
    result = await call_host_tool(_tool(handler=handler), {}, cancel=cancel)
    assert result.is_error
    assert calls == []


async def test_outer_cancellation_propagates_to_handler() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def slow(args: dict[str, Any]) -> HostToolResult:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return HostToolResult(text="never")

    call = asyncio.ensure_future(call_host_tool(_tool(handler=slow), {}, cancel=CancelToken()))
    await started.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert stopped.is_set()


def test_duplicate_names() -> None:
    assert duplicate_host_tool_names([_tool("a"), _tool("b")]) == []
    assert duplicate_host_tool_names([_tool("b"), _tool("a"), _tool("b")]) == ["b"]


def test_object_input_schema_fills_and_checks() -> None:
    assert object_input_schema({}) == {"type": "object", "properties": {}}
    original = {"properties": {"x": {"type": "string"}}, "required": ["x"]}
    filled = object_input_schema(original)
    assert filled["type"] == "object"
    assert "type" not in original
    with pytest.raises(ValueError, match="object"):
        object_input_schema({"type": "string"})
    with pytest.raises(ValueError, match="properties"):
        object_input_schema({"type": "object", "properties": []})
