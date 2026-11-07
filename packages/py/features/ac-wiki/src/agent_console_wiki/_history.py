"""페이지 기록 저장소(X49): 프로토콜 `WikiHistory`와 메모리 구현 `InMemoryWikiHistory`(design
§7R.6).

모든 구현이 지킬 의미(`testing.WikiHistoryContractTests`):

- 버전은 (위키, 페이지 경로)마다 1부터 하나씩 오른다. 지운 버전의 번호를 다시 쓰지 않는다.
- `record(entries)`는 한 번에(원자적으로) 남긴다 — 옮기기의 두 행(`move_out`·`move_in`)이 함께
  남거나 함께 남지 않는다. 같은 본문(sha256)은 한 번만 둔다.
- 본문 없이(`content=None`) 남긴 버전(지우기 등)은 같은 해시의 본문이 이미 있어야 읽힌다 — 지우기는
  지우기 직전 해시를 가리킨다.
- `prune(keep)`: 첫 버전은 남기고 오래된 것부터 지워 `keep`개만 남긴다. 아무 버전도 가리키지 않는
  본문도 지운다. 지운 적이 있으면 목록의 `pruned`가 참이다.
- `changes`: 최근 것부터. `wiki=None`이면 공간의 모든 위키를 가로지른다. `author_run`은 쓴 주체의
  `run_id` **또는** `root_run_id`가 그 값인 기록(루트 실행 상세에서 하위 실행 쓰기까지). 커서는
  구현이 정하는 불투명한 문자열이다.
- 쓴 주체(`WikiAuthor`, `label` 포함)는 받은 그대로 돌려준다(기록 시점 이름이 남는다).
"""

from __future__ import annotations

import builtins
import hashlib
import threading
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agent_console_contracts.wiki import (
    WikiAuthor,
    WikiChange,
    WikiChangePage,
    WikiHistoryPage,
    WikiPageVersion,
)

__all__ = [
    "HistoryEntry",
    "HistorySummary",
    "InMemoryWikiHistory",
    "WikiHistory",
]


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """남길 기록 한 줄.

    Attributes:
        wiki: 위키 id.
        path: 페이지 경로.
        op: 동작(`KnownWikiVersionOps`, 열린 문자열).
        sha256: 본문 해시(지우기·옮겨 감은 그 직전 본문 해시).
        bytes: 본문 바이트 수.
        author: 쓴 쪽.
        at: 시각(유닉스 초).
        content: 본문(없으면 같은 해시 본문이 이미 있어야 읽힌다).
        message: 한 줄 메시지.
        from_: `move_in`의 옛 경로.
        to: `move_out`의 새 경로.
    """

    wiki: str
    path: str
    op: str
    sha256: str
    bytes: int
    author: WikiAuthor
    at: float
    content: builtins.bytes | None = None
    message: str | None = None
    from_: str | None = None
    to: str | None = None

    @classmethod
    def of(
        cls,
        wiki: str,
        path: str,
        op: str,
        data: builtins.bytes,
        *,
        author: WikiAuthor,
        at: float,
        message: str | None = None,
        from_: str | None = None,
        to: str | None = None,
    ) -> HistoryEntry:
        """본문 바이트로 만든다(해시·크기 계산)."""
        return cls(
            wiki=wiki,
            path=path,
            op=op,
            sha256=hashlib.sha256(data).hexdigest(),
            bytes=len(data),
            author=author,
            at=at,
            content=data,
            message=message,
            from_=from_,
            to=to,
        )


@dataclass(frozen=True, slots=True)
class HistorySummary:
    """페이지 하나의 기록 요약(목록·점검·외부 변경 감지가 페이지마다 따로 묻지 않게).

    Attributes:
        path: 페이지 경로.
        first_at: 첫 기록 시각.
        latest: 마지막 기록.
    """

    path: str
    first_at: float
    latest: WikiPageVersion


@runtime_checkable
class WikiHistory(Protocol):
    """페이지 기록 저장소. 메서드는 동기이며 스레드 안전해야 한다."""

    def record(self, entries: Sequence[HistoryEntry]) -> list[WikiPageVersion]:
        """기록을 한 번에 남기고 새 버전들을 같은 순서로 돌려준다."""
        ...

    def list(self, wiki: str, path: str, *, limit: int | None = None) -> WikiHistoryPage:
        """페이지 기록(최근 것부터, `limit`개까지)."""
        ...

    def get(self, wiki: str, path: str, version: int) -> WikiPageVersion | None:
        """버전 하나(없거나 지웠으면 None)."""
        ...

    def read(self, wiki: str, path: str, version: int) -> bytes | None:
        """그 버전 본문(없거나 본문이 없으면 None)."""
        ...

    def latest(self, wiki: str, path: str) -> WikiPageVersion | None:
        """마지막 버전(기록이 없으면 None)."""
        ...

    def summaries(self, wiki: str) -> dict[str, HistorySummary]:
        """위키의 기록이 있는 페이지마다 요약."""
        ...

    def changes(
        self,
        wiki: str | None = None,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        """최근 변경(최근 것부터). `ops`가 비면 모든 동작."""
        ...

    def prune(self, wiki: str, path: str, *, keep: int) -> int:
        """첫 버전을 남기고 오래된 것부터 지워 `keep`개만 남긴다. Returns: 지운 버전 수."""
        ...


@dataclass(slots=True)
class _Row:
    seq: int
    wiki: str
    path: str
    version: WikiPageVersion


class InMemoryWikiHistory:
    """메모리 기록 저장소(X49 기본 구현 — 단독 실행·시험용). 프로세스가 끝나면 사라진다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[_Row] = []
        self._pages: dict[tuple[str, str], list[_Row]] = {}
        self._next_version: dict[tuple[str, str], int] = {}
        self._blobs: dict[str, bytes] = {}
        self._pruned: set[tuple[str, str]] = set()
        self._seq = 0

    def record(self, entries: Sequence[HistoryEntry]) -> list[WikiPageVersion]:
        with self._lock:
            out: list[WikiPageVersion] = []
            for entry in entries:
                key = (entry.wiki, entry.path)
                number = self._next_version.get(key, 1)
                self._next_version[key] = number + 1
                if entry.content is not None:
                    self._blobs.setdefault(entry.sha256, bytes(entry.content))
                version = WikiPageVersion.model_validate(
                    {
                        "version": number,
                        "op": entry.op,
                        "sha256": entry.sha256,
                        "bytes": entry.bytes,
                        "author": entry.author.model_dump(mode="json"),
                        "message": entry.message,
                        "at": entry.at,
                        "from": entry.from_,
                        "to": entry.to,
                    }
                )
                self._seq += 1
                row = _Row(self._seq, entry.wiki, entry.path, version)
                self._rows.append(row)
                self._pages.setdefault(key, []).append(row)
                out.append(version)
            return out

    def list(self, wiki: str, path: str, *, limit: int | None = None) -> WikiHistoryPage:
        with self._lock:
            rows = list(reversed(self._pages.get((wiki, path), [])))
            if limit is not None:
                rows = rows[: max(0, limit)]
            return WikiHistoryPage(
                items=[r.version for r in rows], pruned=(wiki, path) in self._pruned
            )

    def get(self, wiki: str, path: str, version: int) -> WikiPageVersion | None:
        with self._lock:
            for row in self._pages.get((wiki, path), []):
                if row.version.version == version:
                    return row.version
            return None

    def read(self, wiki: str, path: str, version: int) -> bytes | None:
        found = self.get(wiki, path, version)
        if found is None:
            return None
        with self._lock:
            return self._blobs.get(found.sha256)

    def latest(self, wiki: str, path: str) -> WikiPageVersion | None:
        with self._lock:
            rows = self._pages.get((wiki, path))
            return rows[-1].version if rows else None

    def summaries(self, wiki: str) -> dict[str, HistorySummary]:
        with self._lock:
            return {
                path: HistorySummary(
                    path=path, first_at=rows[0].version.at, latest=rows[-1].version
                )
                for (w, path), rows in self._pages.items()
                if w == wiki and rows
            }

    def changes(
        self,
        wiki: str | None = None,
        *,
        author_run: str | None = None,
        ops: Collection[str] = (),
        limit: int = 50,
        cursor: str | None = None,
    ) -> WikiChangePage:
        wanted = set(ops)
        before = int(cursor) if cursor and cursor.isdigit() else None
        size = max(1, limit)
        items: list[WikiChange] = []
        next_cursor: str | None = None
        items_last_seq = 0
        with self._lock:
            for row in reversed(self._rows):
                if before is not None and row.seq >= before:
                    continue
                if wiki is not None and row.wiki != wiki:
                    continue
                version = row.version
                if wanted and version.op not in wanted:
                    continue
                if author_run is not None and author_run not in (
                    version.author.run_id,
                    version.author.root_run_id,
                ):
                    continue
                if len(items) == size:
                    next_cursor = str(items_last_seq)
                    break
                items.append(
                    WikiChange.model_validate(
                        {
                            **version.model_dump(mode="json", by_alias=True),
                            "wiki": row.wiki,
                            "path": row.path,
                        }
                    )
                )
                items_last_seq = row.seq
        return WikiChangePage(items=items, next_cursor=next_cursor)

    def prune(self, wiki: str, path: str, *, keep: int) -> int:
        keep = max(1, keep)
        with self._lock:
            key = (wiki, path)
            rows = self._pages.get(key, [])
            if len(rows) <= keep:
                return 0
            drop = rows[1 : len(rows) - keep + 1]
            gone = {id(r) for r in drop}
            self._pages[key] = [r for r in rows if id(r) not in gone]
            self._rows = [r for r in self._rows if id(r) not in gone]
            self._pruned.add(key)
            used = {r.version.sha256 for r in self._rows}
            for sha in [s for s in self._blobs if s not in used]:
                del self._blobs[sha]
            return len(drop)
