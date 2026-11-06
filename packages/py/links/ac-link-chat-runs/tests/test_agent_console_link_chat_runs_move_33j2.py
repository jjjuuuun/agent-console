"""5.7R.33j2: 대화를 프로젝트 기록 DB로 옮기면 그 대화의 Run도 함께(대화 모듈은 Run을 모른다).

`mod-runs`의 `runs.move_hook`을 이 연동이 `chat.move_hooks`로 걸어 준다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    Conversation,
    NodeRun,
    RecordsMoveRequest,
    Run,
    RunEvent,
)
from agent_console_link_chat_runs import CHAT_MOVE_HOOKS, RUNS_MOVE, module
from agent_console_mod_chat import ConversationMover
from agent_console_mod_chat import module as chat_module
from agent_console_mod_chat.spaces import chat_records
from agent_console_mod_chat.storage import BRANCH as CHAT_BRANCH
from agent_console_mod_chat.storage import SqliteChatStorage
from agent_console_mod_runs import RECORDS_SPACES, RunMover, space_records
from agent_console_mod_runs import module as runs_module
from agent_console_mod_runs.storage import BRANCH as RUNS_BRANCH
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_runtime import Registries, load_registries
from agent_console_store import (
    RecordsDb,
    RecordsMove,
    RecordsUnavailable,
    SqliteDatabase,
    SqliteStorage,
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
        if space not in self.handles:
            folder = self.root / space.split(":", 1)[1]
            db = open_records_db(
                folder / "records.sqlite3", [CHAT_BRANCH, RUNS_BRANCH], backup_dir=folder / "b"
            )
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
    db.upgrade([CHAT_BRANCH, RUNS_BRANCH])
    yield db
    db.close()


def count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as c:
        return int(c.exec_driver_sql(f"select count(*) from {table}").scalar() or 0)


def seed(db: SqliteDatabase) -> None:
    """대화 c1(Run r1 + 자식 r1c, 이벤트), c2(실행 중인 Run r2), c3(Run 없음)."""
    chat = SqliteChatStorage(db.engine)
    runs = SqliteStorage(db.engine)
    for cid in ("c1", "c2", "c3"):
        chat.conversations.save(
            Conversation(id=cid, graph_id="g", created_at=1.0, updated_at=2.0, project_id="p1")
        )
        chat.queue.enqueue(f"q-{cid}", cid, "대기", created_at=1.0)
    for r in (
        Run(
            id="r1",
            graph_id="g",
            graph_version="h",
            status="completed",
            input={},
            origin="chat",
            created_at=3.0,
            conversation_id="c1",
            project_id="p1",
        ),
        Run(
            id="r1c",
            graph_id="g",
            graph_version="h",
            status="completed",
            input={},
            origin="api",
            created_at=4.0,
            parent_run_id="r1",
            root_run_id="r1",
            project_id="p1",
        ),
        Run(
            id="r2",
            graph_id="g",
            graph_version="h",
            status="running",
            input={},
            origin="chat",
            created_at=5.0,
            conversation_id="c2",
            project_id="p1",
        ),
    ):
        runs.runs.save(r)
        runs.runs.save_node_run(NodeRun(run_id=r.id, node_id="n1", status="succeeded"))
        runs.events.append(
            RunEvent(
                event_id=f"{r.id}-e1", run_id=r.id, seq=1, ts=1.0, type="log.info", node_path=["n1"]
            )
        )


def movers(db: SqliteDatabase, spaces: Spaces) -> tuple[ConversationMover, RunMover]:
    run_mover = RunMover(lambda: db.engine, space_records(lambda: spaces, prefix="project:"))
    chat_mover = ConversationMover(
        lambda: db.engine,
        chat_records(lambda: spaces, prefix="project:"),
        lambda: [run_mover.conversation_hook()],
    )
    return chat_mover, run_mover


def test_conversation_move_takes_its_runs_and_skips_running_conversation(
    app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(app_db)
    chat_mover, _ = movers(app_db, spaces)
    result = chat_mover.move(RecordsMoveRequest(project_id="p1", select="project"))
    assert result.moved == 2  # c1, c3 (c2는 실행 중인 Run이 있어 건너뜀)
    assert [(i.code, i.details["id"]) for i in result.failed] == [("conversation.move_busy", "c2")]
    out = spaces.open("project:p1").writable_engine()
    assert (count(out, "conversations"), count(out, "chat_queue")) == (2, 2)
    assert (count(out, "runs"), count(out, "node_runs"), count(out, "run_events")) == (2, 2, 2)
    assert SqliteStorage(out).runs.get("r1c") is not None
    # 원본에는 c2와 그 Run만 남는다
    assert (count(app_db.engine, "conversations"), count(app_db.engine, "runs")) == (1, 1)
    assert count(app_db.engine, "run_events") == 1
    again = chat_mover.move(RecordsMoveRequest(project_id="p1", select="project"))
    assert (again.moved, again.skipped) == (0, 0)  # 원본에서 지워졌으니 더 옮길 것이 없다
    assert (count(out, "runs"), count(out, "conversations")) == (2, 2)


def test_runs_failure_rolls_back_conversations(
    app_db: SqliteDatabase, spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(app_db)

    def bad(self: RecordsMove) -> None:
        if self._spec.table == "runs":
            raise RuntimeError("verify failed")

    monkeypatch.setattr(RecordsMove, "verify", bad)
    chat_mover, _ = movers(app_db, spaces)
    result = chat_mover.move(RecordsMoveRequest(project_id="p1", select="ids", ids=["c1"]))
    assert result.moved == 0
    out = spaces.open("project:p1").writable_engine()
    assert (count(out, "conversations"), count(out, "runs"), count(out, "run_events")) == (0, 0, 0)
    assert (count(app_db.engine, "conversations"), count(app_db.engine, "runs")) == (3, 3)


def _provider(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


def _client(tmp_path: Path, db: SqliteDatabase, spaces: Spaces | None, link: bool) -> TestClient:
    registries = Registries()
    load_registries(registries)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        database=db,
        registries=registries,
    )
    modules: list[Module] = [chat_module, runs_module, local_definitions_module()]
    if link:
        modules.append(module)
    if spaces is not None:
        modules.append(_provider("t-records", RECORDS_SPACES, spaces))
    assembly = assemble(modules, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_assembled_server_moves_conversation_and_its_runs(
    tmp_path: Path, app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(app_db)
    # 서버 시작 때 끝나지 않은 r2는 끊김 처리되어 c2도 옮겨진다
    with _client(tmp_path, app_db, spaces, link=True) as client:
        body = {"project_id": "p1", "select": "project"}
        moved = client.post(f"{API}/conversations/move-to-project", json=body)
        assert moved.status_code == 200, moved.text
        assert moved.json()["moved"] == 3
        ids = sorted(r["id"] for r in client.get(f"{API}/runs?project=p1").json())
        assert ids == ["r1", "r1c", "r2"]
        assert client.get(f"{API}/runs?project=p1&source=app").json() == []
        assert len(client.get(f"{API}/conversations?project=p1").json()) == 3


def test_without_link_only_conversations_move(
    tmp_path: Path, app_db: SqliteDatabase, spaces: Spaces
) -> None:
    seed(app_db)
    with _client(tmp_path, app_db, spaces, link=False) as client:
        body = {"project_id": "p1", "select": "ids", "ids": ["c1"]}
        assert client.post(f"{API}/conversations/move-to-project", json=body).json()["moved"] == 1
        assert client.get(f"{API}/runs?project=p1").json() == []  # Run은 건드리지 않는다
        assert len(client.get(f"{API}/runs?project=p1&source=app").json()) == 3
        runs = client.post(
            f"{API}/runs/move-to-project", json={"project_id": "p1", "select": "project"}
        )
        assert runs.json()["moved"] == 3  # Run은 따로 옮길 수 있다


def test_port_names_are_declared() -> None:
    assert (CHAT_MOVE_HOOKS.name, RUNS_MOVE.name) == ("chat.move_hooks", "runs.move_hook")
