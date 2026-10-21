"""플러그인 레지스트리 묶음 → 팀 의미 계산에 쓰는 디스크립터 묶음(``TeamCatalog``).

팀 계산(``team_plan``·``node_settings``·``bundle_preview``·``definition_references`` 등)은 노드·엣지
타입 디스크립터, 위임 방식 디스크립터, 백엔드 능력을 인자로 받는다. 서버 모듈들은 이것을 호스트의
플러그인 레지스트리 묶음(``BaseServices.registries``)에서 읽는다. 이 모듈은 그 읽기를 한 곳에 둔다.

레지스트리 묶음의 형식은 모른다(구조적): ``node_types``·``edge_types``·``delegation_strategies``·
``backends`` 속성이 ``list(all_versions=...)``로 항목(``key``·``item``)을 돌려주고 항목의 ``item``에
``descriptor``가 있으면 된다. 없는 속성은 빈 목록이다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts import (
    BackendCapabilities,
    BackendDescriptor,
    DelegationStrategyDescriptor,
    EdgeTypeDescriptor,
    Graph,
    NodeTypeDescriptor,
)
from agent_console_teams._conventions import DEFAULT_CONVENTIONS, TeamConventions
from agent_console_teams._issues import SettingsValidator
from agent_console_teams._plan import TeamPlan, team_plan
from agent_console_teams._preview import PreviewNotes


@dataclass(frozen=True)
class TeamCatalog:
    """팀 계산에 쓰는 디스크립터 묶음.

    Attributes:
        node_types: 노드 타입 디스크립터(모든 버전).
        edge_types: 엣지 타입 디스크립터(모든 버전).
        strategies: 위임 방식 id → 디스크립터.
        backends: 백엔드 id → 능력.
        settings_validators: 백엔드 id → ``validate_settings`` 훅(가진 백엔드만).
        preview_notes: 백엔드 id → ``preview_notes`` 훅(가진 백엔드만, ``bundle_preview(notes=)``).
        backend_descriptors: 백엔드 디스크립터 전체(등록 순서). 사전 점검 오류의 선택지로 쓴다.
    """

    node_types: tuple[NodeTypeDescriptor, ...] = ()
    edge_types: tuple[EdgeTypeDescriptor, ...] = ()
    strategies: Mapping[str, DelegationStrategyDescriptor] = field(default_factory=dict)
    backends: Mapping[str, BackendCapabilities] = field(default_factory=dict)
    settings_validators: Mapping[str, SettingsValidator] = field(default_factory=dict)
    preview_notes: Mapping[str, PreviewNotes] = field(default_factory=dict)
    backend_descriptors: tuple[BackendDescriptor, ...] = ()

    def plan(self, graph: Graph, *, conventions: TeamConventions = DEFAULT_CONVENTIONS) -> TeamPlan:
        """``team_plan(graph, node_types=..., edge_types=...)``."""
        return team_plan(
            graph, node_types=self.node_types, edge_types=self.edge_types, conventions=conventions
        )

    def try_plan(self, graph: Graph) -> TeamPlan | None:
        """해석할 수 없는 그래프면 None(검사·목록 표시용 — 구조 검증은 따로 한다)."""
        try:
            return self.plan(graph)
        except Exception:
            return None


def _entries(registries: Any, name: str, *, all_versions: bool) -> Iterable[Any]:
    registry = getattr(registries, name, None) if registries is not None else None
    listing = getattr(registry, "list", None)
    if not callable(listing):
        return ()
    entries: Iterable[Any] = listing(all_versions=all_versions)
    return entries


def catalog_from_registries(registries: Any) -> TeamCatalog:
    """플러그인 레지스트리 묶음(예: ``agent_console_runtime.Registries``)에서 디스크립터를 읽는다.

    Args:
        registries: 레지스트리 묶음. None이거나 속성이 없으면 그 부분은 비어 있다.
    """
    backends = list(_entries(registries, "backends", all_versions=False))
    return TeamCatalog(
        node_types=tuple(
            e.item.descriptor for e in _entries(registries, "node_types", all_versions=True)
        ),
        edge_types=tuple(
            e.item.descriptor for e in _entries(registries, "edge_types", all_versions=True)
        ),
        strategies={
            e.key: e.item.descriptor
            for e in _entries(registries, "delegation_strategies", all_versions=False)
        },
        backends={e.key: e.item.descriptor.capabilities for e in backends},
        settings_validators={
            e.key: e.item for e in backends if isinstance(e.item, SettingsValidator)
        },
        preview_notes={e.key: e.item for e in backends if isinstance(e.item, PreviewNotes)},
        backend_descriptors=tuple(e.item.descriptor for e in backends),
    )


__all__ = ["TeamCatalog", "catalog_from_registries"]
