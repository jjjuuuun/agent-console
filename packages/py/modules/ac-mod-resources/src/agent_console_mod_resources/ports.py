"""mod-resources의 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

받음:
- 필수 ``definitions.store``: 정의 저장소(``ResourceStore`` — ``agent_console_store`` 파일 저장소가
  만족). 리소스 정의·본문·여러 파일을 읽고 쓴다.
- 선택 ``definitions.usages``: 정의가 붙은 곳(``DefinitionUsages``). 없으면 목록 ``usage_count``는
  null(계산 안 함).
- 선택 ``definitions.checks``(여러 제공자): 저장 전 정의 검사(``DefinitionCheck``). 만들기·저장 때
  error는 422, warning·info는 응답 헤더 ``X-Console-Issues``로 싣는다. 없으면 종류 검사만.

제공:
- ``resources.lookup``: ``ac-resources.ResourceLookup`` + ``FileContentLookup``
  (정의·본문·여러 파일).
- ``resources.types``: 리소스 종류 레지스트리(``Registry[ResourceType]``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import DefinitionReference, Issue
from agent_console_modkit import PortKey
from agent_console_registry import Registry
from agent_console_resources import ResourceLookup, ResourceType
from agent_console_store import DefinitionStore


@runtime_checkable
class DefinitionUsages(Protocol):
    """정의 하나가 붙은 곳(팀 구성 노드·층 첨부·에이전트·공통 설정)."""

    def references(self, kind: str, id: str) -> Sequence[DefinitionReference]: ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """저장 전 정의 검사 하나. 이슈 path는 문서 기준 JSON Pointer, 메시지에 값이 없다."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


type ResourceStore = DefinitionStore
"""리소스 경로가 쓰는 정의 저장소(``agent_console_store.DefinitionStore``)."""


DEFINITIONS_STORE: PortKey[ResourceStore] = PortKey("definitions.store", "정의 저장소")
DEFINITION_USAGES: PortKey[DefinitionUsages] = PortKey("definitions.usages", "정의가 붙은 곳")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
RESOURCES_LOOKUP: PortKey[ResourceLookup] = PortKey("resources.lookup", "리소스 정의·본문 조회")
RESOURCE_TYPES: PortKey[Registry[ResourceType]] = PortKey("resources.types", "리소스 종류")

__all__ = [
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "DEFINITION_USAGES",
    "RESOURCES_LOOKUP",
    "RESOURCE_TYPES",
    "DefinitionCheck",
    "DefinitionUsages",
    "ResourceStore",
]
