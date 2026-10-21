"""채팅 대기열 · 본문 스냅샷 · 이어 가기 (design §2R.3).

- 새 테이블 `chat_queue`(+ (conversation_id, position) 인덱스): 서버 재시작 뒤에도 남는 대기열
- 새 테이블 `content_blobs`: 정의 본문 파일의 내용 주소(sha256) 저장
- `definition_versions.content_files`: 그 버전의 본문 스냅샷(경로 -> sha256 JSON). 이전 버전은 NULL
- `runs.resumed_from` + 인덱스: 이어 간 Run 조회. `doc`의 투영이라 적용할 때 채운다

되돌리면 `chat_queue`·`content_blobs`·`content_files`의 내용은 사라진다(기록이 아니라 상태/사본이라
되돌릴 값이 없다). `runs.resumed_from`은 `doc`에 남아 있어 다시 적용하면 복구된다.

이 파일은 고치지 않는다. 스키마를 바꾸려면 새 마이그레이션을 추가한다.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_queue",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("conversation_id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("held", sa.Integer, nullable=False, server_default="0"),
        sa.Column("held_reason", sa.Text),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index(
        "ix_chat_queue_conversation_position", "chat_queue", ["conversation_id", "position"]
    )

    op.create_table(
        "content_blobs",
        sa.Column("sha256", sa.Text, primary_key=True),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )

    with op.batch_alter_table("definition_versions") as batch:
        batch.add_column(sa.Column("content_files", sa.Text))

    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("resumed_from", sa.Text))
        batch.create_index("ix_runs_resumed_from", ["resumed_from"])
    op.execute("UPDATE runs SET resumed_from = json_extract(doc, '$.resumed_from')")


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_resumed_from")
        batch.drop_column("resumed_from")

    with op.batch_alter_table("definition_versions") as batch:
        batch.drop_column("content_files")

    op.drop_table("content_blobs")
    op.drop_index("ix_chat_queue_conversation_position", table_name="chat_queue")
    op.drop_table("chat_queue")
