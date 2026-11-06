"""5.7R.33y2: 프로젝트 대화·대기열을 그 기록 DB에, 대기열 ``host_id``(두 앱이 같은 DB를 쓸 때)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agent_console_chat import ChatService
from agent_console_chat.testing import MemoryGraphs
from agent_console_contracts import CreateConversationRequest
from agent_console_mod_chat.spaces import SpacedChatService, chat_records
from agent_console_mod_chat.storage import (
    BRANCH,
    InMemoryChatStorage,
    SqliteChatStorage,
    SqliteQueueRepository,
)
from agent_console_store import (
    RecordsDb,
    RecordsUnavailable,
    SqliteDatabase,
    open_records_db,
)


class Handle:
    def __init__(self, db: RecordsDb, host_id: str) -> None:
        self.db = db
        self.host_id = host_id
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
            db = open_records_db(folder / "records.sqlite3", [BRANCH], backup_dir=folder / "b")
            self.handles[space] = Handle(db, "host-mine")
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path)
    yield found
    for handle in found.handles.values():
        handle.close()


def _queue(tmp_path: Path, host_id: str | None) -> SqliteQueueRepository:
    db = SqliteDatabase.open(tmp_path / "q.sqlite3")
    db.upgrade([BRANCH])
    return SqliteQueueRepository(db.engine, host_id=host_id)


def test_queue_hides_other_host_items_and_release_takes_them(tmp_path: Path) -> None:
    other = _queue(tmp_path, "host-other")
    other.enqueue("o1", "c1", "남의 것", created_at=1.0)
    mine = SqliteQueueRepository(other._engine, host_id="host-mine")
    mine.enqueue("m1", "c1", "내 것", created_at=2.0)
    got = {i.id: (i.held, i.held_reason, i.host_id) for i in mine.list("c1")}
    assert got == {"o1": (True, "other_host", "host-other"), "m1": (False, None, "host-mine")}
    assert mine.counts()["c1"].held == 1
    assert mine.pop_next("c1") is None  # 맨 앞이 남의 항목이면 꺼내지 않는다(순서 유지)
    assert mine.hold_all("restart") == 1  # 자기 항목만 멈춘다
    theirs = other.get("o1")
    assert theirs is not None
    assert not theirs.held
    released = mine.release("o1")
    assert (released.held, released.host_id) == (False, "host-mine")
    assert mine.clear("c1") == 2
    assert mine.list("c1") == []


def test_queue_without_host_id_keeps_old_behavior(tmp_path: Path) -> None:
    queue = _queue(tmp_path, None)
    queue.enqueue("a", "c1", "x", created_at=1.0)
    item = queue.get("a")
    assert item is not None
    assert item.host_id is None
    assert not item.held


def _service(spaces: Spaces | None) -> SpacedChatService:
    graphs = MemoryGraphs()
    host = InMemoryChatStorage()

    def make(conversations: Any, queue: Any, busy: Any) -> ChatService:
        return ChatService(conversations, graphs, queue=queue, busy_elsewhere=busy)

    return SpacedChatService(
        host.conversations,
        graphs,
        queue=host.queue,
        records=chat_records(lambda: spaces, prefix="project:") if spaces else None,
        make=make,
    )


def test_spaced_service_writes_project_conversation_to_records_db(
    spaces: Spaces, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(spaces)
    space = service.for_project("pa")
    assert space is not service
    assert service.for_project("pa") is space
    assert service.for_project(None) is service
    monkeypatch.setattr(space, "_require_graph", lambda *a, **k: None)
    created = space.create(CreateConversationRequest(graph_id="g", project_id="pa", title="t"))
    assert service.list() == []  # 호스트에는 없다
    assert [c.id for c in space.list()] == [created.id]
    assert service.service_of(created.id) is space
    stored = SqliteChatStorage(spaces.open("project:pa").db.engine)
    assert [c.id for c in stored.conversations.list()] == [created.id]
    assert not (tmp_path / "pb" / "records.sqlite3").exists()
    assert service.for_project("pb").list() == []  # 보기만으로 파일을 만들지 않는다
    assert not (tmp_path / "pb" / "records.sqlite3").exists()


def test_readonly_space_refuses_new_conversation(
    spaces: Spaces, monkeypatch: pytest.MonkeyPatch
) -> None:
    spaces.open("project:ro").readonly = True
    service = _service(spaces)
    space = service.for_project("ro")
    monkeypatch.setattr(space, "_require_graph", lambda *a, **k: None)
    with pytest.raises(RecordsUnavailable) as caught:
        space.create(CreateConversationRequest(graph_id="g", project_id="ro"))
    assert caught.value.details() == {"reason": "readonly", "project_id": "ro"}


def test_without_port_for_project_is_host() -> None:
    service = _service(None)
    assert service.for_project("pa") is service
    assert not service.spaced
