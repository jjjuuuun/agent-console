"""FakeBackend v2(1R.10): 서브에이전트 위임 흉내, `usage.rate_limit` 흉내, 실행 묶음 요약."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from agent_console_backend_fake_agent import (
    DEFAULT_RESOURCE_SLOTS,
    EMPTY_BUNDLE,
    FakeBackend,
    bundle_summary,
    mask_secret_refs,
)
from agent_console_backend_fake_agent.testing import InteractiveSink, ListeningSink, ValidatingSink
from agent_console_contracts import (
    Agent,
    AgentSubagentPayload,
    BundleSource,
    InteractionGrant,
    ResourceBundle,
    RunEvent,
)
from agent_console_runtime import (
    AgentRequest,
    CancelToken,
    InteractionOutcome,
    SecretResolver,
    SubagentSpec,
)


def _agent(**options: Any) -> Agent:
    return Agent(id="pl", name="PL", model="m-test", backend="fake-agent", backend_options=options)


class _Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        value = self.now
        self.now += 0.25  # 부를 때마다 250ms 흐른다
        return value


def _backend(**kwargs: Any) -> FakeBackend:
    kwargs.setdefault("ids", lambda: "s1")
    return FakeBackend(**kwargs)


SUBAGENTS = [
    SubagentSpec(name="be-node", description="백엔드 일", actor="backend-lead", model="m-sub"),
    SubagentSpec(name="qa-node", description="검증", actor="qa-lead"),
]


def _delegating_agent(**extra: Any) -> Agent:
    return _agent(
        rules=[
            {
                "contains": "구현",
                "delegate": [
                    {
                        "to": "be-node",
                        "prompt": "API: $prompt",
                        "response": "$agent_name 완료($prompt)",
                        "tool_calls": [
                            {"name": "Write", "input": {"path": "a.py"}, "output": "ok"}
                        ],
                    },
                    {"to": "qa-node", "response": "검증 통과"},
                ],
                "response": "정리: $delegate_1 / $delegate_2",
            }
        ],
        **extra,
    )


# ------------------------------------------------------------------ 위임


async def test_delegate_event_order_actor_and_path_match_sdk_shape() -> None:
    sink = ValidatingSink(node_path=["pl-node"])
    req = AgentRequest(agent=_delegating_agent(), prompt="구현 해 줘", subagents=SUBAGENTS)
    result = await _backend(clock=_Clock()).run(req, sink, CancelToken())

    assert result.status == "succeeded"
    assert result.text == "정리: be-node 완료(API: 구현 해 줘) / 검증 통과"
    rows = [(e.type, e.actor, e.node_path) for e in sink.events]
    lead, be, qa = ["pl-node"], ["pl-node", "be-node"], ["pl-node", "qa-node"]
    assert rows[:12] == [
        ("agent.session_started", None, lead),
        ("agent.tool_call", None, lead),  # 위임 도구 호출(위임자)
        ("agent.subagent_started", "backend-lead", be),
        ("agent.tool_call", "backend-lead", be),
        ("agent.tool_result", "backend-lead", be),
        ("agent.message", "backend-lead", be),
        ("agent.subagent_stopped", "backend-lead", be),
        ("agent.tool_result", None, lead),  # 위임 도구 결과(위임자)
        ("agent.tool_call", None, lead),
        ("agent.subagent_started", "qa-lead", qa),
        ("agent.message", "qa-lead", qa),
        ("agent.subagent_stopped", "qa-lead", qa),
    ]
    assert [t for t, _, _ in rows[12:]][-2:] == ["agent.message", "agent.usage"]
    # 서브에이전트는 텍스트 델타를 내지 않는다(SDK와 같다)
    assert all(e.node_path == lead for e in sink.events if e.type == "agent.text_delta")

    call = sink.of("agent.tool_call")[0]
    assert call["name"] == "Agent"
    assert call["input"] == {
        "subagent_type": "be-node",
        "description": "백엔드 일",
        "prompt": "API: 구현 해 줘",
    }
    started = AgentSubagentPayload.model_validate(sink.of("agent.subagent_started")[0])
    stopped = AgentSubagentPayload.model_validate(sink.of("agent.subagent_stopped")[0])
    # 시작·종료·위임 도구 호출이 명시 id로 이어진다
    assert started.tool_use_id == call["tool_use_id"] == stopped.tool_use_id
    assert started.subagent_id == stopped.subagent_id
    assert started.name == stopped.name == "be-node"
    assert started.task_preview == "API: 구현 해 줘"
    # TaskUsage 모양: 총 토큰만 + 도구 사용 수 + 소요 시간
    assert stopped.status == "completed"
    assert stopped.usage is not None
    assert stopped.usage.model_dump(exclude_none=True) == {
        "total_tokens": 9
    }  # 과제 4단어 + 결과 5단어
    assert stopped.tool_uses == 1
    assert stopped.duration_ms is not None
    assert stopped.duration_ms > 0
    assert stopped.result_preview == "be-node 완료(API: 구현 해 줘)"
    tool_results = {p["tool_use_id"]: p for p in sink.of("agent.tool_result")}
    assert tool_results[call["tool_use_id"]]["is_error"] is False
    assert tool_results[call["tool_use_id"]]["output_preview"] == stopped.result_preview


async def test_delegate_notifies_listener_with_full_result_per_delegation() -> None:
    agent = _agent(
        rules=[
            {
                "delegate": [
                    {"to": "be-node", "response": "전문 " * 200},
                    {"to": "qa-node", "response": "실패", "status": "failed"},
                ]
            }
        ]
    )
    sink = ListeningSink(node_path=["pl-node"])
    req = AgentRequest(agent=agent, prompt="x", subagents=SUBAGENTS)
    await _backend().run(req, sink, CancelToken())
    calls = {p["tool_use_id"] for p in sink.of("agent.tool_call") if p["name"] == "Agent"}
    assert [(r["name"], r["status"], r["actor"]) for r in sink.results] == [
        ("be-node", "succeeded", "backend-lead"),
        ("qa-node", "failed", "qa-lead"),
    ]
    assert sink.results[0]["text"] == "전문 " * 200  # 잘리지 않은 결과
    assert {r["tool_use_id"] for r in sink.results} == calls
    # 알림 능력이 없는 sink에는 부르지 않는다(기존 동작 그대로)
    plain = ValidatingSink(node_path=["pl-node"])
    assert (await _backend().run(req, plain, CancelToken())).status == "succeeded"


async def test_delegate_is_deterministic() -> None:
    def events() -> list[tuple[str, Any]]:
        return [(e.type, e.payload) for e in sink.events]

    req = AgentRequest(agent=_delegating_agent(), prompt="구현", subagents=SUBAGENTS)
    sink = ValidatingSink()
    await _backend(clock=lambda: 5.0).run(req, sink, CancelToken())
    first = events()
    sink = ValidatingSink()
    await _backend(clock=lambda: 5.0).run(req, sink, CancelToken())
    assert events() == first


async def test_delegate_to_unknown_target_is_tool_error_without_subagent_events() -> None:
    sink = ValidatingSink()
    agent = _agent(rules=[{"delegate": [{"to": "nobody"}], "response": "[$delegate_1]"}])
    result = await _backend().run(
        AgentRequest(agent=agent, prompt="x", subagents=SUBAGENTS), sink, CancelToken()
    )
    assert result.status == "succeeded"
    assert result.text == "[]"
    assert "agent.subagent_started" not in sink.types
    assert sink.of("agent.tool_result")[0]["is_error"] is True


async def test_delegate_status_usage_and_tool_name_are_data() -> None:
    sink = ValidatingSink()
    agent = _agent(
        rules=[
            {
                "delegate": [
                    {
                        "to": "qa-node",
                        "status": "failed",
                        "description": "직접 쓴 설명",
                        "usage": {"total_tokens": 1234, "tool_uses": 3, "duration_ms": 50},
                    }
                ]
            }
        ]
    )
    backend = FakeBackend.from_options(
        {"delegate_tool": "Task"}, secrets=SecretResolver(), environ={}
    )
    await backend.run(
        AgentRequest(agent=agent, prompt="p", subagents=SUBAGENTS), sink, CancelToken()
    )
    call = sink.of("agent.tool_call")[0]
    assert call["name"] == "Task"
    assert call["input"]["description"] == "직접 쓴 설명"
    stopped = sink.of("agent.subagent_stopped")[0]
    assert stopped["status"] == "failed"
    assert stopped["usage"]["total_tokens"] == 1234
    assert {k for k, v in stopped["usage"].items() if v is not None} == {"total_tokens"}
    assert (stopped["tool_uses"], stopped["duration_ms"]) == (3, 50)
    assert sink.of("agent.tool_result")[0]["is_error"] is True


async def test_cancel_during_delegate_closes_subagent_as_stopped() -> None:
    sink = ListeningSink()
    agent = _agent(rules=[{"delegate": [{"to": "be-node", "delay_ms": 5000}]}])
    cancel = CancelToken()
    task = asyncio.create_task(
        _backend().run(AgentRequest(agent=agent, prompt="p", subagents=SUBAGENTS), sink, cancel)
    )
    while "agent.subagent_started" not in sink.types:
        await asyncio.sleep(0.005)
    cancel.cancel()
    result = await asyncio.wait_for(task, 2)
    assert result.status == "cancelled"
    assert sink.types[-1] == "agent.subagent_stopped"
    stopped = sink.of("agent.subagent_stopped")[0]
    assert stopped["status"] == "stopped"
    assert "agent.message" not in sink.types
    # claude-sdk와 같게(1R.10 QA): 위임 도구 결과·결과 알림 없음, 사용량·결과를 꾸미지 않는다
    assert "agent.tool_result" not in sink.types
    assert sink.results == []
    assert {k for k, v in stopped.items() if v is not None} == {
        "subagent_id",
        "name",
        "tool_use_id",
        "status",
    }


class _PlainSink:
    """최소 sink(BackendEventSink 프로토콜만: `emit` + `child_path`)."""

    def __init__(self) -> None:
        self.paths: list[tuple[str, Sequence[str] | None, str | None]] = []

    def child_path(self, node_id: str) -> list[str]:
        return ["n", node_id]

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        raw: Any = None,
        evidence: str = "observed",
        actor: str | None = None,
        node_path: Sequence[str] | None = None,
    ) -> RunEvent:
        self.paths.append((type, node_path, actor))
        return RunEvent(
            event_id="e", run_id="r", seq=len(self.paths), ts=0.0, node_path=["n"], type=type
        )


async def test_minimal_sink_gets_child_path_and_actor() -> None:
    sink = _PlainSink()
    agent = _agent(rules=[{"delegate": [{"to": "be-node"}]}])
    await _backend().run(
        AgentRequest(agent=agent, prompt="p", subagents=SUBAGENTS), sink, CancelToken()
    )
    started = next(p for p in sink.paths if p[0] == "agent.subagent_started")
    assert started == ("agent.subagent_started", ["n", "be-node"], "backend-lead")


async def test_capabilities_declare_subagents_and_slots() -> None:
    caps = FakeBackend().descriptor.capabilities
    assert caps.subagents is True
    assert caps.interactions is None
    assert caps.resource_slots == list(DEFAULT_RESOURCE_SLOTS)
    custom = FakeBackend.from_options(
        {"resource_slots": ["instructions"]}, secrets=SecretResolver(), environ={}
    )
    assert custom.descriptor.capabilities.resource_slots == ["instructions"]


# ------------------------------------------------------------------ rate limit


async def test_install_option_rate_limits_follow_session_started() -> None:
    backend = FakeBackend.from_options(
        {
            "rate_limits": [
                {"window": "five_hour", "status": "allowed", "utilization": 0.4, "resets_at": 99.0},
                {"window": "seven_day", "status": "allowed_warning"},
            ]
        },
        secrets=SecretResolver(),
        environ={},
    )
    sink = ValidatingSink()
    await backend.run(AgentRequest(agent=_agent(), prompt="hi"), sink, CancelToken())
    assert sink.types[:3] == ["agent.session_started", "usage.rate_limit", "usage.rate_limit"]
    five, seven = sink.of("usage.rate_limit")
    assert five == {
        "window": "five_hour",
        "status": "allowed",
        "utilization": 0.4,
        "resets_at": 99.0,
        "overage_status": None,
    }
    assert seven["window"] == "seven_day"
    assert seven["utilization"] is None  # 없는 값은 지어내지 않는다
    assert seven["resets_at"] is None


async def test_rate_limit_relative_reset_uses_injected_clock() -> None:
    backend = FakeBackend(
        rate_limits=[{"window": "five_hour", "resets_in_seconds": 60}], clock=lambda: 1000.0
    )
    sink = ValidatingSink()
    await backend.run(AgentRequest(agent=_agent(), prompt="hi"), sink, CancelToken())
    assert sink.of("usage.rate_limit")[0]["resets_at"] == 1060.0


async def test_no_rate_limit_events_by_default() -> None:
    sink = ValidatingSink()
    await _backend().run(AgentRequest(agent=_agent(), prompt="hi"), sink, CancelToken())
    assert "usage.rate_limit" not in sink.types


def test_rate_limit_option_errors_do_not_echo_values() -> None:
    with pytest.raises(ValueError, match="rate_limits") as info:
        FakeBackend.from_options(
            {"rate_limits": [{"window": "w", "resets_at": 1.0, "resets_in_seconds": 2.0}]},
            secrets=SecretResolver(),
            environ={},
        )
    assert "2.0" not in str(info.value)


# ------------------------------------------------------------------ 묶음 요약


def _bundle() -> ResourceBundle:
    return ResourceBundle(
        slots={
            "instructions": ["팀 지침", "PL 지침"],
            "mcp_servers": {"github": {"env": {"TOKEN": "secret://gh"}}},
            "hooks": [{"event": "Stop"}],
            "custom": "x",
        },
        sources={
            "instructions": [
                BundleSource(ref="team-guide", layer="common"),
                BundleSource(ref="pl-guide", layer="agent"),
                BundleSource(ref="team-guide", layer="graph"),
            ],
            "mcp_servers": [BundleSource(ref="github")],
        },
    )


def test_bundle_summary_counts_refs_and_ignored_slots() -> None:
    summary = bundle_summary(_bundle(), ["instructions", "mcp_servers", "custom"])
    assert summary == (
        "bundle: custom=1; instructions=2 [team-guide, pl-guide]; mcp_servers=1 [github]"
        "; ignored=[hooks]"
    )
    assert "secret://gh" not in summary  # 칸 값은 싣지 않는다
    assert bundle_summary(None, ["instructions"]) == EMPTY_BUNDLE
    assert bundle_summary(ResourceBundle(), ["instructions"]) == EMPTY_BUNDLE


def test_bundle_summary_masks_secret_references() -> None:
    bundle = ResourceBundle(
        slots={"mcp_servers": [{}]},
        sources={"mcp_servers": [BundleSource(ref="secret://vault/key")]},
    )
    assert bundle_summary(bundle, ["mcp_servers"]) == "bundle: mcp_servers=1 [secret://***]"
    assert mask_secret_refs("a secret://x/y, b") == "a secret://***, b"


async def test_echo_bundle_appends_summary_to_response() -> None:
    sink = ValidatingSink()
    agent = _agent(echo_bundle=True, default={"response": "답"})
    result = await _backend().run(
        AgentRequest(agent=agent, prompt="p", bundle=_bundle()), sink, CancelToken()
    )
    expected = (
        "답\n\nbundle: hooks=1; instructions=2 [team-guide, pl-guide]; mcp_servers=1 [github]"
        "; ignored=[custom]"
    )
    assert result.text == expected
    assert sink.of("agent.message")[0]["text"] == expected


async def test_bundle_template_variable_for_lead_and_subagent() -> None:
    sink = ValidatingSink()
    sub = SubagentSpec(
        name="be-node",
        actor="backend-lead",
        bundle=ResourceBundle(
            slots={"instructions": ["be"]},
            sources={"instructions": [BundleSource(ref="be-guide")]},
        ),
    )
    agent = _agent(
        default={
            "delegate": [{"to": "be-node", "response": "$bundle"}],
            "response": "$bundle | $delegate_1",
        }
    )
    result = await _backend().run(
        AgentRequest(agent=agent, prompt="p", subagents=[sub]), sink, CancelToken()
    )
    assert result.text == "bundle: - | bundle: instructions=1 [be-guide]"


# ------------------------------------------------------------------ 소비자와의 모양 맞춤


async def test_delegate_events_build_child_span_in_trace() -> None:
    trace_mod = pytest.importorskip("agent_console_trace")
    sink = ValidatingSink(node_path=["pl-node"])
    await _backend(clock=_Clock()).run(
        AgentRequest(agent=_delegating_agent(), prompt="구현", subagents=SUBAGENTS),
        sink,
        CancelToken(),
    )
    events = [
        sink.events[0].model_copy(
            update={"type": "node.started", "payload": {"status": "running"}}
        ),
        *sink.events,
    ]
    trace = trace_mod.build_trace(events)
    delegated = [s for s in trace.spans if s.node_id in {"be-node", "qa-node"}]
    assert {s.node_id: s.actor for s in delegated} == {
        "be-node": "backend-lead",
        "qa-node": "qa-lead",
    }
    parents = {s.parent_id for s in delegated}
    assert len(parents) == 1
    assert None not in parents
    be = next(s for s in delegated if s.node_id == "be-node")
    assert be.usage is not None
    assert be.usage.total_tokens == 5


# ------------------------------------------------------------------ 상호작용(ask)


def _asking_agent() -> Agent:
    return _agent(
        rules=[
            {
                "ask": [
                    {
                        "kind": "question",
                        "payload": {"text": "$prompt?"},
                        "answer_path": "/answers/q",
                    },
                    {"kind": "tool_permission", "payload": {"tool_name": "Bash"}},
                ],
                "response": "$answer_1|$answer_1_status|$answer_2|$answer_2_status",
            }
        ]
    )


async def test_ask_opens_granted_kinds_and_fills_variables() -> None:
    outcome = InteractionOutcome(
        interaction_id="i1", status="answered", response={"answers": {"q": "pg"}}
    )
    sink = InteractiveSink(lambda _req: outcome)
    grant = InteractionGrant(kinds=["question"])
    req = AgentRequest(agent=_asking_agent(), prompt="db", interactions=grant)
    result = await _backend().run(req, sink, CancelToken())
    # question만 허용: tool_permission은 열지 않는다
    assert [r.kind for r in sink.requests] == ["question"]
    assert sink.requests[0].payload == {"text": "db?"}
    assert result.text == "pg|answered|unavailable|unavailable"


async def test_ask_without_interactive_sink_or_grant_is_unavailable() -> None:
    req = AgentRequest(agent=_asking_agent(), prompt="db")
    result = await _backend().run(req, ValidatingSink(), CancelToken())
    assert result.text == "unavailable|unavailable|unavailable|unavailable"
    expired = InteractiveSink(lambda _req: InteractionOutcome(interaction_id="i", status="expired"))
    granted = req.model_copy(
        update={"interactions": InteractionGrant(kinds=["question", "tool_permission"])}
    )
    result = await _backend().run(granted, expired, CancelToken())
    assert result.text == "expired|expired|expired|expired"
