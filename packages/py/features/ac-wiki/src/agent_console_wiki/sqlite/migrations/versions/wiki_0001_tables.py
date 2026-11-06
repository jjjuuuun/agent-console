"""wiki 계보의 첫 리비전: 페이지 기록 표 둘(design §7R.6, `[7R.11 구현]`).

이 파일은 고치지 않는다. 이후 스키마 변경은 새 리비전으로 추가한다. 표 모양은
`agent_console_wiki.sqlite.schema.metadata`와 같아야 하며, 테스트가 `compare_metadata`로 확인한다.
(스키마를 import하지 않고 풀어 쓴 이유: 이미 적용된 리비전은 나중에 코드가 바뀌어도 같은 모양을
만들어야 하기 때문이다.)

Revision ID: wiki_0001
Revises: (없음)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "wiki_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """표 둘과 색인을 만든다."""
    op.create_table(
        "wiki_page_versions",
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("wiki_id", sa.String, nullable=False),
        sa.Column("path", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("op", sa.String, nullable=False),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False),
        sa.Column("at", sa.Float, nullable=False),
        sa.Column("author_run_id", sa.String, nullable=True),
        sa.Column("author_root_run_id", sa.String, nullable=True),
        sa.Column("from_path", sa.String, nullable=True),
        sa.Column("to_path", sa.String, nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("author_json", sa.Text, nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ux_wiki_page_versions_key",
        "wiki_page_versions",
        ["wiki_id", "path", "version"],
        unique=True,
    )
    op.create_index("ix_wiki_page_versions_wiki_seq", "wiki_page_versions", ["wiki_id", "seq"])
    op.create_index(
        "ix_wiki_page_versions_author_run",
        "wiki_page_versions",
        ["author_run_id"],
        sqlite_where=sa.text("author_run_id IS NOT NULL"),
    )
    op.create_index(
        "ix_wiki_page_versions_author_root",
        "wiki_page_versions",
        ["author_root_run_id"],
        sqlite_where=sa.text("author_root_run_id IS NOT NULL"),
    )
    op.create_index("ix_wiki_page_versions_sha256", "wiki_page_versions", ["sha256"])

    op.create_table(
        "wiki_blobs",
        sa.Column("sha256", sa.String, primary_key=True),
        sa.Column("content", sa.LargeBinary, nullable=False),
    )


def downgrade() -> None:
    """기록 표를 모두 지운다."""
    op.drop_table("wiki_blobs")
    op.drop_table("wiki_page_versions")
