"""mod-versions가 받는 포트·토픽(이름 = 포트, design §3R.1.2·§3R.1.3·§3R.1.5).

- 필수 ``definitions.store``: 정의 저장소(``VersionStore`` — ``DefinitionStore`` + 버전 기록소
  ``versions``). 버전 목록·비교·되돌리기와 보존 개수 정리에 쓴다.
- 선택 ``definitions.checks``(여러 제공자): 저장 전 검사. 되돌리기 전 검사(error면 422)와 비교
  결과의 비밀 위치(설정 ``secret_issue_codes``의 이슈) 판정에 쓴다. 없으면 검사 없이 되돌린다.
- 선택 ``secrets.rules``: 지금 비밀 의심 규칙(``() -> SecretRules``). 없으면 기본 규칙.
- 구독 토픽 ``definitions.saved``(``SavedDefinition``): 정의가 저장될 때마다 보존 개수
  (``max_per_definition``)를 적용한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import Issue
from agent_console_modkit import PortKey, Topic
from agent_console_secret_rules import SecretRules
from agent_console_store import DefinitionStore, VersionRepository


class VersionStore(DefinitionStore, Protocol):
    """버전 경로가 쓰는 정의 저장소(``agent_console_store.BaseDefinitionStore``가 만족)."""

    @property
    def versions(self) -> VersionRepository:
        """버전 기록소(보존 개수 정리 ``trim``·``prune_blobs``)."""
        ...


@runtime_checkable
class DefinitionCheck(Protocol):
    """저장 전 정의 검사 하나(소비자 쪽 프로토콜). 이슈 path는 문서 기준 JSON Pointer."""

    def issues(self, kind: str, document: Mapping[str, Any]) -> Sequence[Issue]: ...


@runtime_checkable
class SavedDefinition(Protocol):
    """``definitions.saved`` 토픽 항목(정의 하나가 새 버전으로 저장됨)."""

    @property
    def kind(self) -> str: ...

    @property
    def id(self) -> str: ...

    @property
    def version_hash(self) -> str: ...


type SecretRulesReader = Callable[[], SecretRules]
"""지금 비밀 의심 규칙을 돌려주는 함수(``secrets.rules`` 포트 모양)."""

DEFINITIONS_STORE: PortKey[VersionStore] = PortKey("definitions.store", "정의 저장소")
DEFINITION_CHECKS: PortKey[DefinitionCheck] = PortKey(
    "definitions.checks", "저장 전 정의 검사", multi=True
)
SECRET_RULES: PortKey[SecretRulesReader] = PortKey("secrets.rules", "지금 비밀 의심 규칙")
DEFINITIONS_SAVED: Topic[SavedDefinition] = Topic("definitions.saved")

__all__ = [
    "DEFINITIONS_SAVED",
    "DEFINITIONS_STORE",
    "DEFINITION_CHECKS",
    "SECRET_RULES",
    "DefinitionCheck",
    "SavedDefinition",
    "SecretRulesReader",
    "VersionStore",
]
