"""혼합 위임 합치기(design §5R.6, 5R.9): `DelegationContribution`·`merge_contributions`·
`apply_contribution`·선택 프로토콜 `ComposableDelegation`."""

from __future__ import annotations

from typing import Any

from agent_console_contracts import Agent
from agent_console_runtime import (
    AgentRequest,
    BackendEventSink,
    ComposableDelegation,
    DelegationContribution,
    DelegationIssueCodes,
    HostTool,
    HostToolResult,
    SubagentSpec,
    apply_contribution,
    merge_contributions,
)
from agent_console_runtime.testing import InlineStrategy


async def _ok(arguments: dict[str, Any]) -> HostToolResult:
    return HostToolResult(text="ok")


def _tool(name: str) -> HostTool:
    return HostTool(name=name, description="d", input_schema={"type": "object"}, handler=_ok)


def test_merge_concatenates_in_order_and_chains_sink_wrappers() -> None:
    seen: list[str] = []

    def wrapper(tag: str) -> Any:
        def wrap(sink: BackendEventSink) -> BackendEventSink:
            seen.append(tag)
            return sink

        return wrap

    a = DelegationContribution(
        subagents=[SubagentSpec(name="qa")], options={"x": 1}, wrap_sink=wrapper("a")
    )
    b = DelegationContribution(host_tools=[_tool("delegate")], options={"x": 1, "y": 2})
    c = DelegationContribution(wrap_sink=wrapper("c"))
    merged, issues = merge_contributions([a, b, c])
    assert issues == []
    assert [s.name for s in merged.subagents] == ["qa"]
    assert [t.name for t in merged.host_tools] == ["delegate"]
    assert merged.options == {"x": 1, "y": 2}
    assert merged.wrap_sink is not None
    sink: Any = object()
    assert merged.wrap_sink(sink) is sink
    assert seen == ["a", "c"]
    assert merge_contributions([b])[0].wrap_sink is None


def test_merge_reports_name_and_option_conflicts() -> None:
    a = DelegationContribution(
        subagents=[SubagentSpec(name="qa")], host_tools=[_tool("delegate")], options={"x": 1}
    )
    b = DelegationContribution(
        subagents=[SubagentSpec(name="qa")], host_tools=[_tool("delegate")], options={"x": 2}
    )
    _, issues = merge_contributions([a, b])
    assert [(i.code, i.details) for i in issues] == [
        (DelegationIssueCodes.DUPLICATE_HOST_TOOL_NAMES, {"names": ["delegate"]}),
        (DelegationIssueCodes.DUPLICATE_SUBAGENT_NAMES, {"names": ["qa"]}),
        (DelegationIssueCodes.CONFLICTING_OPTIONS, {"keys": ["x"]}),
    ]
    assert all(i.severity == "error" for i in issues)


def test_apply_appends_and_keeps_request_options() -> None:
    request = AgentRequest(
        agent=Agent(id="lead", name="Lead"),
        prompt="p",
        subagents=[SubagentSpec(name="first")],
        options={"x": "node"},
    )
    contribution = DelegationContribution(
        subagents=[SubagentSpec(name="qa")],
        host_tools=[_tool("delegate")],
        options={"x": "strategy", "y": 1},
    )
    applied = apply_contribution(request, contribution)
    assert [s.name for s in applied.subagents] == ["first", "qa"]
    assert [t.name for t in applied.host_tools] == ["delegate"]
    assert applied.options == {"x": "node", "y": 1}
    assert request.host_tools == []  # 원본은 그대로
    assert "host_tools" not in contribution.model_dump()


def test_composable_protocol_requires_contribute() -> None:
    assert not isinstance(InlineStrategy(), ComposableDelegation)

    class WithContribute(InlineStrategy):
        def contribute(self, plan: Any, ctx: Any) -> DelegationContribution:
            return DelegationContribution()

    assert isinstance(WithContribute(), ComposableDelegation)
