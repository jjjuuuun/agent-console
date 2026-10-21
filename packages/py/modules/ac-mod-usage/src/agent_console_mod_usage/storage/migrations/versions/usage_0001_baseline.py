"""usage 계보의 기준점: 스키마 변경 없음.

`usage_observations`는 legacy 0002가 만들었고 그대로다(3R.11은 코드 소유권만 옮겼다). 이 리비전은
계보(버전 테이블 `alembic_version_usage`)를 시작하는 표시일 뿐이다. 이후 이 모듈의 스키마 변경은
여기에 리비전을 추가한다. 이 파일은 고치지 않는다.

Revision ID: usage_0001
Revises: (없음)
"""

from collections.abc import Sequence

revision: str = "usage_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """변경 없음."""


def downgrade() -> None:
    """변경 없음(legacy의 테이블은 건드리지 않는다)."""
