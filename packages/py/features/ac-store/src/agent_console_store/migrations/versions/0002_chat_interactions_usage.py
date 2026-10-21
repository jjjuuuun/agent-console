"""채팅·에이전트 활동·상호작용·사용량 (design §R1.4, §R4.1, §R4.3, §R14.4).

- `runs.conversation_id` + (conversation_id, created_at) 인덱스
- `run_events.actor` + (actor, ts), (type, ts) 인덱스
- 새 테이블: `conversations`, `usage_observations`, `interactions`

새 컬럼은 기존 `doc`/`body`의 투영이므로 적용할 때 JSON에서 채운다. 되돌려도 `doc`/`body`에
값이 남아 있어 다시 적용하면 같은 값이 복구된다(손실 없음).

이 파일은 고치지 않는다. 스키마를 바꾸려면 새 마이그레이션을 추가한다.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("conversation_id", sa.Text))
        batch.create_index("ix_runs_conversation", ["conversation_id", "created_at"])
    op.execute("UPDATE runs SET conversation_id = json_extract(doc, '$.conversation_id')")

    with op.batch_alter_table("run_events") as batch:
        batch.add_column(sa.Column("actor", sa.Text))
        batch.create_index("ix_run_events_actor_ts", ["actor", "ts"])
        batch.create_index("ix_run_events_type_ts", ["type", "ts"])
    op.execute("UPDATE run_events SET actor = json_extract(body, '$.actor')")

    op.create_table(
        "conversations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("graph_id", sa.Text, nullable=False),
        sa.Column("archived", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("doc", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_conversations_archived_updated", "conversations", ["archived", "updated_at"]
    )
    op.create_index("ix_conversations_graph_updated", "conversations", ["graph_id", "updated_at"])

    op.create_table(
        "usage_observations",
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("window_id", sa.Text, nullable=False),
        sa.Column("observed_at", sa.Float, nullable=False),
        sa.Column("used_ratio", sa.Float),
        sa.Column("used_tokens", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("resets_at", sa.Float),
        sa.Column("doc", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("source", "window_id", "observed_at"),
    )
    op.create_index("ix_usage_observations_observed", "usage_observations", ["observed_at"])

    op.create_table(
        "interactions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("conversation_id", sa.Text),
        sa.Column("node_id", sa.Text, nullable=False),
        sa.Column("actor", sa.Text),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("closed_at", sa.Float),
        sa.Column("doc", sa.Text, nullable=False),
    )
    op.create_index("ix_interactions_status_created", "interactions", ["status", "created_at"])
    op.create_index("ix_interactions_run", "interactions", ["run_id"])
    op.create_index(
        "ix_interactions_conversation_status", "interactions", ["conversation_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("interactions")
    op.drop_table("usage_observations")
    op.drop_table("conversations")

    with op.batch_alter_table("run_events") as batch:
        batch.drop_index("ix_run_events_type_ts")
        batch.drop_index("ix_run_events_actor_ts")
        batch.drop_column("actor")

    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_conversation")
        batch.drop_column("conversation_id")
