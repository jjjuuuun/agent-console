"""link-definitions-teams의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L9).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다. 모양은 계약 테스트가 확인한다):
- 필수 ``definitions.lookup``: 정의 읽기(``DefinitionLookup``).
- 선택 ``workspace.settings``: 지금 공통 설정. 없으면 기본값.
- 선택 ``resources.lookup``·``resources.types``: 리소스 조회·종류. 없으면 빈 것(리소스 연결 없음).
- 선택 ``secrets.redact``: 해석한 비밀 값 가리기(묶음 미리보기). 없으면 ``secrets.rules``의 의심
  값 가리기, 그것도 없으면 그대로.
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙.
- 선택 ``settings.scope_layers``(여러 제공자, 5.2R.34): 범위 id(예: 프로젝트 id) → 공통 바로 아래에
  끼울 설정 층·경고(``ScopeLayersSource``). 유효 설정 경로의 ``?project=``가 이것을 쓴다. 없으면
  ``project``를 무시한다(층 없음).

제공:
- ``graphs.entry_labels``: 팀 구성 입구 노드 표시 이름(``mod-definitions`` 목록).
- ``definitions.usages``: 정의가 붙은 곳(``mod-resources`` 목록 ``usage_count``).
- ``definitions.dependencies``: 정의 문서가 쓰는 정의(여러 정의를 쓸 때 쓰는 정의 먼저, 5R.15).
- ``definitions.references``(여러 제공자, X25): 참조 추출 함수 ``(kind, document) -> [(kind, id)]``
  (``mod-projects`` 범위 검사·옮기기 계획, design §UX-P.6, 5.2R.31).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import DefinitionReference, Graph, Issue, WorkspaceSettings
from agent_console_modkit import PortKey
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType
from agent_console_secret_rules import SecretRules
from agent_console_teams import DefinitionDependency, Layer


class StoredLike(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기. 없으면 저장소 예외(``NotFound`` 등)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...

    def list_ids(self, kind: str) -> list[str]: ...


@runtime_checkable
class EntryLabels(Protocol):
    """``graphs.entry_labels`` 모양."""

    def entry_labels(self, graph: Graph) -> list[str] | None: ...


@runtime_checkable
class DefinitionUsages(Protocol):
    """``definitions.usages`` 모양."""

    def references(self, kind: str, id: str) -> Sequence[DefinitionReference]: ...


@runtime_checkable
class DocumentDependencies(Protocol):
    """``definitions.dependencies`` 모양: 문서(저장 전이어도 됨)가 쓰는 정의."""

    def dependencies_of(
        self, kind: str, document: Mapping[str, Any]
    ) -> Sequence[DefinitionDependency]: ...


class ScopeLayersLike(Protocol):
    """``ScopeLayersSource.scope_layers`` 결과 모양."""

    @property
    def layers(self) -> Sequence[Layer]: ...

    @property
    def warnings(self) -> Sequence[Issue]: ...


@runtime_checkable
class ScopeLayersSource(Protocol):
    """``settings.scope_layers`` 모양: 범위 id → 설정 층(이 연동은 범위의 뜻을 모른다)."""

    def scope_layers(self, scope_id: str) -> ScopeLayersLike: ...


type DocumentReferences = Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]]
"""``definitions.references`` 모양(X25): 문서 하나가 쓰는 정의의 ``(종류, id)``.
모르는 종류 = 빈 목록."""

type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
type SecretRulesReader = Callable[[], SecretRules]
type Redactor = Callable[[str], str]

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)
RESOURCES_LOOKUP: PortKey[ResourceLookup] = PortKey("resources.lookup", "리소스 정의·본문 조회")
RESOURCE_TYPES: PortKey[Registry[ResourceType]] = PortKey("resources.types", "리소스 종류")
SECRET_REDACT: PortKey[Redactor] = PortKey("secrets.redact", "해석한 비밀 값 가리기")
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
GRAPH_ENTRY_LABELS: PortKey[EntryLabels] = PortKey("graphs.entry_labels", "팀 구성 입구 이름")
DEFINITION_USAGES: PortKey[DefinitionUsages] = PortKey("definitions.usages", "정의가 붙은 곳")
DEFINITION_DEPENDENCIES: PortKey[DocumentDependencies] = PortKey(
    "definitions.dependencies", "정의 문서가 쓰는 정의"
)
DEFINITION_REFERENCES: PortKey[DocumentReferences] = PortKey(
    "definitions.references", "정의 문서의 참조 추출(X25)", multi=True
)
SCOPE_LAYERS: PortKey[ScopeLayersSource] = PortKey(
    "settings.scope_layers", "범위 id → 설정 층(예: 프로젝트 층)", multi=True
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITION_DEPENDENCIES",
    "DEFINITION_REFERENCES",
    "DEFINITION_USAGES",
    "GRAPH_ENTRY_LABELS",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "SCOPE_LAYERS",
    "SECRET_REDACT",
    "SECRET_RULES",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "DefinitionUsages",
    "DocumentDependencies",
    "DocumentReferences",
    "EntryLabels",
    "Redactor",
    "ScopeLayersLike",
    "ScopeLayersSource",
    "SecretRulesReader",
    "StoredLike",
    "WorkspaceSettingsReader",
]
