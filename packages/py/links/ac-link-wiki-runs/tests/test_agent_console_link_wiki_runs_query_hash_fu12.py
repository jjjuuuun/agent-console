"""FU.12 위키 도구 검색어 해시: 서비스 해셔(설치자 설정) → 없으면 범위 하나의 무작위 솔트 해셔."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from agent_console_contracts import BackendCapabilities, ResourceBundle
from agent_console_link_wiki_runs import (
    QueryHashSource,
    WikiRunScope,
    WikiToolProvider,
    load_wiki_resource_type,
    service_query_hash,
    wiki_slot,
)
from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
from agent_console_nodes_core import TOOL_PROVIDERS, ToolProvisionContext
from agent_console_runtime import CancelToken, Services
from agent_console_wiki import QueryHasher, query_hasher

SLOT = wiki_slot(load_wiki_resource_type())
QUERY = "plan"
PLAIN = hashlib.sha256(QUERY.encode()).hexdigest()


class HashingService(StaticWikiService):
    """``query_hash``가 있는 위키 서비스(``mod-wiki`` ``WikiService`` 모양)."""

    def __init__(self, hasher: QueryHasher) -> None:
        super().__init__({None: {"notes": memory_repository("notes")}})
        self._hasher = hasher

    @property
    def query_hash(self) -> QueryHasher:
        return self._hasher


def _search_hash(provider: WikiToolProvider) -> Any:
    emitted: list[dict[str, Any]] = []

    async def emit(_type: str, payload: Any) -> None:
        emitted.append(dict(payload))

    ctx = ToolProvisionContext(
        run_id="r1",
        root_run_id="r1",
        graph_id="g",
        node_id="n",
        node_path=["n"],
        agent_id="a",
        call=0,
        iteration=0,
        bundle=ResourceBundle(
            slots={
                SLOT: [
                    {
                        "resource": "r",
                        "layer": "agent",
                        "config": {"wikis": [{"wiki": "notes", "access": ["search"]}]},
                    }
                ]
            }
        ),
        backend_capabilities=BackendCapabilities(host_tools=True),
        emit=emit,
        cancel=CancelToken(),
    )
    [tool] = provider.provide(ctx).host_tools

    async def go() -> None:
        await tool.handler({"query": QUERY})

    asyncio.run(go())
    [payload] = emitted
    assert payload["query_chars"] == len(QUERY)
    assert QUERY not in str(payload)
    return payload.get("query_sha256")


def test_service_query_hash_reads_optional_attribute() -> None:
    hasher = query_hasher("hmac", salt=b"s")
    with_hash = HashingService(hasher)
    assert isinstance(with_hash, QueryHashSource)
    assert service_query_hash(with_hash) is hasher
    plain_service = StaticWikiService({None: {}})
    assert not isinstance(plain_service, QueryHashSource)
    assert service_query_hash(plain_service) is None

    class NotCallable:
        query_hash = "nope"

    assert service_query_hash(NotCallable()) is None


def test_service_hasher_wins_over_provider_fallback() -> None:
    salted = query_hasher("hmac", salt=b"salt")
    service = HashingService(salted)
    provider = WikiToolProvider(lambda: service, slot=SLOT, query_hash=query_hasher("sha256"))
    assert _search_hash(provider) == salted(QUERY)
    off = HashingService(query_hasher("off"))
    assert _search_hash(WikiToolProvider(lambda: off, slot=SLOT)) is None


def test_scope_fallback_is_salted_and_shared_across_runs() -> None:
    service = StaticWikiService({None: {"notes": memory_repository("notes")}})
    scope = WikiRunScope(lambda: service, slot=SLOT)
    graph: Any = None
    first = scope.scope_run(graph, Services({}), project_id=None)
    second = scope.scope_run(graph, Services({}), project_id=None)
    assert first is not None
    assert second is not None
    a = _search_hash(first.services[TOOL_PROVIDERS][-1])
    b = _search_hash(second.services[TOOL_PROVIDERS][-1])
    assert a == b
    assert a not in (None, PLAIN)
    other_scope = WikiRunScope(lambda: service, slot=SLOT)
    assert _search_hash(other_scope.provider_for(None)) != a


def test_scope_passes_given_hasher() -> None:
    service = StaticWikiService({None: {"notes": memory_repository("notes")}})
    scope = WikiRunScope(lambda: service, slot=SLOT, query_hash=query_hasher("sha256"))
    assert _search_hash(scope.provider_for(None)) == PLAIN
