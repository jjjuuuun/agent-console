"""실행 계보 열(design §5R.9 #3·#5, §5R.10).

- `runs.parent_node_id`, `runs.root_run_id` + 색인 `ix_runs_root`(`parent_run_id` 색인
  `ix_runs_parent`는 legacy 0001이 이미 만들었다).
- `node_runs.call`(INTEGER NOT NULL DEFAULT 0), `node_runs.invoked_by`(JSON, null 허용). 같은 노드를
  위임자가 여러 번 부를 수 있으므로 기본키가 (run_id, node_id, attempt, iteration, call)로 바뀐다
  (SQLite는 기본키를 바꿀 수 없어 표를 새로 만들어 옮긴다).
- `interactions.root_run_id` + 색인 `ix_interactions_root`.

새 열은 `doc`의 투영이라 적용할 때 JSON에서 채운다(4R까지의 기록은 모두 비어 있다). 되돌릴 때는
열만 지운다. 되돌리면 `call > 0`인 NodeRun 행(기본키가 겹쳐 옛 모양에 둘 수 없다)이 사라진다.
`doc`에는 남지 않으므로 이 한 가지는 손실이다 — 호출 NodeRun은 5R.6부터 생긴다.

Revision ID: runs_0002
Revises: runs_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "runs_0002"
down_revision: str | None = "runs_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_PK = ("run_id", "node_id", "attempt", "iteration")


def _node_runs_table(name: str, *, with_lineage: bool) -> None:
    columns: list[sa.schema.SchemaItem] = [
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("node_id", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False),
    ]
    if with_lineage:
        columns.append(sa.Column("call", sa.Integer, nullable=False, server_default="0"))
    columns += [
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("node_type", sa.Text),
        sa.Column("started_at", sa.Float),
        sa.Column("ended_at", sa.Float),
        sa.Column("duration_ms", sa.Integer),
    ]
    if with_lineage:
        columns.append(sa.Column("invoked_by", sa.JSON(none_as_null=True)))
    columns.append(sa.Column("doc", sa.Text, nullable=False))
    pk = (*_OLD_PK, "call") if with_lineage else _OLD_PK
    columns.append(sa.PrimaryKeyConstraint(*pk))
    op.create_table(name, *columns)


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("parent_node_id", sa.Text))
        batch.add_column(sa.Column("root_run_id", sa.Text))
        batch.create_index("ix_runs_root", ["root_run_id"])
    op.execute(
        "UPDATE runs SET parent_node_id = json_extract(doc, '$.parent_node_id'), "
        "root_run_id = json_extract(doc, '$.root_run_id')"
    )

    with op.batch_alter_table("interactions") as batch:
        batch.add_column(sa.Column("root_run_id", sa.Text))
        batch.create_index("ix_interactions_root", ["root_run_id"])
    op.execute("UPDATE interactions SET root_run_id = json_extract(doc, '$.root_run_id')")

    _node_runs_table("node_runs_new", with_lineage=True)
    op.execute(
        "INSERT INTO node_runs_new (run_id, node_id, attempt, iteration, call, status, node_type, "
        "started_at, ended_at, duration_ms, invoked_by, doc) "
        "SELECT run_id, node_id, attempt, iteration, COALESCE(json_extract(doc, '$.call'), 0), "
        "status, node_type, started_at, ended_at, duration_ms, "
        "json_extract(doc, '$.invoked_by'), doc FROM node_runs"
    )
    op.drop_index("ix_node_runs_type_status", table_name="node_runs")
    op.drop_table("node_runs")
    op.rename_table("node_runs_new", "node_runs")
    op.create_index("ix_node_runs_type_status", "node_runs", ["node_type", "status"])


def downgrade() -> None:
    op.execute("DELETE FROM node_runs WHERE call > 0")
    _node_runs_table("node_runs_old", with_lineage=False)
    op.execute(
        "INSERT INTO node_runs_old (run_id, node_id, attempt, iteration, status, node_type, "
        "started_at, ended_at, duration_ms, doc) "
        "SELECT run_id, node_id, attempt, iteration, status, node_type, started_at, ended_at, "
        "duration_ms, doc FROM node_runs"
    )
    op.drop_index("ix_node_runs_type_status", table_name="node_runs")
    op.drop_table("node_runs")
    op.rename_table("node_runs_old", "node_runs")
    op.create_index("ix_node_runs_type_status", "node_runs", ["node_type", "status"])

    with op.batch_alter_table("interactions") as batch:
        batch.drop_index("ix_interactions_root")
        batch.drop_column("root_run_id")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_root")
        batch.drop_column("root_run_id")
        batch.drop_column("parent_node_id")
