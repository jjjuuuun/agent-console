"""메모리 저장소 프로토콜(X31)과 질의 값.

구현(메모리·SQLite·사용자 구현)은 모두 같은 의미를 지킨다(`testing.MemoryStoreContractTests`):

- 쓰기마다 버전이 1 오르고 버전 기록이 남는다(만들기·고치기·지우기·되돌리기·보관·옮기기).
- `if_version`을 주면 현재 버전과 다를 때 `VersionConflictError`, 주지 않으면 마지막 쓰기가 이긴다.
- 같은 항목에 대한 쓰기는 줄을 선다(스레드·asyncio 병렬에서도 버전이 겹치지 않는다).
- 쓰기 값은 `prepare_write`(키 규칙·비밀 검사·크기 한도)를 거친다.
- 지우기는 표시(soft)이고, 완전 삭제(`purge`)는 버전까지 지운다.
- 시각은 주입한 시계(Unix epoch 초)다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from agent_console_contracts.memory import (
    MemoryAuthor,
    MemoryEntry,
    MemoryEntryPage,
    MemoryScopeRef,
    MemoryScopeSummary,
    MemoryVersion,
    MemoryVersionSummary,
)

from ._policy import MemoryPolicy

WriteMode = Literal["replace", "append"]
"""쓰기 방식: replace = 본문을 바꿈, append = 기존 본문 뒤에 붙임(없으면 만듦)."""

SortOrder = Literal["asc", "desc"]


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    """목록·검색 조건. 모든 조건은 AND.

    Attributes:
        scopes: 범위 목록(None = 모든 범위).
        text: 키·본문·태그 포함 검색어(대소문자 무시, 빈 값 = 조건 없음).
        tags: 모두 붙어 있어야 하는 태그.
        author_run: 마지막으로 쓴 실행 id.
        author_kind: 마지막으로 쓴 주체 종류.
        include_archived: 보관 항목 포함.
        include_deleted: 지운 항목 포함.
        sort: 정렬 필드(`MEMORY_ENTRY_SORTS`).
        order: 방향.
        cursor: 앞 쪽 응답의 `next_cursor`.
        limit: 쪽 크기.
    """

    scopes: Sequence[MemoryScopeRef] | None = None
    text: str = ""
    tags: Sequence[str] = ()
    author_run: str | None = None
    author_kind: str | None = None
    include_archived: bool = False
    include_deleted: bool = False
    sort: str = "updated_at"
    order: SortOrder = "desc"
    cursor: str | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class MemoryWriteOutcome:
    """`write` 결과: 저장된 항목과 새로 만들었는지."""

    entry: MemoryEntry
    created: bool


@runtime_checkable
class MemoryStore(Protocol):
    """메모리 저장소(X31). 메서드는 동기이며 스레드 안전해야 한다."""

    policy: MemoryPolicy
    """쓰기 정책(한도·비밀 검사·버전 보관 수). 설정이 바뀌면 바꿔 끼운다."""

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
        """(범위, 키)에 쓴다. 없으면 만들고(버전 1) 있으면 새 버전.

        `tags`·`content_type`·`pinned`가 None이면 기존 값(만들 때는 기본값)을 둔다.

        Raises:
            InvalidKeyError, SecretRejectedError, TooLargeError: 쓰기 검사.
            VersionConflictError: `if_version`이 다름(없는 항목에 1 이상을 주어도).
            EntryExistsError: `create_only`인데 이미 있음.
        """
        ...

    def get(self, entry_id: str, *, include_deleted: bool = False) -> MemoryEntry | None:
        """id로 항목 하나. 없거나(지운 것은 `include_deleted`가 아니면) None."""
        ...

    def find(self, scope: MemoryScopeRef, key: str) -> MemoryEntry | None:
        """(범위, 키)의 지우지 않은 항목(보관 포함). 없으면 None."""
        ...

    def mark_read(self, entry_id: str) -> None:
        """에이전트 도구가 읽은 시각(`last_read_at`)을 남긴다. 버전은 오르지 않는다."""
        ...

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
        """id로 고친다(None = 그대로). Raises: `EntryNotFoundError`, 쓰기 검사 오류, 충돌."""
        ...

    def delete(
        self, entry_id: str, *, author: MemoryAuthor, if_version: int | None = None
    ) -> MemoryEntry:
        """표시 삭제(버전 동작 `delete`). 이미 지운 항목이면 `EntryNotFoundError`."""
        ...

    def purge(self, entry_id: str) -> MemoryEntry:
        """완전 삭제(항목·버전). 지운 직전 상태를 돌려준다. Raises: `EntryNotFoundError`."""
        ...

    def restore(
        self, entry_id: str, *, author: MemoryAuthor, version: int | None = None
    ) -> MemoryEntry:
        """되돌리기(버전 동작 `restore`). 지운 항목이면 되살리고, `version`을 주면 그 버전의
        본문으로 바꾼다(키·범위는 지금 값).

        Raises:
            EntryNotFoundError: 항목·버전이 없음.
            EntryExistsError: 되살릴 (범위, 키)에 다른 항목이 있음.
        """
        ...

    def archive(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        archived: bool = True,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """보관·보관 풀기(버전 동작 `archive`·`unarchive`). 이미 그 상태면 그대로 돌려준다."""
        ...

    def move(
        self,
        entry_id: str,
        *,
        author: MemoryAuthor,
        to_scope: MemoryScopeRef | None = None,
        to_key: str | None = None,
        if_version: int | None = None,
    ) -> MemoryEntry:
        """범위·키 바꾸기(버전 동작 `move`, id는 그대로).

        Raises:
            EntryExistsError: 대상에 같은 키가 있음. 그 밖에 키 규칙·비밀(키)·범위 개수 한도.
        """
        ...

    def history(self, entry_id: str) -> list[MemoryVersionSummary]:
        """버전 목록(오름차순). 항목이 없으면 `EntryNotFoundError`(지운 항목은 본다)."""
        ...

    def get_version(self, entry_id: str, version: int) -> MemoryVersion | None:
        """버전 하나(본문 포함). 없으면 None."""
        ...

    def search(self, query: MemoryQuery) -> MemoryEntryPage:
        """목록·검색(`MemoryQuery`). 항목은 요약(미리보기는 비밀 가림 뒤)."""
        ...

    def list_scopes(self, *, kind: str | None = None) -> list[MemoryScopeSummary]:
        """항목이 있는 범위 요약(범위 종류·범위 id 순). `kind_known`은 판단하지 않는다(true)
        — 범위 종류 목록을 아는 쪽이 `ScopeKindCatalog.annotate`로 채운다."""
        ...
