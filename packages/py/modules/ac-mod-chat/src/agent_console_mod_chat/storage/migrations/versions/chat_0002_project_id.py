"""대화에 프로젝트 id 열(design §5.2R.4, §UX-P.4).

`conversations.project_id`(null 허용) + 색인 `ix_conversations_project_updated`(`project_id`,
`updated_at`): 프로젝트별 최근 갱신순 목록(`GET /conversations?project=`).
기존 대화는 null로 남는다(이관하지 않는다). 새 열은 `doc`의 투영이라 다시 올릴 때 `doc`에서 채운다.
되돌릴 때는 열과 색인만 지운다.

Revision ID: chat_0002
Revises: chat_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "chat_0002"
down_revision: str | None = "chat_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("project_id", sa.Text))
        batch.create_index("ix_conversations_project_updated", ["project_id", "updated_at"])
    op.execute("UPDATE conversations SET project_id = json_extract(doc, '$.project_id')")


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_index("ix_conversations_project_updated")
        batch.drop_column("project_id")
