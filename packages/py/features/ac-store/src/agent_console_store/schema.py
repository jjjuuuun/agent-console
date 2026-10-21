"""SQLite 테이블 정의(SQLAlchemy Core). design §2.3과 같은 내용이어야 하며,
마이그레이션(`migrations/versions`)과의 일치는 테스트가 검사한다.

원칙: 목록·필터·집계에 쓰는 필드만 컬럼으로 올리고, 전체 모델은 `doc`(JSON 텍스트)에 둔다.
그래서 모델에 필드가 늘어도 마이그레이션이 필요 없다.
"""

import sqlalchemy as sa

metadata = sa.MetaData()

MODULE_OWNED_TABLES: frozenset[str] = frozenset(
    {
        "usage_observations",
        "conversations",
        "chat_queue",
        "runs",
        "node_runs",
        "run_events",
        "interactions",
    }
)
"""legacy 마이그레이션(0001~0003)이 만들지만 코드·테이블 정의는 모듈 패키지가 소유한 테이블.

테이블 정의(`sa.Table`)는 소유 모듈 패키지에 있으므로 이 `metadata`에는 없다. 그래서 마이그레이션
결과와 `metadata`를 비교하는 곳은 이 이름들을 비교에서 뺀다(design §3R.1.7).
- `usage_observations`: `agent_console_mod_usage.storage`(3R.11).
- `conversations`·`chat_queue`: `agent_console_mod_chat.storage`(3R.15).
- `runs`·`node_runs`·`run_events`·`interactions`: 계보 `runs`(`agent_console_mod_runs`,
  5R.4)가 소유권을 넘겨받는다. 코드(저장소 구현)와 아래 legacy 정의는 여기에 그대로 있다.
  이 표들은 legacy 모양(`metadata`)과 계보 적용 뒤 모양(`runs_lineage_metadata`) 둘이라
  비교는 호출자가 정한다.
"""


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    """Alembic `include_object`: 모듈 소유 테이블(과 그 인덱스)을 비교에서 뺀다."""
    if type_ == "table":
        return name not in MODULE_OWNED_TABLES
    table = getattr(obj, "table", None)
    return getattr(table, "name", None) not in MODULE_OWNED_TABLES


definition_versions = sa.Table(
    "definition_versions",
    metadata,
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("def_id", sa.Text, nullable=False),
    sa.Column("version_hash", sa.Text, nullable=False),
    sa.Column("saved_at", sa.Float, nullable=False),
    sa.Column("message", sa.Text, nullable=False, server_default=""),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("content_files", sa.Text),
    sa.PrimaryKeyConstraint("kind", "def_id", "version_hash"),
    sa.Index("ix_definition_versions_history", "kind", "def_id", "saved_at"),
)

runs = sa.Table(
    "runs",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("graph_id", sa.Text, nullable=False),
    sa.Column("graph_version", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("origin", sa.Text, nullable=False),
    sa.Column("parent_run_id", sa.Text),
    sa.Column("conversation_id", sa.Text),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("started_at", sa.Float),
    sa.Column("ended_at", sa.Float),
    sa.Column("doc", sa.Text, nullable=False),
    sa.Column("resumed_from", sa.Text),
    sa.Index("ix_runs_graph_created", "graph_id", "created_at"),
    sa.Index("ix_runs_status", "status"),
    sa.Index("ix_runs_parent", "parent_run_id"),
    sa.Index("ix_runs_created", "created_at"),
    sa.Index("ix_runs_conversation", "conversation_id", "created_at"),
    sa.Index("ix_runs_resumed_from", "resumed_from"),
)

node_runs = sa.Table(
    "node_runs",
    metadata,
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("node_id", sa.Text, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("iteration", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("node_type", sa.Text),
    sa.Column("started_at", sa.Float),
    sa.Column("ended_at", sa.Float),
    sa.Column("duration_ms", sa.Integer),
    sa.Column("doc", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("run_id", "node_id", "attempt", "iteration"),
    sa.Index("ix_node_runs_type_status", "node_type", "status"),
)

run_events = sa.Table(
    "run_events",
    metadata,
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("event_id", sa.Text, nullable=False),
    sa.Column("ts", sa.Float, nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("node_id", sa.Text),
    sa.Column("attempt", sa.Integer),
    sa.Column("actor", sa.Text),
    sa.Column("body", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("run_id", "seq"),
    sa.UniqueConstraint("run_id", "event_id", name="uq_run_events_event_id"),
    sa.Index("ix_run_events_type", "run_id", "type"),
    sa.Index("ix_run_events_node", "run_id", "node_id"),
    sa.Index("ix_run_events_actor_ts", "actor", "ts"),
    sa.Index("ix_run_events_type_ts", "type", "ts"),
)

# legacy(2R.20): 라우터를 삭제해 이 테이블에 쓰는 코드는 없다. 마이그레이션 0001~0003 동결(파괴적
# 마이그레이션 금지)이라 테이블은 남긴다. Run 삭제 때 남은 행을 지우는 코드만 있다(sqlite.py).
routing_decisions = sa.Table(
    "routing_decisions",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("node_id", sa.Text, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("category", sa.Text),
    sa.Column("confidence", sa.Float),
    sa.Column("chosen_port", sa.Text),
    sa.Column("manual", sa.Integer, nullable=False),
    sa.Column("overridden_by", sa.Text),
    sa.Column("overridden_port", sa.Text),
    sa.Column("decided_at", sa.Float, nullable=False),
    sa.Column("doc", sa.Text, nullable=False),
    sa.UniqueConstraint("run_id", "node_id", "attempt", "decided_at", name="uq_routing_decision"),
    sa.Index("ix_routing_run_node", "run_id", "node_id"),
    sa.Index("ix_routing_category_port", "category", "chosen_port"),
    sa.Index("ix_routing_decided_at", "decided_at"),
)

interactions = sa.Table(
    "interactions",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("conversation_id", sa.Text),
    sa.Column("node_id", sa.Text, nullable=False),
    sa.Column("actor", sa.Text),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("created_at", sa.Float, nullable=False),
    sa.Column("closed_at", sa.Float),
    sa.Column("doc", sa.Text, nullable=False),
    sa.Index("ix_interactions_status_created", "status", "created_at"),
    sa.Index("ix_interactions_run", "run_id"),
    sa.Index("ix_interactions_conversation_status", "conversation_id", "status"),
)

content_blobs = sa.Table(
    "content_blobs",
    metadata,
    sa.Column("sha256", sa.Text, primary_key=True),
    sa.Column("size", sa.Integer, nullable=False),
    sa.Column("data", sa.LargeBinary, nullable=False),
)
"""정의 본문 파일의 내용 주소 저장(0003). `definition_versions.content_files`(경로 -> sha256 JSON)가
가리킨다. 같은 내용은 한 행을 여러 버전이 공유하고, 어떤 버전도 안 쓰면 `prune_blobs`가 지운다."""


# --- 계보 `runs`(5R.4, `agent_console_mod_runs`의 `runs_0002`)가 바꾸는 모양 ---------
# legacy 표(위)는 동결이다. 계보가 열을 더한 뒤의 모양은 따로 정의하고, 저장소 구현은 DB에 그 열이
# 있을 때만 이 정의로 쓴다(`runs_lineage_active`). 마이그레이션 `runs_0002`와 같은 내용이어야 하며
# `agent_console_mod_runs` 테스트가 `compare_metadata`로 맞춘다.
runs_lineage_metadata = sa.MetaData()

runs_v2 = runs.to_metadata(runs_lineage_metadata)
runs_v2.append_column(sa.Column("parent_node_id", sa.Text))
runs_v2.append_column(sa.Column("root_run_id", sa.Text))
sa.Index("ix_runs_root", runs_v2.c.root_run_id)
# `runs_0003`(5.2R.32): 프로젝트 열 + (project_id, created_at) 색인. `runs_lineage_active`는 이 열을
# 요구하지 않는다(0002까지만 올린 DB도 계보로 읽는다). 저장소는 `runs_project_active`로 따로 본다.
runs_v2.append_column(sa.Column("project_id", sa.Text))
sa.Index("ix_runs_project_created", runs_v2.c.project_id, runs_v2.c.created_at)

node_runs_v2 = sa.Table(
    "node_runs",
    runs_lineage_metadata,
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("node_id", sa.Text, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("iteration", sa.Integer, nullable=False),
    sa.Column("call", sa.Integer, nullable=False, server_default="0"),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("node_type", sa.Text),
    sa.Column("started_at", sa.Float),
    sa.Column("ended_at", sa.Float),
    sa.Column("duration_ms", sa.Integer),
    sa.Column("invoked_by", sa.JSON(none_as_null=True)),
    sa.Column("doc", sa.Text, nullable=False),
    sa.PrimaryKeyConstraint("run_id", "node_id", "attempt", "iteration", "call"),
    sa.Index("ix_node_runs_type_status", "node_type", "status"),
)

run_events_v2 = run_events.to_metadata(runs_lineage_metadata)

interactions_v2 = interactions.to_metadata(runs_lineage_metadata)
interactions_v2.append_column(sa.Column("root_run_id", sa.Text))
sa.Index("ix_interactions_root", interactions_v2.c.root_run_id)

# 계보 밖 표도 같이 두어 이 metadata 하나로 "legacy + 계보" 전체 모양을 비교할 수 있게 한다.
for _table in metadata.tables.values():
    if _table.name not in runs_lineage_metadata.tables:
        _table.to_metadata(runs_lineage_metadata)


def runs_lineage_active(engine: sa.Engine) -> bool:
    """DB에 계보 `runs`의 새 열이 모두 있는가(`runs_0002` 적용 여부).

    저장소 구현이 새 열을 읽고 쓸지, `doc` JSON만으로 동작할지(계보를 안 올린 단독 사용) 고른다.
    """
    inspector = sa.inspect(engine)
    names = set(inspector.get_table_names())
    wanted = {
        "runs": {"root_run_id", "parent_node_id"},
        "node_runs": {"call", "invoked_by"},
        "interactions": {"root_run_id"},
    }
    if not set(wanted) <= names:
        return False
    return all(
        cols <= {c["name"] for c in inspector.get_columns(table)} for table, cols in wanted.items()
    )


def runs_project_active(engine: sa.Engine) -> bool:
    """`runs.project_id` 열이 DB에 있는가(`runs_0003` 적용 여부).

    없으면 저장소는 `project_id`를 `doc`에만 남기고 `project` 거르기는 `doc`의 JSON을 훑는다.
    """
    inspector = sa.inspect(engine)
    if "runs" not in inspector.get_table_names():
        return False
    return "project_id" in {c["name"] for c in inspector.get_columns("runs")}
