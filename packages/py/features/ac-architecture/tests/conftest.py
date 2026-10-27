"""공용 재료: 테스트 전용 프로필(`testing.demo_profile()`)과 이벤트 묶음."""

from __future__ import annotations

import pytest

from agent_console_architecture import parse_profiles_document
from agent_console_architecture.testing import demo_profile as demo_profile_document
from agent_console_architecture.testing import make_events
from agent_console_conditions import ConditionOperator, default_operators
from agent_console_contracts.architecture import ArchitectureProfile
from agent_console_contracts.logs import LogEvent, TokenSample


@pytest.fixture
def source_kinds() -> dict[str, str]:
    return {"a1": "kind-a", "b1": "kind-b"}


@pytest.fixture(scope="session")
def operators() -> dict[str, ConditionOperator]:
    found, _reports = default_operators()
    return found


@pytest.fixture
def demo_profile() -> ArchitectureProfile:
    return parse_profiles_document(demo_profile_document())["demo"]


@pytest.fixture
def demo_events() -> list[LogEvent]:
    main = {"thread": "main", "source": "a1"}
    return make_events(
        [
            {**main, "category": "input", "time": 9.5},
            {**main, "category": "llm", "model": "m1", "message_id": "r1", "time": 10.0},
            {**main, "category": "llm", "model": "m1", "message_id": "r1", "time": 10.1},
            {
                **main,
                "category": "tool",
                "tool": "Read",
                "call_id": "c1",
                "time": 11.0,
                "tags": ["tool", "tool_call"],
            },
            {
                **main,
                "category": "tool",
                "tool": "Read",
                "call_id": "c1",
                "time": 11.2,
                "tags": ["tool", "tool_result"],
                "duration_ms": 120.0,
                "status": "ok",
            },
            {
                "thread": "main",
                "source": "b1",
                "category": "tool",
                "tool": "Read",
                "call_id": "c1",
                "time": 11.2,
                "tags": ["tool", "tool_result"],
                "duration_ms": 130.0,
            },
            {
                **main,
                "category": "tool",
                "tool": "Grep",
                "call_id": "c2",
                "time": 12.0,
                "tags": ["tool", "tool_call"],
                "status": "failed",
            },
            {
                "thread": "sub1",
                "source": "a1",
                "category": "llm",
                "model": "m2",
                "message_id": "r2",
                "time": 20.0,
                "status": "error",
            },
            {**main, "category": "agent", "time": 21.0},
            {
                **main,
                "category": "tool",
                "tool": "Write",
                "call_id": "c3",
                "time": 22.0,
                "tags": ["tool", "tool_call"],
            },
        ]
    )


@pytest.fixture
def demo_tokens() -> list[TokenSample]:
    return [
        TokenSample(thread="main", message_id="r1", input_tokens=10, output_tokens=5),
        TokenSample(thread="main", message_id="r1", input_tokens=10, output_tokens=3),
        TokenSample(thread="sub1", message_id="r2", output_tokens=7),
        TokenSample(thread="main", message_id="zz", output_tokens=1000),
    ]
