"""색인 테이블 정의(SQLAlchemy Core, design §4R.5). 계보 `logs`의 마이그레이션이 같은 모양을 만든다.

컬럼으로 올린 것은 필터·정렬·집계·묶기에 실제로 쓰는 필드뿐이다. 나머지는 `body`(JSON)에 둔다.
큰 원문은 목록용 `body`와 분리해 `heavy`에 둔다(목록 질의는 `heavy`를 읽지 않는다).

설계(§4R.5)에 더한 것(4R.5 결정):
- `log_events.via`·`status`·`etime`: `via`·`status`는 값 필터 열, `etime`은 이벤트 시각
  (`time`, 없으면 `observed_at`)이라 기간 필터·정렬·집계가 인덱스를 탄다.
- `log_bodies(seq, body, heavy)`·`log_search(seq, text)`: 큰 열을 `log_events`에서 뺐다.
  목록·집계·세션 요약이 좁은 행만 읽고, 검색(`q`)만 `log_search`를, 상세만 `heavy`를 읽는다.
  `body`는 기본값과 같은 필드를 뺀 JSON이다(읽을 때 모델이 기본값을 채운다).
- `log_corr(seq, basis, value)`: 근거 연결 후보를 인덱스로 찾는다(`body.correlation` 스캔 방지).
- `thread`·`session`·`run_id`는 `(값, seq)` 색인이다(5.5R.6): `thread`·`scope`
  필터가 `seq` 순서 쪽 넘김을
  임시 정렬 없이 하고, 확장 판정이 있어도 `LIMIT`만큼 맞는 행을 찾으면 읽기가 멈춘다.
- `log_usage.repo_root`: 프로젝트 묶기 기준(이벤트 조인 없이 표본만으로 묶는다).
"""

from __future__ import annotations

import sqlalchemy as sa

__all__ = [
    "OBSOLETE_INDEXES",
    "TABLE_NAMES",
    "log_agents",
    "log_bodies",
    "log_corr",
    "log_cursors",
    "log_events",
    "log_links",
    "log_metadata",
    "log_search",
    "log_tags",
    "log_usage",
]

log_metadata = sa.MetaData()
"""색인 테이블 묶음. 다른 모듈의 메타데이터와 섞지 않는다."""

log_events = sa.Table(
    "log_events",
    log_metadata,
    sa.Column("seq", sa.Integer, primary_key=True),
    sa.Column("uid", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("ref", sa.Text, nullable=False, server_default=""),
    sa.Column("thread", sa.Text, nullable=False, server_default=""),
    sa.Column("actor", sa.Text, nullable=False, server_default=""),
    sa.Column("tool", sa.Text, nullable=False, server_default=""),
    sa.Column("call_id", sa.Text, nullable=False, server_default=""),
    sa.Column("stage", sa.Text, nullable=False, server_default=""),
    sa.Column("category", sa.Text, nullable=False),
    sa.Column("via", sa.Text, nullable=False, server_default=""),
    sa.Column("status", sa.Text, nullable=False, server_default=""),
    sa.Column("session", sa.Text, nullable=False, server_default=""),
    sa.Column("cwd", sa.Text, nullable=False, server_default=""),
    sa.Column("repo_root", sa.Text, nullable=False, server_default=""),
    sa.Column("model", sa.Text, nullable=False, server_default=""),
    sa.Column("run_id", sa.Text, nullable=False, server_default=""),
    sa.Column("message_id", sa.Text, nullable=False, server_default=""),
    sa.Column("time", sa.Float),
    sa.Column("observed_at", sa.Float, nullable=False),
    sa.Column("etime", sa.Float, nullable=False),
    sa.UniqueConstraint("uid", name="uq_log_events_uid"),
    sa.Index("ix_log_events_session_time", "session", "etime"),
    sa.Index("ix_log_events_thread_call", "thread", "call_id"),
    sa.Index("ix_log_events_thread_message", "thread", "message_id"),
    sa.Index("ix_log_events_category_seq", "category", "seq"),
    sa.Index("ix_log_events_cwd", "cwd", "repo_root"),
    sa.Index("ix_log_events_session_seq", "session", "seq"),
    sa.Index("ix_log_events_thread_seq", "thread", "seq"),
    sa.Index("ix_log_events_run_seq", "run_id", "seq"),
    sa.Index("ix_log_events_time", "etime"),
    sa.Index("ix_log_events_source", "source", "seq"),
    sqlite_autoincrement=True,
)

log_bodies = sa.Table(
    "log_bodies",
    log_metadata,
    sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("heavy", sa.Text),
)

log_search = sa.Table(
    "log_search",
    log_metadata,
    sa.Column("seq", sa.Integer, primary_key=True, autoincrement=False),
    sa.Column("text", sa.Text, nullable=False),
)

log_tags = sa.Table(
    "log_tags",
    log_metadata,
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("tag", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("seq", "tag"),
    sa.Index("ix_log_tags_tag", "tag", "seq"),
)

log_links = sa.Table(
    "log_links",
    log_metadata,
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("agent", sa.Text, nullable=False),
    sa.Column("side", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("seq", "side", "agent"),
    sa.Index("ix_log_links_agent", "agent", "side", "seq"),
)

log_corr = sa.Table(
    "log_corr",
    log_metadata,
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("basis", sa.Text, nullable=False),
    sa.Column("value", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("seq", "basis", "value"),
    sa.Index("ix_log_corr_key", "basis", "value", "seq"),
)

log_agents = sa.Table(
    "log_agents",
    log_metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("label", sa.Text),
    sa.Column("parent_id", sa.Text),
    sa.Column("source", sa.Text, nullable=False, server_default=""),
)

log_cursors = sa.Table(
    "log_cursors",
    log_metadata,
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("ref", sa.Text, nullable=False),
    sa.Column("offset", sa.Integer, nullable=False, server_default="0"),
    sa.Column("size", sa.Integer),
    sa.Column("mtime", sa.Float),
    sa.Column("state", sa.Text, nullable=False, server_default="{}"),
    sa.Column("updated_at", sa.Float),
    sa.PrimaryKeyConstraint("source", "ref"),
)

log_usage = sa.Table(
    "log_usage",
    log_metadata,
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("thread", sa.Text, nullable=False),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("session", sa.Text, nullable=False, server_default=""),
    sa.Column("cwd", sa.Text, nullable=False, server_default=""),
    sa.Column("repo_root", sa.Text, nullable=False, server_default=""),
    sa.Column("model", sa.Text, nullable=False, server_default=""),
    sa.Column("time", sa.Float),
    sa.Column("input_tokens", sa.Integer),
    sa.Column("cache_creation_input_tokens", sa.Integer),
    sa.Column("cache_read_input_tokens", sa.Integer),
    sa.Column("output_tokens", sa.Integer),
    sa.PrimaryKeyConstraint("source", "thread", "message_id"),
    sa.Index("ix_log_usage_session", "session"),
    sa.Index("ix_log_usage_time", "time"),
    sa.Index("ix_log_usage_message", "thread", "message_id"),
)

TABLE_NAMES: tuple[str, ...] = tuple(sorted(log_metadata.tables))
"""이 색인이 소유한 테이블 이름."""

OBSOLETE_INDEXES: tuple[str, ...] = ("ix_log_events_run",)
"""옛 스키마에만 있던 색인 이름(`logs_0002`가 지운다). 단독 열기(`open_log_index`)도 지운다."""
