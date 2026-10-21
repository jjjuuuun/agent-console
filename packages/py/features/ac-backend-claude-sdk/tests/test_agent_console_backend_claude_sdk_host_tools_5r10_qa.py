"""5R.10 QA 보강: 도구 이름 주입 거부, 예외 메시지·핸들러가 이벤트·직렬화에 새지 않음."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agent_console_backend_claude_sdk import ClaudeSdkBackend, build_host_tool_server
from agent_console_backend_claude_sdk.testing import SdkToolCall, ValidatingSink
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken, HostToolResult

_spec = importlib.util.spec_from_file_location(
    "_host_tools_5r10_helpers",
    Path(__file__).with_name("test_agent_console_backend_claude_sdk_host_tools_5r10.py"),
)
assert _spec is not None
assert _spec.loader is not None
_h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h)
DEFAULT_HOST_TOOL_SERVER = _h.DEFAULT_HOST_TOOL_SERVER
_agent, _factory, _host, _script, host_tool_rule = (
    _h._agent,
    _h._factory,
    _h._host,
    _h._script,
    _h.host_tool_rule,
)

SECRET = "sk-ant-SECRET-VALUE"


@pytest.mark.parametrize(
    "name", ["a b", "a/b", "a.b", "a*", "mcp__x__y ", "a\nb", "도구", "", "a:b", "a,b"]
)
def test_bad_tool_names_rejected(name: str) -> None:
    with pytest.raises(ValueError, match=r".+"):
        build_host_tool_server([_host(name)], server="s")


def test_double_underscore_tool_name_cannot_spoof_server() -> None:
    mapping = build_host_tool_server([_host("evil__x")], server="agent-console")
    assert mapping is not None
    assert mapping.rules == ["mcp__agent-console__evil__x"]


async def test_handler_exception_message_and_handler_do_not_leak() -> None:
    async def boom(args: dict[str, Any]) -> HostToolResult:
        raise RuntimeError(f"token {SECRET}")

    call = SdkToolCall(
        server=DEFAULT_HOST_TOOL_SERVER,
        tool="delegate",
        arguments={"target": "writer", "task": "t"},
    )
    _c, make = _factory(_script(call, host_tool_rule(DEFAULT_HOST_TOOL_SERVER, "delegate")))
    backend = ClaudeSdkBackend(client_factory=make, environ={})
    sink = ValidatingSink()
    req = AgentRequest(
        agent=Agent(id="l", name="L", backend="claude-agent-sdk", tools=["Read"]),
        prompt="p",
        host_tools=[_host(handler=boom)],
        observe={"collectors": {"mcp-calls": {"enabled": True}}},
    )
    dumped = json.dumps(req.model_dump(mode="json"), default=str)
    assert "handler" not in dumped
    assert "delegate" not in dumped
    await backend.run(req, sink, CancelToken())
    blob = json.dumps(
        [(e.type, dict(e.payload)) for e in sink.events], default=str, ensure_ascii=False
    )
    assert SECRET not in blob
    assert "function" not in blob
    assert "0x" not in blob
    assert "RuntimeError" in json.dumps(call.results, ensure_ascii=False)
    assert SECRET not in json.dumps(call.results, ensure_ascii=False)
