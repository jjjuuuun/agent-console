"""link-exports-teams의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L10).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):
- 필수 ``definitions.lookup``: 정의 읽기.
- 선택 ``workspace.settings``: 지금 공통 설정(공통 층 첨부도 의존으로 넣는다). 없으면 넣지 않는다.
- 선택 ``settings.scope_layers``(여러 제공자): 범위 id(예: 프로젝트 id) → 공통 바로 아래 설정 층
  (``ScopeLayersSource``). 프로젝트 공간에서 내보낼 때 그 범위 층의 공통 첨부도 의존으로 넣는다.
  없으면 넣지 않는다.

제공:
- ``exports.dependencies``: 정의가 쓰는 정의(팀 구성 → 에이전트·리소스, 에이전트 → 리소스).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import WorkspaceSettings
from agent_console_modkit import PortKey
from agent_console_teams import DefinitionDependency, Layer


class StoredLike(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기. 없으면 저장소 예외(``NotFound`` 등)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...


@runtime_checkable
class ExportDependencies(Protocol):
    """``exports.dependencies`` 모양."""

    def dependencies(self, kind: str, id: str) -> Sequence[DefinitionDependency]: ...


class ScopeLayersLike(Protocol):
    """``ScopeLayersSource.scope_layers`` 결과 모양(경고는 이 연동이 쓰지 않는다)."""

    @property
    def layers(self) -> Sequence[Layer]: ...


@runtime_checkable
class ScopeLayersSource(Protocol):
    """``settings.scope_layers`` 모양: 범위 id → 설정 층(이 연동은 범위의 뜻을 모른다)."""

    def scope_layers(self, scope_id: str) -> ScopeLayersLike: ...


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
EXPORT_DEPENDENCIES: PortKey[ExportDependencies] = PortKey(
    "exports.dependencies", "정의가 쓰는 정의(함께 내보내기)"
)
SCOPE_LAYERS: PortKey[ScopeLayersSource] = PortKey(
    "settings.scope_layers", "범위 id → 설정 층(예: 프로젝트 층)", multi=True
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "EXPORT_DEPENDENCIES",
    "SCOPE_LAYERS",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "ExportDependencies",
    "ScopeLayersLike",
    "ScopeLayersSource",
    "StoredLike",
    "WorkspaceSettingsReader",
]
