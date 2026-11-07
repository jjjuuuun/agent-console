"""6R.12(L-19): ``ChatService.page`` — ``updated_at``·``id`` 내림차순 페이지, 끝까지 중복·누락 0."""

from __future__ import annotations

from agent_console_chat import ChatService
from agent_console_chat.testing import MemoryConversations, MemoryGraphs
from agent_console_contracts import Conversation


def _conv(cid: str, at: float, **kw: object) -> Conversation:
    return Conversation.model_validate(
        {"id": cid, "graph_id": "g", "created_at": 0.0, "updated_at": at, **kw}
    )


def _service() -> tuple[ChatService, MemoryConversations]:
    store = MemoryConversations()
    return ChatService(store, MemoryGraphs()), store


def test_pages_cover_everything_once_with_ties() -> None:
    service, store = _service()
    for i in range(23):
        store.save(_conv(f"c{i:02d}", float(i // 4), project_id="pa" if i % 3 else None))
    seen: list[str] = []
    after = None
    pages = 0
    while True:
        items, after = service.page(after=after, limit=5)
        pages += 1
        seen += [c.id for c in items]
        if after is None:
            break
    expected = [c.id for c in service.list()]
    assert seen == expected
    assert pages == 5
    assert len(set(seen)) == 23
    only, last = service.page(limit=100, project_id="pa")
    assert last is None
    assert [c.id for c in only] == [c.id for c in service.list(project_id="pa")]


def test_page_end_exact_and_filters() -> None:
    service, store = _service()
    store.save(_conv("a", 1.0))
    store.save(_conv("b", 2.0, archived=True))
    items, last = service.page(limit=2)
    assert ([c.id for c in items], last) == (["b", "a"], None)  # 딱 맞게 끝나면 None
    items, last = service.page(limit=1)
    assert ([c.id for c in items], last) == (["b"], (2.0, "b"))
    items, last = service.page(limit=1, archived=False)
    assert ([c.id for c in items], last) == (["a"], None)
    assert service.page(limit=0)[0] != []  # 1로 올린다


def test_page_title_query_6r19() -> None:
    """6R.19: ``query`` = 제목 부분 일치(``casefold``, 앞뒤 공백 무시), 커서와 함께."""
    service, store = _service()
    for i, title in enumerate(["Straße 계획", "", "STRASSE", "다른 것", "strasse 2"]):
        store.save(_conv(f"c{i}", float(i), title=title))
    seen: list[str] = []
    after = None
    while True:
        items, after = service.page(after=after, limit=1, query="  strasse ")
        seen += [c.id for c in items]
        if after is None:
            break
    assert seen == ["c4", "c2", "c0"]
    items, _ = service.page(limit=10, query="")
    assert len(items) == 5
    assert service.page(limit=10, query="계획")[0][0].id == "c0"
