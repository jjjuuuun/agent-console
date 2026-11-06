"""5.7R.34: 기본 노드·연결·위임 방식의 화면 세션 속성은 디스크립터 데이터다."""

from __future__ import annotations

from agent_console_nodes_core import (
    AgentNode,
    AskUserEdge,
    DataEdge,
    DelegateEdge,
    HandoffEdge,
    LoopEdge,
    MessageEdge,
    OnErrorEdge,
    ReplyEdge,
    ResourceNode,
    SdkSubagentsStrategy,
    SubagentEdge,
    TeamNode,
    UserNode,
    UsesEdge,
    WhenEdge,
)


def test_flow_edges_declare_separate_session() -> None:
    for edge in (HandoffEdge, DataEdge, LoopEdge, WhenEdge, OnErrorEdge):
        assert edge.descriptor.scheduling == "flow"
        assert edge.descriptor.session == "separate", edge.descriptor.id


def test_other_edges_leave_session_to_strategy_or_unset() -> None:
    for edge in (SubagentEdge, DelegateEdge, UsesEdge, MessageEdge, ReplyEdge, AskUserEdge):
        assert edge.descriptor.session is None, edge.descriptor.id


def test_sdk_subagents_attributes() -> None:
    d = SdkSubagentsStrategy.descriptor
    assert (d.session, d.backend, d.nestable, d.max_depth) == ("same", "delegator", False, 1)


def test_only_agent_nodes_open_sessions() -> None:
    assert AgentNode.descriptor.opens_session is True
    for node in (UserNode, ResourceNode, TeamNode):
        assert node.descriptor.opens_session is False, node.descriptor.id
