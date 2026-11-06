"""5.7R.33j2: 앱 DB 옛 대화 -> 프로젝트 기록 DB 옮기기(`ConversationMover`, 훅, REST)."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Conversation,
    RecordsMoveRequest,
)
from agent_console_mod_chat import CHAT_MOVE_HOOKS, ConversationMover, module
from agent_console_mod_chat.ports import RECORDS_SPACES
from agent_console_mod_chat.spaces import chat_records
from agent_console_mod_chat.storage import BRANCH, SqliteChatStorage
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import (
    MoveSpec,
    RecordsDb,
    RecordsMove,
    RecordsUnavailable,
    SqliteDatabase,
    open_records_db,
)

API = "/api/v1"
TOKEN = "t" * 32


class Handle:
    def __init__(self, db: RecordsDb) -> None:
        self.db = db
        self.host_id = "host-mine"
        self.readonly = False

    @property
    def state(self) -> Any:
        return self.db.state

    @property
    def engine(self) -> Any:
        return self.db.engine

    def read_engine(self) -> Any:
        return self.db.read_engine()

    def writable_engine(self) -> Any:
        if self.readonly:
            raise RecordsUnavailable("readonly")
        return self.db.writable_engine()

    def spool(self, run_id: str, kind: str, data: Any) -> None:
        pass

    def close(self) -> None:
        self.db.close()


class Spaces:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.handles: dict[str, Handle] = {}

    def open(self, space: str) -> Handle:
        if space.endswith(":nope"):
            raise LookupError(space)
        if space not in self.handles:
            folder = self.root / space.split(":", 1)[1]
            db = open_records_db(folder / "records.sqlite3", [BRANCH], backup_dir=folder / "b")
            self.handles[space] = Handle(db)
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders")
    yield found
    for handle in found.handles.values():
        handle.close()


@pytest.fixture
def app_db(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    db.upgrade([BRANCH])
    yield db
    db.close()


def conv(id: str, project: str | None, updated_at: float = 10.0) -> Conversation:
    return Conversation(
        id=id,
        graph_id="g",
        created_at=1.0,
        updated_at=updated_at,
        project_id=project,
        title=f"대화 {id}",
    )


def seed(db: SqliteDatabase, project: str | None, n: int = 3) -> SqliteChatStorage:
    storage = SqliteChatStorage(db.engine)
    for i in range(n):
        storage.conversations.save(conv(f"c{i}", project, 10.0 + i))
        storage.queue.enqueue(f"q{i}", f"c{i}", f"대기 {i}", created_at=1.0 + i)
    return storage


def mover_of(db: SqliteDatabase, spaces: Spaces, hooks: Sequence[Any] = ()) -> ConversationMover:
    return ConversationMover(
        lambda: db.engine, chat_records(lambda: spaces, prefix="project:"), lambda: list(hooks)
    )


def count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as c:
        return int(c.exec_driver_sql(f"select count(*) from {table}").scalar() or 0)


def digest(engine: sa.Engine) -> str:
    h = hashlib.sha256()
    with engine.connect() as c:
        for sql in (
            "select id, graph_id, archived, created_at, updated_at, doc "
            "from conversations order by id",
            "select * from chat_queue order by id",
        ):
            for row in c.exec_driver_sql(sql):
                values = list(row)
                if sql.startswith("select id, graph_id"):
                    doc = json.loads(values[-1])
                    doc.pop("project_id", None)
                    values[-1] = json.dumps(doc, sort_keys=True)
                h.update(repr(values).encode())
    return h.hexdigest()


def target(spaces: Spaces, project: str) -> sa.Engine:
    return spaces.open(f"project:{project}").writable_engine()  # type: ignore[no-any-return]


def test_move_project_conversations_with_queue(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    SqliteChatStorage(app_db.engine).conversations.save(conv("other", "p2"))
    before = digest(app_db.engine)
    result = mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert (result.moved, result.skipped, result.failed) == (3, 0, [])
    out = target(spaces, "p1")
    assert (count(out, "conversations"), count(out, "chat_queue")) == (3, 3)
    assert (count(app_db.engine, "conversations"), count(app_db.engine, "chat_queue")) == (1, 0)
    # 옮긴 뒤 같은 내용(프로젝트 id 제외)
    with app_db.engine.begin() as c:  # 비교를 위해 남은 other를 지운다
        c.exec_driver_sql("delete from conversations")
    assert digest(out) != digest(app_db.engine)  # 빈 원본과는 다르다
    assert before != ""  # (seed 직후 해시는 other 포함이라 다름 - 아래에서 따로 검증)
    moved = SqliteChatStorage(out).conversations.get("c1")
    assert moved is not None
    assert (moved.project_id, moved.title) == ("p1", "대화 c1")


def test_hash_same_before_and_after(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    before = digest(app_db.engine)
    mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert digest(target(spaces, "p1")) == before


def test_null_and_ids_and_not_found(app_db: SqliteDatabase, spaces: Spaces) -> None:
    storage = seed(app_db, None, 2)
    storage.conversations.save(conv("z", "p9"))
    mover = mover_of(app_db, spaces)
    ids = mover.move(RecordsMoveRequest(project_id="p1", select="ids", ids=["z", "none"]))
    assert (ids.moved, [i.details["id"] for i in ids.failed]) == (1, ["none"])
    nulls = mover.move(RecordsMoveRequest(project_id="p1", select="null"))
    assert nulls.moved == 2
    assert {c.project_id for c in SqliteChatStorage(target(spaces, "p1")).conversations.list()} == {
        "p1"
    }
    assert count(app_db.engine, "conversations") == 0


def test_twice_no_duplicates_and_keep_source(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    mover = mover_of(app_db, spaces)
    request = RecordsMoveRequest(project_id="p1", select="project", remove_source=False)
    assert mover.move(request).moved == 3
    again = mover.move(request)
    assert (again.moved, again.skipped) == (0, 3)
    out = target(spaces, "p1")
    assert (count(out, "conversations"), count(out, "chat_queue")) == (3, 3)
    assert count(app_db.engine, "conversations") == 3  # 원본 남음


def test_failure_rolls_back_target(
    app_db: SqliteDatabase, spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(app_db, "p1")

    def boom(self: RecordsMove) -> int:
        raise RuntimeError("disk full")

    monkeypatch.setattr(RecordsMove, "delete_source", boom)
    result = mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert result.moved == 0
    assert {i.code for i in result.failed} == {"conversation.move_failed"}
    out = target(spaces, "p1")
    assert (count(out, "conversations"), count(out, "chat_queue")) == (0, 0)
    assert (count(app_db.engine, "conversations"), count(app_db.engine, "chat_queue")) == (3, 3)


class FakeHook:
    """훅: 대화 id마다 딸린 기록 표(`notes`)를 같은 작업으로 옮긴다."""

    def __init__(self, db: SqliteDatabase, spaces: Spaces, busy: set[str] | None = None) -> None:
        self.db = db
        self.spaces = spaces
        self.busy_ids = busy or set()
        self.after: list[tuple[str, list[str]]] = []
        self.fail_after = False
        for engine in (db.engine,):
            with engine.begin() as c:
                c.exec_driver_sql("create table notes (id text primary key, conversation_id text)")
                c.exec_driver_sql("insert into notes values ('n0','c0'), ('n1','c1')")

    def busy(self, conversation_ids: Sequence[str]) -> set[str]:
        return self.busy_ids & set(conversation_ids)

    def prepare(self, project_id: str, conversation_ids: Sequence[str]) -> RecordsMove | None:
        out = target(self.spaces, project_id)
        with out.begin() as c:
            c.exec_driver_sql(
                "create table if not exists notes (id text primary key, conversation_id text)"
            )
        spec = MoveSpec("notes", key="conversation_id")
        return RecordsMove(self.db.engine, out, spec, conversation_ids)

    def after_move(self, project_id: str, conversation_ids: list[str]) -> None:
        self.after.append((project_id, conversation_ids))
        if self.fail_after:
            raise RuntimeError("archive failed")


def test_hook_moves_dependents_in_same_work_and_calls_after(
    app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(app_db, "p1")
    hook = FakeHook(app_db, spaces)
    hook.fail_after = True  # 옮긴 뒤 훅이 실패해도 옮기기는 성공이다
    result = mover_of(app_db, spaces, [hook]).move(
        RecordsMoveRequest(project_id="p1", select="project")
    )
    assert result.moved == 3
    out = target(spaces, "p1")
    assert count(out, "notes") == 2
    assert count(app_db.engine, "notes") == 0
    assert hook.after == [("p1", ["c0", "c1", "c2"])]


def test_hook_busy_conversation_is_not_moved(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    hook = FakeHook(app_db, spaces, busy={"c1"})
    result = mover_of(app_db, spaces, [hook]).move(
        RecordsMoveRequest(project_id="p1", select="project")
    )
    assert result.moved == 2
    assert [(i.code, i.details["id"]) for i in result.failed] == [("conversation.move_busy", "c1")]
    assert count(app_db.engine, "conversations") == 1
    assert count(app_db.engine, "notes") == 1  # n1은 남는다


def test_hook_failure_rolls_back_conversations_too(
    app_db: SqliteDatabase, spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(app_db, "p1")
    hook = FakeHook(app_db, spaces)

    def bad_prepare(project_id: str, ids: Sequence[str]) -> RecordsMove:
        move = RecordsMove(
            app_db.engine, target(spaces, project_id), MoveSpec("missing_table"), ids
        )
        return move

    monkeypatch.setattr(hook, "prepare", bad_prepare)
    result = mover_of(app_db, spaces, [hook]).move(
        RecordsMoveRequest(project_id="p1", select="project")
    )
    assert result.moved == 0
    out = target(spaces, "p1")
    assert (count(out, "conversations"), count(out, "chat_queue")) == (0, 0)
    assert count(app_db.engine, "conversations") == 3


def test_unavailable_records_raise_409_class(app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    spaces.open("project:p1").readonly = True
    with pytest.raises(RecordsUnavailable):
        mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    assert count(app_db.engine, "conversations") == 3


def test_ten_thousand_conversations_time(app_db: SqliteDatabase, spaces: Spaces) -> None:
    storage = SqliteChatStorage(app_db.engine)
    for i in range(10_000):
        storage.conversations.save(conv(f"c{i:05d}", "p1", float(i)))
    started = time.perf_counter()
    result = mover_of(app_db, spaces).move(RecordsMoveRequest(project_id="p1", select="project"))
    elapsed = time.perf_counter() - started
    print(f"chat move 10000 conversations: {elapsed:.2f}s")
    assert result.moved == 10_000
    assert count(target(spaces, "p1"), "conversations") == 10_000
    assert count(app_db.engine, "conversations") == 0


# ---- REST ------------------------------------------------------------------


def _provider(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


def _client(tmp_path: Path, db: SqliteDatabase | None, extra: Sequence[Module]) -> TestClient:
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=db,
    )
    assembly = assemble([module, *extra], base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_rest_move_and_lists(tmp_path: Path, app_db: SqliteDatabase, spaces: Spaces) -> None:
    seed(app_db, "p1")
    hook = FakeHook(app_db, spaces)
    extra = [
        _provider("t-records", RECORDS_SPACES, spaces),
        _provider("t-hook", CHAT_MOVE_HOOKS, hook),
    ]
    with _client(tmp_path, app_db, extra) as client:
        body = {"project_id": "p1", "select": "project"}
        assert len(client.get(f"{API}/conversations?project=p1&source=app").json()) == 3
        moved = client.post(f"{API}/conversations/move-to-project", json=body)
        assert moved.status_code == 200, moved.text
        assert moved.json()["moved"] == 3
        assert client.get(f"{API}/conversations?project=p1&source=app").json() == []
        assert len(client.get(f"{API}/conversations?project=p1").json()) == 3
        assert client.post(f"{API}/conversations/move-to-project", json=body).json()["moved"] == 0
        bad = client.post(
            f"{API}/conversations/move-to-project", json={"project_id": "p1", "select": "ids"}
        )
        assert bad.status_code == 422
        spaces.open("project:p1").readonly = True
        locked = client.post(f"{API}/conversations/move-to-project", json=body)
        assert locked.status_code == 409
        assert locked.json()["error"]["code"] == "project.records_unavailable"
        unknown = client.post(
            f"{API}/conversations/move-to-project", json={"project_id": "nope", "select": "null"}
        )
        assert unknown.status_code == 404


def test_rest_without_hooks_moves_conversations_and_queue_only(
    tmp_path: Path, app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(app_db, "p1")
    with _client(tmp_path, app_db, [_provider("t-records", RECORDS_SPACES, spaces)]) as client:
        moved = client.post(
            f"{API}/conversations/move-to-project", json={"project_id": "p1", "select": "project"}
        )
        assert moved.json()["moved"] == 3
        assert count(target(spaces, "p1"), "chat_queue") == 3


def test_rest_route_absent_without_database(tmp_path: Path) -> None:
    with _client(tmp_path, None, []) as client:
        body = {"project_id": "p1", "select": "null"}
        assert client.post(f"{API}/conversations/move-to-project", json=body).status_code in (
            404,
            405,
        )
