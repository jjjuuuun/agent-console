"""FU.12 위키 검색 이벤트 검색어 해시: 주입한 해셔(솔트 HMAC 기본·sha256·끔)."""

from __future__ import annotations

import hashlib

from agent_console_contracts.wiki import WikiAccessConfig, WikiEventPayload
from agent_console_wiki import (
    QUERY_HASH_MODES,
    InMemoryWikiHistory,
    QueryHasher,
    WikiRepository,
    WikiToolkit,
    compile_syntax,
    effective_syntax,
    query_hasher,
    query_hasher_from_env,
)
from agent_console_wiki.testing import MemoryWikiPages

QUERY = "plan"
PLAIN = hashlib.sha256(QUERY.encode()).hexdigest()


def _access() -> WikiAccessConfig:
    return WikiAccessConfig.model_validate({"wikis": [{"wiki": "notes", "access": ["search"]}]})


async def _search_event(query_hash: QueryHasher | None) -> WikiEventPayload:
    repo = WikiRepository(
        MemoryWikiPages(),
        wiki_id="notes",
        syntax=compile_syntax(effective_syntax()),
        history=InMemoryWikiHistory(),
    )
    seen: list[WikiEventPayload] = []

    async def sink(_type: str, payload: WikiEventPayload) -> None:
        seen.append(payload)

    kit = WikiToolkit({"notes": repo}, access=_access(), on_event=sink, query_hash=query_hash)
    await kit.call("search", {"query": QUERY})
    return seen[-1]


def test_reexports_shared_hasher() -> None:
    assert set(QUERY_HASH_MODES) == {"hmac", "sha256", "off"}
    assert query_hasher_from_env("hmac", salt_env="S", environ={"S": "x"})(QUERY) == (
        query_hasher("hmac", salt=b"x")(QUERY)
    )


async def test_default_is_salted_not_plain_sha256() -> None:
    first = await _search_event(None)
    second = await _search_event(None)
    assert first.query_sha256 not in (None, PLAIN)
    assert first.query_sha256 != second.query_sha256  # 묶음마다 무작위 솔트
    assert first.query_chars == len(QUERY)


async def test_injected_hasher_modes() -> None:
    salted = query_hasher("hmac", salt=b"salt")
    assert (await _search_event(salted)).query_sha256 == salted(QUERY)
    assert (await _search_event(query_hasher("sha256"))).query_sha256 == PLAIN
    off = await _search_event(query_hasher("off"))
    assert off.query_sha256 is None
    assert "query_sha256" not in off.model_dump(exclude_none=True)
    assert off.query_chars == len(QUERY)


async def test_shared_hasher_gives_same_value_across_kits() -> None:
    shared = query_hasher()
    a = await _search_event(shared)
    b = await _search_event(shared)
    assert a.query_sha256 == b.query_sha256 != PLAIN
