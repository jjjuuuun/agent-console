"""fake 규칙 `observe`(2R.5, R8.4): hook·MCP 관측 이벤트 흉내는 데이터, 관측 설정이 켜졌을 때만."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from agent_console_backend_fake_agent import (
    DEFAULT_OBSERVE_SWITCHES,
    FakeBackend,
    FakeBackendOptions,
    FakeObserve,
)
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken

OBSERVE: list[dict[str, Any]] = [
    {
        "type": "hook.invoked",
        "payload": {"event": "PreToolUse", "hook_type": "sdk-callback", "tool_name": "Bash"},
    },
    {
        "type": "mcp.call_started",
        "after": "tool",
        "payload": {"server": "docs", "tool": "lookup", "tool_use_id": "$session_id:tool0"},
    },
    {
        "type": "mcp.call_completed",
        "after": "tool",
        "payload": {
            "server": "docs",
            "tool": "lookup",
            "tool_use_id": "$session_id:tool0",
            "is_error": False,
            "duration_ms": 12,
        },
    },
    {"type": "hook.completed", "after": "end", "payload": {"event": "Stop", "note": "$prompt"}},
]


def _agent(**rule: Any) -> Agent:
    return Agent(
        id="a",
        name="A",
        backend="fake-agent",
        backend_options={
            "default": {
                "response": "ok",
                "tool_calls": [{"name": "mcp__docs__lookup", "input": {"q": "x"}}],
                "observe": OBSERVE,
                **rule,
            }
        },
    )


async def _run(observe: dict[str, Any], agent: Agent | None = None) -> ValidatingSink:
    sink = ValidatingSink()
    req = AgentRequest(agent=agent or _agent(), prompt="go", observe=observe)
    result = await FakeBackend(ids=lambda: "s1").run(req, sink, CancelToken())
    assert result.status == "succeeded"
    return sink


async def test_observe_events_follow_rule_data_and_points() -> None:
    sink = await _run({"hooks": True, "mcp": True})
    assert sink.types == [
        "agent.session_started",
        "hook.invoked",  # start
        "agent.tool_call",
        "agent.tool_result",
        "mcp.call_started",  # tool
        "mcp.call_completed",
        "agent.text_delta",
        "agent.message",
        "hook.completed",  # end: 응답 다음, 사용량 앞
        "agent.usage",
    ]
    assert sink.of("hook.invoked") == [OBSERVE[0]["payload"]]
    started = sink.of("mcp.call_started")[0]
    assert started["tool_use_id"] == sink.of("agent.tool_call")[0]["tool_use_id"] == "s1:tool0"
    assert sink.of("hook.completed") == [{"event": "Stop", "note": "go"}]  # 템플릿 채움


async def test_observe_is_off_unless_request_switch_is_on() -> None:
    off = await _run({})
    assert not [t for t in off.types if t.startswith(("hook.", "mcp."))]
    false = await _run({"hooks": False, "mcp": False})
    assert not [t for t in false.types if t.startswith(("hook.", "mcp."))]
    hooks_only = await _run({"hooks": True})
    assert [t for t in hooks_only.types if t.startswith(("hook.", "mcp."))] == [
        "hook.invoked",
        "hook.completed",
    ]
    mcp_only = await _run({"mcp": True})
    assert [t for t in mcp_only.types if t.startswith(("hook.", "mcp."))] == [
        "mcp.call_started",
        "mcp.call_completed",
    ]


async def test_other_event_families_need_explicit_switch() -> None:
    with pytest.raises(ValidationError, match="when"):
        FakeObserve.model_validate({"type": "lsp.diagnostics"})
    with pytest.raises(ValidationError):
        FakeObserve.model_validate({"type": "nodot"})
    item = FakeObserve.model_validate({"type": "lsp.diagnostics", "when": "lsp"})
    assert item.switch == "lsp"
    assert DEFAULT_OBSERVE_SWITCHES == {"hook": "hooks", "mcp": "mcp"}
    agent = Agent(
        id="a",
        name="A",
        backend_options={"default": {"observe": [{"type": "lsp.diagnostics", "when": "lsp"}]}},
    )
    sink = await _run({"lsp": True, "hooks": True}, agent)
    assert "lsp.diagnostics" in sink.types
    sink = await _run({"hooks": True}, agent)
    assert "lsp.diagnostics" not in sink.types


async def test_observe_end_runs_on_failure_but_not_on_cancel() -> None:
    failing = _agent(fail={"code": "boom"})
    sink = ValidatingSink()
    req = AgentRequest(agent=failing, prompt="go", observe={"hooks": True})
    result = await FakeBackend().run(req, sink, CancelToken())
    assert result.status == "failed"
    assert sink.types[-2:] == ["hook.completed", "agent.usage"]

    slow = _agent(delay_ms=5000)
    sink = ValidatingSink()
    cancel = CancelToken()
    task = asyncio.create_task(
        FakeBackend().run(
            AgentRequest(agent=slow, prompt="go", observe={"hooks": True}), sink, cancel
        )
    )
    while "hook.invoked" not in sink.types:
        await asyncio.sleep(0.005)
    cancel.cancel()
    assert (await asyncio.wait_for(task, 2)).status == "cancelled"
    assert "hook.completed" not in sink.types


def test_observe_is_in_config_schema() -> None:
    schema = FakeBackendOptions.model_json_schema()
    assert "FakeObserve" in schema["$defs"]
    assert schema["$defs"]["FakeObserve"]["properties"]["after"]["enum"] == [
        "start",
        "tool",
        "end",
    ]
