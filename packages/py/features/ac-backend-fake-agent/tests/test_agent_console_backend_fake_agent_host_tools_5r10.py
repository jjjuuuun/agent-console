"""FakeBackend 5R.10: 규칙 `host_tool_calls`(플랫폼 도구 호출 흉내, 결정적)."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_console_backend_fake_agent import FakeBackend, FakeBackendOptions, HostCallStatus
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken, HostTool, HostToolResult


def _agent(**options: Any) -> Agent:
    return Agent(id="lead", name="Lead", backend="fake-agent", backend_options=options)


def _host(name: str, replies: dict[str, HostToolResult], calls: list[Any]) -> HostTool:
    async def handler(args: dict[str, Any]) -> HostToolResult:
        calls.append((name, args))
        return replies.get(str(args.get("target")), HostToolResult(text="?", is_error=True))

    return HostTool(name=name, description="위임", input_schema={}, handler=handler)


async def _run(
    options: dict[str, Any], tools: list[HostTool], cancel: CancelToken | None = None
) -> tuple[Any, ValidatingSink]:
    sink = ValidatingSink()
    result = await FakeBackend(ids=lambda: "s1").run(
        AgentRequest(agent=_agent(**options), prompt="기능 만들기", host_tools=tools),
        sink,
        cancel or CancelToken(),
    )
    return result, sink


def test_descriptor_and_schema() -> None:
    assert FakeBackend().descriptor.capabilities.host_tools is True
    schema = FakeBackendOptions.model_json_schema()
    assert "host_tool_calls" in schema["$defs"]["FakeRule"]["properties"]


async def test_calls_tools_in_order_and_appends_results() -> None:
    calls: list[Any] = []
    tool = _host(
        "delegate",
        {
            "writer": HostToolResult(text="초안 완료"),
            "reviewer": HostToolResult(text="승인"),
        },
        calls,
    )
    options = {
        "default": {
            "response": "정리: $host_1 / $host_2 ($host_2_status)",
            "host_tool_calls": [
                {"tool": "delegate", "input": {"target": "writer", "task": "$prompt"}},
                {
                    "tool": "delegate",
                    "input": {"target": "reviewer", "task": "$host_1"},
                    "append": False,
                },
            ],
        }
    }
    result, sink = await _run(options, [tool])
    assert result.status == "succeeded"
    assert calls == [
        ("delegate", {"target": "writer", "task": "기능 만들기"}),
        ("delegate", {"target": "reviewer", "task": "초안 완료"}),
    ]
    assert result.text == "정리: 초안 완료 / 승인 (succeeded)\n\n초안 완료"
    pairs = [
        (e.type, dict(e.payload).get("name"), dict(e.payload).get("is_error"))
        for e in sink.events
        if e.type in {"agent.tool_call", "agent.tool_result"}
    ]
    assert pairs == [
        ("agent.tool_call", "delegate", None),
        ("agent.tool_result", None, False),
        ("agent.tool_call", "delegate", None),
        ("agent.tool_result", None, False),
    ]
    # 결정적: 같은 요청 → 같은 결과.
    again, _ = await _run(options, [_host("delegate", {}, [])])
    assert again.text == (await _run(options, [_host("delegate", {}, [])]))[0].text


async def test_when_uses_previous_result() -> None:
    calls: list[Any] = []
    tool = _host(
        "delegate",
        {"reviewer": HostToolResult(text="반려: 테스트 없음"), "writer": HostToolResult("고침")},
        calls,
    )
    options = {
        "default": {
            "response": "$host_2_status/$host_3_status",
            "host_tool_calls": [
                {"tool": "delegate", "input": {"target": "reviewer"}, "append": False},
                {
                    "tool": "delegate",
                    "input": {"target": "writer"},
                    "when": {"contains": "반려"},
                    "append": False,
                },
                {
                    "tool": "delegate",
                    "input": {"target": "writer"},
                    "when": {"after": 1, "contains": "승인"},
                },
            ],
        }
    }
    result, _ = await _run(options, [tool])
    assert [args["target"] for _, args in calls] == ["reviewer", "writer"]
    assert result.text == f"{HostCallStatus.SUCCEEDED}/{HostCallStatus.SKIPPED}"


async def test_unknown_tool_and_error_result() -> None:
    calls: list[Any] = []
    options = {
        "default": {
            "response": "$host_1_status $host_2_status",
            "host_tool_calls": [
                {"tool": "missing", "append": False},
                {"tool": "delegate", "input": {"target": "nobody"}, "append": False},
                {"tool": "delegate", "when": {"is_error": True}, "input": {"target": "x"}},
            ],
        }
    }
    result, sink = await _run(options, [_host("delegate", {}, calls)])
    assert result.status == "succeeded"
    assert result.text.startswith("failed failed")
    errors = [dict(e.payload)["is_error"] for e in sink.events if e.type == "agent.tool_result"]
    assert errors == [True, True, True]
    assert len(calls) == 2


async def test_cancel_during_tool_call() -> None:
    started = asyncio.Event()

    async def slow(args: dict[str, Any]) -> HostToolResult:
        started.set()
        await asyncio.Event().wait()
        return HostToolResult(text="never")

    tool = HostTool(name="delegate", description="", input_schema={}, handler=slow)
    cancel = CancelToken()
    run = asyncio.ensure_future(
        _run({"default": {"host_tool_calls": [{"tool": "delegate"}]}}, [tool], cancel)
    )
    await asyncio.wait_for(started.wait(), 5)
    cancel.cancel()
    result, sink = await asyncio.wait_for(run, 5)
    assert result.status == "cancelled"
    assert not [e for e in sink.events if e.type == "agent.tool_result"]
