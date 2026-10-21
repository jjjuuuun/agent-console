"""1R.30: `can_use_tool` ↔ 상호작용(되묻기·도구 승인), grant, 귀속, 검증 훅.

가짜 SDK 클라이언트의 `PermissionCall`로 콜백을 부르고, `InteractiveSink`가 응답한다.
상호작용 종류 디스크립터(1R.29)는 쓰지 않는다 — 백엔드는 요청만 열고 엔진이 종류를 조회한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TaskStartedMessage,
    ToolPermissionContext,
    ToolUseBlock,
)

from agent_console_backend_claude_sdk import ClaudeSdkBackend
from agent_console_backend_claude_sdk.testing import (
    FakeSdkClient,
    InteractiveSink,
    PermissionCall,
    ValidatingSink,
)
from agent_console_contracts import Agent, AgentSettings, InteractionGrant, Limits
from agent_console_runtime import (
    AgentRequest,
    CancelToken,
    EnvSecretProvider,
    InteractionOutcome,
    InteractionRequest,
    SecretResolver,
    SubagentSpec,
)

SECRET = "sk-ant-api-INTERACTIONSECRET0001"
RESOLVER = SecretResolver([EnvSecretProvider({"anthropic_api_key": SECRET})])
BOTH = InteractionGrant(kinds=["question", "tool_permission"])
QUESTION_INPUT = {
    "questions": [
        {
            "question": "어느 DB를 쓸까요?",
            "header": "DB",
            "options": [{"label": "SQLite", "description": "로컬"}, {"label": "Postgres"}],
            "multiSelect": False,
        }
    ]
}


def _agent(**options: Any) -> Agent:
    return Agent(
        id="lead",
        name="Lead",
        model="m",
        tools=["Read", "Bash"],
        backend="claude-agent-sdk",
        backend_options={"permission_mode": "default", **options},
    )


def _init() -> SystemMessage:
    return SystemMessage(subtype="init", data={"session_id": "s", "model": "m"})


def _result() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
        result="ok",
    )


def _capture(
    script: list[Any],
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script)
        clients.append(client)
        return client

    return clients, factory


def _backend(factory: Callable[[ClaudeAgentOptions], Any], **kw: Any) -> ClaudeSdkBackend:
    kw.setdefault("environ", {})
    kw.setdefault("secrets", RESOLVER)
    return ClaudeSdkBackend(client_factory=factory, **kw)


async def _run(
    script: list[Any],
    sink: Any,
    *,
    grant: InteractionGrant | None = BOTH,
    agent: Agent | None = None,
    **req: Any,
) -> list[FakeSdkClient]:
    clients, factory = _capture([_init(), *script, _result()])
    request = AgentRequest(agent=agent or _agent(), prompt="p", interactions=grant, **req)
    result = await _backend(factory).run(request, sink, CancelToken())
    assert result.status == "succeeded", result.error
    return clients


def _ctx(**fields: Any) -> ToolPermissionContext:
    return ToolPermissionContext(**fields)


# ---------------------------------------------------------------- 등록·도구 목록


async def test_question_grant_adds_ask_tool_without_preapproval() -> None:
    clients = await _run([], InteractiveSink())
    opts = clients[0].options
    assert "AskUserQuestion" in opts.tools
    assert "AskUserQuestion" not in opts.allowed_tools  # 콜백을 거쳐야 답이 들어간다
    assert "AskUserQuestion" not in opts.disallowed_tools
    assert opts.can_use_tool is not None


async def test_no_question_grant_disallows_ask_tool() -> None:
    clients = await _run([], InteractiveSink(), grant=InteractionGrant(kinds=["tool_permission"]))
    opts = clients[0].options
    assert "AskUserQuestion" not in opts.tools
    assert "AskUserQuestion" in opts.disallowed_tools


async def test_sink_without_port_cannot_open_and_falls_back_to_unmatched() -> None:
    call = PermissionCall("Read", {"file_path": "x"})
    clients = await _run([call], ValidatingSink())
    assert "AskUserQuestion" in clients[0].options.disallowed_tools
    result = call.results[0]
    assert isinstance(result, PermissionResultDeny)
    assert "unmatched_permission" in result.message


async def test_dont_ask_without_grant_registers_no_callback_but_grant_does() -> None:
    clients = await _run([], InteractiveSink(), grant=None, agent=_agent(permission_mode="dontAsk"))
    assert clients[0].options.can_use_tool is None
    clients = await _run([], InteractiveSink(), agent=_agent(permission_mode="dontAsk"))
    assert clients[0].options.can_use_tool is not None
    bypass = await _run([], InteractiveSink(), agent=_agent(permission_mode="bypassPermissions"))
    assert bypass[0].options.can_use_tool is None


# ---------------------------------------------------------------- 되묻기


async def test_question_round_trip_fills_answers() -> None:
    def answer(req: InteractionRequest) -> dict[str, Any]:
        return {"answers": {"어느 DB를 쓸까요?": "SQLite"}, "response": "로컬로"}

    sink = InteractiveSink(answer)
    call = PermissionCall("AskUserQuestion", QUESTION_INPUT, _ctx(tool_use_id="tq"))
    await _run([call], sink)
    req = sink.requests[0]
    assert req.kind == "question"
    assert req.payload == {
        "questions": [
            {
                "question": "어느 DB를 쓸까요?",
                "header": "DB",
                "options": [{"label": "SQLite", "description": "로컬"}, {"label": "Postgres"}],
                "multi_select": False,
            }
        ]
    }
    assert req.message == "어느 DB를 쓸까요?"
    result = call.results[0]
    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == {
        **QUESTION_INPUT,
        "answers": {"어느 DB를 쓸까요?": "SQLite"},
        "response": "로컬로",
    }
    assert result.updated_permissions is None


async def test_question_cancelled_by_run_interrupts() -> None:
    call = PermissionCall("AskUserQuestion", QUESTION_INPUT)
    await _run([call], InteractiveSink(lambda _r: None))
    result = call.results[0]
    assert isinstance(result, PermissionResultDeny)
    assert result.interrupt is True


async def test_question_not_granted_is_unmatched() -> None:
    sink = InteractiveSink(lambda _r: {"answers": {}})
    call = PermissionCall("AskUserQuestion", QUESTION_INPUT)
    await _run([call], sink, grant=InteractionGrant(kinds=["tool_permission"]))
    assert sink.requests == []
    assert isinstance(call.results[0], PermissionResultDeny)


# ---------------------------------------------------------------- 도구 승인


async def test_permission_allow_with_updated_input_and_context_payload() -> None:
    def answer(req: InteractionRequest) -> dict[str, Any]:
        return {"decision": "allow", "updated_input": {"command": "ls -la"}}

    sink = InteractiveSink(answer)
    ctx = _ctx(tool_use_id="tu1", title="Claude wants to run ls", display_name="Run command")
    call = PermissionCall("Bash", {"command": "ls", "api_key": SECRET}, ctx)
    await _run([call], sink, limits=Limits(commands=["ls"]))
    req = sink.requests[0]
    assert req.kind == "tool_permission"
    assert req.title == "Run command"
    assert req.message == "Claude wants to run ls"
    assert req.payload["tool_name"] == "Bash"
    assert req.payload["tool_use_id"] == "tu1"
    # 있는 필드만 싣는다
    assert "blocked_path" not in req.payload
    assert "agent_id" not in req.payload
    # 입력은 가린 미리보기(문자열)만
    assert isinstance(req.payload["input_preview"], str)
    assert SECRET not in repr(req.payload)
    assert req.actor is None
    assert req.node_path is None
    result = call.results[0]
    assert isinstance(result, PermissionResultAllow)
    assert result.updated_input == {"command": "ls -la"}
    assert result.updated_permissions is None


async def test_allow_for_run_is_remembered_in_memory_only() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "allow_for_run"})
    first = PermissionCall("Read", {"file_path": "a"})
    again = PermissionCall("Read", {"file_path": "a"})
    other = PermissionCall("Read", {"file_path": "b"})
    await _run([first, again, other], sink)
    assert len(sink.requests) == 2  # a 한 번 + b 한 번
    assert all(isinstance(c.results[0], PermissionResultAllow) for c in (first, again, other))
    assert again.results[0].updated_input == {"file_path": "a"}
    assert all(c.results[0].updated_permissions is None for c in (first, again))

    # 새 실행에는 이어지지 않는다
    sink2 = InteractiveSink(lambda _r: {"decision": "deny"})
    repeat = PermissionCall("Read", {"file_path": "a"})
    await _run([repeat], sink2)
    assert len(sink2.requests) == 1
    assert isinstance(repeat.results[0], PermissionResultDeny)


async def test_deny_messages_and_expiry() -> None:
    reasons = PermissionCall("Read", {"file_path": "a"})
    plain = PermissionCall("Read", {"file_path": "b"})
    expired = PermissionCall("Read", {"file_path": "c"})
    cancelled = PermissionCall("Read", {"file_path": "d"})

    def answer(req: InteractionRequest) -> Any:
        path = req.payload["input_preview"]
        if '"a"' in path:
            return {"decision": "deny", "message": "그 파일은 안 됩니다"}
        if '"b"' in path:
            return {"decision": "deny"}
        if '"c"' in path:
            return InteractionOutcome(
                interaction_id="x",
                status="expired",
                response={"decision": "deny", "message": "사용자 응답 없음(만료)"},
                reason="timeout",
            )
        return None

    await _run([reasons, plain, expired, cancelled], InteractiveSink(answer))
    assert reasons.results[0].message == "그 파일은 안 됩니다"
    assert reasons.results[0].interrupt is False
    assert plain.results[0].message == "사용자가 거부했습니다"
    assert expired.results[0].message == "사용자 응답 없음(만료)"
    assert expired.results[0].interrupt is False
    assert cancelled.results[0].interrupt is True


async def test_tool_guard_blocks_before_user_can_allow() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "allow"})
    call = PermissionCall("Bash", {"command": "rm -rf /"})
    await _run([call], sink, limits=Limits(commands=["git status"]))
    assert sink.requests == []  # 사용자에게 묻기 전에 막는다
    result = call.results[0]
    assert isinstance(result, PermissionResultDeny)
    assert "실행 범위 제한" in result.message


async def test_not_granted_permission_is_unmatched_allow_when_configured() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "deny"})
    call = PermissionCall("Read", {"file_path": "a"})
    await _run(
        [call],
        sink,
        grant=InteractionGrant(kinds=["question"]),
        agent=_agent(unmatched_permission="allow"),
    )
    assert sink.requests == []
    assert isinstance(call.results[0], PermissionResultAllow)


# ---------------------------------------------------------------- 서브에이전트 귀속


async def test_subagent_permission_is_attributed_by_agent_id() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "allow"}, node_path=["lead"])
    delegate = AssistantMessage(
        content=[
            ToolUseBlock(
                id="toolu_agent",
                name="Agent",
                input={"subagent_type": "reviewer", "description": "d", "prompt": "p"},
            )
        ],
        model="m",
    )
    started = TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id="task-1",
        description="d",
        uuid="u",
        session_id="s",
        tool_use_id="toolu_agent",
    )
    mine = PermissionCall("Read", {"file_path": "a"}, _ctx(agent_id="task-1"))
    unknown = PermissionCall("Read", {"file_path": "b"}, _ctx(agent_id="who-knows"))
    question = PermissionCall("AskUserQuestion", QUESTION_INPUT, _ctx(agent_id="task-1"))
    members = [SubagentSpec(name="reviewer", description="d", prompt="p", actor="rev-agent")]
    await _run([delegate, started, mine, unknown, question], sink, subagents=members)
    first, second = sink.requests  # 서브에이전트 질문은 열지 않는다
    assert first.actor == "rev-agent"
    assert first.node_path == ["lead", "reviewer"]
    assert first.payload["agent_id"] == "task-1"
    assert second.actor is None  # 못 맞추면 위임자
    assert second.node_path is None
    assert isinstance(question.results[0], PermissionResultDeny)


# ---------------------------------------------------------------- 설정 검증·경고


def test_validate_settings_warns_no_path_for_prompting_modes() -> None:
    backend = ClaudeSdkBackend()
    none = InteractionGrant()
    asking = AgentSettings(backend_options={"permission_mode": "default"})
    issues = backend.validate_settings(asking, none)
    assert [i.code for i in issues] == ["interaction.no_path"]
    assert issues[0].severity == "warning"
    assert issues[0].details["kinds"] == ["tool_permission"]
    assert backend.validate_settings(asking, InteractionGrant(kinds=["tool_permission"])) == []
    assert backend.validate_settings(AgentSettings(), none) == []  # 기본 dontAsk
    via_sdk = AgentSettings(backend_options={"sdk_options": {"permission_mode": "acceptEdits"}})
    assert backend.validate_settings(via_sdk, none)
    custom = AgentSettings(
        backend_options={"permission_mode": "default", "prompting_permission_modes": ["plan"]}
    )
    assert backend.validate_settings(custom, none) == []
    assert backend.validate_settings(AgentSettings(backend_options={"nope": 1}), none) == []


def test_interaction_kind_names_are_installer_data() -> None:
    from agent_console_runtime import EnvSecretProvider as Env

    backend = ClaudeSdkBackend.from_options(
        {"interaction_kinds": {"question": "ask", "tool_permission": "approve"}},
        secrets=SecretResolver([Env({})]),
        environ={},
    )
    assert backend.descriptor.capabilities.interactions == ["ask", "approve"]
    issues = backend.validate_settings(
        AgentSettings(backend_options={"permission_mode": "default"}), InteractionGrant()
    )
    assert issues[0].details["kinds"] == ["approve"]


async def test_renamed_kinds_are_used_for_grants_and_requests() -> None:
    sink = InteractiveSink(lambda _r: {"decision": "allow"})
    call = PermissionCall("Read", {"file_path": "a"})
    clients, factory = _capture([_init(), call, _result()])
    backend = _backend(factory, interaction_kinds={"tool_permission": "approve"})
    req = AgentRequest(agent=_agent(), prompt="p", interactions=InteractionGrant(kinds=["approve"]))
    await backend.run(req, sink, CancelToken())
    assert [r.kind for r in sink.requests] == ["approve"]
    assert "AskUserQuestion" in clients[0].options.disallowed_tools


async def test_prompting_mode_is_not_risky_but_bypass_is() -> None:
    sink = InteractiveSink()
    await _run([], sink)
    assert sink.of("log.warning") == []
    bypass = InteractiveSink()
    await _run([], bypass, agent=_agent(permission_mode="bypassPermissions"))
    assert [w["details"]["option"] for w in bypass.of("log.warning")] == ["permission_mode"]
