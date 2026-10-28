"""저장소 항목 훑기: 정리 계획·내보내기가 저장소 구현을 모른 채 모든 항목을 읽는 길.

- 저장소가 선택 능력 `EntryScanner`(`scan_entries`)를 가지면 그것으로 본문까지 한 번에 훑는다
  (미리보기 가림·쪽 정렬이 없어 빠르다).
- 없으면 `MemoryStore` 프로토콜의 `search`만 쓴다(쪽 단위, 오래 안 쓴 것부터). 쪽 사이에 다른 쓰기가
  끼면 같은 항목이 두 번 나올 수 있어 항목 id로 한 번만 낸다.
- 본문이 필요 없다고 하면(`with_content=False`) 선택 능력 `HeadScanner`(`scan_heads`)를 먼저
  쓴다(본문을 읽지 않고 계약 모델도 만들지 않는 가벼운 머리 `EntryHead`). 없으면 위 순서대로다.
- 태그 집계(`tag_counts`)는 선택 능력 `TagCounter`(`count_tags`)가 있으면 그것을, 없으면 훑어 센다.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import NamedTuple, Protocol, runtime_checkable

from agent_console_contracts.memory import (
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryEntrySummary,
    MemoryScopeRef,
)

from ._store import MemoryQuery

DEFAULT_SCAN_PAGE: int = 5_000
"""`search`로 훑을 때 한 번에 읽는 항목 수(기본)."""


class EntryHead(NamedTuple):
    """본문·미리보기 없는 항목 머리(`scan_heads`). 필드 이름·뜻은 `MemoryEntrySummary`와 같다.

    계약 모델을 만들지 않아 10만 개를 훑는 판단(정리 계획)이 가볍다. 화면·응답으로 내보낼 값이
    아니다(필요하면 `get`으로 항목을 읽는다). `tags`는 튜플이다.
    """

    id: str
    scope: MemoryScopeRef
    key: str
    content_type: str
    tags: tuple[str, ...]
    pinned: bool
    archived: bool
    version: int
    bytes: int
    sha256: str
    created_at: float
    created_by: MemoryAuthor
    updated_at: float
    updated_by: MemoryAuthor
    last_read_at: float | None
    deleted_at: float | None


type ScannedEntry = MemoryEntrySummary | MemoryEntry | EntryHead
"""훑기가 내는 항목: 요약(`search` 길), 본문 포함 항목(`scan_entries` 길), 머리(`scan_heads` 길)."""


@runtime_checkable
class SearchableStore(Protocol):
    """훑기에 필요한 저장소 능력(`MemoryStore`의 `search`만). 정리 계획은 이것만 있으면 된다."""

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        """`MemoryStore.search`와 같다."""
        ...


@runtime_checkable
class EntryScanner(Protocol):
    """저장소 선택 능력: 지우지 않은 항목을 본문까지 차례로 낸다(순서는 정하지 않는다).

    큰 저장소에서 정리 계획·내보내기를 빠르게 한다. 없으면 `search` 쪽 단위로 훑는다.
    `InMemoryMemoryStore`가 구현한다.
    """

    def scan_entries(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> Iterator[MemoryEntry]:
        """지우지 않은 항목(범위 `scopes`만, None = 전부). 보관 항목은 `include_archived`일 때만."""
        ...


@runtime_checkable
class HeadScanner(Protocol):
    """저장소 선택 능력: `EntryScanner`와 같은 항목을 본문 없이 머리(`EntryHead`)로 낸다.

    순서는 정하지 않는다. 본문을 읽지 않아 머리 정보만 판단하는 훑기(정리 계획)가 빠르다.
    `SqliteMemoryStore`가 구현한다.
    """

    def scan_heads(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> Iterator[EntryHead]:
        """지우지 않은 항목의 머리(범위 `scopes`만, None = 전부).

        보관 항목은 `include_archived`일 때만 낸다.
        """
        ...


def iter_entries(
    store: SearchableStore,
    *,
    scopes: Sequence[MemoryScopeRef] | None = None,
    include_archived: bool = True,
    page_size: int = DEFAULT_SCAN_PAGE,
    with_content: bool = True,
) -> Iterator[ScannedEntry]:
    """지우지 않은 항목을 하나씩 낸다.

    Args:
        store: 저장소(`search`, 선택 `scan_entries`·`scan_heads`).
        scopes: 범위 목록(None = 모든 범위).
        include_archived: 보관 항목도 낼지.
        page_size: `search`로 훑을 때 한 번에 읽는 수(1 이상).
        with_content: False면 본문이 필요 없다는 뜻이다 — `scan_heads`가 있으면 그것을 쓴다.
            True여도 `search` 길은 요약을 낸다(본문은 호출자가 `get`으로 읽는다).

    Returns:
        항목 반복자. 같은 id는 한 번만 낸다. `scan_heads` 길은 머리 `EntryHead`(순서 없음),
        `scan_entries` 길은 본문 포함 항목(순서 없음), `search` 길은 요약(오래 안 쓴 것부터)이다.

    >>> from agent_console_memory import InMemoryMemoryStore
    >>> from agent_console_memory.testing import user_author
    >>> from agent_console_contracts.memory import MemoryScopeRef
    >>> store = InMemoryMemoryStore()
    >>> _ = store.write(MemoryScopeRef(kind="notes", id=""), "a", "본문", author=user_author())
    >>> [e.key for e in iter_entries(store, with_content=False)]
    ['a']
    """
    if not with_content and isinstance(store, HeadScanner):
        yield from store.scan_heads(scopes=scopes, include_archived=include_archived)
        return
    if isinstance(store, EntryScanner):
        yield from store.scan_entries(scopes=scopes, include_archived=include_archived)
        return
    seen: set[str] = set()
    cursor: str | None = None
    while True:
        page = store.search(
            MemoryQuery(
                scopes=scopes,
                include_archived=include_archived,
                sort="updated_at",
                order="asc",
                cursor=cursor,
                limit=max(page_size, 1),
            )
        )
        for item in page.items:
            if item.id not in seen:
                seen.add(item.id)
                yield item
        if not page.next_cursor or not page.items:
            return
        cursor = page.next_cursor


@runtime_checkable
class TagCounter(Protocol):
    """저장소 선택 능력: 태그별 항목 수를 저장소 안에서 센다(색인 집계, 항목을 훑지 않는다).

    결과는 `tag_counts`가 훑어 센 결과와 같아야 한다(공용 계약 묶음이 비교한다).
    `InMemoryMemoryStore`·`SqliteMemoryStore`가 구현한다.
    """

    def count_tags(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> dict[str, int]:
        """지우지 않은 항목(범위 `scopes`만, None = 전부)의 태그 → 그 태그를 가진 항목 수.

        보관 항목은 `include_archived`일 때만 센다. 항목 수가 0인 태그는 없다.
        """
        ...


def tag_counts(
    store: SearchableStore,
    *,
    scopes: Sequence[MemoryScopeRef] | None = None,
    include_archived: bool = True,
) -> dict[str, int]:
    """태그 → 그 태그를 가진 지우지 않은 항목 수(한 항목은 태그마다 한 번).

    저장소가 `TagCounter`면 `count_tags`를 쓰고, 없으면 `iter_entries`(본문 없이)로 훑어 센다.

    >>> from agent_console_memory import InMemoryMemoryStore
    >>> from agent_console_memory.testing import user_author
    >>> from agent_console_contracts.memory import MemoryScopeRef
    >>> store = InMemoryMemoryStore()
    >>> notes = MemoryScopeRef(kind="notes", id="")
    >>> _ = store.write(notes, "a", "x", author=user_author(), tags=["t", "u"])
    >>> _ = store.write(notes, "b", "y", author=user_author(), tags=["t"])
    >>> sorted(tag_counts(store).items())
    [('t', 2), ('u', 1)]
    """
    if isinstance(store, TagCounter):
        return dict(store.count_tags(scopes=scopes, include_archived=include_archived))
    counts: dict[str, int] = {}
    for entry in iter_entries(
        store, scopes=scopes, include_archived=include_archived, with_content=False
    ):
        for tag in set(entry.tags):
            counts[tag] = counts.get(tag, 0) + 1
    return counts
