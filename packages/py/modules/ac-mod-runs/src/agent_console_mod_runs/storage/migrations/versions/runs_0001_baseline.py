"""runs 계보의 기준점: 스키마 변경 없음.

`runs`·`node_runs`·`run_events`·`interactions`는 legacy 0001~0003이 만들었고 그대로다(5R.4는
소유권만 넘겨받는다). 이 리비전은 계보(버전 테이블 `alembic_version_runs`)를 시작하는 표시일 뿐이다.
이 파일은 고치지 않는다. 스키마 변경은 리비전을 추가한다.

Revision ID: runs_0001
Revises: (없음)
"""

from collections.abc import Sequence

revision: str = "runs_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """변경 없음."""


def downgrade() -> None:
    """변경 없음(legacy의 테이블은 건드리지 않는다)."""
