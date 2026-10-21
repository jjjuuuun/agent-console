"""정의 사용처 찾기: 어떤 팀 구성·에이전트·공통 설정이 이 정의를 쓰는가(사용처 화면, 삭제 확인).

노드 타입 이름을 모른다. 노드가 정의를 쓰는지는 디스크립터 `binds{kind, field}`로, 리소스 첨부는
설정 층의 `resources[].ref`로 판단한다(`TeamConventions`의 키·층 이름).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from agent_console_contracts import (
    Agent,
    DefinitionReference,
    Graph,
    NodeTypeDescriptor,
    WorkspaceSettings,
)
from agent_console_teams._conventions import DEFAULT_CONVENTIONS, TeamConventions

__all__ = ["definition_references"]


def _attachment_refs(value: Any) -> set[str]:
    """`AgentSettings` 모양(모델 또는 dict)의 `resources[].ref` 집합."""
    if value is None:
        return set()
    raw = (
        value.get("resources") if isinstance(value, Mapping) else getattr(value, "resources", None)
    )
    refs: set[str] = set()
    for item in raw or ():
        ref = item.get("ref") if isinstance(item, Mapping) else getattr(item, "ref", None)
        if isinstance(ref, str):
            refs.add(ref)
    return refs


def definition_references(
    kind: str,
    id: str,
    *,
    graphs: Iterable[Graph] = (),
    agents: Iterable[Agent] = (),
    workspace: WorkspaceSettings | None = None,
    node_types: Iterable[NodeTypeDescriptor] = (),
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
    graph_kind: str = "graph",
    agent_kind: str | None = None,
    settings_kind: str = "settings",
) -> list[DefinitionReference]:
    """정의 `kind/id`를 쓰는 곳 목록.

    - 팀 구성: `binds.kind == kind`인 노드의 `config[binds.field] == id`(노드 id 목록, 층 없음).
    - `kind`가 리소스 종류(`conventions.resource_kind`)이면 설정 층 첨부도 찾는다:
      팀 구성 층(`graph.settings.resources`), 노드 층(노드 config `settings.resources`),
      에이전트 층(정의의 `resources`), 공통 층(`workspace.agent_defaults.resources`).
      같은 팀 구성에서 여러 곳이면 층마다 한 항목씩 나온다.

    Args:
        kind, id: 찾을 정의 종류 이름과 id.
        graphs, agents, workspace: 찾아볼 정의.
        node_types: 노드 타입 디스크립터(`binds` 근거).
        graph_kind / agent_kind / settings_kind: 결과 `DefinitionReference.kind`에 쓸 종류 이름
            (`agent_kind` 생략 = `conventions.agent_kind`).

    Returns:
        팀 구성(입력 순서) → 에이전트 → 공통 설정 순.
    """
    c = conventions
    binds = {d.id: d.binds for d in node_types if d.binds is not None}
    is_resource = kind == c.resource_kind
    out: list[DefinitionReference] = []
    for graph in graphs:
        bound: list[str] = []
        node_layer: list[str] = []
        for node in graph.nodes:
            b = binds.get(node.type)
            if b is not None and b.kind == kind and node.config.get(b.field) == id:
                bound.append(node.id)
            if is_resource and id in _attachment_refs(node.config.get(c.node_settings_key)):
                node_layer.append(node.id)
        if bound:
            out.append(
                DefinitionReference(kind=graph_kind, id=graph.id, name=graph.name, node_ids=bound)
            )
        if is_resource and id in _attachment_refs(graph.settings):
            out.append(
                DefinitionReference(
                    kind=graph_kind, id=graph.id, name=graph.name, layer=c.team_layer.id
                )
            )
        if node_layer:
            out.append(
                DefinitionReference(
                    kind=graph_kind,
                    id=graph.id,
                    name=graph.name,
                    node_ids=node_layer,
                    layer=c.node_layer.id,
                )
            )
    if is_resource:
        for agent in agents:
            if id in _attachment_refs(agent):
                out.append(
                    DefinitionReference(
                        kind=agent_kind or c.agent_kind,
                        id=agent.id,
                        name=agent.name,
                        layer=c.agent_layer.id,
                    )
                )
        if workspace is not None and id in _attachment_refs(workspace.agent_defaults):
            out.append(
                DefinitionReference(kind=settings_kind, id=settings_kind, layer=c.common_layer.id)
            )
    return out
