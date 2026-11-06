"""실행 라벨 표(design §6R.1.5·§6R.2, X45).

- ``run_labels(run_id, key, value)``: 루트 Run의 라벨(``Run.labels``)을 질의하기 위한 투영.
  기본키 (``run_id``, ``key``), 색인 ``ix_run_labels_kv``(``key``, ``value``, ``run_id``) -
  라벨 AND 질의(``key=value``)가 이 색인만으로 ``run_id`` 집합을 만든다.
- 진실의 원천은 ``runs.doc``(``Run.labels``)이다. 올릴 때 ``doc``에서 채워, 되돌렸다 다시 올려도
  값을 잃지 않는다. 되돌리면 표와 색인만 지운다(``doc``은 그대로).
- ``run_id`` 외래 키는 두지 않는다(옮기기가 표 단위로 행을 복사하고, 삭제는 저장소가 직접 비운다).

Revision ID: runs_0004
Revises: runs_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "runs_0004"
down_revision: str | None = "runs_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_labels",
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("run_id", "key"),
    )
    op.create_index("ix_run_labels_kv", "run_labels", ["key", "value", "run_id"])
    op.execute(
        "INSERT OR IGNORE INTO run_labels (run_id, key, value) "
        "SELECT r.id, j.key, j.value FROM runs AS r, json_each(r.doc, '$.labels') AS j "
        "WHERE r.root_run_id IS NULL AND json_type(r.doc, '$.labels') = 'object' "
        "AND j.type = 'text'"
    )


def downgrade() -> None:
    op.drop_index("ix_run_labels_kv", table_name="run_labels")
    op.drop_table("run_labels")
