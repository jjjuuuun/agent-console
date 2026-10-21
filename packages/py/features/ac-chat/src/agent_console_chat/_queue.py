"""대기열 저장 프로토콜(`QueueStore`)과 기본 메모리 구현(design §2R.10, D7).

`agent_console_mod_chat.storage`의 대기열 저장소(SQLite·인메모리)가 이 프로토콜을
구조적으로 만족하므로 서버는 그 저장소를 그대로 넘긴다. 이 패키지는 저장소를 import하지 않는다.
"""

import builtins
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

RESTART_HOLD_REASON = "restart"
"""`chat.queue_after_restart = ask`가 멈춘 항목에 남기는 `held_reason`."""


class QueueEntry(Protocol):
    """대기열 항목 하나(읽기 전용)."""

    @property
    def id(self) -> str: ...

    @property
    def conversation_id(self) -> str: ...

    @property
    def position(self) -> int:
        """대화 안 순번(1 = 다음 차례)."""
        ...

    @property
    def text(self) -> str: ...

    @property
    def held(self) -> bool:
        """재시작 등으로 멈춘 항목. 풀기 전에는 꺼내지 않는다."""
        ...


class QueueSize(Protocol):
    """대화의 대기열 규모."""

    @property
    def queued(self) -> int: ...

    @property
    def held(self) -> int: ...


class QueueStore(Protocol):
    """대화별 FIFO 대기열 저장소. 메서드는 `mod-chat` 저장소의 대기열과 같다.

    - `pop_next`는 맨 앞 항목이 멈춰(`held`) 있으면 None을 돌려준다(순서를 지키려고 멈춘 항목이
      뒤의 항목을 막는다). 풀거나(`release`) 지워야(`remove`) 흐른다.
    - 지우면 같은 대화의 뒤 순번을 당긴다.
    """

    def enqueue(
        self,
        item_id: str,
        conversation_id: str,
        text: str,
        *,
        created_at: float,
        held: bool = False,
        held_reason: str | None = None,
    ) -> QueueEntry: ...

    def get(self, item_id: str) -> QueueEntry | None: ...

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> Sequence[QueueEntry]:
        """대화(생략하면 전체)의 항목을 (대화, 순번) 순으로."""
        ...

    def remove(self, item_id: str) -> bool: ...

    def hold_all(self, reason: str | None = None, *, conversation_id: str | None = None) -> int: ...

    def release(self, item_id: str) -> QueueEntry:
        """멈춤을 푼다. 없으면 예외(구현마다 다름 — 서비스는 먼저 `get`으로 확인한다)."""
        ...

    def pop_next(self, conversation_id: str) -> QueueEntry | None: ...

    def counts(self, conversation_ids: Iterable[str] | None = None) -> Mapping[str, QueueSize]:
        """대화 id → 규모(빈 대화는 빠진다)."""
        ...

    def clear(self, conversation_id: str) -> int: ...


@dataclass(frozen=True, slots=True)
class MemoryQueueItem:
    """`MemoryQueue` 항목."""

    id: str
    conversation_id: str
    position: int
    text: str
    created_at: float
    held: bool = False
    held_reason: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryQueueSize:
    """`MemoryQueue.counts` 값."""

    queued: int
    held: int


class MemoryQueue:
    """`QueueStore` 메모리 구현(기본값). 프로세스가 끝나면 사라진다. 스레드 안전."""

    def __init__(self) -> None:
        self._items: dict[str, list[MemoryQueueItem]] = {}
        self._lock = threading.Lock()

    def enqueue(
        self,
        item_id: str,
        conversation_id: str,
        text: str,
        *,
        created_at: float,
        held: bool = False,
        held_reason: str | None = None,
    ) -> MemoryQueueItem:
        with self._lock:
            if any(i.id == item_id for items in self._items.values() for i in items):
                raise ValueError(f"대기열 항목 {item_id!r}가 이미 있습니다")
            items = self._items.setdefault(conversation_id, [])
            item = MemoryQueueItem(
                id=item_id,
                conversation_id=conversation_id,
                position=len(items) + 1,
                text=text,
                created_at=created_at,
                held=held,
                held_reason=held_reason if held else None,
            )
            items.append(item)
            return item

    def get(self, item_id: str) -> MemoryQueueItem | None:
        with self._lock:
            return self._find(item_id)

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> builtins.list[MemoryQueueItem]:
        with self._lock:
            keys = [conversation_id] if conversation_id is not None else sorted(self._items)
            return [
                i
                for key in keys
                for i in self._items.get(key, [])
                if held is None or i.held == held
            ]

    def remove(self, item_id: str) -> bool:
        with self._lock:
            item = self._find(item_id)
            if item is None:
                return False
            items = [i for i in self._items[item.conversation_id] if i.id != item_id]
            self._store(item.conversation_id, items)
            return True

    def hold_all(self, reason: str | None = None, *, conversation_id: str | None = None) -> int:
        with self._lock:
            changed = 0
            keys = [conversation_id] if conversation_id is not None else builtins.list(self._items)
            for key in keys:
                items = self._items.get(key, [])
                for n, item in enumerate(items):
                    if not item.held:
                        items[n] = replace(item, held=True, held_reason=reason)
                        changed += 1
            return changed

    def release(self, item_id: str) -> MemoryQueueItem:
        with self._lock:
            item = self._find(item_id)
            if item is None:
                raise KeyError(item_id)
            items = self._items[item.conversation_id]
            released = replace(item, held=False, held_reason=None)
            items[items.index(item)] = released
            return released

    def pop_next(self, conversation_id: str) -> MemoryQueueItem | None:
        with self._lock:
            items = self._items.get(conversation_id, [])
            if not items or items[0].held:
                return None
            head = items[0]
            self._store(conversation_id, items[1:])
            return head

    def counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, MemoryQueueSize]:
        with self._lock:
            keys = (
                builtins.list(conversation_ids)
                if conversation_ids is not None
                else builtins.list(self._items)
            )
            result: dict[str, MemoryQueueSize] = {}
            for key in keys:
                items = self._items.get(key, [])
                if items:
                    result[key] = MemoryQueueSize(
                        queued=len(items), held=sum(1 for i in items if i.held)
                    )
            return result

    def clear(self, conversation_id: str) -> int:
        with self._lock:
            return len(self._items.pop(conversation_id, []))

    def _find(self, item_id: str) -> MemoryQueueItem | None:
        for items in self._items.values():
            for item in items:
                if item.id == item_id:
                    return item
        return None

    def _store(self, conversation_id: str, items: builtins.list[MemoryQueueItem]) -> None:
        renumbered = [replace(item, position=n) for n, item in enumerate(items, start=1)]
        if renumbered:
            self._items[conversation_id] = renumbered
        else:
            self._items.pop(conversation_id, None)
