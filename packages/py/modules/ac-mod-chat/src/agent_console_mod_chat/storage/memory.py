"""대화·대기열 인메모리 저장소(테스트·DB 없는 사용). SQLite 구현과 같은 규칙.

대화와 대기열은 한 상태·한 락을 공유해, 대화를 지우면 대기열도 함께(원자적으로) 지워진다.
"""

from __future__ import annotations

import builtins
import threading
from collections.abc import Collection, Iterable
from dataclasses import replace

from agent_console_contracts import Conversation
from agent_console_store import AssignCandidate

from .models import QueueCounts, QueuedItem, QueueItemExistsError, QueueItemNotFoundError


class _State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.conversations: dict[str, Conversation] = {}
        self.queue: dict[str, QueuedItem] = {}


class InMemoryConversationRepository:
    """대화 인메모리 저장소."""

    def __init__(self, state: _State) -> None:
        self._s = state

    def save(self, conversation: Conversation) -> None:
        with self._s.lock:
            self._s.conversations[conversation.id] = conversation.model_copy(deep=True)

    def get(self, conversation_id: str) -> Conversation | None:
        with self._s.lock:
            row = self._s.conversations.get(conversation_id)
            return None if row is None else row.model_copy(deep=True)

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Conversation]:
        with self._s.lock:
            rows = [
                c
                for c in self._s.conversations.values()
                if (graph_id is None or c.graph_id == graph_id)
                and (archived is None or c.archived == archived)
                and (project_id is None or c.project_id == project_id)
            ]
        rows.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return [c.model_copy(deep=True) for c in rows[:limit]]

    # ------------------------------------------------ 프로젝트 넣기·개수(`ProjectAssignStore`)

    def project_id_counts(self) -> dict[str | None, int]:
        out: dict[str | None, int] = {}
        with self._s.lock:
            for c in self._s.conversations.values():
                out[c.project_id] = out.get(c.project_id, 0) + 1
        return out

    def candidates(self, ids: Collection[str] | None) -> builtins.list[AssignCandidate]:
        wanted = None if ids is None else set(ids)
        with self._s.lock:
            return [
                AssignCandidate(c.id, c.project_id)
                for c in self._s.conversations.values()
                if (c.project_id is None if wanted is None else c.id in wanted)
            ]

    def set_project(self, ids: Collection[str], project_id: str) -> int:
        changed = 0
        with self._s.lock:
            for cid in ids:
                row = self._s.conversations.get(cid)
                if row is not None:
                    row.project_id = project_id
                    changed += 1
        return changed

    def delete(self, conversation_id: str) -> bool:
        """대화와 그 대기열을 함께 지운다. 대화가 있었으면 True."""
        with self._s.lock:
            self._s.queue = {
                k: v for k, v in self._s.queue.items() if v.conversation_id != conversation_id
            }
            return self._s.conversations.pop(conversation_id, None) is not None


class InMemoryQueueRepository:
    """대기열 인메모리 저장소."""

    def __init__(self, state: _State) -> None:
        self._s = state

    def _of(self, conversation_id: str) -> builtins.list[QueuedItem]:
        rows = [q for q in self._s.queue.values() if q.conversation_id == conversation_id]
        rows.sort(key=lambda q: q.position)
        return rows

    def _compact(self, conversation_id: str) -> None:
        for number, item in enumerate(self._of(conversation_id), start=1):
            if item.position != number:
                self._s.queue[item.id] = replace(item, position=number)

    def enqueue(
        self,
        item_id: str,
        conversation_id: str,
        text: str,
        *,
        created_at: float,
        held: bool = False,
        held_reason: str | None = None,
    ) -> QueuedItem:
        with self._s.lock:
            if item_id in self._s.queue:
                raise QueueItemExistsError(f"queue/{item_id}")
            item = QueuedItem(
                id=item_id,
                conversation_id=conversation_id,
                position=len(self._of(conversation_id)) + 1,
                text=text,
                created_at=created_at,
                held=held,
                held_reason=held_reason if held else None,
            )
            self._s.queue[item_id] = item
            return item

    def get(self, item_id: str) -> QueuedItem | None:
        with self._s.lock:
            return self._s.queue.get(item_id)

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> builtins.list[QueuedItem]:
        with self._s.lock:
            rows = [
                q
                for q in self._s.queue.values()
                if (conversation_id is None or q.conversation_id == conversation_id)
                and (held is None or q.held == held)
            ]
        rows.sort(key=lambda q: (q.conversation_id, q.position))
        return rows

    def remove(self, item_id: str) -> bool:
        with self._s.lock:
            item = self._s.queue.pop(item_id, None)
            if item is None:
                return False
            self._compact(item.conversation_id)
            return True

    def hold_all(self, reason: str | None = None, *, conversation_id: str | None = None) -> int:
        changed = 0
        with self._s.lock:
            for item in builtins.list(self._s.queue.values()):
                if item.held or (
                    conversation_id is not None and item.conversation_id != conversation_id
                ):
                    continue
                self._s.queue[item.id] = replace(item, held=True, held_reason=reason)
                changed += 1
        return changed

    def release(self, item_id: str) -> QueuedItem:
        with self._s.lock:
            item = self._s.queue.get(item_id)
            if item is None:
                raise QueueItemNotFoundError(f"queue/{item_id}")
            released = replace(item, held=False, held_reason=None)
            self._s.queue[item_id] = released
            return released

    def pop_next(self, conversation_id: str) -> QueuedItem | None:
        with self._s.lock:
            rows = self._of(conversation_id)
            if not rows or rows[0].held:
                return None
            head = rows[0]
            del self._s.queue[head.id]
            self._compact(conversation_id)
            return head

    def counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, QueueCounts]:
        wanted = None if conversation_ids is None else set(conversation_ids)
        totals: dict[str, list[int]] = {}
        with self._s.lock:
            for item in self._s.queue.values():
                if wanted is not None and item.conversation_id not in wanted:
                    continue
                entry = totals.setdefault(item.conversation_id, [0, 0])
                entry[0] += 1
                entry[1] += 1 if item.held else 0
        return {cid: QueueCounts(queued=q, held=h) for cid, (q, h) in totals.items()}

    def clear(self, conversation_id: str) -> int:
        with self._s.lock:
            doomed = [q.id for q in self._of(conversation_id)]
            for item_id in doomed:
                del self._s.queue[item_id]
            return len(doomed)


class InMemoryChatStorage:
    """대화·대기열 인메모리 묶음(한 상태를 공유)."""

    def __init__(self) -> None:
        state = _State()
        self.conversations = InMemoryConversationRepository(state)
        self.queue = InMemoryQueueRepository(state)
