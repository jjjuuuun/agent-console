"""대화·대기열 SQLite 구현(엔진은 호스트의 `DatabaseHandle.engine`).

대화를 지우면 그 대화의 대기열도 **같은 트랜잭션**에서 지운다
(`SqliteConversationRepository.delete`).
"""

from __future__ import annotations

import builtins
from collections.abc import Collection, Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agent_console_contracts import Conversation
from agent_console_store import AssignCandidate

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

    # ------------------------------------------------ 프로젝트 넣기·개수(`ProjectAssignStore`)

    def project_id_counts(self) -> dict[str | None, int]:
        """project_id별 대화 수(보관한 대화 포함)."""
        c = t.conversations.c
        stmt = sa.select(c.project_id, sa.func.count()).group_by(c.project_id)
        with self._engine.connect() as conn:
            return {row[0]: int(row[1]) for row in conn.execute(stmt)}

    def candidates(self, ids: Collection[str] | None) -> builtins.list[AssignCandidate]:
        c = t.conversations.c
        if ids is None:
            stmt = sa.select(c.id, c.project_id).where(c.project_id.is_(None))
            with self._engine.connect() as conn:
                return [AssignCandidate(r[0], r[1]) for r in conn.execute(stmt)]
        out: builtins.list[AssignCandidate] = []
        wanted = builtins.list(ids)
        with self._engine.connect() as conn:
            for i in range(0, len(wanted), 500):
                stmt = sa.select(c.id, c.project_id).where(c.id.in_(wanted[i : i + 500]))
                out.extend(AssignCandidate(r[0], r[1]) for r in conn.execute(stmt))
        return out

    def set_project(self, ids: Collection[str], project_id: str) -> int:
        """열과 `doc`의 project_id를 함께 바꾼다(`updated_at`은 그대로 — 정렬을 바꾸지 않는다)."""
        c = t.conversations.c
        wanted = builtins.list(ids)
        changed = 0
        with self._engine.begin() as conn:
            for i in range(0, len(wanted), 500):
                changed += conn.execute(
                    sa.update(t.conversations)
                    .where(c.id.in_(wanted[i : i + 500]))
                    .values(
                        project_id=project_id,
                        doc=sa.func.json_set(c.doc, "$.project_id", project_id),
                    )
                ).rowcount
        return changed

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


OTHER_HOST_HOLD_REASON = "other_host"
"""다른 앱(``host_id``가 다름)이 넣은 항목의 보이는 ``held_reason``(design §PI.4.6.5)."""


def _queued(row: Any, host_id: str | None = None) -> QueuedItem:
    other = _is_other(row, host_id)
    return QueuedItem(
        id=row.id,
        conversation_id=row.conversation_id,
        position=row.position,
        text=row.text,
        created_at=row.created_at,
        held=bool(row.held) or other,
        held_reason=OTHER_HOST_HOLD_REASON if other else row.held_reason,
        host_id=getattr(row, "host_id", None),
    )


def _is_other(row: Any, host_id: str | None) -> bool:
    found = getattr(row, "host_id", None)
    return host_id is not None and found is not None and found != host_id


class SqliteQueueRepository:
    """`chat_queue` 테이블 위의 대기열 저장소. 순번 정리는 한 트랜잭션 안에서 한다.

    Args:
        engine: DB 엔진.
        host_id: 이 앱의 id(프로젝트 기록 DB처럼 두 앱이 같은 표를 쓸 때, 5.7R.33y2). 주면 넣는
            항목에 적고, 다른 앱의 항목은 멈춘 것(``held_reason: other_host``)으로 보이며 꺼내지
            않는다. 재시작 정책(``hold_all``·``clear``)은 자기 항목(과 ``host_id`` 없는 옛 항목)만
            바꾼다. [실행](``release``)하면 그 항목은 이 앱 것이 된다. None이면 지금 동작.
    """

    def __init__(self, engine: Engine, *, host_id: str | None = None) -> None:
        self._engine = engine
        self.host_id = host_id

    def _own(self) -> Any:
        """자기 항목 조건(``host_id``가 같거나 없음). ``host_id``를 모르면 모두."""
        c = t.chat_queue.c
        if self.host_id is None:
            return sa.true()
        return sa.or_(c.host_id.is_(None), c.host_id == self.host_id)

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
                    **({"host_id": self.host_id} if self.host_id is not None else {}),
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
            host_id=self.host_id,
        )

    def get(self, item_id: str) -> QueuedItem | None:
        with self._engine.connect() as conn:
            row = conn.execute(sa.select(t.chat_queue).where(t.chat_queue.c.id == item_id)).first()
        return None if row is None else _queued(row, self.host_id)

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> builtins.list[QueuedItem]:
        c = t.chat_queue.c
        stmt = sa.select(t.chat_queue)
        if conversation_id is not None:
            stmt = stmt.where(c.conversation_id == conversation_id)
        if held is not None and self.host_id is None:
            stmt = stmt.where(c.held == int(held))
        stmt = stmt.order_by(c.conversation_id, c.position, c.id)
        with self._engine.connect() as conn:
            found = [_queued(r, self.host_id) for r in conn.execute(stmt)]
        return found if held is None else [i for i in found if i.held == held]

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
        stmt = (
            sa.update(t.chat_queue)
            .where(c.held == 0, self._own())
            .values(held=1, held_reason=reason)
        )
        if conversation_id is not None:
            stmt = stmt.where(c.conversation_id == conversation_id)
        with self._engine.begin() as conn:
            return int(conn.execute(stmt).rowcount)

    def release(self, item_id: str) -> QueuedItem:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            values: dict[str, Any] = {"held": 0, "held_reason": None}
            if self.host_id is not None:
                values["host_id"] = self.host_id  # [실행]하면 이 앱 것이 된다
            result = conn.execute(sa.update(t.chat_queue).where(c.id == item_id).values(**values))
            if result.rowcount == 0:
                raise QueueItemNotFoundError(f"queue/{item_id}")
            row = conn.execute(sa.select(t.chat_queue).where(c.id == item_id)).one()
        return _queued(row, self.host_id)

    def pop_next(self, conversation_id: str) -> QueuedItem | None:
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            row = conn.execute(
                sa.select(t.chat_queue)
                .where(c.conversation_id == conversation_id)
                .order_by(c.position, c.id)
                .limit(1)
            ).first()
            if row is None or row.held or _is_other(row, self.host_id):
                return None
            deleted = conn.execute(sa.delete(t.chat_queue).where(c.id == row.id)).rowcount
            if deleted == 0:  # 다른 연결이 먼저 꺼냈다
                return None
            self._compact(conn, conversation_id)
        return _queued(row, self.host_id)

    def counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, QueueCounts]:
        c = t.chat_queue.c
        held_expr: Any = c.held
        if self.host_id is not None:  # 다른 앱 항목도 멈춘 것으로 센다
            held_expr = sa.case((sa.not_(self._own()), 1), else_=c.held)
        stmt = sa.select(c.conversation_id, sa.func.count(), sa.func.sum(held_expr)).group_by(
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
        """그 대화의 자기 항목을 지운다(``host_id``를 모르면 모두). 대화를 지우면 대화 저장소가 모든
        항목을 함께 지운다."""
        c = t.chat_queue.c
        with self._engine.begin() as conn:
            removed = int(
                conn.execute(
                    sa.delete(t.chat_queue).where(c.conversation_id == conversation_id, self._own())
                ).rowcount
            )
            if removed and self.host_id is not None:
                self._compact(conn, conversation_id)
            return removed


class SqliteChatStorage:
    """엔진 위의 대화·대기열 저장소 묶음(``host_id``는 대기열에, ``SqliteQueueRepository``)."""

    def __init__(self, engine: Engine, *, host_id: str | None = None) -> None:
        self.engine = engine
        self.conversations = SqliteConversationRepository(engine)
        self.queue = SqliteQueueRepository(engine, host_id=host_id)
