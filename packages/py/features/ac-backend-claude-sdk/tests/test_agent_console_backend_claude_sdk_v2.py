"""1R.9: 서브에이전트(agents·귀속·결과 알림), 실행 묶음 칸 매핑, 인증 방식, 사용량 한도 이벤트.

가짜 SDK 클라이언트(`FakeSdkClient`)만 쓴다. 실제 호출은 `..._live.py`(opt-in).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    RateLimitInfo,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from agent_console_backend_claude_sdk import (
    DEFAULT_SUBAGENT_ENV,
    RESOURCE_SLOTS,
    ClaudeSdkBackend,
)
from agent_console_backend_claude_sdk.testing import (
    FakeSdkClient,
    ListeningSink,
    ValidatingSink,
)
from agent_console_contracts import Agent, Limits, ResourceBundle
from agent_console_runtime import (
    AgentRequest,
    CancelToken,
    EnvSecretProvider,
    SecretResolver,
    SubagentResultListener,
    SubagentSpec,
)

API_KEY = "sk-ant-api-THISISTHEAPIKEYVALUE999"
GH_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWX1234"
OAUTH = "oauth-token-value-0001"
RESOLVER = SecretResolver(
    [
        EnvSecretProvider(
            {"anthropic_api_key": API_KEY, "github_token": GH_TOKEN, "claude_oauth": OAUTH}
        )
    ]
)


# ---------------------------------------------------------------- 도우미


def _agent(**options: Any) -> Agent:
    return Agent(
        id="lead",
        name="Lead",
        model="lead-model",
        tools=["Read"],
        system_prompt="you lead",
        backend="claude-agent-sdk",
        backend_options=options,
    )


def _capture(
    script: list[Any], **kw: Any
) -> tuple[list[FakeSdkClient], Callable[[ClaudeAgentOptions], Any]]:
    clients: list[FakeSdkClient] = []

    def factory(options: ClaudeAgentOptions) -> Any:
        client = FakeSdkClient(options, script, **kw)
        clients.append(client)
        return client

    return clients, factory


def _backend(factory: Callable[[ClaudeAgentOptions], Any], **kw: Any) -> ClaudeSdkBackend:
    kw.setdefault("environ", {})
    kw.setdefault("secrets", RESOLVER)
    return ClaudeSdkBackend(client_factory=factory, **kw)


def _init() -> SystemMessage:
    return SystemMessage(subtype="init", data={"session_id": "sess-1", "model": "m"})


def _result(**kw: Any) -> ResultMessage:
    base: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 10,
        "duration_api_ms": 8,
        "is_error": False,
        "num_turns": 2,
        "session_id": "sess-1",
        "result": "done",
        "usage": {"input_tokens": 50, "output_tokens": 20},
    }
    base.update(kw)
    return ResultMessage(**base)


def _delegate(tool_use_id: str, subagent_type: str, description: str = "review it") -> Any:
    return AssistantMessage(
        content=[
            ToolUseBlock(
                id=tool_use_id,
                name="Agent",
                input={
                    "subagent_type": subagent_type,
                    "description": description,
                    "prompt": "please review",
                },
            )
        ],
        model="m",
        message_id="msg_lead",
        usage={"input_tokens": 10, "output_tokens": 3},
    )


def _task_started(task_id: str, tool_use_id: str | None) -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id=task_id,
        description="review it",
        uuid="u",
        session_id="sess-1",
        tool_use_id=tool_use_id,
        task_type="local_agent",
    )


def _task_done(task_id: str, tool_use_id: str | None, status: str = "completed") -> Any:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id=task_id,
        status=status,  # type: ignore[arg-type]
        output_file="",
        summary="summary text",
        uuid="u",
        session_id="sess-1",
        tool_use_id=tool_use_id,
        usage={"total_tokens": 321, "tool_uses": 4, "duration_ms": 1500},
    )


def _delegation_result(tool_use_id: str, text: str, *, is_error: bool = False) -> UserMessage:
    return UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id=tool_use_id,
                content=[
                    {"type": "text", "text": text},
                    {"type": "text", "text": "agentId: a1b2c3"},
                ],
                is_error=is_error,
            )
        ]
    )


def _subagent_script() -> list[Any]:
    return [
        _init(),
        _delegate("toolu_agent", "reviewer"),
        _task_started("task-1", "toolu_agent"),
        AssistantMessage(
            content=[
                TextBlock("looking at files"),
                ToolUseBlock(id="toolu_sub_read", name="Read", input={"file_path": "a.py"}),
            ],
            model="m",
            parent_tool_use_id="toolu_agent",
            message_id="msg_sub",
            usage={"input_tokens": 999, "output_tokens": 999},
        ),
        UserMessage(
            content=[ToolResultBlock(tool_use_id="toolu_sub_read", content="code", is_error=False)],
            parent_tool_use_id="toolu_agent",
        ),
        _task_done("task-1", "toolu_agent"),
        _delegation_result("toolu_agent", "LGTM with 2 notes"),
        AssistantMessage(content=[TextBlock("done")], model="m", message_id="msg_final"),
        _result(),
    ]


def _members() -> list[SubagentSpec]:
    return [
        SubagentSpec(
            name="reviewer",
            description="Use for code review",
            prompt="you review",
            actor="reviewer-agent",
            tools=["Read", "Grep(*.py)"],
            disallowed_tools=["Write"],
            model="claude-full-model-id",
            options={"maxTurns": 5},
            bundle=ResourceBundle(
                slots={
                    "instructions": ["## 리뷰 규칙\n짧게"],
                    "mcp_servers": [
                        {
                            "name": "gh",
                            "type": "http",
                            "url": "https://example.invalid/mcp",
                            "headers": {"Authorization": "secret://github_token"},
                        }
                    ],
                    "tools": [{"tools": ["Glob"], "disallowed_tools": ["Grep"]}],
                }
            ),
        ),
        SubagentSpec(name="tester", description="Use for tests", prompt="you test"),
    ]


# ---------------------------------------------------------------- 서브에이전트


async def test_subagents_become_agent_definitions_and_allow_delegation_tool() -> None:
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(agent=_agent(), prompt="p", cwd="/w", subagents=_members())
    result = await _backend(factory).run(req, ValidatingSink(), CancelToken())
    assert result.status == "succeeded", result.error
    opts = clients[0].options
    assert set(opts.agents or {}) == {"reviewer", "tester"}
    reviewer = (opts.agents or {})["reviewer"]
    assert isinstance(reviewer, AgentDefinition)
    assert reviewer.description == "Use for code review"
    assert reviewer.prompt == "you review\n\n## 리뷰 규칙\n짧게"
    # 스펙 tools + 묶음 tools, 묶음 금지(Grep)가 우선, 괄호 규칙은 이름만
    assert reviewer.tools == ["Read", "Glob"]
    assert reviewer.disallowedTools == ["Write", "Grep"]
    assert reviewer.model == "claude-full-model-id"
    assert reviewer.maxTurns == 5
    assert reviewer.mcpServers == [
        {
            "gh": {
                "type": "http",
                "url": "https://example.invalid/mcp",
                "headers": {"Authorization": GH_TOKEN},
            }
        }
    ]
    tester = (opts.agents or {})["tester"]
    assert tester.tools is None  # 지정 없음 = SDK 기본(상속)
    # 위임 도구는 쓸 수 있고 사전 승인된다
    assert "Agent" in opts.tools
    assert "Agent" in opts.allowed_tools
    # 대상 도구 규칙은 기본으로 위임자 세션 사전 승인에 넣지 않는다(위임자 권한 확대 방지)
    assert "Glob" not in opts.allowed_tools
    # 깊이 1·전경 실행·기본 서브에이전트 끄기
    for key, value in DEFAULT_SUBAGENT_ENV.items():
        assert opts.env[key] == value
    assert opts.forward_subagent_text is True
    assert opts.setting_sources == ["project"]  # 기본에 user 없음


async def test_no_subagents_means_no_agents_or_subagent_env() -> None:
    clients, factory = _capture([_init(), _result()])
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p"), ValidatingSink(), CancelToken()
    )
    opts = clients[0].options
    assert opts.agents is None
    assert "Agent" not in opts.tools
    assert not set(DEFAULT_SUBAGENT_ENV) & set(opts.env)


async def test_delegation_tool_respects_explicit_disallow() -> None:
    clients, factory = _capture([_init(), _result()])
    req = AgentRequest(
        agent=_agent(disallowed_tools=["Agent"]), prompt="p", subagents=_members()[1:]
    )
    await _backend(factory).run(req, ValidatingSink(), CancelToken())
    assert "Agent" not in clients[0].options.tools
    assert "Agent" not in clients[0].options.allowed_tools


async def test_subagent_events_are_attributed_to_target_actor_and_path() -> None:
    sink = ListeningSink(["lead"])
    _, factory = _capture(_subagent_script())
    req = AgentRequest(agent=_agent(), prompt="p", subagents=_members())
    result = await _backend(factory).run(req, sink, CancelToken())
    assert result.status == "succeeded", result.error

    sub = sink.at("lead", "reviewer")
    assert [e.type for e in sub] == [
        "agent.subagent_started",
        "agent.message",
        "agent.tool_call",
        "agent.tool_result",
        "agent.subagent_stopped",
    ]
    assert {e.actor for e in sub} == {"reviewer-agent"}
    started = sub[0].payload
    assert started["subagent_id"] == "task-1"
    assert started["name"] == "reviewer"
    assert started["tool_use_id"] == "toolu_agent"
    assert started["task_preview"] == "review it"
    stopped = sub[-1].payload
    assert stopped["status"] == "completed"
    assert stopped["usage"]["total_tokens"] == 321
    assert stopped["usage"]["input_tokens"] is None  # TaskUsage는 총 토큰만
    assert stopped["tool_uses"] == 4
    assert stopped["duration_ms"] == 1500

    # 위임 도구 호출·결과는 위임자의 것
    lead_calls = [e for e in sink.at("lead") if e.type == "agent.tool_call"]
    assert [e.payload["name"] for e in lead_calls] == ["Agent"]
    # 서브에이전트 메시지 사용량은 위임자 누적에 섞지 않는다
    usage = sink.of("agent.usage")
    assert usage[0]["usage"]["input_tokens"] == 10
    assert usage[-1]["usage"]["input_tokens"] == 50
    # 최종 텍스트는 위임자 것
    assert result.text == "done"

    # 위임 방식에 결과 알림(끝의 agentId 줄 제거)
    assert sink.results == [
        {
            "name": "reviewer",
            "text": "LGTM with 2 notes",
            "status": "succeeded",
            "actor": "reviewer-agent",
            "tool_use_id": "toolu_agent",
        }
    ]


async def test_listener_protocol_is_structural() -> None:
    assert isinstance(ListeningSink(), SubagentResultListener)
    assert not isinstance(ValidatingSink(), SubagentResultListener)


async def test_unknown_subagent_type_stays_with_delegator() -> None:
    sink = ListeningSink()
    script = [
        _init(),
        _delegate("toolu_x", "general-purpose"),
        _task_started("task-x", "toolu_x"),
        AssistantMessage(
            content=[TextBlock("hidden"), ToolUseBlock(id="t2", name="Read", input={})],
            model="m",
            parent_tool_use_id="toolu_x",
        ),
        _task_done("task-x", "toolu_x"),
        _delegation_result("toolu_x", "result"),
        _result(),
    ]
    _, factory = _capture(script)
    req = AgentRequest(agent=_agent(), prompt="p", subagents=_members())
    await _backend(factory).run(req, sink, CancelToken())
    assert all(e.node_path == ["n1"] for e in sink.events)
    assert sink.of("agent.subagent_started")[0]["name"] is None
    # 대상을 모르는 서브에이전트 텍스트는 위임자 텍스트로 내지 않는다
    assert [p["text"] for p in sink.of("agent.message")] == []
    assert sink.results == []


async def test_missing_task_events_are_synthesized_at_end() -> None:
    sink = ListeningSink()
    script = [
        _init(),
        _delegate("toolu_a", "tester"),
        _delegation_result("toolu_a", "tests failed", is_error=True),
        _result(),
    ]
    _, factory = _capture(script)
    req = AgentRequest(agent=_agent(), prompt="p", subagents=_members())
    await _backend(factory).run(req, sink, CancelToken())
    sub = sink.at("n1", "tester")
    assert [e.type for e in sub] == ["agent.subagent_started", "agent.subagent_stopped"]
    assert sub[0].payload["subagent_id"] == "toolu_a"
    assert sub[1].payload["subagent_id"] == "toolu_a"
    assert sub[1].payload["status"] == "failed"
    assert sub[1].payload["result_preview"] == "tests failed"
    assert sink.results[0]["status"] == "failed"


async def test_task_updated_terminal_status_stops_once() -> None:
    sink = ValidatingSink()
    script = [
        _init(),
        _delegate("toolu_a", "tester"),
        _task_started("task-a", "toolu_a"),
        TaskUpdatedMessage(
            subtype="task_updated", data={}, task_id="task-a", patch={"status": "killed"}
        ),
        _task_done("task-a", "toolu_a", status="stopped"),
        _result(),
    ]
    _, factory = _capture(script)
    req = AgentRequest(agent=_agent(), prompt="p", subagents=_members())
    await _backend(factory).run(req, sink, CancelToken())
    stopped = sink.of("agent.subagent_stopped")
    assert len(stopped) == 1
    assert stopped[0]["status"] == "stopped"


async def test_listener_failure_becomes_warning() -> None:
    sink = ListeningSink(fail=True)
    _, factory = _capture(_subagent_script())
    req = AgentRequest(agent=_agent(), prompt="p", subagents=_members())
    result = await _backend(factory).run(req, sink, CancelToken())
    assert result.status == "succeeded"
    warnings = [w for w in sink.of("log.warning") if w["details"].get("subagent") == "reviewer"]
    assert warnings[0]["details"]["error"] == "RuntimeError"


async def test_invalid_subagent_options_fail_before_client() -> None:
    clients, factory = _capture([])
    for spec in (
        SubagentSpec(name="a", options={"prompt": "x"}),
        SubagentSpec(name="a", options={"nope": 1}),
    ):
        req = AgentRequest(agent=_agent(), prompt="p", subagents=[spec])
        result = await _backend(factory).run(req, ValidatingSink(), CancelToken())
        assert result.error is not None
        assert result.error.code == "validation_failed"
    dup = AgentRequest(
        agent=_agent(), prompt="p", subagents=[SubagentSpec(name="a"), SubagentSpec(name="a")]
    )
    result = await _backend(factory).run(dup, ValidatingSink(), CancelToken())
    assert result.error is not None
    assert clients == []


# ---------------------------------------------------------------- 사용량 한도


async def test_rate_limit_event_becomes_usage_rate_limit() -> None:
    sink = ValidatingSink()
    script = [
        _init(),
        RateLimitEvent(
            rate_limit_info=RateLimitInfo(
                status="allowed_warning",
                resets_at=1_800_000_000,
                rate_limit_type="five_hour",
                utilization=0.82,
                overage_status="allowed",
            ),
            uuid="u",
            session_id="sess-1",
        ),
        RateLimitEvent(
            rate_limit_info=RateLimitInfo(status="allowed"), uuid="u2", session_id="sess-1"
        ),
        _result(),
    ]
    _, factory = _capture(script)
    await _backend(factory).run(AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken())
    limits = sink.of("usage.rate_limit")
    assert limits[0] == {
        "window": "five_hour",
        "status": "allowed_warning",
        "utilization": 0.82,
        "resets_at": 1_800_000_000.0,
        "overage_status": "allowed",
    }
    # 창 이름이 없으면 값을 지어내지 않고 "unspecified"로 둔다(사용률도 없음)
    assert limits[1]["window"] == "unspecified"
    assert limits[1]["utilization"] is None


# ---------------------------------------------------------------- 실행 묶음


def _bundle(**slots: Any) -> ResourceBundle:
    return ResourceBundle(slots=slots)


async def test_instructions_join_system_prompt_and_preset_append() -> None:
    clients, factory = _capture([_init(), _result()])
    bundle = _bundle(instructions=["## 팀 규칙\n존댓말", "노드 지침"])
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", bundle=bundle), ValidatingSink(), CancelToken()
    )
    assert clients[0].options.system_prompt == "you lead\n\n## 팀 규칙\n존댓말\n\n노드 지침"

    agent = _agent(system_prompt_mode="claude_code_append")
    await _backend(factory).run(
        AgentRequest(agent=agent, prompt="p", bundle=bundle), ValidatingSink(), CancelToken()
    )
    assert clients[1].options.system_prompt == {
        "type": "preset",
        "preset": "claude_code",
        "append": "you lead\n\n## 팀 규칙\n존댓말\n\n노드 지침",
    }


async def test_files_become_add_dirs_notice_and_readable_paths(tmp_path: Any) -> None:
    work = tmp_path / "work"
    run_dir = tmp_path / "state" / "run1" / "node1"
    work.mkdir()
    run_dir.mkdir(parents=True)
    doc = str(run_dir / "guide.md")
    calls = [
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": doc},
                "tool_use_id": "t1",
            },
        )
    ]
    clients, factory = _capture([_init(), _result()], hook_calls=calls)
    sink = ValidatingSink()
    bundle = _bundle(files=[{"path": doc, "root": str(run_dir)}, {"name": "x.md", "content": "c"}])
    req = AgentRequest(agent=_agent(), prompt="p", cwd=str(work), bundle=bundle)
    await _backend(factory).run(req, sink, CancelToken())
    opts = clients[0].options
    assert opts.add_dirs == [str(run_dir)]
    assert doc in str(opts.system_prompt)
    assert clients[0].hook_outputs == [{}]  # 묶음 파일 폴더는 실행 범위 검사를 통과
    assert any("경로가 없어" in w["message"] for w in sink.of("log.warning"))
    assert "c" not in repr(sink.of("log.warning"))


async def test_mcp_servers_resolve_secrets_and_stay_out_of_events() -> None:
    clients, factory = _capture(
        [
            _init(),
            AssistantMessage(
                content=[
                    ToolUseBlock(id="t1", name="mcp__gh__search", input={"q": f"token {GH_TOKEN}"})
                ],
                model="m",
            ),
            _result(),
        ]
    )
    sink = ValidatingSink()
    bundle = _bundle(
        mcp_servers=[
            {"name": "gh", "type": "stdio", "command": "old"},
            {
                "name": "gh",
                "type": "stdio",
                "command": "gh-mcp",
                "args": ["--ro"],
                "env": {"GITHUB_TOKEN": "secret://github_token"},
            },
        ]
    )
    agent = _agent(mcp_servers={"base": {"type": "stdio", "command": "base"}})
    await _backend(factory).run(
        AgentRequest(agent=agent, prompt="p", bundle=bundle), sink, CancelToken()
    )
    servers = clients[0].options.mcp_servers
    assert servers == {
        "base": {"type": "stdio", "command": "base"},
        "gh": {
            "type": "stdio",
            "command": "gh-mcp",
            "args": ["--ro"],
            "env": {"GITHUB_TOKEN": GH_TOKEN},
        },
    }
    assert GH_TOKEN not in repr([(e.payload, e.raw) for e in sink.events])


async def test_bundle_secret_without_resolver_fails() -> None:
    clients, factory = _capture([])
    bundle = _bundle(
        mcp_servers=[{"name": "gh", "type": "http", "url": "u", "headers": {"A": "secret://nope"}}]
    )
    result = await _backend(factory, secrets=None).run(
        AgentRequest(agent=_agent(), prompt="p", bundle=bundle), ValidatingSink(), CancelToken()
    )
    assert result.error is not None
    assert result.error.code == "secret_unresolved"
    assert clients == []


async def test_tools_union_disallow_wins_and_commands_widen_with_warning() -> None:
    calls = [
        (
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "pytest -q"},
                "tool_use_id": "t1",
            },
        )
    ]
    clients, factory = _capture([_init(), _result()], hook_calls=calls)
    sink = ValidatingSink()
    bundle = _bundle(
        tools=[
            {"tools": ["Bash(pytest:*)", "Edit"], "commands": ["pytest"]},
            {"tools": ["Write"], "disallowed_tools": ["Edit"]},
        ]
    )
    req = AgentRequest(
        agent=_agent(), prompt="p", bundle=bundle, limits=Limits(commands=["git status"])
    )
    await _backend(factory).run(req, sink, CancelToken())
    opts = clients[0].options
    assert opts.tools == ["Read", "Bash", "Write"]
    assert opts.allowed_tools == ["Read", "Bash(pytest:*)", "Write"]
    assert "Edit" in opts.disallowed_tools
    assert clients[0].hook_outputs == [{}]  # 묶음 명령이 허용 목록에 합쳐짐
    widened = [w for w in sink.of("log.warning") if w["details"].get("option") == "limits.commands"]
    assert widened[0]["details"]["added"] == ["pytest"]


async def test_unknown_slot_warns_and_bad_shape_fails() -> None:
    _, factory = _capture([_init(), _result()])
    sink = ValidatingSink()
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", bundle=_bundle(hooks=[{"x": 1}])),
        sink,
        CancelToken(),
    )
    assert any(w["details"].get("slot") == "hooks" for w in sink.of("log.warning"))
    bad = await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", bundle=_bundle(tools="Read")),
        ValidatingSink(),
        CancelToken(),
    )
    assert bad.error is not None
    assert bad.error.code == "validation_failed"


def test_descriptor_declares_subagents_and_resource_slots() -> None:
    caps = ClaudeSdkBackend().descriptor.capabilities
    assert caps.subagents is True
    assert caps.resource_slots == list(RESOURCE_SLOTS)
    assert caps.resource_slots == [
        "instructions",
        "files",
        "mcp_servers",
        "tools",
        "skills",
        "rules",
    ]  # hooks는 allow_command_hooks가 켜졌을 때만(2R.12)
    assert caps.slot_notes is not None
    assert "hooks" in caps.slot_notes
    assert caps.interactions == ["question", "tool_permission"]  # 1R.30


# ---------------------------------------------------------------- 인증


async def test_api_key_auth_from_secret_ref() -> None:
    clients, factory = _capture([_init(), _result()])
    sink = ValidatingSink()
    agent = _agent(auth={"mode": "api_key", "api_key": "secret://anthropic_api_key"})
    result = await _backend(factory).run(AgentRequest(agent=agent, prompt="p"), sink, CancelToken())
    assert result.status == "succeeded"
    env = clients[0].options.env
    assert env["ANTHROPIC_API_KEY"] == API_KEY
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == ""
    assert not sink.of("log.warning")
    assert API_KEY not in repr([(e.payload, e.raw) for e in sink.events])


async def test_api_key_auth_without_key_fails() -> None:
    clients, factory = _capture([])
    result = await _backend(factory).run(
        AgentRequest(agent=_agent(auth={"mode": "api_key"}), prompt="p"),
        ValidatingSink(),
        CancelToken(),
    )
    assert result.error is not None
    assert result.error.code == "auth_missing"
    assert clients == []


async def test_subscription_auth_blanks_api_key_and_warns_when_allowed() -> None:
    clients, factory = _capture([_init(), _result()])
    sink = ValidatingSink()
    parent = {"HOME": "/home/u", "ANTHROPIC_API_KEY": "parent-key-value"}
    agent = _agent(auth={"mode": "subscription"})
    await _backend(factory, environ=parent, allow_subscription_auth=True).run(
        AgentRequest(agent=agent, prompt="p"), sink, CancelToken()
    )
    env = clients[0].options.env
    assert env["ANTHROPIC_API_KEY"] == ""
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "HOME" not in env  # 부모 HOME은 허용 목록으로 그대로 상속(로그인 자격 위치)
    warning = [w for w in sink.of("log.warning") if w["details"].get("option") == "auth.mode"]
    assert "API 키 사용이 안내" in warning[0]["message"]
    assert "본인 책임" in warning[0]["message"]

    token_agent = _agent(auth={"mode": "subscription", "oauth_token": "secret://claude_oauth"})
    await _backend(factory, allow_subscription_auth=True).run(
        AgentRequest(agent=token_agent, prompt="p"), ValidatingSink(), CancelToken()
    )
    assert clients[1].options.env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH


async def test_auth_conflicting_with_env_is_invalid() -> None:
    _, factory = _capture([])
    agent = _agent(auth={"mode": "subscription"}, env={"ANTHROPIC_API_KEY": "x" * 10})
    result = await _backend(factory).run(
        AgentRequest(agent=agent, prompt="p"), ValidatingSink(), CancelToken()
    )
    assert result.error is not None
    assert result.error.code == "validation_failed"


async def test_subagent_tool_rules_preapproval_is_opt_in_and_warned() -> None:
    members = [SubagentSpec(name="w", description="d", prompt="p", tools=["Write", "Bash(rm:*)"])]
    clients, factory = _capture([_init(), _result()])
    sink = ValidatingSink()
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=members), sink, CancelToken()
    )
    opts = clients[0].options
    assert "Write" not in opts.allowed_tools
    assert "Write" not in opts.tools
    off = [w for w in sink.of("log.warning") if "subagent_tools_preapprove" in repr(w)]
    assert off[0]["details"]["not_preapproved"] == ["Write", "Bash(rm:*)"]

    sink2 = ValidatingSink()
    await _backend(factory).run(
        AgentRequest(agent=_agent(subagent_tools_preapprove=True), prompt="p", subagents=members),
        sink2,
        CancelToken(),
    )
    on = clients[1].options
    assert "Write" in on.allowed_tools
    assert "Bash(rm:*)" in on.allowed_tools
    assert "Write" not in on.tools  # 가용 도구는 넓히지 않는다
    widened = [w for w in sink2.of("log.warning") if "subagent_tools_preapprove" in repr(w)]
    assert widened[0]["details"]["added"] == ["Write", "Bash(rm:*)"]
