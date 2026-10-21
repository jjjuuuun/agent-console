"""`scope_layers`: 공통 바로 아래에 끼우는 일반 층(예: 프로젝트 층, design §5.2R.6·5.2R.31).

ac-teams는 층의 뜻(프로젝트)을 모른다. 넣지 않으면 지금과 같다.
"""

from __future__ import annotations

import pytest

from agent_console_contracts import Agent, Graph, WorkspaceSettings
from agent_console_settings import Layer
from agent_console_teams import (
    TeamPlan,
    agent_layers,
    effective_settings,
    layers_for,
    merge_rules,
    node_settings,
    resolve_settings,
    team_plan,
)
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]

WS = WorkspaceSettings.model_validate(
    {"agent_defaults": {"model": "m-common", "working_directory": "/common", "tools": ["Read"]}}
)
SCOPE = Layer("scope", "범위", {"working_directory": "/proj", "model": "m-scope"}, "project:p")
AGENT = Agent.model_validate({"id": "pl", "name": "PL", "model": "m-agent"})


def _plan(k: Kit, team_settings: dict[str, object] | None = None) -> TeamPlan:
    graph: Graph = k.graph(
        [k.person(), k.worker("lead", who="pl")],
        [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")],
        settings=team_settings,
    )
    return team_plan(graph, node_types=k.node_types, edge_types=k.edge_types)


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_scope_layer_sits_right_below_common(k: Kit) -> None:
    plan = _plan(k)
    layers = layers_for(plan, "lead", agent=AGENT, workspace=WS, scope_layers=[SCOPE])
    assert [layer.id for layer in layers] == ["common", "scope", "team", "agent", "node"]
    assert layers[1] is SCOPE


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_default_is_unchanged(k: Kit) -> None:
    plan = _plan(k)
    assert layers_for(plan, "lead", agent=AGENT, workspace=WS) == layers_for(
        plan, "lead", agent=AGENT, workspace=WS, scope_layers=()
    )
    assert [layer.id for layer in agent_layers(AGENT, WS)] == ["common", "agent"]


def test_scope_overrides_common_and_lower_layers_override_scope() -> None:
    k = Kit()
    plan = _plan(k, {"model": "m-team"})
    eff = effective_settings(plan, "lead", agents={"pl": AGENT}, workspace=WS, scope_layers=[SCOPE])
    # 작업 폴더: 범위 층이 공통을 이긴다(팀·에이전트·노드는 지정하지 않음)
    assert eff.value.working_directory == "/proj"
    assert eff.provenance["/working_directory"] == "scope"
    # 모델: 아래 층(에이전트)이 범위 층을 이긴다
    assert eff.value.model == "m-agent"
    assert eff.provenance["/model"] == "agent"
    assert [i.id for i in eff.layers] == ["common", "scope", "team", "agent", "node"]
    assert eff.layers[1].source == "project:p"


def test_node_settings_passes_scope_layers_and_several_layers_keep_order() -> None:
    k = Kit()
    plan = _plan(k)
    a = Layer("a", "A", {"model": "m-a"})
    b = Layer("b", "B", {"model": "m-b"})
    ns = node_settings(plan, "lead", workspace=WS, scope_layers=[a, b])
    assert ns.effective.value.model == "m-b"
    assert ns.effective.provenance["/model"] == "b"
    assert [i.id for i in ns.effective.layers][:3] == ["common", "a", "b"]


def test_agent_layers_scope_and_duplicate_id_rejected() -> None:
    layers = agent_layers(AGENT, WS, scope_layers=[SCOPE])
    assert [layer.id for layer in layers] == ["common", "scope", "agent"]
    eff = resolve_settings(layers).effective
    assert eff.value.working_directory == "/proj"
    k = Kit()
    plan = _plan(k)
    clash = Layer("team", "겹침", {})
    with pytest.raises(ValueError, match="겹칩니다"):
        resolve_settings(
            layers_for(plan, "lead", agent=None, workspace=WS, scope_layers=[clash]),
            rules=merge_rules(WS, plan.graph),
        )
