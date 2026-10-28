"""프로세스 메모리 저장소(`InMemoryMemoryStore`). 테스트·단독 사용·DB가 없는 서버용."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_console_contracts.memory import (
    MEMORY_DEFAULT_CONTENT_TYPE,
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryVersion,
    MemoryVersionOp,
    MemoryVersionSummary,
)

from ._errors import (
    EntryExistsError,
    EntryNotFoundError,
    TooLargeError,
    VersionConflictError,
)
from ._keys import check_key
from ._policy import MemoryPolicy, check_secret_field, prepare_write
from ._shared import check_sort, decode_cursor, encode_cursor, summarize, versions_to_drop
from ._store import MemoryQuery, MemoryWriteOutcome, WriteMode

type Clock = Callable[[], float]
type IdFactory = Callable[[], str]


def _scope_key(scope: MemoryScopeRef) -> tuple[str, str]:
    return scope.kind, scope.id


@dataclass
class _Row:
    entry: MemoryEntry
    versions: dict[int, MemoryVersion] = field(default_factory=dict)


def _append(existing: str, extra: str) -> str:
    if not existing or existing.endswith("\n"):
        return existing + extra
    return f"{existing}\n{extra}"


class InMemoryMemoryStore:
    """`MemoryStore` 프로세스 메모리 구현. 모든 연산은 잠금 하나로 줄을 선다(스레드 안전).

    Args:
        policy: 쓰기 정책(기본: 기본 한도 + 비밀 기본 규칙 거부 + 버전 50개).
        clock: 시각(Unix epoch 초). 테스트는 `testing.FakeClock`.
        new_id: 항목 id 생성기(기본 UUID4).
    """

    def __init__(
        self,
        *,
        policy: MemoryPolicy | None = None,
        clock: Clock = time.time,
        new_id: IdFactory | None = None,
    ) -> None:
        self.policy = policy if policy is not None else MemoryPolicy()
        self._clock = clock
        self._new_id: IdFactory = new_id if new_id is not None else (lambda: str(uuid.uuid4()))
        self._rows: dict[str, _Row] = {}
        self._live: dict[tuple[str, str, str], str] = {}
        self._lock = threading.RLock()

    # ---- 내부 -------------------------------------------------------------------------

    def _row(self, entry_id: str, *, include_deleted: bool = False) -> _Row:
        row = self._rows.get(entry_id)
        if row is None or (row.entry.deleted_at is not None and not include_deleted):
            raise EntryNotFoundError("항목이 없다")
        return row

    @staticmethod
    def _check_version(entry: MemoryEntry, if_version: int | None) -> None:
        if if_version is not None and if_version != entry.version:
            raise VersionConflictError(
                "다른 쪽이 먼저 고쳤다", entry_id=entry.id, current_version=entry.version
            )

    def _scope_count(self, scope: MemoryScopeRef) -> int:
        kind, sid = _scope_key(scope)
        return sum(1 for (k, s, _key) in self._live if k == kind and s == sid)

    def _check_scope_room(self, scope: MemoryScopeRef) -> None:
        limit = self.policy.limits.max_entries_per_scope
        if self._scope_count(scope) >= limit:
            raise TooLargeError(
                f"범위 하나에 항목은 {limit}개까지다", limit="max_entries_per_scope", value=limit
            )

    def _check_total(self, delta: int) -> None:
        limit = self.policy.limits.max_total_bytes
        if delta <= 0:
            return
        total = sum(self._rows[eid].entry.bytes for eid in self._live.values())
        if total + delta > limit:
            raise TooLargeError(
                f"저장소 전체 본문은 {limit}바이트까지다", limit="max_total_bytes", value=limit
            )

    def _record(self, row: _Row, op: MemoryVersionOp, author: MemoryAuthor, at: float) -> None:
        entry = row.entry
        row.versions[entry.version] = MemoryVersion(
            entry_id=entry.id,
            version=entry.version,
            op=op,
            scope=entry.scope,
            key=entry.key,
            bytes=entry.bytes,
            sha256=entry.sha256,
            author=author,
            at=at,
            content=entry.content,
        )
        for old in versions_to_drop(list(row.versions), self.policy.max_versions_per_entry):
            del row.versions[old]

    def _bump(self, row: _Row, op: MemoryVersionOp, author: MemoryAuthor, **changes: Any) -> None:
        at = self._clock()
        row.entry = row.entry.model_copy(
            update={
                **changes,
                "version": row.entry.version + 1,
                "updated_at": at,
                "updated_by": author,
            }
        )
        self._record(row, op, author, at)

    # ---- MemoryStore ------------------------------------------------------------------

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
        """`MemoryStore.write`."""
        with self._lock:
            check_key(key, max_chars=self.policy.limits.max_key_chars)
            existing_id = self._live.get((scope.kind, scope.id, key))
            if existing_id is None:
                if if_version is not None and if_version != 0:
                    raise VersionConflictError("항목이 없다", entry_id="", current_version=0)
                prepared = prepare_write(self.policy, key, content, list(tags or ()))
                self._check_scope_room(scope)
                self._check_total(prepared.bytes)
                at = self._clock()
                entry = MemoryEntry(
                    id=self._new_id(),
                    scope=scope,
                    key=key,
                    content=prepared.content,
                    content_type=content_type or MEMORY_DEFAULT_CONTENT_TYPE,
                    tags=prepared.tags,
                    pinned=bool(pinned),
                    version=1,
                    bytes=prepared.bytes,
                    sha256=prepared.sha256,
                    created_at=at,
                    created_by=author,
                    updated_at=at,
                    updated_by=author,
                )
                row = _Row(entry=entry)
                self._rows[entry.id] = row
                self._live[(scope.kind, scope.id, key)] = entry.id
                self._record(row, "create", author, at)
                return MemoryWriteOutcome(entry=entry, created=True)
            row = self._rows[existing_id]
            if create_only:
                raise EntryExistsError("같은 키의 항목이 이미 있다", entry_id=existing_id)
            self._check_version(row.entry, if_version)
            new_content = _append(row.entry.content, content) if mode == "append" else content
            self._update_row(
                row,
                author=author,
                content=new_content,
                content_type=content_type,
                tags=tags,
                pinned=pinned,
            )
            return MemoryWriteOutcome(entry=row.entry, created=False)

    def _update_row(
        self,
        row: _Row,
        *,
        author: MemoryAuthor,
        content: str | None,
        content_type: str | None,
        tags: Sequence[str] | None,
        pinned: bool | None,
    ) -> None:
        entry = row.entry
        prepared = prepare_write(
            self.policy,
            entry.key,
            entry.content if content is None else content,
            entry.tags if tags is None else list(tags),
        )
        self._check_total(prepared.bytes - entry.bytes)
        changes: dict[str, Any] = {
            "content": prepared.content,
            "tags": prepared.tags,
            "bytes": prepared.bytes,
            "sha256": prepared.sha256,
        }
        if content_type is not None:
            changes["content_type"] = content_type
        if pinned is not None:
            changes["pinned"] = pinned
        self._bump(row, "update", author, **changes)

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry | None:
        """`MemoryStore.get`."""
        with self._lock:
            row = self._rows.get(entry_id)
            if row is None or (row.entry.deleted_at is not None and not include_deleted):
                return None
            return row.entry

    def find(self, scope: MemoryScopeRef, key: str) -> MemoryEntry | None:
        """`MemoryStore.find`."""
        with self._lock:
            entry_id = self._live.get((scope.kind, scope.id, key))
            return None if entry_id is None else self._rows[entry_id].entry

    def mark_read(self, entry_id: str) -> None:
        """`MemoryStore.mark_read`."""
        with self._lock:
            row = self._row(entry_id)
            row.entry = row.entry.model_copy(update={"last_read_at": self._clock()})

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
        """`MemoryStore.update`."""
        with self._lock:
            row = self._row(entry_id)
            self._check_version(row.entry, if_version)
            self._update_row(
                row,
                author=author,
                content=content,
                content_type=content_type,
                tags=tags,
                pinned=pinned,
            )
            return row.entry

    def delete(
        self, entry_id: str, *, author: MemoryAuthor, if_version: int | None = None
    ) -> MemoryEntry:
        """`MemoryStore.delete`."""
        with self._lock:
            row = self._row(entry_id)
            self._check_version(row.entry, if_version)
            entry = row.entry
            del self._live[(entry.scope.kind, entry.scope.id, entry.key)]
            self._bump(row, "delete", author, deleted_at=self._clock())
            return row.entry

    def purge(self, entry_id: str) -> MemoryEntry:
        """`MemoryStore.purge`."""
        with self._lock:
            row = self._row(entry_id, include_deleted=True)
            entry = row.entry
            if entry.deleted_at is None:
                del self._live[(entry.scope.kind, entry.scope.id, entry.key)]
            del self._rows[entry_id]
            return entry

    def restore(
        self, entry_id: str, *, author: MemoryAuthor, version: int | None = None
    ) -> MemoryEntry:
        """`MemoryStore.restore`."""
        with self._lock:
            row = self._row(entry_id, include_deleted=True)
            entry = row.entry
            content = entry.content
            if version is not None:
                old = row.versions.get(version)
                if old is None:
                    raise EntryNotFoundError("그 버전이 없다")
                content = old.content
            live_key = (entry.scope.kind, entry.scope.id, entry.key)
            if entry.deleted_at is not None:
                other = self._live.get(live_key)
                if other is not None:
                    raise EntryExistsError("같은 키의 항목이 이미 있다", entry_id=other)
                self._check_scope_room(entry.scope)
            prepared = prepare_write(self.policy, entry.key, content, entry.tags)
            self._check_total(prepared.bytes - (entry.bytes if entry.deleted_at is None else 0))
            self._live[live_key] = entry_id
            self._bump(
                row,
                "restore",
                author,
                content=prepared.content,
                tags=prepared.tags,
                bytes=prepared.bytes,
                sha256=prepared.sha256,
                deleted_at=None,
            )
            return row.entry

    def archive(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        archived: bool = True,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """`MemoryStore.archive`."""
        with self._lock:
            row = self._row(entry_id)
            self._check_version(row.entry, if_version)
            if row.entry.archived == archived:
                return row.entry
            self._bump(row, "archive" if archived else "unarchive", author, archived=archived)
            return row.entry

    def move(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        to_scope: MemoryScopeRef | None = None,
        to_key: str | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """`MemoryStore.move`."""
        with self._lock:
            row = self._row(entry_id)
            self._check_version(row.entry, if_version)
            entry = row.entry
            scope = to_scope if to_scope is not None else entry.scope
            key = to_key if to_key else entry.key
            check_key(key, max_chars=self.policy.limits.max_key_chars)
            check_secret_field(self.policy.secrets, "key", key)
            old_live = (entry.scope.kind, entry.scope.id, entry.key)
            new_live = (scope.kind, scope.id, key)
            if new_live == old_live:
                return entry
            other = self._live.get(new_live)
            if other is not None:
                raise EntryExistsError("옮길 곳에 같은 키의 항목이 이미 있다", entry_id=other)
            if _scope_key(scope) != _scope_key(entry.scope):
                self._check_scope_room(scope)
            del self._live[old_live]
            self._live[new_live] = entry_id
            self._bump(row, "move", author, scope=scope, key=key)
            return row.entry

    def history(self, entry_id: str) -> list[MemoryVersionSummary]:
        """`MemoryStore.history`."""
        with self._lock:
            row = self._row(entry_id, include_deleted=True)
            return [
                MemoryVersionSummary.model_validate(v.model_dump(exclude={"content"}))
                for _n, v in sorted(row.versions.items())
            ]

    def get_version(self, entry_id: str, version: int) -> MemoryVersion | None:
        """`MemoryStore.get_version`."""
        with self._lock:
            row = self._rows.get(entry_id)
            return None if row is None else row.versions.get(version)

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        """`MemoryStore.search`(대소문자 무시 포함 검색)."""
        check_sort(query.sort, query.order)
        offset = decode_cursor(query.cursor)
        with self._lock:
            entries = [row.entry for row in self._rows.values()]
        scopes = None if query.scopes is None else {_scope_key(s) for s in query.scopes}
        needle = query.text.casefold()
        wanted_tags = set(query.tags)

        def keep(entry: MemoryEntry) -> bool:
            if entry.deleted_at is not None and not query.include_deleted:
                return False
            if entry.archived and not query.include_archived:
                return False
            if scopes is not None and _scope_key(entry.scope) not in scopes:
                return False
            if wanted_tags and not wanted_tags.issubset(entry.tags):
                return False
            if query.author_run is not None and entry.updated_by.run_id != query.author_run:
                return False
            if query.author_kind is not None and entry.updated_by.kind != query.author_kind:
                return False
            if needle:
                hay = (entry.key, entry.content, *entry.tags)
                return any(needle in part.casefold() for part in hay)
            return True

        matched = [e for e in entries if keep(e)]
        matched.sort(key=lambda e: e.id)
        matched.sort(key=lambda e: getattr(e, query.sort), reverse=query.order == "desc")
        page = matched[offset : offset + max(query.limit, 1)]
        end = offset + len(page)
        return MemoryEntryPage(
            items=[summarize(e, self.policy) for e in page],
            next_cursor=encode_cursor(end) if end < len(matched) else None,
            total=len(matched),
        )

    def scan_entries(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> Iterator[MemoryEntry]:
        """선택 능력 `EntryScanner`: 지우지 않은 항목(본문 포함)을 순서 없이 낸다(부른 때 사본)."""
        wanted = None if scopes is None else {_scope_key(s) for s in scopes}
        with self._lock:
            live = [self._rows[eid].entry for eid in self._live.values()]
        for entry in live:
            if entry.archived and not include_archived:
                continue
            if wanted is None or _scope_key(entry.scope) in wanted:
                yield entry

    def count_tags(
        self,
        *,
        scopes: Sequence[MemoryScopeRef] | None = None,
        include_archived: bool = True,
    ) -> dict[str, int]:
        """선택 능력 `TagCounter`: 태그 → 그 태그를 가진 지우지 않은 항목 수."""
        counts: dict[str, int] = {}
        for entry in self.scan_entries(scopes=scopes, include_archived=include_archived):
            for tag in set(entry.tags):
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    def list_scopes(self, *, kind: str | None = None) -> list[MemoryScopeSummary]:
        """`MemoryStore.list_scopes`."""
        with self._lock:
            live = [self._rows[eid].entry for eid in self._live.values()]
        groups: dict[tuple[str, str], list[MemoryEntry]] = {}
        for entry in live:
            if kind is None or entry.scope.kind == kind:
                groups.setdefault(_scope_key(entry.scope), []).append(entry)
        return [
            MemoryScopeSummary(
                scope=MemoryScopeRef(kind=k, id=s),
                entries=len(items),
                archived=sum(1 for e in items if e.archived),
                bytes=sum(e.bytes for e in items),
                updated_at=max(e.updated_at for e in items),
            )
            for (k, s), items in sorted(groups.items())
        ]
