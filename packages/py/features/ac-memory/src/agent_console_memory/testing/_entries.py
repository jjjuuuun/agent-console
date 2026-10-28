"""테스트 도구: 저장소 없이 만드는 항목 표본(정리 규칙 판단 대상·내보내기 형식 시험용)."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.memory import (
    MEMORY_DEFAULT_CONTENT_TYPE,
    KnownMemoryAuthorKinds,
    MemoryAuthor,
    MemoryEntry,
    MemoryEntrySummary,
    MemoryScopeRef,
)


def sample_entry_summary(**values: Any) -> MemoryEntrySummary:
    """항목 요약 표본. 기본: 범위 `sample:s1`, 키 `k`, 시각 0, 사람이 씀, 버전 1. `values`로 바꾼다.

    >>> sample_entry_summary(key="a/b", tags=["x"]).tags
    ['x']
    """
    author = MemoryAuthor(kind=KnownMemoryAuthorKinds.USER)
    base: dict[str, Any] = {
        "id": "entry-1",
        "scope": MemoryScopeRef(kind="sample", id="s1"),
        "key": "k",
        "content_type": MEMORY_DEFAULT_CONTENT_TYPE,
        "version": 1,
        "bytes": 0,
        "sha256": "",
        "created_at": 0.0,
        "created_by": author,
        "updated_at": 0.0,
        "updated_by": author,
    }
    base.update(values)
    return MemoryEntrySummary.model_validate(base)


def sample_entry(**values: Any) -> MemoryEntry:
    """본문 포함 항목 표본(`sample_entry_summary`와 같은 기본값 + 본문 `""`).

    >>> sample_entry(content="x").content
    'x'
    """
    data = sample_entry_summary().model_dump(exclude={"preview"})
    data.update({"content": "", **values})
    return MemoryEntry.model_validate(data)
