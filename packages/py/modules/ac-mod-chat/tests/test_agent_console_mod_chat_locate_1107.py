"""요청 11/07 후속: 대화 위치 찾기(``GET /conversations/{id}/locate``)와 WS ``conversation:<id>``.

- 주소로 바로 연 대화(아직 이 프로세스에서 열지 않은 프로젝트 기록 DB)의 등록 id를 알려 준다.
  앱 기록(호스트 DB)이면 null, 없으면 404, 여러 공간이면 409 ``conversation.ambiguous``.
- 상세 ``GET /conversations/{id}``는 ``?project=`` 없이 다른 공간을 대신 읽지 않는다(범위 고정).
- 등록 프로젝트 수 상한(``locate_max_projects``)을 넘는 공간은 읽지 않고, 기록 DB 파일을
  만들지 않는다.
- WS 구독은 열지 않은 프로젝트 기록 DB의 대화도 찾아 요약을 보내고, 이후 바뀐 요약도 보낸다.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_chat import ChatService, ConversationNotFoundError
from agent_console_chat.testing import MemoryGraphs
from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, Conversation
from agent_console_mod_chat import module
from agent_console_mod_chat.ports import PROJECTS_LOOKUP, RECORDS_SPACES
from agent_console_mod_chat.spaces import (
    ConversationAmbiguousError,
    SpacedChatService,
    chat_records,
)
from agent_console_mod_chat.storage import BRANCH, InMemoryChatStorage, SqliteChatStorage
from agent_console_modkit import BaseServices, Module, ModuleContext, ModuleParts, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import RecordsDb, SqliteDatabase, open_records_db

API = "/api/v1"
TOKEN = "t" * 32


class Handle:
    def __init__(self, db: RecordsDb) -> None:
        self.db = db
        self.host_id = "host-mine"

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
    """``project:<id>`` → 폴더 기록 DB. 등록되지 않은 id는 ``LookupError``(실제 풀과 같다)."""

    def __init__(self, root: Path, registered: Sequence[str]) -> None:
        self.root = root
        self.registered = set(registered)
        self.handles: dict[str, Handle] = {}
        self.opened: list[str] = []

    def open(self, space: str) -> Handle:
        project_id = space.split(":", 1)[1]
        if project_id not in self.registered:
            raise LookupError(space)
        self.opened.append(project_id)
        if space not in self.handles:
            folder = self.root / project_id
            db = open_records_db(folder / "records.sqlite3", [BRANCH], backup_dir=folder / "b")
            self.handles[space] = Handle(db)
        return self.handles[space]

    def state(self, space: str) -> Any:
        return self.open(space).state

    def close(self, space: str) -> None:
        pass

    def file(self, project_id: str) -> Path:
        return self.root / project_id / "records.sqlite3"


class Listing:
    """``projects.lookup`` 가짜(``list_projects`` 항목의 ``id``만)."""

    def __init__(self, ids: Sequence[str]) -> None:
        self.ids = list(ids)
        self.calls = 0

    def list_projects(self) -> list[Any]:
        self.calls += 1
        return [SimpleNamespace(id=i) for i in self.ids]


IDS = ("pa", "pb", "pc")


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path / "folders", IDS)
    yield found
    for handle in found.handles.values():
        handle.close()


def _conv(conversation_id: str, project_id: str | None) -> Conversation:
    return Conversation(
        id=conversation_id, graph_id="g", created_at=1.0, updated_at=1.0, project_id=project_id
    )


def _seed(spaces: Spaces, project_id: str, conversation_id: str) -> None:
    """이전 프로세스가 그 프로젝트 기록 DB에 남긴 대화(이 프로세스는 아직 공간을 열지 않음)."""
    engine = spaces.open(f"project:{project_id}").writable_engine()
    SqliteChatStorage(engine).conversations.save(_conv(conversation_id, project_id))
    spaces.opened.clear()


def _service(
    spaces: Spaces, ids: Sequence[str] | None = IDS, limit: int = 200
) -> tuple[SpacedChatService, InMemoryChatStorage]:
    graphs = MemoryGraphs()
    host = InMemoryChatStorage()

    def make(conversations: Any, queue: Any, busy: Any) -> ChatService:
        return ChatService(conversations, graphs, queue=queue, busy_elsewhere=busy)

    service = SpacedChatService(
        host.conversations,
        graphs,
        queue=host.queue,
        records=chat_records(lambda: spaces, prefix="project:"),
        make=make,
        project_ids=(lambda: list(ids)) if ids is not None else None,
        locate_limit=limit,
    )
    return service, host


# ---- 서비스 ----------------------------------------------------------------


def test_locate_finds_unopened_project_and_host(spaces: Spaces) -> None:
    _seed(spaces, "pb", "c1")
    service, host = _service(spaces)
    host.conversations.save(_conv("c-app", None))
    assert service.locate("c1") == "pb"
    assert service.spaces() == {}  # 찾기만으로 공간 서비스를 열지 않는다
    assert service.locate("c-app") is None
    with pytest.raises(ConversationNotFoundError):
        service.locate("nope")
    # 기록 DB가 없는 프로젝트는 읽기만 하고 파일을 만들지 않는다
    assert not spaces.file("pa").exists()
    assert not spaces.file("pc").exists()


def test_locate_remembers_place_and_rechecks_it(spaces: Spaces) -> None:
    _seed(spaces, "pc", "c1")
    service, _ = _service(spaces)
    assert service.locate("c1") == "pc"
    spaces.opened.clear()
    assert service.locate("c1") == "pc"
    assert spaces.opened == ["pc"]  # 기억한 자리만 다시 본다
    SqliteChatStorage(spaces.open("project:pc").writable_engine()).conversations.delete("c1")
    with pytest.raises(ConversationNotFoundError):
        service.locate("c1")  # 지워졌으면 다시 찾고, 없으면 404


def test_locate_ambiguous_lists_places(spaces: Spaces) -> None:
    _seed(spaces, "pa", "dup")
    _seed(spaces, "pc", "dup")
    service, host = _service(spaces)
    host.conversations.save(_conv("dup", None))
    with pytest.raises(ConversationAmbiguousError) as caught:
        service.locate("dup")
    assert caught.value.code == "conversation.ambiguous"
    assert caught.value.details["project_ids"] == ["pa", "pc", None]


def test_locate_respects_limit_and_missing_listing(spaces: Spaces) -> None:
    _seed(spaces, "pc", "c1")
    limited, _ = _service(spaces, limit=2)
    with pytest.raises(ConversationNotFoundError):
        limited.locate("c1")  # 앞의 2개(pa, pb)만 읽는다
    none, _ = _service(spaces, limit=0)
    with pytest.raises(ConversationNotFoundError):
        none.locate("c1")
    unlisted, _ = _service(spaces, ids=None)
    with pytest.raises(ConversationNotFoundError):
        unlisted.locate("c1")  # 목록이 없으면 연 공간과 호스트만
    unlisted.for_project("pc")  # 연 공간은 목록 없이도 본다
    assert unlisted.locate("c1") == "pc"


def test_locate_skips_unregistered_ids(spaces: Spaces) -> None:
    _seed(spaces, "pb", "c1")
    service, _ = _service(spaces, ids=["gone", "pb"])
    assert service.locate("c1") == "pb"


def test_service_of_finds_unopened_space(spaces: Spaces) -> None:
    _seed(spaces, "pb", "c1")
    service, _ = _service(spaces)
    owner = service.service_of("c1")
    assert owner is service.for_project("pb")
    assert owner.get("c1").project_id == "pb"
    assert service.service_of("nope") is service


# ---- REST·WS(모듈 조립) ----------------------------------------------------


def _provider(module_id: str, port: Any, item: object) -> Module:
    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(port, item)
        return ModuleParts()

    return fake_module(module_id, kind="link", provides=[port], on_build=build)


def _client(tmp_path: Path, extra: Sequence[Module], db: SqliteDatabase | None) -> TestClient:
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


@pytest.fixture
def app_db(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "app.sqlite3")
    db.upgrade([BRANCH])
    yield db
    db.close()


def test_rest_locate(tmp_path: Path, spaces: Spaces, app_db: SqliteDatabase) -> None:
    _seed(spaces, "pb", "c1")
    _seed(spaces, "pa", "dup")
    _seed(spaces, "pc", "dup")
    SqliteChatStorage(app_db.engine).conversations.save(_conv("c-app", None))
    listing = Listing(IDS)
    extra = [
        _provider("t-records", RECORDS_SPACES, spaces),
        _provider("t-projects", PROJECTS_LOOKUP, listing),
    ]
    with _client(tmp_path, extra, app_db) as client:
        found = client.get(f"{API}/conversations/c1/locate")
        assert found.status_code == 200, found.text
        assert found.json() == {"project_id": "pb"}
        # 상세는 ?project= 없이 다른 공간을 대신 읽지 않는다(범위 고정), 찾은 값을 붙이면 읽힌다
        assert client.get(f"{API}/conversations/c1").status_code == 404
        detail = client.get(f"{API}/conversations/c1", params={"project": "pb"})
        assert detail.status_code == 200
        assert detail.json()["project_id"] == "pb"
        assert client.get(f"{API}/conversations/c-app/locate").json() == {"project_id": None}
        missing = client.get(f"{API}/conversations/nope/locate")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
        ambiguous = client.get(f"{API}/conversations/dup/locate")
        assert ambiguous.status_code == 409
        body = ambiguous.json()["error"]
        assert body["code"] == "conversation.ambiguous"
        assert body["details"]["project_ids"] == ["pa", "pc"]


def test_rest_locate_without_records_port_is_host_only(
    tmp_path: Path, app_db: SqliteDatabase
) -> None:
    SqliteChatStorage(app_db.engine).conversations.save(_conv("c-app", "p1"))
    extra = [_provider("t-projects", PROJECTS_LOOKUP, Listing(["p1"]))]
    with _client(tmp_path, extra, app_db) as client:
        assert client.get(f"{API}/conversations/c-app/locate").json() == {"project_id": None}
        assert client.get(f"{API}/conversations/nope/locate").status_code == 404


def test_ws_subscribe_finds_project_records_conversation(
    tmp_path: Path, spaces: Spaces, app_db: SqliteDatabase
) -> None:
    """재시작 직후(공간을 아직 열지 않음) ``conversation:<id>`` 구독이 그 기록 DB 대화를 찾고,
    이후 그 공간 서비스의 변경(제목 바꾸기)도 받는다."""
    _seed(spaces, "pb", "c1")
    extra = [
        _provider("t-records", RECORDS_SPACES, spaces),
        _provider("t-projects", PROJECTS_LOOKUP, Listing(IDS)),
    ]
    with (
        _client(tmp_path, extra, app_db) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:c1"}})
        first = ws.receive_json()
        assert first["type"] == "conversation.updated", first
        assert first["payload"]["conversation"]["id"] == "c1"
        assert first["payload"]["conversation"]["project_id"] == "pb"
        patched = client.patch(
            f"{API}/conversations/c1", params={"project": "pb"}, json={"title": "새 제목"}
        )
        assert patched.status_code == 200, patched.text
        second = ws.receive_json()
        assert second["type"] == "conversation.updated"
        assert second["payload"]["conversation"]["title"] == "새 제목"
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:nope"}})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "not_found"


def test_ws_without_projects_port_still_finds_opened_space(
    tmp_path: Path, spaces: Spaces, app_db: SqliteDatabase
) -> None:
    """``projects.lookup``가 없으면 REST ``?project=``로 연 공간의 대화만 찾는다(지금 동작)."""
    _seed(spaces, "pb", "c1")
    extra = [_provider("t-records", RECORDS_SPACES, spaces)]
    with (
        _client(tmp_path, extra, app_db) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as ws,
    ):
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:c1"}})
        assert ws.receive_json()["type"] == "error"
        assert client.get(f"{API}/conversations/c1", params={"project": "pb"}).status_code == 200
        ws.send_json({"type": "subscribe", "payload": {"topic": "conversation:c1"}})
        assert ws.receive_json()["type"] == "conversation.updated"
