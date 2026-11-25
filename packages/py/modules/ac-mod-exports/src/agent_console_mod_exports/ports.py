"""mod-exports가 받는 포트(이름 = 포트, design §3R.1.2·§3R.1.3).

- 필수 ``definitions.lookup``: 정의 읽기(``DefinitionLookup`` — ``agent_console_store``
  ``DefinitionStore``가 만족). 내보낼 정의 원문·본문 파일을 읽는다.
- 선택 ``exports.dependencies``: 정의가 쓰는 정의(``ExportDependencies``). 없으면 고른 항목만
  내보낸다(의존 자동 포함 없음). 값이 ``for_lookup(lookup, *, scope)``
  (``ScopedExportDependencies``)도 가지면 프로젝트 공간에서 내보낼 때 그 공간 저장소·범위(프로젝트
  id) 기준 계산을 받아 쓴다. 없으면 공간 원본은 고른 항목만.
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙(``() -> SecretRules``). 없으면 기본 규칙.
- 선택 ``projects.folders``(5.7R.33k): 등록 프로젝트 폴더(``entries``의 id·폴더). 있으면 폴더 쓰기
  대상 = 등록 폴더(루트 id = 등록 id)이고 설치자 ``roots``는 쓰지 않는다.
- 선택 ``definitions.spaces``(5.7R.33k): 등록 id → 그 프로젝트 공간 정의 저장소. 내보낼 원본 기본
  (``?project=``가 있을 때).
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

    def read_content(self, kind: str, id: str) -> bytes | None: ...


@runtime_checkable
class ExportDependencies(Protocol):
    """정의 하나가 쓰는 정의(팀 구성 → 에이전트·리소스, 에이전트 → 리소스)."""

    def dependencies(self, kind: str, id: str) -> Sequence[DependencyLike]: ...


@runtime_checkable
class ScopedExportDependencies(ExportDependencies, Protocol):
    """다른 정의 저장소 기준으로 같은 계산을 만들 수 있는 의존 계산(선택 모양).

    ``exports.dependencies`` 값이 이 모양이면 프로젝트 공간에서 내보낼 때
    ``for_lookup(공간 저장소, scope=프로젝트 id)``를 불러 그 공간에서만 쓰는 정의를 찾는다(공용
    라이브러리로 넘어가지 않는다). ``scope``는 범위 설정 층(예: 프로젝트 층의 공통 첨부)을 고르는
    데 쓴다 — 범위의 뜻은 제공자가 안다.
    """

    def for_lookup(
        self, lookup: DefinitionLookup, *, scope: str | None = None
    ) -> ExportDependencies:
        """``lookup``에서 정의를 읽고 ``scope``(범위 id, 없으면 범위 층 없음) 층도 보는 계산."""
        ...


type SecretRulesReader = Callable[[], SecretRules]
"""지금 비밀 의심 규칙을 돌려주는 함수(``secrets.rules`` 포트 모양)."""

DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
PROJECT_FOLDERS: PortKey[Callable[[], Any]] = PortKey(
    "projects.folders", "앱에 등록된 프로젝트 폴더(전체·보관)"
)
"""값 모양은 ``projects.ProjectFoldersLike``(``entries``)."""
DEFINITIONS_SPACES: PortKey[Any] = PortKey("definitions.spaces", "공간 이름(등록 id) → 정의 저장소")
"""값 모양은 ``projects.DefinitionSpacesLike``(``open(project_id)``)."""
EXPORT_DEPENDENCIES: PortKey[ExportDependencies] = PortKey(
    "exports.dependencies", "정의가 쓰는 정의(함께 내보내기)"
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")

__all__ = [
    "DEFINITIONS_LOOKUP",
    "DEFINITIONS_SPACES",
    "EXPORT_DEPENDENCIES",
    "PROJECT_FOLDERS",
    "SECRET_RULES",
    "DefinitionLookup",
    "ExportDependencies",
    "FileLike",
    "ScopedExportDependencies",
    "SecretRulesReader",
    "StoredLike",
]
