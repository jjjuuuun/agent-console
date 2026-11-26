"""P1.10(R15.9·R7): 33j2 기록 옮기기(대화·실행)는 위키 표를 건드리지 않는다.

위키 표는 `wiki_page_versions`·`wiki_blobs`다.
앱 DB와 프로젝트 기록 DB 양쪽에 위키 행을 넣고, 대화·실행을 옮긴 뒤 위키 행 수·내용이 양쪽 다
그대로인지 본다. 확인 실패(롤백) 경로에서도 같다. ac-store 테스트는 ac-wiki를 몰라야 하므로
두 쪽을 함께 아는 이 통합 테스트에 둔다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import Conversation, NodeRun, RecordsMoveRequest, Run
from agent_console_mod_chat import ConversationMover
from agent_console_mod_chat.spaces import chat_records
from agent_console_mod_chat.storage import BRANCH as CHAT_BRANCH
from agent_console_mod_chat.storage import SqliteChatStorage
from agent_console_mod_runs import RunMover, space_records
from agent_console_mod_runs.storage import BRANCH as RUNS_BRANCH
from agent_console_store import (
    MoveVerifyError,
    RecordsDb,
    RecordsMove,
    SqliteDatabase,
    SqliteStorage,
    open_records_db,
)
from agent_console_wiki.sqlite.schema import BLOBS_TABLE, VERSIONS_TABLE, metadata

WIKI_TABLES = (VERSIONS_TABLE, BLOBS_TABLE)
PROJECT = "p1"


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
                folder / "records.sqlite3",
                [CHAT_BRANCH, RUNS_BRANCH],
                backup_dir=folder / "backups",
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


def seed_wiki(engine: sa.Engine, tag: str) -> None:
    """위키 표를 만들고(없으면) 버전·본문 행을 넣는다. 값은 `tag`로 양쪽이 서로 다르다."""
    metadata.create_all(engine)
    with engine.begin() as c:
        for i in range(3):
            body = f"{tag}-본문-{i}".encode()
            sha = hashlib.sha256(body).hexdigest()
            c.exec_driver_sql(
                f"insert or ignore into {BLOBS_TABLE} (sha256, content) values (?, ?)", (sha, body)
            )
            c.exec_driver_sql(
                f"insert into {VERSIONS_TABLE} (wiki_id, path, version, op, sha256, bytes, at,"
                " author_json) values (?, ?, 1, 'create', ?, ?, 1.0, '{}')",
                (f"w-{tag}", f"page{i}.md", sha, len(body)),
            )


def wiki_snapshot(engine: sa.Engine) -> dict[str, list[tuple[Any, ...]]]:
    with engine.connect() as c:
        return {
            t: [tuple(r) for r in c.exec_driver_sql(f"select * from {t} order by 1")]
            for t in WIKI_TABLES
        }


def seed_records(engine: sa.Engine) -> None:
    chat = SqliteChatStorage(engine)
    for i in range(2):
        chat.conversations.save(
            Conversation(
                id=f"c{i}", graph_id="g", created_at=1.0, updated_at=2.0, project_id=PROJECT
            )
        )
    runs = SqliteStorage(engine)
    for rid in ("r1", "r2"):
        runs.runs.save(
            Run(
                id=rid,
                graph_id="g",
                graph_version="h",
                status="completed",
                input={"text": "hi"},
                origin="api",
                created_at=1.0,
                project_id=PROJECT,
            )
        )
        runs.runs.save_node_run(NodeRun(run_id=rid, node_id="n1", status="succeeded"))


def count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as c:
        return int(c.exec_driver_sql(f"select count(*) from {table}").scalar() or 0)


def setup(app_db: SqliteDatabase, spaces: Spaces) -> tuple[sa.Engine, sa.Engine]:
    seed_records(app_db.engine)
    target = spaces.open(f"project:{PROJECT}").writable_engine()
    seed_wiki(app_db.engine, "app")
    seed_wiki(target, "proj")
    return app_db.engine, target


def test_move_leaves_wiki_tables_untouched_on_both_sides(
    app_db: SqliteDatabase, spaces: Spaces
) -> None:
    source, target = setup(app_db, spaces)
    before = (wiki_snapshot(source), wiki_snapshot(target))
    assert all(len(rows) == 3 for snap in before for rows in snap.values())

    request = RecordsMoveRequest(project_id=PROJECT, select="project")
    chat = ConversationMover(lambda: source, chat_records(lambda: spaces, prefix="project:"))
    runs = RunMover(lambda: source, space_records(lambda: spaces, prefix="project:"))
    assert (chat.move(request).moved, runs.move(request).moved) == (2, 2)

    # 대화·실행은 옮겨졌다
    assert (count(source, "conversations"), count(source, "runs")) == (0, 0)
    assert (count(target, "conversations"), count(target, "runs")) == (2, 2)
    # 위키 행은 양쪽 모두 행 수·내용이 그대로다
    assert (wiki_snapshot(source), wiki_snapshot(target)) == before


def test_rollback_path_keeps_wiki_rows(app_db: SqliteDatabase, spaces: Spaces) -> None:
    source, target = setup(app_db, spaces)
    before = (wiki_snapshot(source), wiki_snapshot(target))

    class Failing(RecordsMove):
        def verify(self) -> None:
            raise MoveVerifyError("conversations", 1, 0)

    class Hook:
        def busy(self, ids: Any) -> set[str]:
            return set()

        def prepare(self, project_id: str, ids: Any) -> RecordsMove | None:
            from agent_console_store import MoveSpec

            return Failing(source, target, MoveSpec("conversations"), list(ids))

    chat = ConversationMover(
        lambda: source, chat_records(lambda: spaces, prefix="project:"), lambda: [Hook()]
    )
    result = chat.move(RecordsMoveRequest(project_id=PROJECT, select="project"))
    assert result.moved == 0
    assert len(result.failed) == 2  # 확인 실패 -> 되돌림

    # 되돌려져 대화는 원본에만 있고, 위키 행은 양쪽 그대로다
    assert (count(source, "conversations"), count(target, "conversations")) == (2, 0)
    assert (wiki_snapshot(source), wiki_snapshot(target)) == before
