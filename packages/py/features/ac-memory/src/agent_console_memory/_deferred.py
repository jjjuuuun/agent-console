"""처음 쓸 때 여는 저장소 `DeferredMemoryStore`(보기만으로 파일을 만들지 않기).

파일 하나에 저장소를 두는 구현(예: 프로젝트 폴더의 SQLite 파일)은 목록·검색만 해도 파일이 생기면
안 된다. 이 감싸개는 저장소가 아직 없으면(`exists()` 거짓) 읽기를 빈 메모리 저장소에 맡기고,
항목을 새로 만드는 `write`가 처음 올 때 `open_store()`로 진짜 저장소를 연다. 그 사이 다른 곳이
저장소를 만들었으면(`exists()` 참) 읽기도 진짜 저장소를 연다.

항목이 하나도 없으므로 `update`·`delete`·`move` 등 있는 항목을 바꾸는 연산은 빈 저장소에서 그대로
`EntryNotFoundError`가 된다(파일을 만들지 않는다).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from agent_console_contracts.memory import (
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryVersion,
    MemoryVersionSummary,
)

from ._memory_store import InMemoryMemoryStore
from ._policy import MemoryPolicy
from ._scan import EntryScanner, tag_counts
from ._store import MemoryQuery, MemoryStore, MemoryWriteOutcome, WriteMode

__all__ = ["DeferredMemoryStore"]


class DeferredMemoryStore:
    """`MemoryStore`: 저장소가 없으면 읽기는 빈 저장소, 첫 `write`에서 진짜 저장소를 연다.

    Args:
        open_store: 진짜 저장소를 열거나 만든다(한 번만 부른다. 실패하면 다음 호출에서 다시).
        exists: 진짜 저장소가 이미 있나(예: 파일이 있나). 참이면 읽기에도 연다.
        policy: 쓰기 정책(연 저장소에 넣는다). 생략하면 기본 정책.

    `close()`는 연 저장소에 `close`가 있으면 닫고, 그 뒤에는 새로 열지 않는다(`RuntimeError`).
    선택 능력 `scan_entries`(`EntryScanner`)·`count_tags`(`TagCounter`)를 드러낸다 — 빈 저장소와
    `InMemoryMemoryStore`·SQLite 저장소가 모두 가진다(연 저장소에 `scan_entries`가 없으면
    `TypeError`).
    `MemoryStore` 밖 속성(예: SQLite `warnings`)은 지금 대상(연 저장소 또는 빈 저장소)으로 넘긴다.

    >>> from agent_console_memory import InMemoryMemoryStore
    >>> from agent_console_contracts.memory import MemoryScopeRef
    >>> from agent_console_memory.testing import user_author
    >>> made = []
    >>> store = DeferredMemoryStore(
    ...     lambda: made.append(1) or InMemoryMemoryStore(), exists=lambda: bool(made)
    ... )
    >>> store.search(MemoryQuery()).items, made
    ([], [])
    >>> store.write(MemoryScopeRef(kind="k", id=""), "a", "x", author=user_author()).created
    True
    >>> made, store.opened is not None
    ([1], True)
    """

    def __init__(
        self,
        open_store: Callable[[], MemoryStore],
        *,
        exists: Callable[[], bool],
        policy: MemoryPolicy | None = None,
    ) -> None:
        self._open_store = open_store
        self._exists = exists
        self._policy = policy if policy is not None else MemoryPolicy()
        self._empty = InMemoryMemoryStore(policy=self._policy)
        self._real: MemoryStore | None = None
        self._closed = False
        self._lock = threading.Lock()

    # ---- 대상 고르기 --------------------------------------------------------------------

    @property
    def opened(self) -> MemoryStore | None:
        """연 진짜 저장소(아직 열지 않았으면 None)."""
        return self._real

    @property
    def policy(self) -> MemoryPolicy:
        return self._policy

    @policy.setter
    def policy(self, value: MemoryPolicy) -> None:
        self._policy = value
        self._empty.policy = value
        if self._real is not None:
            self._real.policy = value

    def _materialize(self) -> MemoryStore:
        with self._lock:
            if self._real is None:
                if self._closed:
                    raise RuntimeError("memory store is closed")
                store = self._open_store()
                store.policy = self._policy
                self._real = store
            return self._real

    def _reader(self) -> MemoryStore:
        if self._real is not None:
            return self._real
        if not self._closed and self._exists():
            return self._materialize()
        return self._empty

    def close(self) -> None:
        """연 저장소를 닫는다(`close`가 있을 때). 그 뒤에는 새로 열지 않는다."""
        with self._lock:
            self._closed = True
            real = self._real
        closer = getattr(real, "close", None)
        if callable(closer):
            closer()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._reader(), name)

    # ---- 쓰기(새 항목을 만들 수 있음) ---------------------------------------------------

    def write(
        self,
        scope: MemoryScopeRef,
        key: str,
        content: str,
        *,
        author: MemoryAuthor,
        tags: Sequence[str] | None = None,
        content_type: str | None = None,
        pinned: bool | None = None,
        if_version: int | None = None,
        mode: WriteMode = "replace",
        create_only: bool = False,
    ) -> MemoryWriteOutcome:
        return self._materialize().write(
            scope,
            key,
            content,
            author=author,
            tags=tags,
            content_type=content_type,
            pinned=pinned,
            if_version=if_version,
            mode=mode,
            create_only=create_only,
        )

    # ---- 있는 항목만 다루는 연산(없으면 빈 저장소가 답한다) -----------------------------

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry | None:
        return self._reader().get(entry_id, include_deleted=include_deleted)

    def find(self, scope: MemoryScopeRef, key: str) -> MemoryEntry | None:
        return self._reader().find(scope, key)

    def mark_read(self, entry_id: str) -> None:
        self._reader().mark_read(entry_id)

    def update(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        content: str | None = None,
        content_type: str | None = None,
        tags: Sequence[str] | None = None,
        pinned: bool | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        return self._reader().update(
            entry_id,
            author=author,
            content=content,
            content_type=content_type,
            tags=tags,
            pinned=pinned,
            if_version=if_version,
        )

    def delete(
        self, entry_id: str, *, author: MemoryAuthor, if_version: int | None = None
    ) -> MemoryEntry:
        return self._reader().delete(entry_id, author=author, if_version=if_version)

    def purge(self, entry_id: str) -> MemoryEntry:
        return self._reader().purge(entry_id)

    def restore(
        self, entry_id: str, *, author: MemoryAuthor, version: int | None = None
    ) -> MemoryEntry:
        return self._reader().restore(entry_id, author=author, version=version)

    def archive(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        archived: bool = True,
        if_version: int | None = None,
    ) -> MemoryEntry:
        return self._reader().archive(
            entry_id, author=author, archived=archived, if_version=if_version
        )

    def move(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        to_scope: MemoryScopeRef | None = None,
        to_key: str | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        return self._reader().move(
            entry_id, author=author, to_scope=to_scope, to_key=to_key, if_version=if_version
        )

    def history(self, entry_id: str) -> list[MemoryVersionSummary]:
        return self._reader().history(entry_id)

    def get_version(self, entry_id: str, version: int) -> MemoryVersion | None:
        return self._reader().get_version(entry_id, version)

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        return self._reader().search(query)

    def list_scopes(self, *, kind: str | None = None) -> list[MemoryScopeSummary]:
        return self._reader().list_scopes(kind=kind)

    # ---- 선택 능력(빈 저장소와 SQLite·메모리 저장소가 모두 가진 것) ---------------------

    def scan_entries(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> Iterator[MemoryEntry]:
        target = self._reader()
        if not isinstance(target, EntryScanner):
            raise TypeError("the opened store has no scan_entries")
        return target.scan_entries(scopes=scopes, include_archived=include_archived)

    def count_tags(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> dict[str, int]:
        return tag_counts(self._reader(), scopes=scopes, include_archived=include_archived)
