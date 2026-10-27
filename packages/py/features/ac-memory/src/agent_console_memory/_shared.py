"""저장소 구현이 함께 쓰는 작은 도구: 쪽 커서, 요약 만들기, 버전 보관 정리, 정렬 검사."""

from __future__ import annotations

from collections.abc import Sequence

from agent_console_contracts.memory import (
    MEMORY_ENTRY_SORTS,
    MemoryEntry,
    MemoryEntrySummary,
)

from ._errors import MemoryStoreError
from ._policy import MemoryPolicy

_CURSOR_PREFIX = "o:"


def encode_cursor(offset: int) -> str:
    """쪽 위치 → 불투명 커서.

    >>> decode_cursor(encode_cursor(40))
    40
    """
    return f"{_CURSOR_PREFIX}{offset}"


def decode_cursor(cursor: str | None) -> int:
    """커서 → 쪽 위치(None = 0).

    Raises:
        MemoryStoreError: 형식이 틀린 커서.
    """
    if not cursor:
        return 0
    raw = cursor.removeprefix(_CURSOR_PREFIX)
    if raw == cursor or not raw.isdigit():
        raise MemoryStoreError("커서 형식이 틀렸다")
    return int(raw)


def check_sort(sort: str, order: str) -> None:
    """정렬 값 검사(`MEMORY_ENTRY_SORTS`, asc·desc). 틀리면 `MemoryStoreError`."""
    if sort not in MEMORY_ENTRY_SORTS:
        raise MemoryStoreError(f"정렬 값은 {', '.join(MEMORY_ENTRY_SORTS)} 중 하나다")
    if order not in ("asc", "desc"):
        raise MemoryStoreError("정렬 방향은 asc·desc 중 하나다")


def summarize(entry: MemoryEntry, policy: MemoryPolicy) -> MemoryEntrySummary:
    """항목 → 목록 요약.

    미리보기는 본문 전체를 가린 뒤 앞부분을 자른다(잘린 비밀 조각이 새지 않게).
    """
    data = entry.model_dump(exclude={"content"})
    preview = policy.secrets.preview(entry.content)[: policy.limits.preview_chars]
    return MemoryEntrySummary.model_validate({**data, "preview": preview})


def versions_to_drop(versions: Sequence[int], keep: int) -> list[int]:
    """보관 수 `keep`을 넘는 버전 번호(첫 버전은 남기고 오래된 것부터).

    >>> versions_to_drop([1, 2, 3, 4, 5], 3)
    [2, 3]
    >>> versions_to_drop([1, 2], 1)
    [2]
    """
    ordered = sorted(versions)
    extra = len(ordered) - max(keep, 1)
    if extra <= 0:
        return []
    return ordered[1 : 1 + extra]
