"""logs 계보 두 번째 리비전: `thread`·`run_id`·`session` 질의 색인(design §5.5R.10, 작업 5.5R.6).

`thread`·`scope`(세션·run_id 합집합) 필터는 결과를 `seq` 순서로 쪽 넘김한다. 값 열만 있는 색인은
`seq` 정렬을 위해 임시 정렬을 하거나 다른 색인으로 빠지므로, `seq`를 뒤에 붙인 색인을 둔다:
- `ix_log_events_session_seq (session, seq)`
- `ix_log_events_thread_seq (thread, seq)`
- `ix_log_events_run_seq (run_id, seq)` — 값만 있던 `ix_log_events_run (run_id)`를 대신한다.

색인만 바꾸므로 행은 건드리지 않는다(손실 없음). 이 파일 앞의 리비전은 고치지 않는다.

Revision ID: logs_0002
Revises: logs_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "logs_0002"
down_revision: str | None = "logs_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """`seq`를 뒤에 붙인 색인 세 개를 만들고 옛 `run_id` 색인을 지운다."""
    op.create_index("ix_log_events_session_seq", "log_events", ["session", "seq"])
    op.create_index("ix_log_events_thread_seq", "log_events", ["thread", "seq"])
    op.create_index("ix_log_events_run_seq", "log_events", ["run_id", "seq"])
    op.drop_index("ix_log_events_run", table_name="log_events")


def downgrade() -> None:
    """리비전 0001의 색인 모양으로 되돌린다(행은 그대로)."""
    op.create_index("ix_log_events_run", "log_events", ["run_id"])
    op.drop_index("ix_log_events_run_seq", table_name="log_events")
    op.drop_index("ix_log_events_thread_seq", table_name="log_events")
    op.drop_index("ix_log_events_session_seq", table_name="log_events")
