"""기록 출처를 잇는 커서 페이지(design §6R.18 Q14, 6R.12).

한 목록이 기록 DB 여러 곳(예: 프로젝트 폴더 기록 → 앱 DB 옛 기록)에 나뉘어 있을 때, 한 출처를
커서로 끝까지 읽은 뒤 다음 출처를 처음부터 읽는다. 두 출처를 시간순으로 섞지 않고, 한 페이지는 한
출처에서만 나온다.

커서 모양은 ``<출처>.<그 출처 저장소 커서>``다(저장소 커서는 base64url이라 ``.``이 없다). 저장소
커서가 빈 문자열이면 그 출처의 처음이다(다음 출처로 넘어갈 때). 호출자에게는 불투명 문자열이다.

>>> encode_source_cursor("app", None)
'app.'
>>> decode_source_cursor("project.abc", ("project", "app"))
('project', 'abc')
>>> pages = {"project": ([1, 2], None), "app": ([3], None)}
>>> first = page_across_sources(
...     None, "project", order=("project", "app"),
...     read=lambda src, cur: pages[src], has_any=lambda src: True,
... )
>>> first.items, first.source, first.next_cursor
([1, 2], 'project', 'app.')
>>> second = page_across_sources(
...     first.next_cursor, "project", order=("project", "app"),
...     read=lambda src, cur: pages[src], has_any=lambda src: True,
... )
>>> second.items, second.source, second.next_cursor
([3], 'app', None)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .run_page import InvalidCursor

_SEP = "."


def encode_source_cursor(source: str, cursor: str | None) -> str:
    """출처 + 그 출처 저장소 커서(None = 그 출처의 처음) → 불투명 커서."""
    if not source or _SEP in source:
        raise ValueError(f"출처 이름이 올바르지 않습니다: {source!r}")
    return f"{source}{_SEP}{cursor or ''}"


def decode_source_cursor(text: str, sources: Sequence[str]) -> tuple[str, str | None]:
    """``encode_source_cursor``의 역. 모르는 출처·모양이 틀리면 ``InvalidCursor``.

    Args:
        text: 커서 문자열.
        sources: 받을 수 있는 출처 이름들.
    """
    source, sep, inner = text.partition(_SEP)
    if not sep or source not in sources:
        raise InvalidCursor("invalid cursor")
    return source, (inner or None)


@dataclass(frozen=True)
class SourcePage[T]:
    """출처 하나에서 읽은 페이지.

    Attributes:
        items: 이 페이지 항목(그 출처 저장소 순서 그대로).
        source: 이 페이지를 읽은 출처.
        next_cursor: 다음 요청 커서(같은 출처 다음 페이지 또는 다음 출처의 처음). None = 끝.
    """

    items: list[T] = field(default_factory=list)
    source: str = ""
    next_cursor: str | None = None


def page_across_sources[T](
    cursor: str | None,
    source: str,
    *,
    order: Sequence[str],
    read: Callable[[str, str | None], tuple[list[T], str | None]],
    has_any: Callable[[str], bool],
) -> SourcePage[T]:
    """한 페이지를 읽는다. 지금 출처가 끝나면 ``order``에서 뒤에 오는 출처 중 항목이 있는 첫
    출처의 처음을 ``next_cursor``로 준다.

    Args:
        cursor: 이전 응답의 ``next_cursor``(None = ``source``의 처음). 커서에 든 출처가 ``source``
            보다 우선한다.
        source: 커서가 없을 때 읽을 출처.
        order: 잇는 순서(예: ``("project", "app")``). 하나면 잇지 않는다. ``source``가 여기 없으면
            그 출처만 읽는다.
        read: (출처, 그 출처 저장소 커서) → (항목, 다음 저장소 커서).
        has_any: 그 출처에 항목이 하나라도 있나(빈 페이지 한 번을 아낀다).

    Raises:
        InvalidCursor: 커서 모양이 틀렸거나 모르는 출처다.
    """
    known = tuple(dict.fromkeys([*order, source]))
    if cursor is not None:
        current, inner = decode_source_cursor(cursor, known)
    else:
        current, inner = source, None
    items, inner_next = read(current, inner)
    if inner_next is not None:
        return SourcePage(items, current, encode_source_cursor(current, inner_next))
    if current in order:
        for later in order[order.index(current) + 1 :]:
            if has_any(later):
                return SourcePage(items, current, encode_source_cursor(later, None))
    return SourcePage(items, current, None)


__all__ = [
    "SourcePage",
    "decode_source_cursor",
    "encode_source_cursor",
    "page_across_sources",
]
