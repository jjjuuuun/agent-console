"""6R.12(L-19·Q14): ``GET /conversations/page`` — 커서, 서버 ``?project=``, 폴더 → 앱 기록."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_console_chat import ChatService
from agent_console_chat.testing import MemoryGraphs
from agent_console_contracts import Conversation
from agent_console_mod_chat.errors import error_map
from agent_console_mod_chat.routes import build_router
from agent_console_mod_chat.spaces import SpacedChatService, chat_records
from agent_console_mod_chat.storage import InMemoryChatStorage, SqliteChatStorage
from agent_console_store import InvalidCursor

from .test_agent_console_mod_chat_records_33y2 import Spaces  # type: ignore[import-not-found]

API = "/api/v1"


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path)
    yield found
    for handle in found.handles.values():
        handle.close()


def _conv(cid: str, at: float, project: str | None = None) -> Conversation:
    return Conversation.model_validate(
        {"id": cid, "graph_id": "g", "created_at": 0.0, "updated_at": at, "project_id": project}
    )


def _setup(spaces: Spaces | None) -> tuple[TestClient, InMemoryChatStorage]:
    graphs = MemoryGraphs()
    host = InMemoryChatStorage()

    def make(conversations: Any, queue: Any, busy: Any) -> ChatService:
        return ChatService(conversations, graphs, queue=queue, busy_elsewhere=busy)

    service = SpacedChatService(
        host.conversations,
        graphs,
        queue=host.queue,
        records=chat_records(lambda: spaces, prefix="project:") if spaces else None,
        make=make,
    )
    app = FastAPI()
    app.include_router(build_router(lambda: service), prefix=API)
    return TestClient(app), host


def _collect(client: TestClient, query: str) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    sources: list[str] = []
    cursor: str | None = None
    for _ in range(200):
        url = f"{API}/conversations/page?{query}" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(url).json()
        ids += [c["id"] for c in body["items"]]
        sources.append(body["source"])
        cursor = body["next_cursor"]
        if cursor is None:
            return ids, sources
    raise AssertionError("끝나지 않았다")


def test_host_only_pages_and_server_project_filter() -> None:
    client, host = _setup(None)
    for i in range(13):
        host.conversations.save(_conv(f"c{i:02d}", float(i // 2), "pa" if i % 2 else None))
    ids, sources = _collect(client, "limit=4")
    assert ids == [c["id"] for c in client.get(f"{API}/conversations").json()]
    assert len(set(ids)) == 13
    assert set(sources) == {"project"}
    in_pa, _ = _collect(client, "limit=2&project=pa")
    assert in_pa == [c["id"] for c in client.get(f"{API}/conversations?project=pa").json()]


def test_folder_then_app_without_mixing(spaces: Spaces) -> None:
    client, host = _setup(spaces)
    folder = SqliteChatStorage(spaces.open("project:pa").db.writable_engine())
    for i in range(5):
        folder.conversations.save(_conv(f"f{i}", 10.0 + i))
    for i in range(3):
        host.conversations.save(_conv(f"a{i}", 100.0 + i, "pa"))  # 더 새 시각이어도 뒤에 온다
    host.conversations.save(_conv("x", 200.0, "pb"))
    ids, sources = _collect(client, "limit=2&project=pa")
    assert ids == ["f4", "f3", "f2", "f1", "f0", "a2", "a1", "a0"]
    assert sources == ["project", "project", "project", "app", "app"]
    direct, direct_sources = _collect(client, "project=pa&source=app")
    assert (direct, direct_sources) == (["a2", "a1", "a0"], ["app"])
    empty = client.get(f"{API}/conversations/page?project=pb").json()
    assert (empty["items"], empty["next_cursor"]) == ([], "app.")


def test_bad_cursor_maps_to_bad_request_and_old_route_deprecated() -> None:
    assert error_map("mod-chat")[InvalidCursor] == "bad_request"
    client, _ = _setup(None)
    with pytest.raises(InvalidCursor):  # 조립 없는 앱에는 오류 맵이 없다(호스트가 400으로 바꾼다)
        client.get(f"{API}/conversations/page?cursor=zzz")
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    assert paths[f"{API}/conversations"]["get"].get("deprecated") is True
    assert "deprecated" not in paths[f"{API}/conversations/page"]["get"]
