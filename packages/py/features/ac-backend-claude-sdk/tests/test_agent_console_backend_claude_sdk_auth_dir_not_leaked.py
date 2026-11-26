"""앱 전용 자격 폴더(``CLAUDE_CONFIG_DIR``)의 위치는 하위 프로세스 환경으로만 간다(K33-11).

위임자 + 하위 에이전트(같은 세션 위임) 실행에서 자격 폴더 경로가 SDK 옵션의 환경 변수에만 있고,
백엔드가 낸 이벤트(``sink``)·실행 결과·요청 어디에도 실리지 않는다. 실행 엔진이 이벤트를 그대로
기록하므로 이벤트에 없으면 실행 기록에도 없다. 가짜 SDK 클라이언트만 쓴다(실제 CLI·SDK 호출 없음).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_console_backend_claude_sdk import ClaudeSdkBackend
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
from agent_console_contracts import Agent
from agent_console_runtime import AgentRequest, CancelToken, SubagentSpec

MARKER = "creds-zq7x"
"""자격 폴더 이름(경로 어느 형태로 새어도 이 글자는 남는다)."""

SESSION = "sess-1"


@pytest.fixture(autouse=True)
def _no_server_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def _script(cwd: str) -> list[Any]:
    """init → 하위 에이전트 위임(Agent 도구) → 하위 에이전트 메시지 → 결과."""
    return [
        SystemMessage(
            subtype="init",
            data={"session_id": SESSION, "model": "m", "cwd": cwd, "tools": ["Read", "Agent"]},
        ),
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="toolu_agent",
                    name="Agent",
                    input={"subagent_type": "reviewer", "description": "d", "prompt": "review"},
                )
            ],
            model="m",
            message_id="msg_lead",
            usage={"input_tokens": 10, "output_tokens": 3},
        ),
        TaskStartedMessage(
            subtype="task_started",
            data={},
            task_id="task-1",
            description="d",
            uuid="u1",
            session_id=SESSION,
            tool_use_id="toolu_agent",
            task_type="local_agent",
        ),
        AssistantMessage(
            content=[
                TextBlock("reading"),
                ToolUseBlock(id="toolu_read", name="Read", input={"file_path": f"{cwd}/a.py"}),
            ],
            model="m",
            parent_tool_use_id="toolu_agent",
            message_id="msg_sub",
            usage={"input_tokens": 5, "output_tokens": 2},
        ),
        UserMessage(
            content=[ToolResultBlock(tool_use_id="toolu_read", content="code", is_error=False)],
            parent_tool_use_id="toolu_agent",
        ),
        TaskNotificationMessage(
            subtype="task_notification",
            data={},
            task_id="task-1",
            status="completed",
            output_file="",
            summary="ok",
            uuid="u2",
            session_id=SESSION,
            tool_use_id="toolu_agent",
            usage={"total_tokens": 7, "tool_uses": 1, "duration_ms": 10},
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="toolu_agent",
                    content=[{"type": "text", "text": "LGTM"}],
                    is_error=False,
                )
            ]
        ),
        AssistantMessage(content=[TextBlock("done")], model="m", message_id="msg_final"),
        ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=8,
            is_error=False,
            num_turns=2,
            session_id=SESSION,
            result="done",
            usage={"input_tokens": 15, "output_tokens": 5},
        ),
    ]


def _capture(script: list[Any]) -> tuple[list[FakeSdkClient], Callable[[Any], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script)
        clients.append(client)
        return client

    return clients, factory


def _needles(path: Path) -> list[str]:
    """경로가 새었다고 볼 글자들(이름·절대 경로·POSIX 형태·실제 경로)."""
    return sorted({MARKER, str(path), path.as_posix(), str(path.resolve())})


@pytest.mark.parametrize("override", [False, True], ids=["plain", "agent-env-override"])
async def test_auth_dir_reaches_only_subprocess_env(tmp_path: Path, override: bool) -> None:
    workspace = tmp_path / "app-data"
    workspace.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    auth_dir = workspace / MARKER
    env = {"CLAUDE_CONFIG_DIR": "/elsewhere"} if override else {}
    agent = Agent(
        id="lead",
        name="Lead",
        model="m",
        backend="claude-agent-sdk",
        backend_options={"env": env} if env else {},
    )
    request = AgentRequest(
        agent=agent,
        prompt="p",
        cwd=str(project),
        subagents=[SubagentSpec(name="reviewer", description="review", prompt="you review")],
        run_folder=str(tmp_path / "runs" / "r1" / "lead"),
        run_context={"run_id": "r1", "node_path": "lead"},
    )
    clients, factory = _capture(_script(str(project)))
    backend = ClaudeSdkBackend(
        client_factory=factory,
        environ={"HOME": str(tmp_path / "no-home")},
        workspace=workspace,
        auth_dir={"config_dir": MARKER},
    )
    sink = ValidatingSink()
    result = await backend.run(request, sink, CancelToken())
    assert result.status == "succeeded", result.error

    # 자격 폴더는 SDK 하위 프로세스 환경으로만 간다
    [client] = clients
    assert client.options.env["CLAUDE_CONFIG_DIR"] == str(auth_dir)
    assert set(client.options.agents or {}) == {"reviewer"}  # 위임이 실제로 일어난 실행

    events = [e.model_dump(mode="json") for e in sink.events]
    types = [e["type"] for e in events]
    assert {"agent.subagent_started", "agent.subagent_stopped"} <= set(types), types
    assert any(e.get("node_path", [])[-1:] == ["reviewer"] for e in events)  # 하위 에이전트 이벤트
    if override:  # 덮어쓴 사실은 알리되 위치는 싣지 않는다
        assert any(e["type"] == "log.warning" and "env" in str(e["payload"]) for e in events)
    for where, blob in (
        ("백엔드 이벤트", json.dumps(events, ensure_ascii=False, default=str)),
        ("실행 결과", result.model_dump_json()),
        ("백엔드 요청", request.model_dump_json()),
    ):
        for needle in _needles(auth_dir):
            assert needle not in blob, (where, needle)
