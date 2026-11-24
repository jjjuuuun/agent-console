"""link-definitions-resources의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L8).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다. 모양은 계약 테스트가 확인한다):
- 필수 ``definitions.lookup``: 정의 읽기(첨부가 가리키는 리소스 정의를 찾는다).
- 필수 ``resources.types``: 리소스 종류 레지스트리.
- 선택 ``resources.lookup``: 리소스 조회. 없으면 ``definitions.lookup``으로 찾는다.
- 선택 ``secrets.rules``: 리소스가 없는 첨부의 비밀 의심 규칙. 없으면 기본 규칙.
- 선택 ``definitions.spaces``: 공간 이름 → 정의 저장소(``agent_console_store.DefinitionSpaces``).
  공간 기준 검사(``space_issues``)가 첨부 ``ref``를 그 공간 저장소의 리소스로 푼다. 없으면 공간
  기준 검사는 ``SpacesUnavailable``(409 ``feature_unavailable``)이다(라이브러리로 넘어가지 않는다).

제공:
- ``definitions.checks``(여러 제공자): 리소스 종류 검사, 첨부 덮어쓰기 검사(``x-secret`` 평문 거부).
  저장 전 검사(정의 경로·버전 되돌리기)와 평문 점검(``/server-info``)이 이것을 쓴다. 선택 메서드
  ``space_issues(space, kind, document)``(``SpaceDefinitionCheck``)도 준다 — 소비자는 공간에
  저장할 때 이 메서드가 있으면 그것을, 없으면 ``issues``를 부른다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_modkit import PortKey
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType
from agent_console_secret_rules import SecretRules
from agent_console_store import DEFINITIONS_SPACES_PORT, DefinitionSpaces


class StoredLike(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기. 없으면 저장소 예외(``NotFound`` 등)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """``definitions.checks`` 모양."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


@runtime_checkable
class SpaceDefinitionCheck(Protocol):
    """``definitions.checks``의 선택 능력: 공간(예: 프로젝트)에 저장할 때의 검사.

    ``issues``와 같은 이슈를 내되, 정의가 가리키는 다른 정의(첨부 리소스 등)는 그 공간에서만
    찾는다. 이 메서드가 없는 검사는 공간 저장에도 ``issues``로 부른다.
    """

    def space_issues(
        self, space: str, kind: str, document: Mapping[str, Any]
    ) -> Sequence[Issue]: ...


type SecretRulesReader = Callable[[], SecretRules]

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
RESOURCE_TYPES: PortKey[Registry[ResourceType]] = PortKey("resources.types", "리소스 종류")
RESOURCES_LOOKUP: PortKey[ResourceLookup] = PortKey("resources.lookup", "리소스 정의·본문 조회")
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
DEFINITIONS_SPACES: PortKey[DefinitionSpaces] = PortKey(
    DEFINITIONS_SPACES_PORT, "공간 이름 → 정의 저장소"
)

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SPACES",
    "DEFINITION_CHECKS",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "SECRET_RULES",
    "DefinitionCheck",
    "DefinitionLookup",
    "SecretRulesReader",
    "SpaceDefinitionCheck",
    "StoredLike",
]
