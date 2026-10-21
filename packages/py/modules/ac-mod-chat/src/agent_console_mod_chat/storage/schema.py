"""`conversations`·`chat_queue` 테이블 정의(SQLAlchemy Core).

두 테이블은 legacy 마이그레이션 0002·0003이 만들었다. `conversations.project_id`와 그 색인은
`chat_0002`가 더했다(이동은 코드 소유권만 바뀐다,
design §3R.1.7). 컬럼으로 올린 것은 목록 필터·정렬(그래프, 보관 여부, 갱신 시각)과 대기열 순서에
쓰는 필드뿐이고, 대화 전체는 `doc`(JSON)에 둔다.
"""

import sqlalchemy as sa

metadata = sa.MetaData()

CONVERSATIONS_TABLE = "conversations"
QUEUE_TABLE = "chat_queue"
TABLE_NAMES: frozenset[str] = frozenset({CONVERSATIONS_TABLE, QUEUE_TABLE})

conversations = sa.Table(
    CONVERSATIONS_TABLE,
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("graph_id", sa.Text, nullable=False),
    sa.Column("archived", sa.Integer, nullable=False),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("updated_at", sa.Float, nullable=False),
    sa.Column("doc", sa.Text, nullable=False),
    sa.Column("project_id", sa.Text),
    sa.Index("ix_conversations_archived_updated", "archived", "updated_at"),
    sa.Index("ix_conversations_graph_updated", "graph_id", "updated_at"),
    sa.Index("ix_conversations_project_updated", "project_id", "updated_at"),
)

chat_queue = sa.Table(
    QUEUE_TABLE,
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("conversation_id", sa.Text, nullable=False),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("held", sa.Integer, nullable=False, server_default="0"),
    sa.Column("held_reason", sa.Text),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Index("ix_chat_queue_conversation_position", "conversation_id", "position"),
)

__all__ = [
    "CONVERSATIONS_TABLE",
    "QUEUE_TABLE",
    "TABLE_NAMES",
    "chat_queue",
    "conversations",
    "metadata",
]
