"""mod-exports가 받는 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

- 필수 ``definitions.lookup``: 정의 읽기(``DefinitionLookup`` — ``agent_console_store``
  ``DefinitionStore``가 만족). 내보낼 정의 원문·본문 파일을 읽는다.
- 선택 ``exports.dependencies``: 정의가 쓰는 정의(``ExportDependencies``). 없으면 고른 항목만
  내보낸다(의존 자동 포함 없음).
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙(``() -> SecretRules``). 없으면 기본 규칙.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_exports import DependencyLike
from agent_console_modkit import PortKey
from agent_console_secret_rules import SecretRules


class StoredLike(Protocol):
    @property
    def document(self) -> Mapping[str, Any]: ...


class FileLike(Protocol):
    @property
    def path(self) -> str: ...


@runtime_checkable
class DefinitionLookup(Protocol):
    """정의 읽기(소비자 쪽 프로토콜). 없으면 저장소 예외(``NotFound`` 등)를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...

    def list_files(self, kind: str, id: str) -> Sequence[FileLike]: ...

    def read_file(self, kind: str, id: str, path: str) -> bytes: ...


@runtime_checkable
class ExportDependencies(Protocol):
    """정의 하나가 쓰는 정의(팀 구성 → 에이전트·리소스, 에이전트 → 리소스)."""

    def dependencies(self, kind: str, id: str) -> Sequence[DependencyLike]: ...


type SecretRulesReader = Callable[[], SecretRules]
"""지금 비밀 의심 규칙을 돌려주는 함수(``secrets.rules`` 포트 모양)."""

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
EXPORT_DEPENDENCIES: PortKey[ExportDependencies] = PortKey(
    "exports.dependencies", "정의가 쓰는 정의(함께 내보내기)"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "EXPORT_DEPENDENCIES",
    "SECRET_RULES",
    "DefinitionLookup",
    "ExportDependencies",
    "FileLike",
    "SecretRulesReader",
    "StoredLike",
]
