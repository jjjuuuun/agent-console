"""memory 계보의 첫 리비전: 메모리 표(design §5.7R.6, `[5.7R.10 구현·측정]`).

이 파일은 고치지 않는다. 이후 스키마 변경은 새 리비전으로 추가한다. 표 모양은
`agent_console_memory.sqlite.schema.metadata`와 같아야 하며, 테스트가 `compare_metadata`로 확인한다.
(스키마를 import하지 않고 풀어 쓴 이유: 이미 적용된 리비전은 나중에 코드가 바뀌어도 같은 모양을
만들어야 하기 때문이다.)

전문 검색 가상 표(`memory_fts`, FTS5 trigram)는 여기서 만들지 않는다. SQLite 빌드에 따라 없을 수
있고(그러면 포함 검색으로 떨어진다) 항목 표에서 다시 만들 수 있는 색인이라, 저장소를 열 때
(`open_sqlite_memory_store`) 있으면 만들고 없으면 경고한다.

Revision ID: memory_0001
Revises: (없음)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "memory_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """표 4개와 색인을 만든다."""
    op.create_table(
        "memory_entries",
        sa.Column("rid", sa.Integer, primary_key=True),
        sa.Column("id", sa.String, nullable=False),
        sa.Column("scope_kind", sa.String, nullable=False),
        sa.Column("scope_id", sa.String, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
        sa.Column("pinned", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("archived", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False),
        sa.Column("author_run_id", sa.String, nullable=True),
        sa.Column("last_read_at", sa.Float, nullable=True),
        sa.Column("deleted_at", sa.Float, nullable=True),
        sa.Column("preview", sa.Text, nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
    )
    op.create_index("ux_memory_entries_id", "memory_entries", ["id"], unique=True)
    op.create_index(
        "ux_memory_entries_live_key",
        "memory_entries",
        ["scope_kind", "scope_id", "key"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_memory_entries_live_summary",
        "memory_entries",
        ["scope_kind", "scope_id", "archived", "updated_at", "id", "bytes", "deleted_at"],
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_memory_entries_author_run", "memory_entries", ["author_run_id"])
    op.create_index(
        "ix_memory_entries_deleted",
        "memory_entries",
        ["deleted_at"],
        sqlite_where=sa.text("deleted_at IS NOT NULL"),
    )

    op.create_table(
        "memory_versions",
        sa.Column("entry_id", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("op", sa.String, nullable=False),
        sa.Column("scope_kind", sa.String, nullable=False),
        sa.Column("scope_id", sa.String, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("author", sa.Text, nullable=False),
        sa.Column("run_id", sa.String, nullable=True),
        sa.Column("at", sa.Float, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "version", name="pk_memory_versions"),
    )
    op.create_index("ix_memory_versions_run", "memory_versions", ["run_id"])

    op.create_table(
        "memory_tags",
        sa.Column("entry_id", sa.String, nullable=False),
        sa.Column("tag", sa.String, nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "tag", name="pk_memory_tags"),
    )
    op.create_index("ix_memory_tags_tag", "memory_tags", ["tag", "entry_id"])

    op.create_table(
        "memory_stats",
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("value", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    """메모리 표를 모두 지운다(전문 검색 가상 표가 있으면 그것도)."""
    op.execute("DROP TABLE IF EXISTS memory_fts")
    for table in ("memory_stats", "memory_tags", "memory_versions", "memory_entries"):
        op.drop_table(table)
