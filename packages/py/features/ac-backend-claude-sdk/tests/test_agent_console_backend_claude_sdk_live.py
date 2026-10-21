"""실제 모델 호출 스모크 테스트(opt-in).

`AGENT_CONSOLE_CLAUDE_SDK_LIVE=1`일 때만 실행한다(API 키가 있어도 이 변수가 없으면 건너뛴다).
모델은 `AGENT_CONSOLE_CLAUDE_SDK_LIVE_MODEL`(없으면 CLI 기본 모델). 인증은 기본 경로인 API 키
방식(`auth.api_key = secret://ANTHROPIC_API_KEY`, 서버 환경 변수에서 해석)이다.

서브에이전트 스모크는 design §R3.1d·§R4.3의 미확인 항목을 관찰해 출력한다(`-s`로 본다):
위임자 사용량에 서브에이전트 토큰이 포함되는지, Task 이벤트·tool_use_id 매핑, 결과 텍스트 모양.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from agent_console_backend_claude_sdk import ClaudeSdkBackend
from agent_console_backend_claude_sdk.testing import (
    InteractiveSink,
    ListeningSink,
    ValidatingSink,
)
from agent_console_contracts import Agent, InteractionGrant, Limits
from agent_console_runtime import (
    AgentRequest,
    CancelToken,
    EnvSecretProvider,
    InteractionRequest,
    SecretResolver,
    SubagentSpec,
)

LIVE = os.environ.get("AGENT_CONSOLE_CLAUDE_SDK_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="실제 모델 호출은 AGENT_CONSOLE_CLAUDE_SDK_LIVE=1일 때만 실행(opt-in)"
)


async def test_live_short_answer(tmp_path: Any) -> None:
    sink = ValidatingSink()
    agent = Agent(
        id="smoke",
        name="smoke",
        model=os.environ.get("AGENT_CONSOLE_CLAUDE_SDK_LIVE_MODEL") or None,
        backend_options={"setting_sources": [], "max_turns": 1},
    )
    req = AgentRequest(agent=agent, prompt="Reply with the single word: pong", cwd=str(tmp_path))
    result = await ClaudeSdkBackend().run(req, sink, CancelToken())
    assert result.status == "succeeded", result.error
    assert "pong" in result.text.lower()
    assert result.session is not None
    assert "agent.session_started" in sink.types
    assert "agent.usage" in sink.types


async def test_live_one_subagent_delegation(tmp_path: Any) -> None:
    sink = ListeningSink(["lead"])
    agent = Agent(
        id="lead",
        name="lead",
        model=os.environ.get("AGENT_CONSOLE_CLAUDE_SDK_LIVE_MODEL") or None,
        system_prompt="You delegate. Always use the echo agent for the user's request, "
        "then reply with exactly what it returned.",
        backend_options={
            "setting_sources": [],
            "max_turns": 4,
            "auth": {"mode": "api_key", "api_key": "secret://ANTHROPIC_API_KEY"},
        },
    )
    req = AgentRequest(
        agent=agent,
        prompt="Use the echo agent to say the single word: pong",
        cwd=str(tmp_path),
        subagents=[
            SubagentSpec(
                name="echo",
                description="Repeats back the requested word. Use for every request.",
                prompt="Reply with only the requested single word.",
                actor="echo-agent",
                tools=[],
            )
        ],
    )
    backend = ClaudeSdkBackend(secrets=SecretResolver([EnvSecretProvider(dict(os.environ))]))
    result = await backend.run(req, sink, CancelToken())
    assert result.status == "succeeded", result.error
    sub = sink.at("lead", "echo")
    print("subagent events:", [(e.type, e.actor) for e in sub])
    print("results:", sink.results)
    print("lead usage:", result.usage)
    print("subagent usage:", sink.of("agent.subagent_stopped"))
    assert "agent.subagent_started" in [e.type for e in sub]
    assert "agent.subagent_stopped" in [e.type for e in sub]
    assert sink.results
    assert sink.results[0]["name"] == "echo"
    assert "pong" in sink.results[0]["text"].lower()


def _live_backend() -> ClaudeSdkBackend:
    return ClaudeSdkBackend(secrets=SecretResolver([EnvSecretProvider(dict(os.environ))]))


def _live_options(**extra: Any) -> dict[str, Any]:
    return {
        "setting_sources": [],
        "max_turns": 4,
        "permission_mode": "default",
        "auth": {"mode": "api_key", "api_key": "secret://ANTHROPIC_API_KEY"},
        **extra,
    }


async def test_live_question_once(tmp_path: Any) -> None:
    """되묻기 1회. §R14.8 미확인: 스트림 유지, 빈 답으로 진행되는 버그 여부."""

    def answer(req: InteractionRequest) -> dict[str, Any]:
        first = req.payload["questions"][0]
        return {"answers": {first["question"]: first["options"][0]["label"]}}

    sink = InteractiveSink(answer)
    agent = Agent(
        id="asker",
        name="asker",
        model=os.environ.get("AGENT_CONSOLE_CLAUDE_SDK_LIVE_MODEL") or None,
        system_prompt="Before answering, ask the user one multiple-choice question with the "
        "AskUserQuestion tool (options: red, blue). Then reply with only the chosen option.",
        backend_options=_live_options(),
    )
    req = AgentRequest(
        agent=agent,
        prompt="Pick a color by asking me.",
        cwd=str(tmp_path),
        interactions=InteractionGrant(kinds=["question"]),
    )
    result = await _live_backend().run(req, sink, CancelToken())
    print("question requests:", [r.payload for r in sink.requests])
    print("result:", result.text)
    assert result.status == "succeeded", result.error
    assert [r.kind for r in sink.requests] == ["question"]
    chosen = sink.requests[0].payload["questions"][0]["options"][0]["label"]
    assert chosen.lower() in result.text.lower()


async def test_live_tool_permission_once(tmp_path: Any) -> None:
    """도구 승인 1회. §R14.8 미확인: 설치 버전의 ToolPermissionContext 필드."""
    sink = InteractiveSink(lambda _req: {"decision": "allow"})
    agent = Agent(
        id="runner",
        name="runner",
        model=os.environ.get("AGENT_CONSOLE_CLAUDE_SDK_LIVE_MODEL") or None,
        tools=["Bash"],
        backend_options=_live_options(allowed_tools=[]),
    )
    req = AgentRequest(
        agent=agent,
        prompt="Run the shell command `echo approved-run` and reply with its output only.",
        cwd=str(tmp_path),
        limits=Limits(commands=["echo"]),
        interactions=InteractionGrant(kinds=["tool_permission"]),
    )
    result = await _live_backend().run(req, sink, CancelToken())
    print("permission payloads:", [r.payload for r in sink.requests])
    print("result:", result.text)
    assert result.status == "succeeded", result.error
    assert [r.kind for r in sink.requests] == ["tool_permission"]
    assert sink.requests[0].payload["tool_name"] == "Bash"
    assert "approved-run" in result.text
