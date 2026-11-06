"""5.7R.33y: Run의 정의 조회 출처.

실행 환경 ``definitions``(노드 서비스 공급)·노드 서비스 ``RUN_DEFINITIONS``(검사·사전 점검)가 있으면
에이전트·팀 구성(고정 버전)·리소스(본문·여러 파일) 조회가 그 출처 하나로만 간다(조회 감시).
없으면 지금처럼 모듈이 받은 포트로 찾는다.
"""

from __future__ import annotations

import doctest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_contracts import Graph
from agent_console_link_runs_teams import RUN_DEFINITIONS, TeamRules, lookups_from, sources
from agent_console_nodes_core import AGENT_LOOKUP, RESOURCE_LOOKUP, TEAM_LOOKUP
from agent_console_runtime import Registries, Services, load_registries
from agent_console_store import DEFAULT_KINDS, InMemoryDefinitionStore
from agent_console_teams import catalog_from_registries


def _graph(graph_id: str, agent_ref: str) -> dict[str, Any]:
    return {
        "id": graph_id,
        "name": graph_id,
        "nodes": [
            {"id": "you", "type": "user", "label": "나"},
            {"id": "n1", "type": "agent", "label": "응답자", "config": {"agent_ref": agent_ref}},
        ],
        "edges": [
            {
                "id": "m1",
                "source": {"node": "you", "port": "says"},
                "target": {"node": "n1", "port": "in"},
                "kind": "message",
            },
            {
                "id": "r1",
                "source": {"node": "n1", "port": "out"},
                "target": {"node": "you", "port": "hears"},
                "kind": "reply",
            },
        ],
    }


class Spy:
    """정의 저장소 읽기 감시(메서드 이름, 종류, id)."""

    def __init__(self) -> None:
        self.store = InMemoryDefinitionStore(DEFAULT_KINDS)
        self.calls: list[tuple[str, str, str]] = []

    def __getattr__(self, name: str) -> Any:
        method = getattr(self.store, name)

        def call(kind: str, id: str, *rest: Any) -> Any:
            self.calls.append((name, kind, id))
            return method(kind, id, *rest)

        return call


def _stores() -> tuple[Spy, Spy]:
    library, project = Spy(), Spy()
    library.store.create("agent", {"id": "helper", "name": "라이브러리"})
    library.store.create("resource", {"id": "doc", "type": "text", "name": "라이브러리"})
    project.store.create("agent", {"id": "helper", "name": "프로젝트", "backend": "fake-agent"})
    created = project.store.create("resource", {"id": "doc", "type": "text", "name": "프로젝트"})
    project.store.write_content(
        "resource", "doc", b"project body", file="body.md", expected_version=created.version_hash
    )
    project.store.create("graph", _graph("team", "helper"))
    library.calls.clear()
    project.calls.clear()
    return library, project


@dataclass(frozen=True)
class _Env:
    working_directory: Path
    run_files_root: Path
    definitions: Any = None


def _no_library_graph(graph_id: str, version: str | None) -> Graph:
    raise LookupError(graph_id)  # 라이브러리 팀 구성 읽기(쓰이면 "없음")


def _rules(library: Spy) -> TeamRules:
    registries = Registries()
    load_registries(registries)
    library_resources = lookups_from(library).resources
    return TeamRules(
        library,
        catalog=lambda: catalog_from_registries(registries),
        registries=lambda: registries,
        resources=lambda: library_resources,
        graphs=lambda: _no_library_graph,
    )


def test_node_services_bind_to_run_source_only() -> None:
    library, project = _stores()
    rules = _rules(library)
    services = rules.services(_Env(Path("/w"), Path("/r"), definitions=project))
    agent = services[AGENT_LOOKUP]("helper")
    assert agent is not None
    assert agent.name == "프로젝트"
    assert services[AGENT_LOOKUP]("ghost") is None
    resources = services[RESOURCE_LOOKUP]
    found = resources.get_resource("doc")
    assert found is not None
    assert found.name == "프로젝트"
    assert resources.read_content(found) == b"project body"
    assert resources.read_files(found) is not None
    team = services[TEAM_LOOKUP]("team", None)
    assert team is not None
    assert team.id == "team"
    version = project.store.get("graph", "team").version_hash
    pinned = services[TEAM_LOOKUP]("team", version)
    assert pinned is not None
    assert pinned.id == "team"
    assert ("get_version", "graph", "team") in project.calls
    assert services[TEAM_LOOKUP]("missing", None) is None
    assert library.calls == []  # 라이브러리로 넘어가 찾지 않았다


def test_without_source_services_use_module_ports() -> None:
    library, project = _stores()
    services = _rules(library).services(_Env(Path("/w"), Path("/r")))
    agent = services[AGENT_LOOKUP]("helper")
    assert agent is not None
    assert agent.name == "라이브러리"
    assert project.calls == []


def test_checks_and_preflight_follow_run_definitions_service() -> None:
    library, project = _stores()
    rules = _rules(library)
    graph = Graph.model_validate(_graph("team", "helper"))
    # 라이브러리 helper는 백엔드가 없어 막히고, 프로젝트 helper는 백엔드가 있어 통과한다
    blocked = rules.preflight(graph, Services())
    assert blocked is not None
    assert blocked.code == "backend.unresolved"
    scoped = Services({RUN_DEFINITIONS: project})
    assert rules.preflight(graph, scoped) is None
    library.calls.clear()
    project.calls.clear()
    rules.check(graph, [], scoped, strict=True)
    assert ("get", "agent", "helper") in project.calls
    assert library.calls == []
    # 출처에 없는 에이전트는 "없음"(라이브러리에만 있는 참조 → 실행 실패 쪽으로)
    other = Spy()
    issues = rules.check(graph, [], Services({RUN_DEFINITIONS: other}), strict=True)
    assert [i.code for i in issues] == ["team.agent_not_found"]
    assert library.calls == []


def test_resource_lookup_is_off_when_resources_feature_is_off() -> None:
    library, project = _stores()
    registries = Registries()
    load_registries(registries)
    rules = TeamRules(library, catalog=lambda: catalog_from_registries(registries))
    services = rules.services(_Env(Path("/w"), Path("/r"), definitions=project))
    assert RESOURCE_LOOKUP not in services
    assert TEAM_LOOKUP not in services


def test_sources_doctest() -> None:
    assert doctest.testmod(sources).failed == 0
