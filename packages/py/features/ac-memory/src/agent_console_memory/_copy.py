"""저장소 사이 메모리 복사(design §PI.4.3, 계약 `MemoryCopyRequest`).

원본 저장소에서 조건(`MemoryCopyFilter`)에 맞는 항목을 골라 대상 저장소에 새 항목으로 쓴다. 복사 뒤
두 저장소는 독립이다(출처를 기록하지 않는다). 범위 id는 `remap`으로 대상 맥락의 id로 바꿀 수 있다
(어느 범위 종류가 바꿀 대상인지는 호출자가 정한다 — 이 함수는 범위 종류 이름을 모른다).

>>> from agent_console_contracts.memory import MemoryCopyFilter, MemoryScopeRef
>>> from agent_console_memory import InMemoryMemoryStore
>>> from agent_console_memory.testing import user_author
>>> source, target = InMemoryMemoryStore(), InMemoryMemoryStore()
>>> _ = source.write(MemoryScopeRef(kind="notes", id="a"), "k", "본문", author=user_author())
>>> result = copy_memory(source, target, remap=[MemoryScopeRemap.model_validate(
...     {"from": "a", "to": "b"})])
>>> result.copied, target.find(MemoryScopeRef(kind="notes", id="b"), "k").content
(1, '본문')
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, get_args

from agent_console_contracts import Issue
from agent_console_contracts.memory import (
    KnownMemoryAuthorKinds,
    MemoryAuthor,
    MemoryCopyConflict,
    MemoryCopyFilter,
    MemoryCopyResult,
    MemoryEntry,
    MemoryEntrySummary,
    MemoryImportPolicy,
    MemoryScopeRef,
    MemoryScopeRemap,
)

from ._errors import MemoryStoreError
from ._scan import iter_entries
from ._store import MemoryStore

DEFAULT_COPY_RENAME_FORMAT: Final = "{key} ({n})"
"""`rename` 새 키 틀(`{key}` = 원래 키, `{n}` = 2부터 오르는 수). 가져오기와 같은 모양."""

_MAX_RENAME_TRIES: Final = 1000


def copy_author() -> MemoryAuthor:
    """복사 버전의 기본 쓴 주체(`system`)."""
    return MemoryAuthor(kind=KnownMemoryAuthorKinds.SYSTEM)


def matches_filter(entry: MemoryEntrySummary | MemoryEntry, flt: MemoryCopyFilter) -> bool:
    """항목이 복사 조건에 맞는지(모든 조건 AND, 비운 조건은 거르지 않음, 태그는 하나라도).

    >>> from agent_console_contracts.memory import MemoryCopyFilter
    >>> from agent_console_memory import InMemoryMemoryStore
    >>> from agent_console_memory.testing import user_author
    >>> s = InMemoryMemoryStore()
    >>> e = s.write(MemoryScopeRef(kind="notes", id=""), "k", "x", author=user_author(),
    ...             tags=["a"]).entry
    >>> matches_filter(e, MemoryCopyFilter(tags=["a", "b"])), matches_filter(
    ...     e, MemoryCopyFilter(scope_kinds=["team"]))
    (True, False)
    """
    if flt.scope_kinds is not None and entry.scope.kind not in flt.scope_kinds:
        return False
    if flt.scope_ids is not None and entry.scope.id not in flt.scope_ids:
        return False
    if flt.keys is not None and entry.key not in flt.keys:
        return False
    return not (flt.tags is not None and not set(entry.tags) & set(flt.tags))


def remap_scope(scope: MemoryScopeRef, remap: Sequence[MemoryScopeRemap]) -> MemoryScopeRef:
    """범위 id 바꾸기(앞의 것이 먼저 맞는다, `kind`가 있으면 그 범위 종류에만).

    >>> rules = [MemoryScopeRemap.model_validate({"from": "a", "to": "b", "kind": "team"})]
    >>> remap_scope(MemoryScopeRef(kind="team", id="a"), rules).id
    'b'
    >>> remap_scope(MemoryScopeRef(kind="notes", id="a"), rules).id
    'a'
    """
    for rule in remap:
        if rule.from_ == scope.id and (rule.kind is None or rule.kind == scope.kind):
            return MemoryScopeRef(kind=scope.kind, id=rule.to)
    return scope


class _Copier:
    def __init__(
        self,
        target: MemoryStore,
        *,
        on_conflict: MemoryImportPolicy,
        author: MemoryAuthor,
        rename_format: str,
    ) -> None:
        self.target = target
        self.on_conflict = on_conflict
        self.author = author
        self.rename_format = rename_format
        self.copied = 0
        self.skipped = 0
        self.conflicts: list[MemoryCopyConflict] = []
        self.issues: list[Issue] = []

    def free_key(self, scope: MemoryScopeRef, key: str) -> str | None:
        for n in range(2, _MAX_RENAME_TRIES):
            candidate = self.rename_format.format(key=key, n=n)
            if self.target.find(scope, candidate) is None:
                return candidate
        return None

    def problem(self, scope: MemoryScopeRef, key: str, code: str, message: str) -> None:
        self.skipped += 1
        shown = self.target.policy.secrets.preview(key)
        self.issues.append(
            Issue(
                severity="warning",
                code=code,
                message=message,
                details={"scope": scope.model_dump(mode="json"), "key": shown},
            )
        )

    def accept(self, entry: MemoryEntry, scope: MemoryScopeRef) -> None:
        key = entry.key
        existing = self.target.find(scope, key)
        target_key, overwrite = key, False
        if existing is not None:
            if self.on_conflict == "skip":
                self.skipped += 1
                self.conflicts.append(MemoryCopyConflict(scope=scope, key=key, resolution="skip"))
                return
            if self.on_conflict == "rename":
                free = self.free_key(scope, key)
                if free is None:
                    self.problem(scope, key, "already_exists", "바꿀 새 키를 찾지 못했습니다")
                    return
                target_key = free
            else:
                overwrite = True
        try:
            written = self.target.write(
                scope,
                target_key,
                entry.content,
                author=self.author,
                tags=list(entry.tags),
                content_type=entry.content_type,
                pinned=entry.pinned,
                create_only=not overwrite,
            ).entry
            if written.archived != entry.archived:
                self.target.archive(
                    written.id,
                    author=self.author,
                    archived=entry.archived,
                    if_version=written.version,
                )
        except MemoryStoreError as exc:
            self.problem(scope, key, exc.code, exc.message)
            return
        self.copied += 1
        if existing is not None:
            self.conflicts.append(
                MemoryCopyConflict(
                    scope=scope,
                    key=key,
                    resolution=self.on_conflict,
                    new_key=target_key if target_key != key else None,
                )
            )

    def result(self) -> MemoryCopyResult:
        return MemoryCopyResult(
            copied=self.copied, skipped=self.skipped, conflicts=self.conflicts, issues=self.issues
        )


def copy_memory(
    source: MemoryStore,
    target: MemoryStore,
    *,
    filter: MemoryCopyFilter | None = None,
    on_conflict: MemoryImportPolicy = "skip",
    remap: Sequence[MemoryScopeRemap] = (),
    author: MemoryAuthor | None = None,
    include_archived: bool = True,
    rename_format: str = DEFAULT_COPY_RENAME_FORMAT,
) -> MemoryCopyResult:
    """원본의 지우지 않은 항목을 골라 대상에 쓴다(복사 뒤 독립, 출처 기록 없음).

    Args:
        source: 원본 저장소(읽기만).
        target: 대상 저장소. 쓰기는 대상 정책(키 규칙·비밀 검사·크기·개수 한도)을 거친다.
        filter: 고를 항목(None = 전부). 범위 조건은 **원본** 범위(바꾸기 전)에 건다.
        on_conflict: 대상에 같은 범위·키가 있을 때 `skip`·`overwrite`(새 버전)·`rename`(새 키).
        remap: 범위 id 바꾸기(`remap_scope`).
        author: 대상에 쓸 버전의 쓴 주체(기본 `system`).
        include_archived: 보관 항목도 복사한다(보관 상태 유지).
        rename_format: `rename` 새 키 틀.

    Returns:
        `MemoryCopyResult`. 쓰지 못한 항목은 `skipped`에 세고 `issues`(본문 없음, 키는 대상 정책으로
        가린 값)에 남긴다. 버전 기록은 옮기지 않는다(대상의 버전 1부터).

    Raises:
        ValueError: 모르는 `on_conflict`.
    """
    if on_conflict not in get_args(MemoryImportPolicy):
        raise ValueError(f"on_conflict는 {', '.join(get_args(MemoryImportPolicy))} 중 하나다")
    flt = filter if filter is not None else MemoryCopyFilter()
    copier = _Copier(
        target,
        on_conflict=on_conflict,
        author=author if author is not None else copy_author(),
        rename_format=rename_format,
    )
    for scanned in iter_entries(source, include_archived=include_archived):
        if not isinstance(scanned, MemoryEntry | MemoryEntrySummary):
            found = source.get(scanned.id)
            if found is None:
                continue
            scanned = found
        if not matches_filter(scanned, flt):
            continue
        entry = scanned if isinstance(scanned, MemoryEntry) else source.get(scanned.id)
        if entry is None:  # 훑는 사이에 지워짐
            continue
        copier.accept(entry, remap_scope(entry.scope, remap))
    return copier.result()


__all__ = [
    "DEFAULT_COPY_RENAME_FORMAT",
    "copy_author",
    "copy_memory",
    "matches_filter",
    "remap_scope",
]
