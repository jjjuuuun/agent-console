"""사용처 찾기: 노드 `binds`·설정 층 리소스 첨부(임의 이름 노드 타입)."""

from __future__ import annotations

import pytest

from agent_console_contracts import (
    Agent,
    AgentDefaults,
    ResourceAttachment,
    WorkspaceSettings,
)
from agent_console_teams import definition_references
from agent_console_teams.testing import KITS, Kit


@pytest.mark.parametrize("k", KITS)
def test_agent_and_resource_references(k: Kit) -> None:
    graph = k.graph(
        [
            k.person(),
            k.worker("a", "alice", settings={"resources": [{"ref": "doc"}]}),
            k.worker("b", "alice"),
            k.worker("c", "carol"),
            k.material("m", "doc"),
        ],
        [k.edge("e1", "entry", "me", "a")],
        settings={"resources": [{"ref": "doc"}]},
    )
    other = k.graph([k.worker("x", "bob")], []).model_copy(update={"id": "other"})
    agents = [
        Agent(id="alice", name="A", resources=[ResourceAttachment(ref="doc")]),
        Agent(id="bob", name="B"),
    ]
    workspace = WorkspaceSettings(
        agent_defaults=AgentDefaults(resources=[ResourceAttachment(ref="doc")])
    )

    refs = definition_references(
        "agent", "alice", graphs=[graph, other], agents=agents, node_types=k.node_types
    )
    assert [(r.kind, r.id, r.node_ids, r.layer) for r in refs] == [
        ("graph", "team", ["a", "b"], None)
    ]

    refs = definition_references(
        "resource",
        "doc",
        graphs=[graph, other],
        agents=agents,
        workspace=workspace,
        node_types=k.node_types,
    )
    assert [(r.kind, r.id, r.node_ids, r.layer) for r in refs] == [
        ("graph", "team", ["m"], None),
        ("graph", "team", [], "team"),
        ("graph", "team", ["a"], "node"),
        ("agent", "alice", [], "agent"),
        ("settings", "settings", [], "common"),
    ]
    assert definition_references("resource", "nope", graphs=[graph], node_types=k.node_types) == []
