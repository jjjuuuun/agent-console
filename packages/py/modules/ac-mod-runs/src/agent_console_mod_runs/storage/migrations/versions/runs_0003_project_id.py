"""실행에 프로젝트 id 열(design §5.2R.4, §UX-P.4).

- `runs.project_id`(null 허용) + 색인 `ix_runs_project_created`(`project_id`, `created_at`):
  프로젝트별 최신순 목록(`GET /runs?project=`).
- 루트만 거르는 조건(`root_run_id IS NULL`)용 부분 색인은 두지 않는다. 목록은 `created_at` 내림차순
  색인(`ix_runs_created`)이나 위 색인을 거꾸로 훑다 limit에서 멈추고, 자식 Run은 루트 수보다 적게
  섞이므로 정렬을 새로 하지 않는 것으로 충분하다(질의 계획 테스트가 확인한다).

새 열은 `doc`의 투영이다. 4R·5R까지의 기록은 `doc`에 값이 없어 null로 남고(이관하지 않는다),
되돌렸다 다시 올릴 때는 `doc`에서 채워 값을 잃지 않는다. 되돌릴 때는 열과 색인만 지운다.

Revision ID: runs_0003
Revises: runs_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "runs_0003"
down_revision: str | None = "runs_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("project_id", sa.Text))
        batch.create_index("ix_runs_project_created", ["project_id", "created_at"])
    op.execute("UPDATE runs SET project_id = json_extract(doc, '$.project_id')")


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_project_created")
        batch.drop_column("project_id")
