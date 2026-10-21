"""쓰는 정의 찾기(내보내기용): 노드 `binds`·노드 층·리소스 연결·팀 층·공통 층(임의 이름 타입)."""

from __future__ import annotations

import pytest

from agent_console_contracts import (
    Agent,
    AgentDefaults,
    ResourceAttachment,
    WorkspaceSettings,
)
from agent_console_teams import (
    DefinitionDependency,
    agent_dependencies,
    graph_dependencies,
    team_plan,
)
from agent_console_teams.testing import KITS, Kit


@pytest.mark.parametrize("k", KITS)
def test_graph_dependencies(k: Kit) -> None:
    graph = k.graph(
        [
            k.person(),
            k.worker("lead", "alice", settings={"resources": [{"ref": "node-doc"}]}),
            k.worker("helper", "bob"),
            k.material("box", "edge-doc"),
        ],
        [
            k.edge("e1", "entry", "me", "lead"),
            k.edge("r1", "attach", "box", "helper", config_override={"x": 1}),
        ],
        settings={"resources": [{"ref": "team-doc"}, {"ref": "gone", "mode": "remove"}]},
    )
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    workspace = WorkspaceSettings(
        agent_defaults=AgentDefaults(resources=[ResourceAttachment(ref="common-doc")])
    )
    deps = graph_dependencies(plan, workspace=workspace)
    assert deps == [
        DefinitionDependency("agent", "alice", node_id="lead"),
        DefinitionDependency("resource", "node-doc", node_id="lead"),
        DefinitionDependency("agent", "bob", node_id="helper"),
        DefinitionDependency("resource", "edge-doc", node_id="helper", config_override={"x": 1}),
        DefinitionDependency("resource", "team-doc", shared=True),
        DefinitionDependency("resource", "gone", shared=True, mode="remove"),
        DefinitionDependency("resource", "common-doc", shared=True),
    ]
    assert all(d.kind != "resource" or d.id != "common-doc" for d in graph_dependencies(plan))


@pytest.mark.parametrize("k", KITS)
def test_graph_dependencies_include_child_teams(k: Kit) -> None:
    """중첩 팀 노드의 자식 팀 구성(5R.15): 종류 = `team_kind`, 고정 버전은 `version`."""
    graph = k.graph(
        [k.person(), k.worker("lead", "alice"), k.nest("sub", "crew"), k.nest("pin", "crew", "v1")],
        [k.edge("e1", "entry", "me", "lead")],
    )
    plan = team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)
    deps = graph_dependencies(plan)
    team_kind = plan.conventions.team_kind
    assert deps == [
        DefinitionDependency("agent", "alice", node_id="lead"),
        DefinitionDependency(team_kind, "crew", node_id="sub"),
        DefinitionDependency(team_kind, "crew", node_id="pin", version="v1"),
    ]


def test_agent_dependencies() -> None:
    agent = Agent(id="a", name="A", resources=[ResourceAttachment(ref="own")])
    workspace = WorkspaceSettings(
        agent_defaults=AgentDefaults(resources=[ResourceAttachment(ref="common")])
    )
    assert agent_dependencies(agent, workspace=workspace) == [
        DefinitionDependency("resource", "own"),
        DefinitionDependency("resource", "common", shared=True),
    ]
    assert agent_dependencies(Agent(id="b", name="B")) == []
