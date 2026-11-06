"""대기열 항목에 소유 앱 id 열(design §PI.4.6.5, 5.7R.33w2).

`chat_queue.host_id`(null 허용): 이 항목을 넣은 앱의 `host_id`. 프로젝트 기록 DB를 두 앱이 함께 쓸
때 재시작 정책을 자기 항목에만 적용하려고 쓴다(남의 항목은 `held_reason = other_host`로 보임).
기존 항목은 null로 남는다(주인을 모르는 항목). 색인은 두지 않는다(대기열은 대화별 조회).
되돌릴 때는 열만 지운다.

Revision ID: chat_0003
Revises: chat_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "chat_0003"
down_revision: str | None = "chat_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_queue") as batch:
        batch.add_column(sa.Column("host_id", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("chat_queue") as batch:
        batch.drop_column("host_id")
