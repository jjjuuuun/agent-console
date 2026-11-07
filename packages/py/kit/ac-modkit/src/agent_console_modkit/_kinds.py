"""정의 종류 기여(X44, design §6R.3·§6R.5): 다른 모듈이 정의 저장소에 새 종류를 더하는 포트.

소비자(정의 모듈·프로젝트 모듈)와 공급자(예: SDD 모듈)가 서로 import하지 않도록 키트에 둔다.
키트는 기능 라이브러리를 모르므로 종류 값의 타입은 매개변수(``K``)다. 정의 모듈은
``agent_console_store.DefinitionKind``만 받고 다른 값은 건너뛴다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ._ports import PortKey

type KindReferences = Callable[[Mapping[str, Any]], Iterable[tuple[str, str]]]
"""기여 종류 문서 하나가 쓰는 정의의 ``(종류, id)``(복사 계획의 참조 닫힘)."""

type KindDelete = Callable[[str | None, str, str | None], None]
"""기여 종류 항목 하나 지우기 ``(공간, id, 기대 버전)``.

공간은 프로젝트 등록 id(None = 라이브러리·단독 공간), 기대 버전은 ``If-Match``(None = 확인 안 함).
기대 버전은 그 공간 정의 저장소의 버전 해시(종류 공통 목록 ``CopyItem.version``과 같은 값)다.
제공 모듈의 자기 삭제 경로와 같은 일(알림·캐시 비우기 등)을 한다. 없는 항목·버전 불일치는 그
모듈이 평소 내는 예외(예: ``agent_console_store.NotFound``·``VersionConflict``)를 그대로 던진다."""


@dataclass(frozen=True)
class KindContribution[K]:
    """정의 종류 하나의 기여.

    Attributes:
        kind: 종류 정의(정의 모듈 조립에서는 ``agent_console_store.DefinitionKind``). 라이브러리에
            둘지·프로젝트 공간에 옮길 수 있는지는 종류 값(``library``·``portable``)이 정한다.
        references: 그 종류 문서의 참조 추출(없으면 참조 없음). 예외는 소비자가 삼킨다.
        summary_fields: 목록 요약에 더 실을 최상위 문자열 필드(종류의 ``summary_fields``에 더한다).
        title: 종류 표시 이름(사용자 언어). 복사 대화상자 종류 목록(``CopyKindInfo.title``)이 쓴다.
            None이면 화면이 종류 이름을 그대로 보인다.
        delete: 그 종류 항목 하나를 지우는 콜백(종류 공통 삭제 경로가 부른다). None이면 종류 공통
            경로로는 지울 수 없다(``CopyKindInfo.deletable`` false) — 제공 모듈의 자기 경로만 쓴다.

    >>> c = KindContribution("note", references=lambda doc: [("agent", doc["agent"])])
    >>> list(c.references({"agent": "rev"})) if c.references else []
    [('agent', 'rev')]
    """

    kind: K
    references: KindReferences | None = None
    summary_fields: tuple[str, ...] = ()
    title: str | None = None
    delete: KindDelete | None = None


DEFINITION_KIND_CONTRIBUTIONS: PortKey[KindContribution[Any]] = PortKey(
    "definitions.kind_contributions", "정의 종류 기여(X44)", multi=True
)
"""여러 제공자 포트. 제공 모듈은 종류마다 ``ctx.provide(DEFINITION_KIND_CONTRIBUTIONS, c)``를 한
번씩 부른다(소비자는 제공 모듈 id 순 목록으로 받는다)."""

__all__ = [
    "DEFINITION_KIND_CONTRIBUTIONS",
    "KindContribution",
    "KindDelete",
    "KindReferences",
]
