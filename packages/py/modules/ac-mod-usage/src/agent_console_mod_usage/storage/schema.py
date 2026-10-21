"""`usage_observations` 테이블 정의(SQLAlchemy Core).

테이블은 legacy 마이그레이션 0002가 만들었고 그대로다(이동은 코드 소유권만 바뀐다, design §3R.1.7).
컬럼으로 올린 것은 창별 최신/이력 조회와 보존 기간 정리에 쓰는 필드뿐이고, 전체 스냅샷
(`raw` 포함)은 `doc`(JSON)에 둔다.
"""

import sqlalchemy as sa

metadata = sa.MetaData()

TABLE_NAME = "usage_observations"

usage_observations = sa.Table(
    TABLE_NAME,
    metadata,
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("window_id", sa.Text, nullable=False),
    sa.Column("observed_at", sa.Float, nullable=False),
    sa.Column("used_ratio", sa.Float),
    sa.Column("used_tokens", sa.Integer),
    sa.Column("status", sa.Text),
    sa.Column("resets_at", sa.Float),
    sa.Column("doc", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("source", "window_id", "observed_at"),
    sa.Index("ix_usage_observations_observed", "observed_at"),
)

__all__ = ["TABLE_NAME", "metadata", "usage_observations"]
