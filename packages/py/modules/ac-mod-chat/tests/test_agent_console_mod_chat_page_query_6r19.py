"""6R.19 잔여: ``GET /conversations/page?q=`` — 대화 제목 부분 일치(대소문자 무시).

- 커서로 이어 붙여도 조건이 유지되고, 폴더 기록 → 앱 DB 옛 기록 잇기에도 같은 조건이 걸린다.
- 빈 검색어는 거르지 않고, 길이 상한을 넘으면 422.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest

from agent_console_contracts import Conversation
from agent_console_mod_chat.routes import MAX_CONVERSATION_QUERY_LENGTH
from agent_console_mod_chat.storage import SqliteChatStorage

from .test_agent_console_mod_chat_page_6r12 import (  # type: ignore[import-not-found]
    API,
    _collect,
    _setup,
)
from .test_agent_console_mod_chat_records_33y2 import Spaces  # type: ignore[import-not-found]


@pytest.fixture
def spaces(tmp_path: Path) -> Iterator[Spaces]:
    found = Spaces(tmp_path)
    yield found
    for handle in found.handles.values():
        handle.close()


def _conv(cid: str, at: float, title: str, project: str | None = None) -> Conversation:
    return Conversation.model_validate(
        {
            "id": cid, "graph_id": "g", "title": title, "created_at": 0.0, "updated_at": at,
            "project_id": project,
        }
    )  # fmt: skip


def test_title_query_with_cursor() -> None:
    client, host = _setup(None)
    titles = ["Login 버그", "결제 화면", "LOGIN 다시", "", "100% 완료", "loginless"]
    for i, title in enumerate(titles):
        host.conversations.save(_conv(f"c{i}", float(i), title))
    assert _collect(client, "limit=1&q=login")[0] == ["c5", "c2", "c0"]
    assert _collect(client, f"limit=1&q={quote('  LoGiN ')}")[0] == ["c5", "c2", "c0"]
    assert _collect(client, f"limit=1&q={quote('결제')}")[0] == ["c1"]
    assert _collect(client, f"limit=1&q={quote('0%')}")[0] == ["c4"]
    assert _collect(client, "limit=1&q=c1")[0] == []  # 제목만 본다(id는 아님)
    assert _collect(client, "limit=2&q=")[0] == ["c5", "c4", "c3", "c2", "c1", "c0"]


def test_query_length_limit() -> None:
    client, _ = _setup(None)
    ok = client.get(f"{API}/conversations/page?q={'a' * MAX_CONVERSATION_QUERY_LENGTH}")
    assert ok.status_code == 200
    bad = client.get(f"{API}/conversations/page?q={'a' * (MAX_CONVERSATION_QUERY_LENGTH + 1)}")
    assert bad.status_code == 422


def test_folder_then_app_with_query(spaces: Spaces) -> None:
    client, host = _setup(spaces)
    folder = SqliteChatStorage(spaces.open("project:pa").db.writable_engine())
    for i in range(4):
        folder.conversations.save(_conv(f"f{i}", 10.0 + i, "plan" if i % 2 else "other"))
    host.conversations.save(_conv("a0", 100.0, "Old PLAN", "pa"))
    host.conversations.save(_conv("a1", 101.0, "old other", "pa"))
    ids, sources = _collect(client, "limit=1&project=pa&q=plan")
    assert ids == ["f3", "f1", "a0"]
    assert sources == ["project", "project", "app"]
    # 옛 기록에도 맞는 대화가 있으면 앱 기록으로 잇고, 없으면 폴더 기록 끝에서 멈춘다
    body = client.get(f"{API}/conversations/page?project=pa&q=other&limit=5").json()
    assert [c["id"] for c in body["items"]] == ["f2", "f0"]
    assert body["next_cursor"] == "app."
    host.conversations.delete("a1")
    body = client.get(f"{API}/conversations/page?project=pa&q=other&limit=5").json()
    assert body["next_cursor"] is None
    assert _collect(client, "project=pa&q=nothing")[0] == []
