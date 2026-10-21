"""정의가 **쓰는** 정의 찾기(사용처 찾기의 반대 방향): 내보내기·프리셋 적용처럼 정의 하나와 함께
가져가야 할 에이전트·리소스·자식 팀 구성 목록.

노드 타입·연결 종류 이름을 모른다. 에이전트 노드는 계획의 `agent_refs`(디스크립터 `binds`),
중첩 팀 노드는 `team_refs`·`team_versions`(디스크립터 `binds.kind == team_kind`),
리소스 연결은 `attachments_of`, 설정 층 첨부는 `resources[]`(`TeamConventions` 키)로 찾는다.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import Agent, ResourceAttachment, WorkspaceSettings
from agent_console_teams._attachments import _list, _settings_list
from agent_console_teams._conventions import DEFAULT_CONVENTIONS, TeamConventions
from agent_console_teams._plan import TeamPlan

__all__ = ["DefinitionDependency", "agent_dependencies", "graph_dependencies"]


@dataclass(frozen=True, slots=True)
class DefinitionDependency:
    """함께 쓰이는 정의 하나.

    Attributes:
        kind / id: 정의 종류 이름과 id.
        node_id: 팀 구성 안에서 이 정의가 묶인 노드(에이전트 노드) 또는 첨부된 노드(노드 층·리소스
            연결). 팀 전체·공통 층이면 None.
        shared: 팀 구성 층·공통 층 첨부(모든 구성원에게 적용).
        mode: 첨부 방식(`add`·`replace`·`remove`, 에이전트 노드는 `add`).
        config_override: 첨부의 리소스 config 덮어쓰기.
        version: 고정한 버전(중첩 팀 노드의 자식 팀 구성 버전 해시). 없으면 최신.
    """

    kind: str
    id: str
    node_id: str | None = None
    shared: bool = False
    mode: str = "add"
    config_override: Mapping[str, Any] | None = None
    version: str | None = None


def _attachments(
    value: Any, *, kind: str, node_id: str | None = None, shared: bool = False
) -> Iterator[DefinitionDependency]:
    for placed in _list(_settings_list(value), ""):
        yield _dependency(placed.attachment, kind=kind, node_id=node_id, shared=shared)


def _dependency(
    att: ResourceAttachment, *, kind: str, node_id: str | None, shared: bool
) -> DefinitionDependency:
    return DefinitionDependency(
        kind=kind,
        id=att.ref,
        node_id=node_id,
        shared=shared,
        mode=att.mode,
        config_override=dict(att.config_override) if att.config_override else None,
    )


def graph_dependencies(
    plan: TeamPlan,
    *,
    workspace: WorkspaceSettings | None = None,
    conventions: TeamConventions | None = None,
) -> list[DefinitionDependency]:
    """팀 구성이 쓰는 정의: 노드마다(그래프 순서) 묶인 에이전트 → 중첩 팀 노드의 자식 팀 구성
    (종류 `team_kind`, 고정 버전은 `version`) → 노드 층 첨부 → 리소스 연결 첨부, 그다음 팀 구성 층
    첨부·공통 층 첨부(`shared`). 에이전트 정의 자신의 첨부·자식 팀 구성 안의 정의는 넣지 않는다
    (`agent_dependencies`, 자식에 다시 부른다). 같은 항목이 여러 번 나올 수 있다(쓰는 쪽이 고른다).
    """
    c = conventions or plan.conventions or DEFAULT_CONVENTIONS
    out: list[DefinitionDependency] = []
    for node in plan.graph.nodes:
        agent_id = plan.agent_refs.get(node.id)
        if agent_id is not None:
            out.append(DefinitionDependency(kind=c.agent_kind, id=agent_id, node_id=node.id))
        team_id = plan.team_refs.get(node.id)
        if team_id is not None:
            out.append(
                DefinitionDependency(
                    kind=c.team_kind,
                    id=team_id,
                    node_id=node.id,
                    version=plan.team_versions.get(node.id),
                )
            )
        out.extend(
            _attachments(
                node.config.get(c.node_settings_key), kind=c.resource_kind, node_id=node.id
            )
        )
        for att in plan.attachments_of.get(node.id, ()):
            out.append(
                _dependency(att.attachment, kind=c.resource_kind, node_id=node.id, shared=False)
            )
    out.extend(_attachments(plan.graph.settings, kind=c.resource_kind, shared=True))
    if workspace is not None:
        out.extend(_attachments(workspace.agent_defaults, kind=c.resource_kind, shared=True))
    return out


def agent_dependencies(
    agent: Agent,
    *,
    workspace: WorkspaceSettings | None = None,
    conventions: TeamConventions = DEFAULT_CONVENTIONS,
) -> list[DefinitionDependency]:
    """에이전트가 쓰는 정의: 에이전트 층 첨부, 그다음 공통 층 첨부(`shared`)."""
    out = list(_attachments(agent, kind=conventions.resource_kind))
    if workspace is not None:
        out.extend(
            _attachments(workspace.agent_defaults, kind=conventions.resource_kind, shared=True)
        )
    return out
