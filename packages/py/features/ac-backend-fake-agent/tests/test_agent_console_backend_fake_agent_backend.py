"""FakeBackend: 규칙 데이터 → 결정적 이벤트·결과, 지연·실패·취소, entry point 등록."""

from __future__ import annotations

import asyncio
from importlib.metadata import entry_points
from typing import Any

import pytest

from agent_console_backend_fake_agent import FakeBackend, FakeBackendOptions
from agent_console_backend_fake_agent.testing import ValidatingSink
from agent_console_contracts import Agent, ModelInfo
from agent_console_runtime import (
    BACKENDS_GROUP,
    AgentRequest,
    CancelToken,
    ExecutionBackend,
    Registries,
    SessionRef,
    load_registries,
)


def _agent(**options: Any) -> Agent:
    return Agent(
        id="a1", name="에이전트", model="m-test", backend="fake-agent", backend_options=options
    )


def _backend() -> FakeBackend:
    return FakeBackend(ids=lambda: "s1")


async def test_default_rule_echoes_prompt_as_streamed_deltas() -> None:
    sink = ValidatingSink()
    req = AgentRequest(agent=_agent(chunk_chars=4), prompt="hello world")
    result = await _backend().run(req, sink, CancelToken())

    assert result.status == "succeeded"
    assert result.text == "hello world"
    assert result.session is not None
    assert result.session.session_id == "s1"
    assert sink.types == [
        "agent.session_started",
        "agent.text_delta",
        "agent.text_delta",
        "agent.text_delta",
        "agent.message",
        "agent.usage",
    ]
    assert "".join(p["text"] for p in sink.of("agent.text_delta")) == "hello world"
    assert sink.of("agent.session_started")[0] == {
        "session_id": "s1",
        "backend": "fake-agent",
        "model": "m-test",
    }
    assert sink.of("agent.usage")[0]["usage"]["input_tokens"] == 2


async def test_rules_are_data_first_match_wins_with_template() -> None:
    sink = ValidatingSink()
    options = {
        "rules": [
            {"contains": "SPEC", "response": "spec for $agent_name: $prompt"},
            {"prefix": "fix", "response": "never"},
        ],
        "default": {"response": "fallback"},
    }
    req = AgentRequest(agent=_agent(**options), prompt="write a spec, then fix")
    result = await _backend().run(req, sink, CancelToken())
    assert result.text == "spec for 에이전트: write a spec, then fix"

    other = await _backend().run(
        AgentRequest(agent=_agent(**options), prompt="nothing"), sink, CancelToken()
    )
    assert other.text == "fallback"


async def test_same_request_gives_same_events() -> None:
    sink = ValidatingSink()
    req = AgentRequest(agent=_agent(), prompt="deterministic")
    await _backend().run(req, sink, CancelToken())
    first = [(e.type, e.payload) for e in sink.events]
    sink.events.clear()
    await _backend().run(req, sink, CancelToken())
    assert [(e.type, e.payload) for e in sink.events] == first


async def test_tool_calls_structured_and_usage_from_rule() -> None:
    sink = ValidatingSink()
    options = {
        "default": {
            "response": "done",
            "structured": {"ok": True},
            "tool_calls": [{"name": "Read", "input": {"path": "x"}, "output": "contents"}],
            "usage": {"input_tokens": 7, "output_tokens": 3, "cost_usd": 0.5},
        }
    }
    result = await _backend().run(
        AgentRequest(agent=_agent(**options), prompt="p"), sink, CancelToken()
    )
    assert result.structured == {"ok": True}
    assert result.usage.input_tokens == 7
    assert result.usage.cost_usd == 0.5
    call = sink.of("agent.tool_call")[0]
    assert call["name"] == "Read"
    assert sink.of("agent.tool_result")[0] == {
        "tool_use_id": call["tool_use_id"],
        "is_error": False,
        "output_preview": "contents",
    }


async def test_failure_after_chunks() -> None:
    sink = ValidatingSink()
    options = {
        "chunk_chars": 2,
        "default": {"response": "abcdef", "fail": {"code": "boom", "after_chunks": 1}},
    }
    result = await _backend().run(
        AgentRequest(agent=_agent(**options), prompt="p"), sink, CancelToken()
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "boom"
    assert result.text == "ab"
    assert "agent.message" not in sink.types


async def test_invalid_options_return_failed_result() -> None:
    sink = ValidatingSink()
    result = await _backend().run(
        AgentRequest(agent=_agent(unknown_key=1), prompt="p"), sink, CancelToken()
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert sink.events == []


async def test_cancel_during_delay_returns_cancelled() -> None:
    sink = ValidatingSink()
    cancel = CancelToken()
    req = AgentRequest(agent=_agent(chunk_chars=1, delay_ms=50), prompt="slow text")
    task = asyncio.create_task(_backend().run(req, sink, cancel))
    await asyncio.sleep(0.12)
    cancel.cancel()
    result = await asyncio.wait_for(task, 1)
    assert result.status == "cancelled"
    assert 0 < len(result.text) < len("slow text")


async def test_resume_reuses_session_id() -> None:
    sink = ValidatingSink()
    req = AgentRequest(
        agent=_agent(), prompt="p", session=SessionRef(backend="fake-agent", session_id="prev")
    )
    result = await _backend().run(req, sink, CancelToken())
    assert result.session is not None
    assert result.session.session_id == "prev"


async def test_list_models_comes_from_injected_data() -> None:
    assert await FakeBackend().list_models() == []
    backend = FakeBackend(models=[{"id": "m-a", "title": "A"}])
    assert await backend.list_models() == [ModelInfo(id="m-a", title="A")]


def test_descriptor_schema_and_capabilities() -> None:
    descriptor = FakeBackend().descriptor
    assert descriptor.id == "fake-agent"
    assert descriptor.config_schema == FakeBackendOptions.model_json_schema()
    assert descriptor.capabilities.streaming
    assert not descriptor.capabilities.enforce.directories
    assert isinstance(FakeBackend(), ExecutionBackend)


def test_descriptor_is_test_only_and_hidden() -> None:
    """5.2R.105: 이름은 "가짜 에이전트(테스트용)", 사용자 화면에서는 기본 숨김(ui_hints.hidden)."""
    descriptor = FakeBackend().descriptor
    assert descriptor.title == "가짜 에이전트(테스트용)"
    assert descriptor.ui_hints is not None
    assert descriptor.ui_hints.hidden is True
    assert not [ep for ep in entry_points(group=BACKENDS_GROUP) if ep.name == "fake"]


def test_registered_as_entry_point() -> None:
    eps = [ep for ep in entry_points(group=BACKENDS_GROUP) if ep.name == "fake-agent"]
    assert len(eps) == 1
    regs = Registries()
    load_registries(regs, enabled={"fake-agent"}, entry_points=eps)
    assert isinstance(regs.backends.get("fake-agent"), FakeBackend)


@pytest.mark.parametrize(
    ("rule", "prompt", "hit"),
    [
        ({"equals": "Hi"}, "hi", True),
        ({"equals": "Hi", "ignore_case": False}, "hi", False),
        ({"prefix": "a", "contains": "z"}, "abc", False),
        ({}, "anything", True),
    ],
)
def test_rule_matching(rule: dict[str, Any], prompt: str, hit: bool) -> None:
    options = FakeBackendOptions.model_validate({"rules": [{**rule, "response": "R"}]})
    assert (options.pick(prompt).response == "R") is hit


async def test_invalid_option_errors_do_not_echo_input() -> None:
    sink = ValidatingSink()
    secret = "sk-ant-api-NOT-A-REAL-SECRET-123"
    result = await _backend().run(
        AgentRequest(agent=_agent(delay_ms=secret), prompt="p"), sink, CancelToken()
    )
    assert result.error is not None
    assert result.error.code == "validation_failed"
    assert secret not in repr(result.error.model_dump())
    assert "input" not in result.error.details["errors"][0]


async def test_from_options_hook() -> None:
    """`ConfigurableBackend` 훅: 설치자 설정 `models`로 만들고, 모르는 키는 값 없이 거부한다."""
    from agent_console_runtime import ConfigurableBackend, EnvSecretProvider, SecretResolver

    resolver = SecretResolver([EnvSecretProvider({})])
    backend = FakeBackend.from_options(
        {"models": [{"id": "fake-small"}]}, secrets=resolver, environ={}
    )
    assert isinstance(backend, ConfigurableBackend)
    assert isinstance(backend, ExecutionBackend)
    assert [m.id for m in await backend.list_models()] == ["fake-small"]
    with pytest.raises(ValueError, match="unknown") as exc:
        FakeBackend.from_options({"unknown": "hidden-value"}, secrets=resolver, environ={})
    assert "hidden-value" not in str(exc.value)
