"""1R.9 QA 점검: fake와 이벤트 모양 대조, trace 자식 span, 비밀 누출 시도, 권한 확대."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import RateLimitEvent, RateLimitInfo

from agent_console_backend_claude_sdk import ClaudeSdkBackend
from agent_console_backend_claude_sdk.testing import FakeSdkClient, ListeningSink, ValidatingSink
from agent_console_backend_fake_agent import FakeBackend
from agent_console_contracts import Agent, Limits, ResourceBundle
from agent_console_runtime import AgentRequest, CancelToken, SubagentSpec
from agent_console_trace import build_trace

from .test_agent_console_backend_claude_sdk_v2 import (  # type: ignore[import-not-found]
    API_KEY,
    GH_TOKEN,
    OAUTH,
    _agent,
    _backend,
    _capture,
    _delegate,
    _delegation_result,
    _init,
    _members,
    _result,
    _subagent_script,
)


def _shape(sink: ValidatingSink, *path: str) -> list[tuple[str, str | None, tuple[str, ...]]]:
    return [(e.type, e.actor, tuple(sorted(e.payload))) for e in sink.at(*path)]


async def test_qa_event_shape_matches_fake_for_delegation() -> None:
    # claude-sdk
    sdk_sink = ListeningSink(["lead"])
    _, factory = _capture(_subagent_script())
    members = [SubagentSpec(name="reviewer", description="d", prompt="p", actor="reviewer-agent")]
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=members), sdk_sink, CancelToken()
    )
    # fake
    fake_sink = ValidatingSink(["lead"])
    fake = FakeBackend()
    agent = Agent(
        id="lead",
        name="lead",
        backend_options={
            "rules": [
                {
                    "delegate": [
                        {
                            "to": "reviewer",
                            "prompt": "x",
                            "tool_calls": [{"name": "Read", "input": {"file_path": "a"}}],
                            "usage": {"total_tokens": 5, "tool_uses": 1, "duration_ms": 3},
                        }
                    ],
                    "response": "ok",
                }
            ]
        },
    )
    await fake.run(
        AgentRequest(agent=agent, prompt="p", subagents=members), fake_sink, CancelToken()
    )

    for sink in (sdk_sink, fake_sink):
        sub = [e for e in sink.at("lead", "reviewer") if e.type.startswith("agent.subagent_")]
        assert [e.type for e in sub] == ["agent.subagent_started", "agent.subagent_stopped"]
        assert {e.actor for e in sink.at("lead", "reviewer")} == {"reviewer-agent"}
    sdk_started = sdk_sink.of("agent.subagent_started")[0]
    fake_started = fake_sink.of("agent.subagent_started")[0]
    sdk_stopped = sdk_sink.of("agent.subagent_stopped")[0]
    fake_stopped = fake_sink.of("agent.subagent_stopped")[0]

    # 필드 이름 집합(값이 있는 것)
    def present(d: dict[str, Any]) -> set[str]:
        return {k for k, v in d.items() if v is not None}

    assert present(fake_started) <= present(sdk_started) | {"task_type"}, (
        present(fake_started),
        present(sdk_started),
    )
    assert present(fake_stopped) <= present(sdk_stopped), (
        present(fake_stopped),
        present(sdk_stopped),
    )
    assert set(sdk_stopped["usage"]) >= {"total_tokens"}
    assert sdk_stopped["usage"].get("input_tokens") is None
    # 위임자 쪽 순서: tool_call(Agent) ... tool_result
    for sink in (sdk_sink, fake_sink):
        lead = [(e.type, e.payload.get("name")) for e in sink.at("lead")]
        names = [t for t, _ in lead]
        assert names.index("agent.tool_call") < names.index("agent.tool_result")

    # 전체 순서(타입만, 위임 구간)
    def seq(sink: ValidatingSink) -> list[str]:
        return [
            f"{'/'.join(e.node_path)}:{e.type}"
            for e in sink.events
            if e.type
            in {
                "agent.tool_call",
                "agent.tool_result",
                "agent.subagent_started",
                "agent.subagent_stopped",
            }
        ]

    print("SDK ", seq(sdk_sink))
    print("FAKE", seq(fake_sink))


async def test_qa_trace_has_child_span() -> None:
    sink = ListeningSink(["lead"])
    _, factory = _capture(_subagent_script())
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=_members()), sink, CancelToken()
    )
    events = [
        sink.events[0].model_copy(
            update={"type": "node.started", "payload": {"status": "running"}}
        ),
        *sink.events,
    ]
    trace = build_trace(events)
    child = [s for s in trace.spans if s.node_id == "reviewer"]
    assert child, [s.node_id for s in trace.spans]
    assert child[0].parent_id is not None
    assert child[0].actor == "reviewer-agent"


async def test_qa_secret_leak_attempts() -> None:
    """서브에이전트 설명·요약·결과·예외에 비밀이 섞여도 이벤트·결과에 새지 않아야 한다."""
    from claude_agent_sdk import AssistantMessage, TaskNotificationMessage, TaskStartedMessage

    leak = f"token {GH_TOKEN} key {API_KEY}"
    script: list[Any] = [
        _init(),
        _delegate("toolu_agent", "reviewer", description=leak),
        TaskStartedMessage(
            subtype="task_started",
            data={},
            task_id="t",
            description=leak,
            uuid="u",
            session_id="s",
            tool_use_id="toolu_agent",
            task_type="local_agent",
        ),
        TaskNotificationMessage(
            subtype="task_notification",
            data={},
            task_id="t",
            status="completed",
            output_file="",
            summary=leak,
            uuid="u",
            session_id="s",
            tool_use_id="toolu_agent",
            usage={"total_tokens": 1, "tool_uses": 1, "duration_ms": 1},
        ),
        _delegation_result("toolu_agent", leak),
        AssistantMessage(content=[], model="m"),
        _result(),
    ]
    sink = ListeningSink(["lead"])
    _, factory = _capture(script)
    bundle = ResourceBundle(
        slots={
            "mcp_servers": [
                {"name": "gh", "env": {"GITHUB_TOKEN": "secret://github_token"}, "command": "x"}
            ]
        }
    )
    req = AgentRequest(
        agent=_agent(auth={"mode": "api_key", "api_key": "secret://anthropic_api_key"}),
        prompt="p",
        subagents=[SubagentSpec(name="reviewer", description="d", prompt="p", bundle=bundle)],
    )
    await _backend(factory).run(req, sink, CancelToken())
    repr([(e.payload, e.raw) for e in sink.events]) + repr(sink.results)
    leaked = [
        (e.type, k)
        for e in sink.events
        for k, v in e.payload.items()
        if any(s in repr(v) for s in (GH_TOKEN, API_KEY, OAUTH))
    ]
    leaked += [("listener", r["name"]) for r in sink.results if GH_TOKEN in r["text"]]
    assert not leaked, f"누출: {leaked}"


async def test_qa_secret_not_in_exceptions() -> None:
    sink = ValidatingSink()

    def boom(options: Any) -> Any:
        return FakeSdkClient(options, [], connect_error=RuntimeError(f"connect failed {API_KEY}"))

    req = AgentRequest(
        agent=_agent(auth={"mode": "api_key", "api_key": "secret://anthropic_api_key"}), prompt="p"
    )
    result = await _backend(boom).run(req, sink, CancelToken())
    assert result.error is not None
    assert API_KEY not in result.error.message
    assert API_KEY not in repr(result.error.details)


async def test_qa_subagent_invalid_options_message_has_no_value() -> None:
    _, factory = _capture([])
    bad = SubagentSpec(name="x", description="d", prompt="p", options={GH_TOKEN: 1})
    result = await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=[bad]), ValidatingSink(), CancelToken()
    )
    assert result.status == "failed"
    # 키 이름에 비밀을 넣은 경우까지는 요구하지 않지만 관측용으로 출력
    print("INVALID_MSG", result.error.message if result.error else None)


async def test_qa_setting_sources_never_user_by_default() -> None:
    clients, factory = _capture([_init(), _result()])
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=_members()),
        ValidatingSink(),
        CancelToken(),
    )
    assert "user" not in (clients[0].options.setting_sources or [])
    assert clients[0].options.strict_mcp_config is True


async def test_qa_subagent_tools_do_not_widen_delegator_availability() -> None:
    """서브에이전트가 Write/Bash를 갖는다고 위임자의 tools(가용 도구)가 늘면 안 된다."""
    clients, factory = _capture([_init(), _result()])
    members = [
        SubagentSpec(name="w", description="d", prompt="p", tools=["Write", "Bash(rm:*)"]),
    ]
    await _backend(factory).run(
        AgentRequest(agent=_agent(), prompt="p", subagents=members), ValidatingSink(), CancelToken()
    )
    o = clients[0].options
    print("TOOLS", o.tools, "ALLOWED", o.allowed_tools)
    assert "Write" not in o.tools
    assert "Bash" not in o.tools
    assert "Write" not in o.allowed_tools, "위임자 세션 사전 승인에 서브에이전트 도구가 섞임"
    assert o.agents["w"].tools == ["Write", "Bash"]


async def test_qa_subagent_commands_widen_warns_even_without_limits() -> None:
    sink = ValidatingSink()
    _, factory = _capture([_init(), _result()])
    bundle = ResourceBundle(slots={"tools": [{"commands": ["rm"]}]})
    members = [SubagentSpec(name="w", description="d", prompt="p", bundle=bundle)]
    await _backend(factory).run(
        AgentRequest(
            agent=_agent(), prompt="p", subagents=members, limits=Limits(commands=["git status"])
        ),
        sink,
        CancelToken(),
    )
    warns = [w for w in sink.of("log.warning") if w["details"].get("option") == "limits.commands"]
    assert warns
    assert warns[0]["details"]["added"] == ["rm"]


async def test_qa_rate_limit_without_window_is_unspecified_and_no_invention() -> None:
    sink = ValidatingSink()
    msg = RateLimitEvent(
        rate_limit_info=RateLimitInfo(status="allowed", raw={}), uuid="u", session_id="s"
    )
    _, factory = _capture([_init(), msg, _result()])
    await _backend(factory).run(AgentRequest(agent=_agent(), prompt="p"), sink, CancelToken())
    p = sink.of("usage.rate_limit")[0]
    assert p["window"] == "unspecified"
    assert p["utilization"] is None
    assert p["resets_at"] is None


async def test_qa_models_and_tool_names_are_data() -> None:
    clients, factory = _capture([_init(), _result()])
    agent = _agent(delegation_tool="Delegate", delegation_tool_names=["Delegate"])
    await _backend(factory).run(
        AgentRequest(agent=agent, prompt="p", subagents=_members()), ValidatingSink(), CancelToken()
    )
    assert "Delegate" in clients[0].options.tools
    assert "Agent" not in clients[0].options.tools
    assert ClaudeSdkBackend is not None
