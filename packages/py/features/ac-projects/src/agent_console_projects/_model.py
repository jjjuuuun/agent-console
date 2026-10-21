"""입력 모양: 범위를 가진 정의 하나(`ScopedDefinition`)와 참조 추출 함수 형식(`References`).

이 패키지는 정의 **종류 이름을 모른다**(design §UX-P.6). 정의가 프로젝트 전용인지는 문서의
`project` 필드나 목록 요약의 `extra.project` 유무로만 판단한다. 참조(무엇이 무엇을 쓰는지)는
호출자가 함수로 주입한다(포트 `definitions.references`, X25). 그래서 `ac-teams`·`ac-store`를
import하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import DefinitionKey, Project

__all__ = [
    "DefinitionId",
    "References",
    "ScopedDefinition",
    "effective_scope",
    "known_project_ids",
]

type DefinitionId = tuple[str, str]
"""정의 하나의 키: (종류 이름, id)."""

type References = Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]]
"""참조 추출 `references(kind, document) -> [(kind, id), ...]`(X25, 주입).

정의 문서 하나가 쓰는 다른 정의의 (종류, id)를 돌려준다(예: 팀 구성 → 에이전트·첨부 리소스).
모르는 종류면 빈 목록을 돌려준다. 같은 참조가 여러 번 나와도 된다(중복은 한 번으로 센다).
"""


def _project_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True, slots=True)
class ScopedDefinition:
    """범위 판단에 쓰는 정의 하나(종류 이름 + id + 범위 + 선택 문서).

    Attributes:
        kind: 정의 종류 이름(열린 문자열, 이 패키지는 의미를 모른다).
        id: 정의 id(종류 안에서 유일).
        project: 프로젝트 id. ``None`` = 공용.
        name: 표시 이름(문구용, 비면 id).
        document: 정의 문서(참조 추출에 넘긴다). ``None``이면 이 정의에서 나가는 참조는 보지 않는다.
    """

    kind: str
    id: str
    project: str | None = None
    name: str = ""
    document: Mapping[str, Any] | None = None

    @property
    def key(self) -> DefinitionId:
        """(종류, id) 키."""
        return (self.kind, self.id)

    @property
    def label(self) -> str:
        """문구에 쓰는 이름(이름이 비면 id)."""
        return self.name or self.id

    def to_key(self) -> DefinitionKey:
        """계약 `DefinitionKey`로."""
        return DefinitionKey(kind=self.kind, id=self.id, name=self.name)

    @classmethod
    def from_document(cls, kind: str, document: Mapping[str, Any]) -> ScopedDefinition:
        """정의 문서(YAML을 읽은 dict)에서 만든다. 범위 = 문서 최상위 `project`(없거나 비면 공용).

        Raises:
            ValueError: 문서에 문자열 `id`가 없을 때.
        """
        def_id = document.get("id")
        if not isinstance(def_id, str) or not def_id:
            raise ValueError(f"정의 문서에 id가 없습니다(종류 {kind!r}).")
        name = document.get("name")
        return cls(
            kind=kind,
            id=def_id,
            project=_project_value(document.get("project")),
            name=name if isinstance(name, str) else "",
            document=document,
        )

    @classmethod
    def from_summary(
        cls, summary: Mapping[str, Any] | object, *, document: Mapping[str, Any] | None = None
    ) -> ScopedDefinition:
        """목록 요약에서 만든다. 범위 = `extra.project` 유무(design §UX-P.6, 종류 이름을 보지 않음).

        `summary`는 `kind`·`id`·`name`·`extra`를 가진 객체(예: 정의 저장소의 `DefinitionSummary`)나
        같은 키의 dict다. `extra`가 없으면 최상위 `project`를 본다(REST 목록 요약 모양).
        """

        def get(name: str) -> Any:
            if isinstance(summary, Mapping):
                return summary.get(name)
            return getattr(summary, name, None)

        kind, def_id = get("kind"), get("id")
        if not isinstance(kind, str) or not isinstance(def_id, str) or not kind or not def_id:
            raise ValueError("요약에 kind·id가 없습니다.")
        extra = get("extra")
        project = (
            _project_value(extra.get("project"))
            if isinstance(extra, Mapping)
            else _project_value(get("project"))
        )
        name = get("name")
        return cls(
            kind=kind,
            id=def_id,
            project=project,
            name=name if isinstance(name, str) else "",
            document=document,
        )


def known_project_ids(projects: Iterable[str | Project | Mapping[str, Any]]) -> frozenset[str]:
    """프로젝트 목록(id 문자열·`Project`·`{"id": ...}` dict)에서 id 집합."""
    ids: set[str] = set()
    for p in projects:
        if isinstance(p, str):
            ids.add(p)
        elif isinstance(p, Project):
            ids.add(p.id)
        elif isinstance(p, Mapping) and isinstance(p.get("id"), str):
            ids.add(p["id"])
    return frozenset(ids)


def effective_scope(project: str | None, known: Collection[str] | None) -> str | None:
    """규칙에 쓰는 범위. 없는 프로젝트를 가리키면 공용(``None``)으로 본다(`project.unknown`).

    Args:
        project: 정의의 `project` 값.
        known: 있는 프로젝트 id. ``None``이면 존재를 따지지 않는다(값 그대로).
    """
    if project is None or known is None or project in known:
        return project
    return None
