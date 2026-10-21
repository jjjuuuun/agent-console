"""mod-chat 저장소: 대화·대기열 규칙(SQLite·인메모리), 마이그레이션 계보, 기존 DB(0003) 호환.

design §3R.1.7. 3R.15에서 ac-store의 같은 테스트를 옮겨 왔다.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_contracts import Conversation, SessionRef
from agent_console_mod_chat.storage import (
    BRANCH,
    TABLE_NAMES,
    InMemoryChatStorage,
    QueueItemExistsError,
    QueueItemNotFoundError,
    SqliteChatStorage,
    metadata,
)
from agent_console_store import SqliteDatabase, create_sqlite_engine, upgrade


@pytest.fixture(params=["sqlite", "memory"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    if request.param == "memory":
        yield InMemoryChatStorage()
        return
    db = SqliteDatabase.open(tmp_path / "c.sqlite3")
    db.upgrade([BRANCH])
    yield SqliteChatStorage(db.engine)
    db.close()


def make_conv(id: str = "c1", graph_id: str = "g1", updated_at: float = 10.0, **kw: Any) -> Any:
    fields: dict[str, Any] = {
        "id": id,
        "graph_id": graph_id,
        "created_at": 1.0,
        "updated_at": updated_at,
    }
    fields.update(kw)
    return Conversation(**fields)


def _q(storage: Any, item_id: str, conv: str = "c1", text: str = "t", **kw: Any) -> Any:
    return storage.queue.enqueue(item_id, conv, text, created_at=1.0, **kw)


# ---- 대화 -----------------------------------------------------------------
def test_conversation_save_get_roundtrip_with_sessions(storage: Any) -> None:
    conv = make_conv(sessions={"pl": SessionRef(backend="fake", session_id="s1", data={"k": 1})})
    storage.conversations.save(conv)
    got = storage.conversations.get("c1")
    assert got == conv
    assert got.sessions["pl"].session_id == "s1"
    assert storage.conversations.get("nope") is None


def test_conversation_save_is_upsert_and_list_filters(storage: Any) -> None:
    repo = storage.conversations
    repo.save(make_conv("c1", "g1", 10.0))
    repo.save(make_conv("c2", "g2", 30.0))
    repo.save(make_conv("c3", "g1", 20.0, archived=True))
    repo.save(make_conv("c1", "g1", 40.0, title="바뀜"))
    assert [c.id for c in repo.list()] == ["c1", "c2", "c3"]
    assert repo.get("c1").title == "바뀜"
    assert [c.id for c in repo.list(graph_id="g1")] == ["c1", "c3"]
    assert [c.id for c in repo.list(archived=False)] == ["c1", "c2"]
    assert [c.id for c in repo.list(archived=True)] == ["c3"]
    assert [c.id for c in repo.list(limit=1)] == ["c1"]


def test_conversation_delete_returns_whether_it_existed(storage: Any) -> None:
    storage.conversations.save(make_conv())
    assert storage.conversations.delete("c1") is True
    assert storage.conversations.delete("c1") is False


def test_conversation_delete_clears_only_its_queue(storage: Any) -> None:
    """대화를 지우면 그 대기열이 함께 지워진다(같은 트랜잭션/락). 다른 대화의 것은 남는다."""
    storage.conversations.save(make_conv("c1"))
    storage.conversations.save(make_conv("c2"))
    _q(storage, "a", held=True, held_reason="why")
    _q(storage, "x", conv="c2")
    assert storage.queue.get("a").held_reason == "why"
    assert storage.conversations.delete("c1") is True
    assert storage.queue.list("c1") == []
    assert [q.id for q in storage.queue.list()] == ["x"]


def test_sqlite_conversation_delete_is_one_transaction(tmp_path: Path) -> None:
    """대화 삭제 중 실패하면 대기열도 지워지지 않는다(트랜잭션 롤백)."""
    db = SqliteDatabase.open(tmp_path / "t.sqlite3")
    db.upgrade([BRANCH])
    storage = SqliteChatStorage(db.engine)
    storage.conversations.save(make_conv("c1"))
    _q(storage, "a")
    with db.engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER boom BEFORE DELETE ON conversations "
            "BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )
    with pytest.raises(sa.exc.DBAPIError):
        storage.conversations.delete("c1")
    assert [q.id for q in storage.queue.list("c1")] == ["a"]
    assert storage.conversations.get("c1") is not None
    db.close()


# ---- 대기열 ---------------------------------------------------------------
def test_queue_is_fifo_per_conversation_and_compacts(storage: Any) -> None:
    a, b, c = _q(storage, "a"), _q(storage, "b"), _q(storage, "c")
    other = _q(storage, "x", conv="c2")
    assert [a.position, b.position, c.position, other.position] == [1, 2, 3, 1]
    assert [q.id for q in storage.queue.list("c1")] == ["a", "b", "c"]
    assert storage.queue.remove("b") is True
    assert storage.queue.remove("b") is False
    assert [(q.id, q.position) for q in storage.queue.list("c1")] == [("a", 1), ("c", 2)]
    assert storage.queue.get("c").position == 2
    assert storage.queue.get("nope") is None
    assert [q.id for q in storage.queue.list()] == ["a", "c", "x"]


def test_queue_duplicate_id_is_rejected(storage: Any) -> None:
    _q(storage, "a")
    with pytest.raises(QueueItemExistsError):
        _q(storage, "a", conv="c2")
    assert [q.id for q in storage.queue.list()] == ["a"]


def test_queue_pop_next_respects_held(storage: Any) -> None:
    _q(storage, "a")
    _q(storage, "b")
    _q(storage, "c")
    assert storage.queue.pop_next("c1").id == "a"
    assert storage.queue.get("b").position == 1
    assert storage.queue.hold_all("restart") == 2
    assert storage.queue.hold_all("restart") == 0  # 이미 멈춘 것은 세지 않는다
    held = storage.queue.get("b")
    assert held.held is True
    assert held.held_reason == "restart"
    assert storage.queue.pop_next("c1") is None  # 맨 앞이 멈춰 있으면 꺼내지 않는다
    assert storage.queue.pop_next("empty") is None
    released = storage.queue.release("b")
    assert released.held is False
    assert released.held_reason is None
    storage.queue.release("c")
    assert [storage.queue.pop_next("c1").id, storage.queue.pop_next("c1").id] == ["b", "c"]
    assert storage.queue.pop_next("c1") is None
    with pytest.raises(QueueItemNotFoundError):
        storage.queue.release("b")


def test_queue_hold_all_by_conversation_and_counts(storage: Any) -> None:
    _q(storage, "a")
    _q(storage, "b")
    _q(storage, "x", conv="c2")
    assert storage.queue.hold_all(conversation_id="c1") == 2
    assert [q.id for q in storage.queue.list(held=True)] == ["a", "b"]
    assert [q.id for q in storage.queue.list(held=False)] == ["x"]
    counts = storage.queue.counts()
    assert (counts["c1"].queued, counts["c1"].held) == (2, 2)
    assert (counts["c2"].queued, counts["c2"].held) == (1, 0)
    assert set(storage.queue.counts(["c2"])) == {"c2"}
    assert storage.queue.clear("c1") == 2
    assert "c1" not in storage.queue.counts()


# ---- 영속 -----------------------------------------------------------------
def test_sqlite_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "q.sqlite3"
    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    storage = SqliteChatStorage(db.engine)
    storage.conversations.save(make_conv())
    _q(storage, "a")
    db.close()
    again = SqliteDatabase.open(path)
    again.upgrade([BRANCH])
    reopened = SqliteChatStorage(again.engine)
    assert reopened.conversations.get("c1") is not None
    assert [q.id for q in reopened.queue.list("c1")] == ["a"]
    again.close()


# ---- 마이그레이션 계보 ----------------------------------------------------
def test_table_definitions_match_legacy_migration(tmp_path: Path) -> None:
    """테이블은 불변: legacy 0002·0003이 만든 모양과 이 모듈의 정의가 같다."""
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])

    def only_chat(obj: object, name: str | None, type_: str, *_: object) -> bool:
        table = obj if type_ == "table" else getattr(obj, "table", None)
        return getattr(table, "name", name) in TABLE_NAMES

    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"include_object": only_chat})
        assert compare_metadata(context, metadata) == []
    db.close()


def test_upgrade_on_empty_db_creates_tables_and_branch_version(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])
    assert set(sa.inspect(db.engine).get_table_names()) >= TABLE_NAMES
    assert db.revision() == "0003"
    assert db.revision("chat") == "chat_0002"
    names = {i["name"] for t in TABLE_NAMES for i in sa.inspect(db.engine).get_indexes(t)}
    assert {
        "ix_conversations_archived_updated",
        "ix_conversations_graph_updated",
        "ix_chat_queue_conversation_position",
        "ix_conversations_project_updated",
    } <= names
    db.close()


def test_branch_downgrade_and_reapply_keeps_tables_and_data(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])
    storage = SqliteChatStorage(db.engine)
    storage.conversations.save(make_conv())
    _q(storage, "a")
    db.downgrade_branch(BRANCH)
    assert db.revision("chat") is None
    assert storage.conversations.get("c1") is not None  # 테이블은 legacy 소유라 그대로
    assert [q.id for q in storage.queue.list()] == ["a"]
    db.upgrade([BRANCH])
    assert db.revision("chat") == "chat_0002"
    db.close()


def test_existing_0003_database_keeps_conversations_and_queue(tmp_path: Path) -> None:
    """3R.15 이전에 만든 DB(0003 + 대화·대기열 행)를 새 구성이 그대로 읽는다."""
    path = tmp_path / "old.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)
    conv = make_conv("c9", "g", 5.0, title="옛 대화")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO conversations (id, graph_id, archived, created_at, updated_at, doc) "
            "VALUES ('c9', 'g', 0, 1.0, 5.0, ?)",
            (conv.model_dump_json(),),
        )
        conn.exec_driver_sql(
            "INSERT INTO chat_queue (id, conversation_id, position, text, held, held_reason, "
            "created_at) VALUES ('q1', 'c9', 1, '남은 말', 1, 'restart', 2.0)"
        )
    engine.dispose()
    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    storage = SqliteChatStorage(db.engine)
    found = storage.conversations.get("c9")
    assert found is not None
    assert found.title == "옛 대화"
    [item] = storage.queue.list("c9")
    assert (item.id, item.held, item.held_reason, item.text) == ("q1", True, "restart", "남은 말")
    assert db.revision() == "0003"
    db.close()


def test_migration_scripts_are_package_data_and_work_after_copy(tmp_path: Path) -> None:
    """스크립트가 패키지 안에 있고, 폴더를 다른 곳에 복사해도 빈 DB에서 upgrade 된다(P9)."""
    assert BRANCH.versions.is_dir()
    assert list(BRANCH.versions.glob("chat_0001*.py"))
    copied = tmp_path / "elsewhere" / "versions"
    shutil.copytree(BRANCH.versions, copied, ignore=shutil.ignore_patterns("__pycache__"))
    db = SqliteDatabase.open(tmp_path / "empty.sqlite3")
    db.upgrade([type("B", (), {"name": "chat", "versions": copied})()])
    assert db.revision("chat") == "chat_0002"
    db.close()


# ---- 프로젝트 id (5.2R.32, chat_0002) --------------------------------------
def test_project_id_roundtrip_and_list_filter(storage: Any) -> None:
    repo = storage.conversations
    repo.save(make_conv("c1", updated_at=10.0, project_id="p1"))
    repo.save(make_conv("c2", updated_at=20.0, project_id="p2"))
    repo.save(make_conv("c3", updated_at=30.0, project_id="p1"))
    repo.save(make_conv("c4", updated_at=40.0))
    assert repo.get("c1").project_id == "p1"
    assert repo.get("c4").project_id is None
    assert [c.id for c in repo.list(project_id="p1")] == ["c3", "c1"]
    assert [c.id for c in repo.list(project_id="p2", archived=False)] == ["c2"]
    assert repo.list(project_id="none") == []
    assert [c.id for c in repo.list()] == ["c4", "c3", "c2", "c1"]  # 거르지 않으면 전부
    repo.save(make_conv("c1", updated_at=50.0, project_id="p9"))  # 옮겨진 대화(upsert)
    assert [c.id for c in repo.list(project_id="p1")] == ["c3"]


def test_project_filter_uses_the_index(tmp_path: Path) -> None:
    """색인 질의 계획(UX-D2): 프로젝트별 최근순 목록이 전체 훑기·임시 정렬 없이 색인을 쓴다."""
    db = SqliteDatabase.open(tmp_path / "plan.sqlite3")
    db.upgrade([BRANCH])
    with db.engine.connect() as conn:
        plan = " ".join(
            str(r[3])
            for r in conn.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT doc FROM conversations WHERE project_id = 'p' "
                "ORDER BY updated_at DESC, id DESC LIMIT 20"
            )
        )
    assert "ix_conversations_project_updated" in plan
    assert "SCAN conversations" not in plan.replace("USING INDEX", "")
    db.close()


def test_chat_0002_upgrade_keeps_old_rows_null_and_downgrade_only_drops_the_column(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)  # 5R까지의 모양(열 없음)
    conv = make_conv("c9", "g", 5.0, title="옛 대화")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO conversations (id, graph_id, archived, created_at, updated_at, doc) "
            "VALUES ('c9', 'g', 0, 1.0, 5.0, ?)",
            (conv.model_dump_json(),),
        )
    engine.dispose()
    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    storage = SqliteChatStorage(db.engine)
    assert db.revision("chat") == "chat_0002"
    old = storage.conversations.get("c9")
    assert old is not None
    assert old.project_id is None
    assert [c.id for c in storage.conversations.list()] == ["c9"]
    assert storage.conversations.list(project_id="p") == []
    storage.conversations.save(make_conv("c10", project_id="p"))

    db.downgrade_branch(BRANCH, "chat_0001")
    cols = {c["name"] for c in sa.inspect(db.engine).get_columns("conversations")}
    assert "project_id" not in cols
    assert "ix_conversations_project_updated" not in {
        i["name"] for i in sa.inspect(db.engine).get_indexes("conversations")
    }
    assert db.revision("chat") == "chat_0001"
    again = storage.conversations.get("c10")
    assert again is not None
    assert again.project_id == "p"  # doc에는 남는다

    db.upgrade([BRANCH])  # 다시 올리면 doc에서 열을 채운다
    assert [c.id for c in storage.conversations.list(project_id="p")] == ["c10"]
    db.close()
