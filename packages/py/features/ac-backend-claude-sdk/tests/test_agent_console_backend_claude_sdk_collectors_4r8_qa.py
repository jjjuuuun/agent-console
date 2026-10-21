"""4R.8 QA: 수집기 이벤트 raw의 비밀 가림, 옛 키 전용 설정의 이벤트 동일성."""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import AssistantMessage, ToolUseBlock

from .test_agent_console_backend_claude_sdk_collectors_4r8 import (  # type: ignore[import-not-found]
    _observed,
    _result,
    _run,
)

SECRET = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWX"


async def test_collected_events_do_not_leak_secrets() -> None:
    script: list[Any] = [
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="t1", name="mcp__wiki__search", input={"q": SECRET, "token": "zzzz1234"}
                )
            ],
            model="m",
        ),
        _result(),
    ]
    sink, _client, result = await _run({"hooks": True, "mcp": True}, script=script)
    assert result.status == "succeeded"
    observed = _observed(sink)
    assert any(t == "mcp.call_started" for t, _, _ in observed)
    blob = json.dumps(observed, default=str)
    assert SECRET not in blob
    assert "zzzz1234" not in blob


async def test_legacy_only_equals_collectors_only() -> None:
    a, _, _ = await _run({"hooks": True, "mcp": True})
    b, _, _ = await _run(
        {"collectors": {"sdk-hooks": {"enabled": True}, "mcp-calls": {"enabled": True}}}
    )
    assert _observed(a) == _observed(b)
    assert _observed(a)
