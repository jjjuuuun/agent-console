"""SQLite 표 정의(design §5.7R.6). 단독 `create_all`과 서버 모듈 마이그레이션이 같은 모양을 지킨다.

- `metadata`: 일반 표 넷(`memory_entries`·`memory_versions`·`memory_tags`·`memory_stats`)과 색인.
  `create_all`로 만든다.
- `SEARCH_TABLE_DDL`: 전문 검색 가상 표 `memory_fts`(FTS5 trigram, 외부 내용 = `memory_entries`).
  SQLAlchemy 메타데이터로 표현할 수 없어 DDL 문자열로 둔다. 마이그레이션 비교 대상이 아니다.

열 순서는 의도적이다: 작은 열을 앞에, 큰 본문(`content`)을 **맨 뒤**에 둔다. SQLite는 행을
앞에서부터 읽으므로 목록·집계가 본문 쪽(넘침 쪽)을 읽지 않는다("큰 원문과 목록용 요약 분리").
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    text,
)

ENTRIES_TABLE: Final = "memory_entries"
VERSIONS_TABLE: Final = "memory_versions"
TAGS_TABLE: Final = "memory_tags"
SEARCH_TABLE: Final = "memory_fts"
STATS_TABLE: Final = "memory_stats"
LIVE_BYTES: Final = "live_bytes"

metadata = MetaData()

entries = Table(
    ENTRIES_TABLE,
    metadata,
    # rid = 전문 검색 색인의 행 번호. `id`(UUID 문자열)만 기본키로 두면 VACUUM이 행 번호를 바꿔
    # 외부 내용 색인이 어긋나므로 정수 기본키를 따로 둔다(design과 다른 점, [5.7R.10 구현·측정]).
    Column("rid", Integer, primary_key=True),
    Column("id", String, nullable=False),
    Column("scope_kind", String, nullable=False),
    Column("scope_id", String, nullable=False),
    Column("key", Text, nullable=False),
    Column("content_type", String, nullable=False),
    Column("tags", Text, nullable=False, server_default="[]"),  # JSON 목록(순서 보존)
    Column("pinned", Boolean, nullable=False, server_default="0"),
    Column("archived", Boolean, nullable=False, server_default="0"),
    Column("version", Integer, nullable=False),
    Column("bytes", Integer, nullable=False),
    Column("sha256", String, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("created_by", Text, nullable=False),  # JSON(MemoryAuthor)
    Column("updated_at", Float, nullable=False),
    Column("updated_by", Text, nullable=False),  # JSON(MemoryAuthor)
    Column("author_run_id", String, nullable=True),  # 마지막 쓰기 실행(updated_by.run_id)
    Column("last_read_at", Float, nullable=True),
    Column("deleted_at", Float, nullable=True),
    # 목록용 요약: 쓸 때 비밀을 가려 자른 앞부분. 목록이 본문(최대 64 KiB)을 읽거나 훑지 않는다.
    Column("preview", Text, nullable=False, server_default=""),
    Column("content", Text, nullable=False),  # 큰 값은 맨 뒤
    Index("ux_memory_entries_id", "id", unique=True),
    Index(
        "ux_memory_entries_live_key",
        "scope_kind",
        "scope_id",
        "key",
        unique=True,
        sqlite_where=text("deleted_at IS NULL"),
    ),
    # 범위 목록(최근순 쪽 넘김)과 범위 요약(개수·보관 수·바이트 합·최근 시각)을 본문을 읽지 않고
    # 색인만으로 답한다. design의 (범위, updated_at) 색인을 이것이 대신한다(측정: 더 싸다).
    Index(
        "ix_memory_entries_live_summary",
        "scope_kind",
        "scope_id",
        "archived",
        "updated_at",
        "id",
        "bytes",
        "deleted_at",  # 부분 색인 조건의 열도 색인에 있어야 SQLite가 "색인만으로 답함"으로 본다
        sqlite_where=text("deleted_at IS NULL"),
    ),
    Index("ix_memory_entries_author_run", "author_run_id"),
    Index(
        "ix_memory_entries_deleted",
        "deleted_at",
        sqlite_where=text("deleted_at IS NOT NULL"),
    ),
)

versions = Table(
    VERSIONS_TABLE,
    metadata,
    Column("entry_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("op", String, nullable=False),
    Column("scope_kind", String, nullable=False),
    Column("scope_id", String, nullable=False),
    Column("key", Text, nullable=False),
    Column("bytes", Integer, nullable=False),
    Column("sha256", String, nullable=False),
    Column("author", Text, nullable=False),  # JSON(MemoryAuthor)
    Column("run_id", String, nullable=True),
    Column("at", Float, nullable=False),
    Column("content", Text, nullable=False),
    PrimaryKeyConstraint("entry_id", "version", name="pk_memory_versions"),
    Index("ix_memory_versions_run", "run_id"),
)

tags = Table(
    TAGS_TABLE,
    metadata,
    Column("entry_id", String, nullable=False),
    Column("tag", String, nullable=False),
    PrimaryKeyConstraint("entry_id", "tag", name="pk_memory_tags"),
    Index("ix_memory_tags_tag", "tag", "entry_id"),
)

stats = Table(
    STATS_TABLE,
    metadata,
    # 쓸 때마다 지우지 않은 항목의 본문 바이트 합을 같은 트랜잭션에서 맞춘다
    # (저장소 전체 한도 검사가 항목 수에 비례해 느려지지 않게).
    Column("name", String, primary_key=True),
    Column("value", Integer, nullable=False),
)

SEARCH_TABLE_DDL: Final = (
    f"CREATE VIRTUAL TABLE IF NOT EXISTS {SEARCH_TABLE} USING fts5("
    f"key, content, tags, content='{ENTRIES_TABLE}', content_rowid='rid', tokenize='trigram')"
)
"""전문 검색 가상 표. `tags` 열에는 태그를 줄바꿈으로 이은 값을 직접 넣는다(JSON 기호 제외)."""

__all__ = [
    "ENTRIES_TABLE",
    "LIVE_BYTES",
    "SEARCH_TABLE",
    "SEARCH_TABLE_DDL",
    "STATS_TABLE",
    "TAGS_TABLE",
    "VERSIONS_TABLE",
    "entries",
    "metadata",
    "stats",
    "tags",
    "versions",
]
