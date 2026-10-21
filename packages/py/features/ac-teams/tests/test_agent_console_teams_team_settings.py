"""5.2R.34: 팀 구성 수준 유효 설정 `team_settings`(공통 → 범위 층 → 팀 구성)와
`resolve_backends(scope_layers=)`(범위 층의 백엔드도 사전 점검에 반영)."""

from __future__ import annotations

import pytest

from agent_console_contracts import Graph, WorkspaceSettings
from agent_console_teams import Layer, resolve_backends, team_plan, team_settings
from agent_console_teams.testing import KITS, Kit

IDS = ["default", "renamed"]
WS = WorkspaceSettings.model_validate({"agent_defaults": {"working_directory": "/common"}})
SCOPE = Layer("scope", "범위", {"working_directory": "/proj", "backend": "b-scope"}, "project:p")


def _graph(k: Kit, settings: dict[str, object] | None = None) -> Graph:
    return k.graph(
        [k.person(), k.worker("lead", who="pl")],
        [k.edge("m1", "entry", "me", "lead"), k.edge("a1", "exit", "lead", "me")],
        settings=settings,
    )


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_team_settings_layers(k: Kit) -> None:
    graph = _graph(k)
    found = team_settings(graph, WS)
    assert found.effective.value.working_directory == "/common"
    scoped = team_settings(graph, WS, scope_layers=[SCOPE])
    assert scoped.effective.value.working_directory == "/proj"
    assert scoped.effective.provenance["/working_directory"] == "scope"
    teamed = team_settings(_graph(k, {"working_directory": "/team"}), WS, scope_layers=[SCOPE])
    assert teamed.effective.value.working_directory == "/team"  # 팀 구성이 범위 층을 이긴다
    assert team_settings(None, None).effective.value.working_directory is None


@pytest.mark.parametrize("k", KITS, ids=IDS)
def test_resolve_backends_sees_scope_layer(k: Kit) -> None:
    plan = team_plan(_graph(k), node_types=k.node_types, edge_types=k.edge_types)
    assert resolve_backends(plan, workspace=WS) == {"lead": None}
    assert resolve_backends(plan, workspace=WS, scope_layers=[SCOPE]) == {"lead": "b-scope"}
