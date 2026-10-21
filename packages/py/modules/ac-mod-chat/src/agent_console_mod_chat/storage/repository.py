"""대화·대기열 SQLite 구현(엔진은 호스트의 `DatabaseHandle.engine`).

대화를 지우면 그 대화의 대기열도 **같은 트랜잭션**에서 지운다
(`SqliteConversationRepository.delete`).
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agent_console_contracts import Conversation

from . import schema as t
from .models import QueueCounts, QueuedItem, QueueItemExistsError, QueueItemNotFoundError


class SqliteConversationRepository:
    """`conversations` 테이블 위의 대화 저장소."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, conversation: Conversation) -> None:
        values = {
            "id": conversation.id,
            "graph_id": conversation.graph_id,
            "archived": int(conversation.archived),
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "project_id": conversation.project_id,
            "doc": conversation.model_dump_json(),
        }
        stmt = sqlite_insert(t.conversations).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={k: v for k, v in values.items() if k != "id"}
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def get(self, conversation_id: str) -> Conversation | None:
        stmt = sa.select(t.conversations.c.doc).where(t.conversations.c.id == conversation_id)
        with self._engine.connect() as conn:
            doc = conn.execute(stmt).scalar()
        return None if doc is None else Conversation.model_validate_json(doc)

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Conversation]:
        c = t.conversations.c
        stmt = sa.select(c.doc)
        if project_id is not None:
            stmt = stmt.where(c.project_id == project_id)
        if graph_id is not None:
            stmt = stmt.where(c.graph_id == graph_id)
        if archived is not None:
            stmt = stmt.where(c.archived == int(archived))
        stmt = stmt.order_by(c.updated_at.desc(), c.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [Conversation.model_validate_json(d) for d in conn.execute(stmt).scalars()]

    def delete(self, conversation_id: str) -> bool:
        """대화와 그 대기열을 한 트랜잭션에서 지운다. 대화가 있었으면 True."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.delete(t.chat_queue).where(t.chat_queue.c.conversation_id == conversation_id)
            )
            result = conn.execute(
                sa.delete(t.conversations).where(t.conversations.c.id == conversation_id)
            )
        return result.rowcount > 0


def _queued(row: Any) -> QueuedItem:
    return QueuedItem(
        id=row.id,
        conversation_id=row.conversation_id,
        position=row.position,
        text=row.text,
        created_at=row.created_at,
        held=bool(row.held),
        held_reason=row.held_reason,
    )


class SqliteQueueRepository:
    """`chat_queue` 테이블 위의 대기열 저장소. 순번 정리는 한 트랜잭션 안에서 한다."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _compact(conn: Connection, conversation_id: str) -> None:
        c = t.chat_queue.c
        ids = conn.execute(
            sa.select(c.id).where(c.conversation_id == conversation_id).order_by(c.position, c.id)
        ).scalars()
        for number, item_id in enumerate(builtins.list(ids), start=1):
            conn.execute(
                sa.update(t.chat_queue)
                .where(c.id == item_id, c.position != number)
                .values(position=number)
            )

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
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            if conn.execute(sa.select(c.id).where(c.id == item_id)).first() is not None:
                raise QueueItemExistsError(f"queue/{item_id}")
            last = conn.execute(
                sa.select(sa.func.max(c.position)).where(c.conversation_id == conversation_id)
            ).scalar()
            position = (last or 0) + 1
            conn.execute(
                sa.insert(t.chat_queue).values(
                    id=item_id,
                    conversation_id=conversation_id,
                    position=position,
                    text=text,
                    held=int(held),
                    held_reason=held_reason if held else None,
                    created_at=created_at,
                )
            )
        return QueuedItem(
            id=item_id,
            conversation_id=conversation_id,
            position=position,
            text=text,
            created_at=created_at,
            held=held,
            held_reason=held_reason if held else None,
        )

    def get(self, item_id: str) -> QueuedItem | None:
        with self._engine.connect() as conn:
            row = conn.execute(sa.select(t.chat_queue).where(t.chat_queue.c.id == item_id)).first()
        return None if row is None else _queued(row)

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> builtins.list[QueuedItem]:
        c = t.chat_queue.c
        stmt = sa.select(t.chat_queue)
        if conversation_id is not None:
            stmt = stmt.where(c.conversation_id == conversation_id)
        if held is not None:
            stmt = stmt.where(c.held == int(held))
        stmt = stmt.order_by(c.conversation_id, c.position, c.id)
        with self._engine.connect() as conn:
            return [_queued(r) for r in conn.execute(stmt)]

    def remove(self, item_id: str) -> bool:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            conversation_id = conn.execute(
                sa.select(c.conversation_id).where(c.id == item_id)
            ).scalar()
            if conversation_id is None:
                return False
            conn.execute(sa.delete(t.chat_queue).where(c.id == item_id))
            self._compact(conn, conversation_id)
        return True

    def hold_all(self, reason: str | None = None, *, conversation_id: str | None = None) -> int:
        c = t.chat_queue.c
        stmt = sa.update(t.chat_queue).where(c.held == 0).values(held=1, held_reason=reason)
        if conversation_id is not None:
            stmt = stmt.where(c.conversation_id == conversation_id)
        with self._engine.begin() as conn:
            return int(conn.execute(stmt).rowcount)

    def release(self, item_id: str) -> QueuedItem:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.update(t.chat_queue).where(c.id == item_id).values(held=0, held_reason=None)
            )
            if result.rowcount == 0:
                raise QueueItemNotFoundError(f"queue/{item_id}")
            row = conn.execute(sa.select(t.chat_queue).where(c.id == item_id)).one()
        return _queued(row)

    def pop_next(self, conversation_id: str) -> QueuedItem | None:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(t.chat_queue)
                .where(c.conversation_id == conversation_id)
                .order_by(c.position, c.id)
                .limit(1)
            ).first()
            if row is None or row.held:
                return None
            deleted = conn.execute(sa.delete(t.chat_queue).where(c.id == row.id)).rowcount
            if deleted == 0:  # 다른 연결이 먼저 꺼냈다
                return None
            self._compact(conn, conversation_id)
        return _queued(row)

    def counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, QueueCounts]:
        c = t.chat_queue.c
        stmt = sa.select(c.conversation_id, sa.func.count(), sa.func.sum(c.held)).group_by(
            c.conversation_id
        )
        if conversation_ids is not None:
            stmt = stmt.where(c.conversation_id.in_(builtins.list(conversation_ids)))
        with self._engine.connect() as conn:
            return {
                str(cid): QueueCounts(queued=int(total), held=int(held or 0))
                for cid, total, held in conn.execute(stmt)
            }

    def clear(self, conversation_id: str) -> int:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            return int(
                conn.execute(
                    sa.delete(t.chat_queue).where(c.conversation_id == conversation_id)
                ).rowcount
            )


class SqliteChatStorage:
    """호스트 엔진 위의 대화·대기열 저장소 묶음."""

    def __init__(self, engine: Engine) -> None:
        self.conversations = SqliteConversationRepository(engine)
        self.queue = SqliteQueueRepository(engine)
