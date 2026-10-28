"""변경 알림을 내는 저장소 감싸개(``ObservedMemoryStore``).

REST·정리·가져오기·에이전트 도구(연동이 ``memory.service``의 ``store``로 쓴다) 어느 쪽에서 쓰든
항목이 바뀌면 ``MemoryChanged``(본문 없음)를 알린다. 웹은 WS 토픽 ``memory.changed``로 목록을
갱신한다. 버전이 오르지 않은 호출(이미 그 상태인 보관 등)은 알리지 않는다.

``MemoryStore`` 프로토콜 밖 속성(SQLite ``warnings`` 등)은 안쪽 저장소로 넘긴다(``__getattr__``).
선택 능력 ``scan_entries``(``EntryScanner``)는 ``isinstance`` 판정이 정적 속성만 보므로(Python 3.12)
안쪽 저장소에 있을 때만 그 능력을 가진 감싸개(``observe``가 고른다)로 드러낸다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAuthor,
    MemoryChanged,
    MemoryEntry,
    MemoryEntryPage,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryVersion,
    MemoryVersionSummary,
)
from agent_console_memory import (
    EntryScanner,
    MemoryPolicy,
    MemoryQuery,
    MemoryStore,
    MemoryWriteOutcome,
)
from agent_console_memory import WriteMode as _WriteMode

type ChangeSink = Callable[[MemoryChanged], None]
"""변경 알림을 받는 함수(막히지 않아야 한다)."""

_log = logging.getLogger(__name__)


def changed(entry: MemoryEntry, op: str, author_kind: str) -> MemoryChanged:
    """항목 → 변경 알림(본문 없음)."""
    return MemoryChanged.model_validate(
        {
            "scope": entry.scope,
            "key": entry.key,
            "entry_id": entry.id,
            "version": entry.version,
            "op": op,
            "author_kind": author_kind,
        }
    )


class ObservedMemoryStore:
    """``MemoryStore``를 감싸 바뀐 항목을 ``sink``로 알린다.

    Args:
        inner: 실제 저장소.
        sink: 변경 알림을 받는 함수. 예외는 로그만 남기고 삼킨다(쓰기는 이미 끝났다).
        purge_author_kind: 완전 삭제 알림의 ``author_kind``(완전 삭제는 사람만 한다, 기본 user).
    """

    def __init__(
        self,
        inner: MemoryStore,
        sink: ChangeSink,
        *,
        purge_author_kind: str = KnownMemoryAuthorKinds.USER,
    ) -> None:
        self._inner = inner
        self._sink = sink
        self._purge_author_kind = purge_author_kind

    @property
    def inner(self) -> MemoryStore:
        """감싼 저장소."""
        return self._inner

    @property
    def policy(self) -> MemoryPolicy:
        """안쪽 저장소의 쓰기 정책."""
        return self._inner.policy

    @policy.setter
    def policy(self, value: MemoryPolicy) -> None:
        self._inner.policy = value

    def __getattr__(self, name: str) -> Any:
        # 프로토콜 밖 속성(선택 능력·보조 메서드)만 여기로 온다.
        return getattr(self._inner, name)

    def _emit(self, entry: MemoryEntry, op: str, author_kind: str) -> None:
        try:
            self._sink(changed(entry, op, author_kind))
        except Exception:
            _log.warning("메모리 변경 알림을 보내지 못했습니다", exc_info=True)

    def _emit_if_bumped(
        self, before: int | None, entry: MemoryEntry, op: str, author: MemoryAuthor
    ) -> None:
        if before is None or entry.version != before:
            self._emit(entry, op, author.kind)

    def _version_of(self, entry_id: str) -> int | None:
        found = self._inner.get(entry_id, include_deleted=True)
        return found.version if found is not None else None

    # ---- 쓰기 -------------------------------------------------------------------------

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
        mode: _WriteMode = "replace",
        create_only: bool = False,
    ) -> MemoryWriteOutcome:
        outcome = self._inner.write(
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
        self._emit(outcome.entry, "create" if outcome.created else "update", author.kind)
        return outcome

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
        before = self._version_of(entry_id)
        entry = self._inner.update(
            entry_id,
            author=author,
            content=content,
            content_type=content_type,
            tags=tags,
            pinned=pinned,
            if_version=if_version,
        )
        self._emit_if_bumped(before, entry, "update", author)
        return entry

    def delete(
        self, entry_id: str, *, author: MemoryAuthor, if_version: int | None = None
    ) -> MemoryEntry:
        entry = self._inner.delete(entry_id, author=author, if_version=if_version)
        self._emit(entry, "delete", author.kind)
        return entry

    def purge(self, entry_id: str) -> MemoryEntry:
        entry = self._inner.purge(entry_id)
        self._emit(entry, "purge", self._purge_author_kind)
        return entry

    def restore(
        self, entry_id: str, *, author: MemoryAuthor, version: int | None = None
    ) -> MemoryEntry:
        before = self._version_of(entry_id)
        entry = self._inner.restore(entry_id, author=author, version=version)
        self._emit_if_bumped(before, entry, "restore", author)
        return entry

    def archive(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        archived: bool = True,
        if_version: int | None = None,
    ) -> MemoryEntry:
        before = self._version_of(entry_id)
        entry = self._inner.archive(
            entry_id, author=author, archived=archived, if_version=if_version
        )
        self._emit_if_bumped(before, entry, "archive" if archived else "unarchive", author)
        return entry

    def move(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        to_scope: MemoryScopeRef | None = None,
        to_key: str | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        before = self._version_of(entry_id)
        entry = self._inner.move(
            entry_id, author=author, to_scope=to_scope, to_key=to_key, if_version=if_version
        )
        self._emit_if_bumped(before, entry, "move", author)
        return entry

    # ---- 읽기(그대로 넘김) ----------------------------------------------------------------

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry | None:
        return self._inner.get(entry_id, include_deleted=include_deleted)

    def find(self, scope: MemoryScopeRef, key: str) -> MemoryEntry | None:
        return self._inner.find(scope, key)

    def mark_read(self, entry_id: str) -> None:
        self._inner.mark_read(entry_id)

    def history(self, entry_id: str) -> list[MemoryVersionSummary]:
        return self._inner.history(entry_id)

    def get_version(self, entry_id: str, version: int) -> MemoryVersion | None:
        return self._inner.get_version(entry_id, version)

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        return self._inner.search(query)

    def list_scopes(self, *, kind: str | None = None) -> list[MemoryScopeSummary]:
        return self._inner.list_scopes(kind=kind)


class ObservedScanningStore(ObservedMemoryStore):
    """``ObservedMemoryStore`` + 선택 능력 ``scan_entries``(안쪽 저장소가 가질 때)."""

    def scan_entries(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> Iterator[MemoryEntry]:
        inner = self.inner
        if not isinstance(inner, EntryScanner):  # pragma: no cover - observe가 고른다
            raise TypeError("안쪽 저장소에 scan_entries가 없다")
        return inner.scan_entries(scopes=scopes, include_archived=include_archived)


def observe(
    inner: MemoryStore,
    sink: ChangeSink,
    *,
    purge_author_kind: str = KnownMemoryAuthorKinds.USER,
) -> ObservedMemoryStore:
    """변경 알림 감싸개를 만든다(안쪽 저장소의 선택 능력 ``scan_entries``를 그대로 드러낸다)."""
    cls = ObservedScanningStore if isinstance(inner, EntryScanner) else ObservedMemoryStore
    return cls(inner, sink, purge_author_kind=purge_author_kind)


__all__ = ["ChangeSink", "ObservedMemoryStore", "ObservedScanningStore", "changed", "observe"]
