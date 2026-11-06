"""example_notes 계보의 첫 리비전: 노트 표.

이 파일은 고치지 않는다. 이후 스키마 변경은 새 리비전으로 추가한다. 표 모양은
``agent_console_example_module.storage.notes``와 같아야 하며 테스트가 확인한다(표 정의를 import하지
않고 풀어 쓴 이유: 이미 적용된 리비전은 나중에 코드가 바뀌어도 같은 모양을 만들어야 한다).

Revision ID: example_notes_0001
Revises: (없음)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "example_notes_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """노트 표를 만든다."""
    op.create_table(
        "example_notes",
        sa.Column("rid", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("id", sa.String, nullable=False, unique=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
        sa.Column("template", sa.String, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    """노트 표를 지운다(계보를 내리면 이 모듈의 데이터가 사라진다)."""
    op.drop_table("example_notes")
