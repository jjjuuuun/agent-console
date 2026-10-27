"""5.5R.7 C2: SDK 결과의 API 시간(`duration_api_ms`)이 마지막 `agent.usage.duration_ms`로 실린다."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import ResultMessage
from pydantic import BaseModel

from agent_console_backend_claude_sdk import MessageTranslator


def _duration(payload: Any) -> Any:
    assert isinstance(payload, BaseModel)
    return payload.model_dump()["duration_ms"]


def _result(**kw: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 900,
        "duration_api_ms": 640,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s",
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }
    base.update(kw)
    return ResultMessage(**base)


def test_result_usage_carries_api_duration() -> None:
    [emission] = MessageTranslator(backend_id="claude-agent-sdk").translate(_result())
    assert emission.type == "agent.usage"
    assert _duration(emission.payload) == 640


def test_unknown_or_negative_duration_is_null() -> None:
    for value in (-1, None):
        msg = _result()
        msg.duration_api_ms = value  # type: ignore[assignment]
        [emission] = MessageTranslator(backend_id="claude-agent-sdk").translate(msg)
        assert _duration(emission.payload) is None
