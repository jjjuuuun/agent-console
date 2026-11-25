"""정의 저장소 → 옛 ``project`` 필드 판단 입력(``ScopedDefinition`` 목록)과 참조 추출 묶기.

정의 종류 이름을 모른다: 읽기 포트가 아는 모든 종류를 읽고, 문서에 문자열 ``id``가 있는 것만
대상으로 본다(싱글턴 공통 설정 등은 빠진다, design §UX-P.6). 옛 정의 정리(``{id}/legacy/plan``)와
종류 기여(X44)의 이름·삭제·참조 추출을 여기서 모은다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any

from agent_console_projects import References, ScopedDefinition
from agent_console_store import StoreError

from .ports import DefinitionReader

type ReferenceSource = Callable[[str, Mapping[str, Any]], Iterable[tuple[str, str]]]


def read_definitions(
    reader: DefinitionReader, *, skip_kinds: Collection[str] = ()
) -> list[ScopedDefinition]:
    """읽기 포트의 모든 정의(문서 포함). 읽을 수 없는 파일·id 없는 문서는 뺀다."""
    out: list[ScopedDefinition] = []
    for kind in reader.kinds():
        if kind in skip_kinds:
            continue
        for def_id in reader.list_ids(kind):
            try:
                document = reader.get(kind, def_id).document
                out.append(ScopedDefinition.from_document(kind, document))
            except (StoreError, ValueError):
                continue
    return out


def combine_references(sources: Iterable[ReferenceSource]) -> References | None:
    """여러 참조 추출 제공자를 하나로(없으면 None). 제공자 예외는 그 제공자만 건너뛴다."""
    items = list(sources)
    if not items:
        return None

    def references(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for source in items:
            try:
                found.extend(source(kind, document))
            except Exception:  # 제공자 하나의 실패가 검사 전체를 막지 않게
                continue
        return found

    return references


def contribution_titles(contributions: Iterable[Any]) -> dict[str, str]:
    """종류 기여(X44)의 표시 이름 ``{종류 이름: title}``(빈 ``title``은 빼고, 먼저 온 것 우선).

    >>> from types import SimpleNamespace as C
    >>> contribution_titles([C(kind=C(name="note"), title="노트"), C(kind=C(name="x"), title=None)])
    {'note': '노트'}
    """
    out: dict[str, str] = {}
    for item in contributions:
        title = getattr(item, "title", None)
        name = getattr(getattr(item, "kind", None), "name", None)
        if isinstance(title, str) and title and isinstance(name, str):
            out.setdefault(name, title)
    return out


def contribution_deleters(
    contributions: Iterable[Any],
) -> dict[str, Callable[[str | None, str, str | None], None] | None]:
    """종류 기여(X44)의 삭제 수단 ``{종류 이름: delete | None}``(먼저 온 것 우선).

    None 값 = 그 종류는 종류 공통 경로로 지울 수 없다(기여가 ``delete``를 주지 않음).

    >>> from types import SimpleNamespace as C
    >>> out = contribution_deleters([C(kind=C(name="a"), delete=print), C(kind=C(name="b"))])
    >>> sorted(out), out["b"]
    (['a', 'b'], None)
    """
    out: dict[str, Callable[[str | None, str, str | None], None] | None] = {}
    for item in contributions:
        name = getattr(getattr(item, "kind", None), "name", None)
        if not isinstance(name, str) or name in out:
            continue
        delete = getattr(item, "delete", None)
        out[name] = delete if callable(delete) else None
    return out


def contribution_references(contributions: Iterable[Any]) -> list[ReferenceSource]:
    """종류 기여(X44)의 ``references``를 X25 모양 ``(kind, document)``로(그 종류 문서에만 적용).

    ``references``가 없는 기여는 건너뛴다(목록이 비면 참조 추출이 없는 것과 같다).
    """
    out: list[ReferenceSource] = []
    for item in contributions:
        extract = getattr(item, "references", None)
        name = getattr(getattr(item, "kind", None), "name", None)
        if extract is None or not isinstance(name, str):
            continue

        def source(
            kind: str,
            document: Mapping[str, Any],
            _name: str = name,
            _extract: Callable[[Mapping[str, Any]], Iterable[tuple[str, str]]] = extract,
        ) -> Iterable[tuple[str, str]]:
            return list(_extract(document)) if kind == _name else []

        out.append(source)
    return out


__all__ = [
    "ReferenceSource",
    "combine_references",
    "contribution_deleters",
    "read_definitions",
]
