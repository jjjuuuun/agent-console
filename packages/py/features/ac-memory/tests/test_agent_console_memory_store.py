"""메모리 저장소(X31): 메모리 구현이 공용 계약 묶음을 통과한다."""

from __future__ import annotations

from agent_console_memory import InMemoryMemoryStore, MemoryPolicy, MemoryStore
from agent_console_memory.testing import FakeClock
from agent_console_memory.testing.contract import MemoryStoreContractTests


class TestInMemoryStore(MemoryStoreContractTests):
    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:
        return InMemoryMemoryStore(policy=policy, clock=clock or FakeClock())


def test_in_memory_store_satisfies_protocol() -> None:
    assert isinstance(InMemoryMemoryStore(), MemoryStore)


def test_default_ids_are_unique_uuid() -> None:
    from agent_console_contracts.memory import MemoryScopeRef
    from agent_console_memory.testing import user_author

    store = InMemoryMemoryStore()
    scope = MemoryScopeRef(kind="k", id="")
    ids = {store.write(scope, f"k{i}", "x", author=user_author()).entry.id for i in range(20)}
    assert len(ids) == 20
    assert all(len(i) == 36 for i in ids)
