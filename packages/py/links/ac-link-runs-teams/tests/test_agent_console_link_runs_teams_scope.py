"""5.2R.34: 노드 서비스 ``SCOPE_LAYERS``(실행 범위 층)를 사전 점검·준비가 쓰고, 준비 결과 Run 맥락에
유효 작업 폴더(``cwd``)를 싣는다. 이 연동은 범위의 뜻(프로젝트)을 모른다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import Graph, WorkspaceSettings
from agent_console_link_runs_teams import RUN_CONTEXT_CWD, TeamRules, TeamRunPreparation
from agent_console_nodes_core import SCOPE_LAYERS, WORKING_DIRECTORY
from agent_console_runtime import Registries, Services, load_registries
from agent_console_store import NotFound
from agent_console_teams import Layer, catalog_from_registries

AGENT = {"id": "helper", "name": "도우미", "backend_options": {"default": {"response": "답"}}}
GRAPH = {
    "id": "solo",
    "name": "solo",
    "nodes": [
        {"id": "you", "type": "user", "label": "나"},
        {"id": "n1", "type": "agent", "label": "응답자", "config": {"agent_ref": "helper"}},
    ],
    "edges": [
        {
            "id": "m1",
            "source": {"node": "you", "port": "says"},
            "target": {"node": "n1", "port": "in"},
            "kind": "message",
            "config": {},
        },
        {
            "id": "r1",
            "source": {"node": "n1", "port": "out"},
            "target": {"node": "you", "port": "hears"},
            "kind": "reply",
            "config": {},
        },
    ],
}
SCOPE = Layer(
    "project", "프로젝트", {"working_directory": "/proj", "backend": "fake-agent"}, "project:p"
)


class _Lookup:
    def __init__(self, agents: Mapping[str, Mapping[str, Any]]) -> None:
        self._agents = agents

    def get(self, kind: str, id: str) -> Any:
        if id not in self._agents:
            raise NotFound(kind, id)
        return type("Stored", (), {"document": dict(self._agents[id])})()

    def get_version(self, kind: str, id: str, version_hash: str) -> Any:  # pragma: no cover
        raise NotImplementedError


def _rules(workspace: WorkspaceSettings | None = None, **options: Any) -> TeamRules:
    registries = Registries()
    load_registries(registries)
    return TeamRules(
        _Lookup({"helper": AGENT}),
        catalog=lambda: catalog_from_registries(registries),
        registries=lambda: registries,
        workspace=lambda: workspace,
        **options,
    )


def test_prepare_puts_run_working_directory_into_run_context() -> None:
    rules, graph = _rules(), Graph.model_validate(GRAPH)
    plain = rules.prepare(graph, Services({WORKING_DIRECTORY: "/srv"}))
    assert isinstance(plain, TeamRunPreparation)
    assert plain.run_context == {RUN_CONTEXT_CWD: "/srv"}
    scoped = rules.prepare(graph, Services({WORKING_DIRECTORY: "/srv", SCOPE_LAYERS: [SCOPE]}))
    assert scoped.run_context == {"cwd": "/proj"}
    assert scoped.grants == plain.grants  # 나머지 준비 값은 그대로
    common = WorkspaceSettings.model_validate({"agent_defaults": {"working_directory": "/c"}})
    assert (
        _rules(common).run_working_directory(graph, Services({WORKING_DIRECTORY: "/srv"})) == "/c"
    )
    assert _rules().prepare(graph, Services()).run_context == {}
    off = _rules(cwd_key=None).prepare(graph, Services({WORKING_DIRECTORY: "/srv"}))
    assert off.run_context == {}


def test_preflight_sees_backend_from_scope_layer() -> None:
    rules, graph = _rules(), Graph.model_validate(GRAPH)
    blocked = rules.preflight(graph, Services())
    assert blocked is not None
    assert blocked.code == "backend.unresolved"
    assert rules.preflight(graph, Services({SCOPE_LAYERS: [SCOPE]})) is None
