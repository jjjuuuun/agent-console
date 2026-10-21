"""초기 스키마: 정의 버전, Run, NodeRun, RunEvent, 라우팅 결정.

이 파일은 고치지 않는다. 스키마를 바꾸려면 새 마이그레이션을 추가한다.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "definition_versions",
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("def_id", sa.Text, nullable=False),
        sa.Column("version_hash", sa.Text, nullable=False),
        sa.Column("saved_at", sa.Float, nullable=False),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("kind", "def_id", "version_hash"),
    )
    op.create_index(
        "ix_definition_versions_history", "definition_versions", ["kind", "def_id", "saved_at"]
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("graph_id", sa.Text, nullable=False),
        sa.Column("graph_version", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("origin", sa.Text, nullable=False),
        sa.Column("parent_run_id", sa.Text),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("started_at", sa.Float),
        sa.Column("ended_at", sa.Float),
        sa.Column("doc", sa.Text, nullable=False),
    )
    op.create_index("ix_runs_graph_created", "runs", ["graph_id", "created_at"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_parent", "runs", ["parent_run_id"])
    op.create_index("ix_runs_created", "runs", ["created_at"])

    op.create_table(
        "node_runs",
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("node_id", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("node_type", sa.Text),
        sa.Column("started_at", sa.Float),
        sa.Column("ended_at", sa.Float),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("doc", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("run_id", "node_id", "attempt", "iteration"),
    )
    op.create_index("ix_node_runs_type_status", "node_runs", ["node_type", "status"])

    op.create_table(
        "run_events",
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False),
        sa.Column("ts", sa.Float, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("node_id", sa.Text),
        sa.Column("attempt", sa.Integer),
        sa.Column("body", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("run_id", "seq"),
        sa.UniqueConstraint("run_id", "event_id", name="uq_run_events_event_id"),
    )
    op.create_index("ix_run_events_type", "run_events", ["run_id", "type"])
    op.create_index("ix_run_events_node", "run_events", ["run_id", "node_id"])

    op.create_table(
        "routing_decisions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("node_id", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("chosen_port", sa.Text),
        sa.Column("manual", sa.Integer, nullable=False),
        sa.Column("overridden_by", sa.Text),
        sa.Column("overridden_port", sa.Text),
        sa.Column("decided_at", sa.Float, nullable=False),
        sa.Column("doc", sa.Text, nullable=False),
        sa.UniqueConstraint(
            "run_id", "node_id", "attempt", "decided_at", name="uq_routing_decision"
        ),
    )
    op.create_index("ix_routing_run_node", "routing_decisions", ["run_id", "node_id"])
    op.create_index("ix_routing_category_port", "routing_decisions", ["category", "chosen_port"])
    op.create_index("ix_routing_decided_at", "routing_decisions", ["decided_at"])


def downgrade() -> None:
    op.drop_table("routing_decisions")
    op.drop_table("run_events")
    op.drop_table("node_runs")
    op.drop_table("runs")
    op.drop_table("definition_versions")
