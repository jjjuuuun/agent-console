"""2R.5(1R.10 QA): 위임 중 취소 때 claude-sdk와 fake의 이벤트 모양이 같다."""

from __future__ import annotations

import asyncio
from typing import Any

from agent_console_backend_claude_sdk.testing import ListeningSink
from agent_console_backend_fake import FakeBackend
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken, SubagentSpec

from .test_agent_console_backend_claude_sdk_v2 import (  # type: ignore[import-not-found]
    _agent,
    _backend,
    _capture,
    _delegate,
    _init,
    _task_started,
)

MEMBERS = [SubagentSpec(name="reviewer", description="d", prompt="p", actor="reviewer-agent")]


async def _cancel_when_started(run: Any, sink: ListeningSink) -> str:
    cancel = CancelToken()
    task = asyncio.create_task(run(sink, cancel))
    while "agent.subagent_started" not in sink.types:
        await asyncio.sleep(0.005)
    cancel.cancel()
    result = await asyncio.wait_for(task, 2)
    return str(result.status)


def _delegation_view(sink: ListeningSink) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """위임 관련 이벤트의 (type, node_path, 값이 있는 payload 키) — id 값은 백엔드마다 다르다."""
    keep = {"agent.tool_call", "agent.tool_result", "agent.subagent_started"}
    keep.add("agent.subagent_stopped")
    out = []
    for e in sink.events:
        if e.type in keep:
            present = tuple(sorted(k for k, v in e.payload.items() if v is not None))
            out.append((e.type, tuple(e.node_path), present))
    return out


async def test_cancel_during_delegation_matches_fake() -> None:
    sdk_sink = ListeningSink(["lead"])
    _, factory = _capture(
        [_init(), _delegate("toolu_agent", "reviewer"), _task_started("task-1", "toolu_agent")],
        block=True,
    )
    req = AgentRequest(agent=_agent(), prompt="p", subagents=MEMBERS)
    sdk_status = await _cancel_when_started(
        lambda sink, cancel: _backend(factory).run(req, sink, cancel), sdk_sink
    )

    fake_sink = ListeningSink(["lead"])
    agent = Agent(
        id="lead",
        name="lead",
        backend_options={"rules": [{"delegate": [{"to": "reviewer", "delay_ms": 5000}]}]},
    )
    fake_req = AgentRequest(agent=agent, prompt="p", subagents=MEMBERS)
    fake_status = await _cancel_when_started(
        lambda sink, cancel: FakeBackend().run(fake_req, sink, cancel), fake_sink
    )

    assert sdk_status == fake_status == "cancelled"
    for sink in (sdk_sink, fake_sink):
        # 위임 도구 결과도, 결과 알림도 없다. 서브에이전트는 stopped로 닫힌다.
        assert "agent.tool_result" not in sink.types
        assert sink.results == []
        assert sink.of("agent.subagent_stopped")[0]["status"] == "stopped"
    sdk_view = [v for v in _delegation_view(sdk_sink) if v[0] != "agent.subagent_started"]
    fake_view = [v for v in _delegation_view(fake_sink) if v[0] != "agent.subagent_started"]
    assert sdk_view == fake_view
