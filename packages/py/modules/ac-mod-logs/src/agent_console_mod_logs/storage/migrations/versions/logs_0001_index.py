"""logs 계보의 첫 리비전: 로그 색인 테이블(design §4R.5).

이 파일은 고치지 않는다. 이후 스키마 변경은 새 리비전으로 추가한다. 테이블 모양은
`agent_console_logs.sqlite.schema`와 같아야 하며, 테스트가 `compare_metadata`로 확인한다.
(스키마를 import하지 않고 풀어 쓴 이유: 이미 적용된 리비전은 나중에 코드가 바뀌어도 같은 모양을
만들어야 하기 때문이다.)

Revision ID: logs_0001
Revises: (없음)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "logs_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _text(name: str) -> sa.Column[str]:
    """빈 문자열이 기본값인 필수 텍스트 열."""
    return sa.Column(name, sa.Text, nullable=False, server_default="")


def upgrade() -> None:
    """색인 테이블 9개와 인덱스를 만든다."""
    op.create_table(
        "log_events",
        sa.Column("seq", sa.Integer, primary_key=True),
        sa.Column("uid", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        _text("ref"),
        _text("thread"),
        _text("actor"),
        _text("tool"),
        _text("call_id"),
        _text("stage"),
        sa.Column("category", sa.Text, nullable=False),
        _text("via"),
        _text("status"),
        _text("session"),
        _text("cwd"),
        _text("repo_root"),
        _text("model"),
        _text("run_id"),
        _text("message_id"),
        sa.Column("time", sa.Float),
        sa.Column("observed_at", sa.Float, nullable=False),
        sa.Column("etime", sa.Float, nullable=False),
        sa.UniqueConstraint("uid", name="uq_log_events_uid"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_log_events_session_time", "log_events", ["session", "etime"])
    op.create_index("ix_log_events_thread_call", "log_events", ["thread", "call_id"])
    op.create_index("ix_log_events_thread_message", "log_events", ["thread", "message_id"])
    op.create_index("ix_log_events_category_seq", "log_events", ["category", "seq"])
    op.create_index("ix_log_events_cwd", "log_events", ["cwd", "repo_root"])
    op.create_index("ix_log_events_run", "log_events", ["run_id"])
    op.create_index("ix_log_events_time", "log_events", ["etime"])
    op.create_index("ix_log_events_source", "log_events", ["source", "seq"])

    op.create_table(
        "log_bodies",
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("heavy", sa.Text),
    )
    op.create_table(
        "log_search",
        sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("text", sa.Text, nullable=False),
    )
    op.create_table(
        "log_tags",
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("tag", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("seq", "tag"),
    )
    op.create_index("ix_log_tags_tag", "log_tags", ["tag", "seq"])
    op.create_table(
        "log_links",
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("side", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("seq", "side", "agent"),
    )
    op.create_index("ix_log_links_agent", "log_links", ["agent", "side", "seq"])
    op.create_table(
        "log_corr",
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("basis", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("seq", "basis", "value"),
    )
    op.create_index("ix_log_corr_key", "log_corr", ["basis", "value", "seq"])
    op.create_table(
        "log_agents",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text),
        sa.Column("parent_id", sa.Text),
        _text("source"),
    )
    op.create_table(
        "log_cursors",
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("ref", sa.Text, nullable=False),
        sa.Column("offset", sa.Integer, nullable=False, server_default="0"),
        sa.Column("size", sa.Integer),
        sa.Column("mtime", sa.Float),
        sa.Column("state", sa.Text, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.Float),
        sa.PrimaryKeyConstraint("source", "ref"),
    )
    op.create_table(
        "log_usage",
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("thread", sa.Text, nullable=False),
        sa.Column("message_id", sa.Text, nullable=False),
        _text("session"),
        _text("cwd"),
        _text("repo_root"),
        _text("model"),
        sa.Column("time", sa.Float),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("cache_creation_input_tokens", sa.Integer),
        sa.Column("cache_read_input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.PrimaryKeyConstraint("source", "thread", "message_id"),
    )
    op.create_index("ix_log_usage_session", "log_usage", ["session"])
    op.create_index("ix_log_usage_time", "log_usage", ["time"])
    op.create_index("ix_log_usage_message", "log_usage", ["thread", "message_id"])


def downgrade() -> None:
    """색인 테이블을 모두 지운다(색인은 원본 로그에서 다시 만들 수 있다)."""
    for table in (
        "log_usage",
        "log_cursors",
        "log_agents",
        "log_corr",
        "log_links",
        "log_tags",
        "log_search",
        "log_bodies",
        "log_events",
    ):
        op.drop_table(table)
