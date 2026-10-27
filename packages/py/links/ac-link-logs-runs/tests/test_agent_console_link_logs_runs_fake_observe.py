"""R8.4: fake 백엔드 observe 규칙의 hook·MCP RunEvent가 범주 hook·mcp와 소요 시간으로 보인다.

fake가 낸 이벤트를 실행 기록에 넣고(시각은 1초 간격으로 다시 찍음) platform-runs 출처로 수집한 뒤
세션 타임라인을 본다.
"""

from __future__ import annotations

from typing import Any

from agent_console_backend_fake_agent import FakeBackend
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent
from agent_console_link_logs_runs.testing import PlatformRunsRig, run_record
from agent_console_logs import query_context
from agent_console_runtime import AgentRequest, CancelToken

OBSERVE: list[dict[str, Any]] = [
    {"type": "hook.invoked", "payload": {"event": "PreToolUse", "hook_type": "sdk-callback"}},
    {
        "type": "hook.finished",
        "after": "tool",
        "payload": {"event": "PreToolUse", "name": "guard", "exit_code": 2, "duration_ms": 25},
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
            "is_error": True,
        },
    },
]


async def _fake_events(observe: dict[str, Any]) -> ValidatingSink:
    agent = Agent(
        id="a",
        name="A",
        backend="fake-agent",
        backend_options={
            "default": {
                "response": "ok",
                "tool_calls": [{"name": "mcp__docs__lookup", "input": {"q": "x"}}],
                "observe": OBSERVE,
            }
        },
    )
    sink = ValidatingSink(("n1",), run_id="r1")
    req = AgentRequest(agent=agent, prompt="go", observe=observe)
    result = await FakeBackend(ids=lambda: "s1").run(req, sink, CancelToken())
    assert result.status == "succeeded"
    return sink


async def _rig(observe: dict[str, Any]) -> PlatformRunsRig:
    sink = await _fake_events(observe)
    rig = PlatformRunsRig()
    rig.records.runs.save(run_record())
    rig.records.events.append(*(e.model_copy(update={"ts": 1000.0 + e.seq}) for e in sink.events))
    report = rig.scan()
    assert report.sources[0].error_code is None
    return rig


async def test_hook_and_mcp_events_show_as_categories_with_durations() -> None:
    rig = await _rig({"hooks": True, "mcp": True})
    timeline = rig.index.timeline("s1", query_context(None))
    assert timeline is not None
    hooks = [e for e in timeline.events if e.category == "hook"]
    mcp = [e for e in timeline.events if e.category == "mcp"]
    finished = [e for e in hooks if e.stage in ("start", "complete")]
    assert [e.stage for e in finished] == ["start", "complete"]
    assert all(e.duration_ms is not None and abs(e.duration_ms - 25) < 1e-6 for e in finished)
    assert finished[1].status == "block"  # exit_code 2 → 대응표 map
    assert finished[0].evidence == "inferred"  # 시작 시각은 소요 시간으로 계산
    assert [h.title for h in hooks if h.stage == "info"] == ["hook PreToolUse"]
    started, completed = mcp
    assert (started.stage, completed.stage, completed.status) == ("start", "complete", "error")
    assert started.tool == completed.tool == "mcp__docs__lookup"
    # 같은 tool_use_id의 도구 호출 시작부터 MCP 완료까지(명시 id 짝, 1초 간격)
    assert completed.duration_ms is not None
    assert completed.duration_ms > 0
    assert completed.correlation == {"session": "s1", "call_id": "s1:tool0"}
    assert {e.session for e in timeline.events} == {"s1"}


async def test_observe_off_means_no_hook_or_mcp_categories() -> None:
    rig = await _rig({})
    timeline = rig.index.timeline("s1", query_context(None))
    assert timeline is not None
    assert not [e for e in timeline.events if e.category in ("hook", "mcp")]
    assert [e for e in timeline.events if e.category == "tool_call"]
