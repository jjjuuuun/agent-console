"""mod-presets가 받는 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

- 필수 ``definitions.store``: 정의 저장소(``agent_console_store.DefinitionStore`` 모양). 프리셋
  항목을 여기에 복사한다(E-19: 정의 쓰기가 프리셋의 본업).
- 선택 ``definitions.checks``(여러 제공자): 저장 전 정의 검사(``DefinitionCheck``). error 이슈가
  있는 항목은 저장하지 않고 ``failed``로 남긴다. 없으면 모델 검증만 한다.
- 선택 ``definitions.dependencies``: 정의 문서가 쓰는 정의(``DocumentDependencies``). 있으면 프리셋
  항목을 쓰는 정의부터 적용한다(예: 에이전트 → 자식 팀 구성 → 팀 구성). 없으면 매니페스트 순서.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_modkit import PortKey
from agent_console_store import DefinitionStore


@runtime_checkable
class DefinitionCheck(Protocol):
    """저장 전 정의 검사 하나(소비자 쪽 프로토콜). 이슈 path는 문서 기준 JSON Pointer."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]:
        """``kind`` 정의 문서의 검사 이슈(값을 담지 않는다)."""
        ...


class DependencyRef(Protocol):
    """쓰는 정의 하나(종류·id만 읽는다)."""

    @property
    def kind(self) -> str: ...

    @property
    def id(self) -> str: ...


@runtime_checkable
class DocumentDependencies(Protocol):
    """정의 문서(저장 전이어도 됨)가 쓰는 정의(소비자 쪽 프로토콜). 문서가 종류 모델에 맞지 않으면
    예외를 낼 수 있다(그 항목은 순서만 포기한다)."""

    def dependencies_of(self, kind: str, document: Mapping[str, Any]) -> Sequence[DependencyRef]:
        """``kind`` 문서가 쓰는 정의."""
        ...


DEFINITIONS_STORE: PortKey[DefinitionStore] = PortKey("definitions.store", "정의 저장소(쓰기)")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
DEFINITION_DEPENDENCIES: PortKey[DocumentDependencies] = PortKey(
    "definitions.dependencies", "정의 문서가 쓰는 정의"
)

__all__ = [
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "DEFINITION_DEPENDENCIES",
    "DefinitionCheck",
    "DependencyRef",
    "DocumentDependencies",
]
