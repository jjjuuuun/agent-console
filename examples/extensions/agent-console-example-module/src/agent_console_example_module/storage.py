"""저장 계층: 마이그레이션 계보 ``example_notes``와 엔진 위의 노트 저장소.

- ``BRANCH``: 이 모듈이 소유한 계보(패키지 데이터 ``migrations/versions``). ``scopes=("app",
  "project")``(X39) — 호스트는 모듈이 켜질 때 앱 DB에 올리고, 프로젝트 기록 DB를 여는 연동은
  ``ModuleContext.active_migrations("project")``로 이 계보를 찾아 그 파일에도 올린다. 그래서 앱
  노트와 프로젝트 노트는 같은 표 모양으로 서로 다른 파일에 있다(공간 열이 없다).
- ``NotesTable``: SQLAlchemy Core 표 하나에 대한 읽기·쓰기. 엔진은 주입받는다.
- ``memory_engine()``: DB가 없는 호스트(테스트·DB 없이 띄운 단독 실행)용 메모리 SQLite. 같은 계보를
  올리므로 표 모양이 한 곳(리비전)에서만 정해진다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import Engine

from agent_console_modkit import MigrationBranch
from agent_console_store import branch_version_table, create_sqlite_engine, upgrade

from .models import Note

BRANCH_NAME = "example_notes"
"""계보 이름(버전 표 ``alembic_version_example_notes``)."""

BRANCH = MigrationBranch(
    BRANCH_NAME, Path(__file__).parent / "migrations" / "versions", scopes=("app", "project")
)
"""모듈 서술자 ``migrations``에 넣는 계보."""

metadata = sa.MetaData()
notes = sa.Table(
    "example_notes",
    metadata,
    sa.Column("rid", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("id", sa.String, nullable=False, unique=True),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
    sa.Column("template", sa.String, nullable=True),
    sa.Column("created_at", sa.Float, nullable=False),
)
"""표 정의(리비전 ``example_notes_0001``과 같은 모양 — 테스트가 비교한다)."""


def upgrade_branch(engine: Engine) -> None:
    """이 계보만 최신까지 올린다(멱등). 호스트 DB에는 호스트가 올리므로 부르지 않는다."""
    upgrade(engine, versions=BRANCH.versions, version_table=branch_version_table(BRANCH.name))


def memory_engine() -> Engine:
    """계보를 올린 메모리 SQLite 엔진(프로세스가 끝나면 사라진다)."""
    engine = create_sqlite_engine(":memory:", journal_mode=None)
    upgrade_branch(engine)
    return engine


def _row(row: sa.Row[tuple[object, ...]]) -> Note:
    m = row._mapping
    return Note(
        id=str(m["id"]),
        text=str(m["text"]),
        tags=list(json.loads(str(m["tags"]))),
        template=None if m["template"] is None else str(m["template"]),
        created_at=datetime.fromtimestamp(float(str(m["created_at"])), UTC),
    )


class NotesTable:
    """엔진 하나의 노트 표.

    Args:
        engine: 계보가 올라간 엔진(앱 DB·프로젝트 기록 DB·메모리).
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, note: Note, *, keep: int) -> None:
        """노트를 넣고 가장 최근 ``keep``개만 남긴다(한 트랜잭션)."""
        with self.engine.begin() as conn:
            conn.execute(
                notes.insert().values(
                    id=note.id,
                    text=note.text,
                    tags=json.dumps(note.tags, ensure_ascii=False),
                    template=note.template,
                    created_at=note.created_at.timestamp(),
                )
            )
            newest = sa.select(notes.c.rid).order_by(notes.c.rid.desc()).limit(keep)
            conn.execute(notes.delete().where(notes.c.rid.not_in(newest.scalar_subquery())))

    def list(self, *, newest_first: bool, limit: int) -> list[Note]:
        """노트 목록(적은 순서 또는 그 반대)."""
        order = notes.c.rid.desc() if newest_first else notes.c.rid.asc()
        with self.engine.connect() as conn:
            rows: Sequence[sa.Row[tuple[object, ...]]] = conn.execute(
                sa.select(notes).order_by(order).limit(limit)
            ).all()
        return [_row(r) for r in rows]

    def get(self, note_id: str) -> Note | None:
        """id로 하나. 없으면 None."""
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(notes).where(notes.c.id == note_id)).first()
        return None if row is None else _row(row)


__all__ = [
    "BRANCH",
    "BRANCH_NAME",
    "NotesTable",
    "memory_engine",
    "metadata",
    "notes",
    "upgrade_branch",
]
