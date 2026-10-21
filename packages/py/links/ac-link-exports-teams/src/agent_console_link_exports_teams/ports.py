"""link-exports-teams의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L10).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):
- 필수 ``definitions.lookup``: 정의 읽기.
- 선택 ``workspace.settings``: 지금 공통 설정(공통 층 첨부도 의존으로 넣는다). 없으면 넣지 않는다.

제공:
- ``exports.dependencies``: 정의가 쓰는 정의(팀 구성 → 에이전트·리소스, 에이전트 → 리소스).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import WorkspaceSettings
from agent_console_modkit import PortKey
from agent_console_teams import DefinitionDependency


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


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
EXPORT_DEPENDENCIES: PortKey[ExportDependencies] = PortKey(
    "exports.dependencies", "정의가 쓰는 정의(함께 내보내기)"
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "EXPORT_DEPENDENCIES",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "ExportDependencies",
    "StoredLike",
    "WorkspaceSettingsReader",
]
