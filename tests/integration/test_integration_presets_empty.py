"""프리셋 통합: 프리셋 없이 동작(빈 프리셋 경로 + 빈 workspace에서 정의 생성·검증·실행).

3R.3에서 ac-presets 테스트에서 옮겼다(패키지는 저장소의 다른 폴더를 보지 않는다, P5).

설치된 실제 플러그인(entry point)으로 서버 없이 실행 스택을 조립한다(서버 조립의 최소 흉내):
레지스트리(노드·연결·위임 방식·상호작용 종류·백엔드) + 리소스 종류 → 정의 저장소 → 런타임
(+ 중첩 팀 조회·자식 Run 준비자, 5R.15). 적용은 서버처럼 쓰는 정의부터
(`definitions.dependencies` 제공 구현 `TeamDocumentDependencies`). 프리셋 내용(에이전트 이름·
문구 등)은 여기 없다 — 프리셋 검사는 프리셋 파일(samples)에서 읽는다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import (
    Agent,
    Graph,
    Interaction,
    Issue,
    NodeRun,
    Resource,
    Run,
    RunEvent,
    WorkspaceSettings,
)
from agent_console_link_definitions_teams import TeamDocumentDependencies
from agent_console_nodes_core import (
    AGENT_LOOKUP,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    RUN_FILES_ROOT,
    TEAM_LOOKUP,
    WORKSPACE_SETTINGS,
    FunctionResources,
)
from agent_console_presets import (
    ItemDependencies,
    discover_presets,
)
from agent_console_resources import load_resource_types
from agent_console_runtime import (
    ChildRunPreparation,
    ChildRunRequest,
    GraphRuntime,
    Registries,
    Services,
    edge_type_descriptors,
    load_registries,
    node_type_descriptors,
    port_resolver,
)
from agent_console_store import DefinitionStore, FileDefinitionStore, InMemoryStorage, NotFound
from agent_console_teams import catalog_from_registries, team_plan, validate_team


@dataclass
class Stack:
    """서버 없이 조립한 실행 스택."""

    registries: Registries
    defs: DefinitionStore
    state_dir: Path
    storage: InMemoryStorage = field(default_factory=InMemoryStorage)

    def lookup_agent(self, agent_id: str) -> Agent | None:
        try:
            return self.defs.get("agent", agent_id).model(Agent)
        except NotFound:
            return None

    def lookup_resource(self, resource_id: str) -> Resource | None:
        try:
            return self.defs.get("resource", resource_id).model(Resource)
        except NotFound:
            return None

    def lookup_team(self, graph_id: str, version: str | None) -> Graph | None:
        """중첩 팀 노드의 팀 구성 조회(`TEAM_LOOKUP`, 서버에서는 link-runs-teams).

        버전 = 저장소 버전 해시."""
        try:
            stored = self.defs.get("graph", graph_id)
        except NotFound:
            return None
        if version is not None and stored.version_hash != version:
            return None
        return stored.model(Graph)

    def workspace(self) -> WorkspaceSettings:
        try:
            return self.defs.get("settings", "settings").model(WorkspaceSettings)
        except NotFound:
            return WorkspaceSettings()

    def services(self) -> Services:
        resources = FunctionResources(
            self.lookup_resource, lambda r: self.defs.read_content("resource", r.id)
        )
        return Services(
            {
                AGENT_LOOKUP: self.lookup_agent,
                WORKSPACE_SETTINGS: self.workspace(),
                RESOURCE_LOOKUP: resources,
                RUN_FILES_ROOT: str(self.state_dir),
                TEAM_LOOKUP: self.lookup_team,
            }
        )

    def prepare_child(self, request: ChildRunRequest) -> ChildRunPreparation:
        """자식 Run 준비(서버에서는 mod-runs가 일반 Run 준비로): 팀 규칙의 허용 상호작용."""
        plan = team_plan(
            request.graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
        )
        return ChildRunPreparation(interaction_grants=dict(plan.grants))

    def runtime(self) -> GraphRuntime:
        return GraphRuntime(
            self.registries,
            self.storage,
            services=self.services(),
            child_preparer=self.prepare_child,
        )

    def dependencies(self) -> ItemDependencies:
        """적용 순서용 의존 함수(서버의 `definitions.dependencies`와 같은 구현)."""
        provider = TeamDocumentDependencies(lambda: catalog_from_registries(self.registries))
        return lambda kind, doc: [(d.kind, d.id) for d in provider.dependencies_of(kind, doc)]

    def graph_issues(self, graph: Graph) -> list[Issue]:
        """팀 구성 검증(`validate_team`, 구조 검사 포함) + 런타임 노드 의미 검증."""
        agents = {
            i: a for i in self.defs.list_ids("agent") if (a := self.lookup_agent(i)) is not None
        }
        team = validate_team(
            graph,
            node_types=node_type_descriptors(self.registries),
            edge_types=edge_type_descriptors(self.registries),
            strategies=[e.item.descriptor for e in self.registries.delegation_strategies.list()],
            agents=agents,
            workspace=self.workspace(),
            backends={
                e.key: e.item.descriptor.capabilities for e in self.registries.backends.list()
            },
            resolve_ports=port_resolver(self.registries),
            teams=self.lookup_team,
        )
        return [*team, *self.runtime().validate(graph)]

    async def run(self, graph: Graph, text: str, responses: list[dict[str, Any]]) -> Run:
        """채팅 메시지 하나로 실행하고, 열리는 상호작용(자식 Run 것 포함)에 `responses`를 순서대로
        답한다. 자식 Run 요청은 그 Run id로 응답한다(서버 `POST /runs/{interaction.run_id}/…`)."""
        runtime = self.runtime()
        handle = await runtime.start(graph, {"text": text})
        queue = list(responses)
        while not handle.done():
            pending = [i for i in runtime.pending() if _in_run(i, handle.run_id)]
            if pending and queue:
                await runtime.respond(pending[0].run_id, pending[0].id, queue.pop(0))
            await asyncio.sleep(0.005)
        assert queue == [], "쓰지 않은 응답이 남았다(상호작용이 열리지 않음)"
        return await handle.wait()

    def node_runs(self, run: Run) -> dict[str, NodeRun]:
        return {nr.node_id: nr for nr in self.storage.runs.list_node_runs(run.id)}

    def events(self, run: Run, type: str) -> list[RunEvent]:
        return [e for e in self.storage.events.list(run.id) if e.type == type]


def _in_run(item: Interaction, run_id: str) -> bool:
    return run_id in (item.run_id, item.root_run_id)


def make_stack(workspace: Path) -> Stack:
    registries = Registries()
    reports = load_registries(registries)
    assert all(r.ok for r in reports), [r for r in reports if not r.ok]
    load_resource_types(registries.extension(RESOURCE_TYPES_EXTENSION))
    return Stack(registries, FileDefinitionStore(workspace), workspace / ".state" / "runs")


# ---------------------------------------------------------------- 프리셋 없이 동작 (R0.1·R0.2 회귀)


def test_discovery_without_presets(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    found = discover_presets([empty, tmp_path / "missing"])
    assert found.presets == []
    assert found.problems == []
    assert discover_presets([]).presets == []


async def test_works_without_any_preset(tmp_path: Path) -> None:
    """빈 workspace + 빈 프리셋 경로: 레지스트리 로드 → 코드로 정의 생성 → 검증 → 실행."""
    assert discover_presets([tmp_path / "no-presets"]).presets == []
    stack = make_stack(tmp_path)
    assert stack.defs.list_ids("graph") == []
    assert stack.defs.list_ids("agent") == []
    with pytest.raises(NotFound):
        stack.defs.get("settings", "settings")
    await _build_and_run_from_scratch(stack)


async def _build_and_run_from_scratch(stack: Stack) -> None:
    """코드로 정의 생성 → 검증 → 실행(프리셋 없이)."""
    # 설정 데이터 데모용 백엔드(플러그인 id)를 공통 층 백엔드로 고른다.
    assert "fake" in stack.registries.backends
    stack.defs.save("settings", {"agent_defaults": {"backend": "fake"}})
    stack.defs.create(
        "agent",
        {"id": "a1", "name": "A1", "backend_options": {"default": {"response": "A1:$prompt"}}},
    )
    stack.defs.create(
        "agent",
        {"id": "a2", "name": "A2", "backend_options": {"default": {"response": "A2:$prompt"}}},
    )
    stack.defs.create(
        "graph",
        {
            "id": "g",
            "name": "G",
            "nodes": [
                {"id": "you", "type": "user"},
                {"id": "n1", "type": "agent", "config": {"agent_ref": "a1"}},
                {"id": "n2", "type": "agent", "config": {"agent_ref": "a2"}},
            ],
            "edges": [
                _edge("m", "you", "says", "n1", "in", "message"),
                _edge("h", "n1", "out", "n2", "in", "handoff"),
                _edge("r", "n2", "out", "you", "hears", "reply"),
            ],
        },
    )
    graph = stack.defs.get("graph", "g").model(Graph)
    assert [i for i in stack.graph_issues(graph) if i.severity == "error"] == []
    run = await stack.run(graph, "hello", [])
    assert run.status == "completed", run.error
    replies = stack.events(run, "run.reply")
    assert [dict(e.payload)["text"] for e in replies] == ["A2:A1:hello"]


def _edge(eid: str, src: str, sp: str, dst: str, tp: str, kind: str) -> dict[str, Any]:
    return {
        "id": eid,
        "source": {"node": src, "port": sp},
        "target": {"node": dst, "port": tp},
        "kind": kind,
    }
