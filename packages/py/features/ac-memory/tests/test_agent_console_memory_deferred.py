"""처음 쓸 때 여는 저장소 `DeferredMemoryStore`: 계약 묶음(메모리·SQLite 파일), 읽기만으로 열지
않음, 있는 저장소는 읽기에도 엶, 정책 전달, 닫은 뒤 새로 열지 않음."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_contracts.memory import MemoryScopeRef
from agent_console_memory import (
    DeferredMemoryStore,
    EntryNotFoundError,
    EntryScanner,
    InMemoryMemoryStore,
    MemoryPolicy,
    MemoryQuery,
    MemoryStore,
    TagCounter,
)
from agent_console_memory.testing import FakeClock, user_author
from agent_console_memory.testing.contract import MemoryStoreContractTests

SCOPE = MemoryScopeRef(kind="k", id="a")


class TestDeferredInMemory(MemoryStoreContractTests):
    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:
        made: list[MemoryStore] = []

        def opener() -> MemoryStore:
            made.append(InMemoryMemoryStore(policy=policy, clock=clock or FakeClock()))
            return made[0]

        return DeferredMemoryStore(opener, exists=lambda: bool(made), policy=policy)


class _Opener:
    def __init__(self, tmp_path: Path) -> None:
        self.path = tmp_path / "space" / "memory.sqlite3"
        self.calls = 0

    def __call__(self) -> MemoryStore:
        from agent_console_memory.sqlite import open_sqlite_memory_store

        self.calls += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return open_sqlite_memory_store(self.path)

    def exists(self) -> bool:
        return self.path.is_file()


def test_reads_do_not_open_or_create_the_file(tmp_path: Path) -> None:
    pytest.importorskip("sqlalchemy")
    opener = _Opener(tmp_path)
    store = DeferredMemoryStore(opener, exists=opener.exists)
    assert isinstance(store, MemoryStore)
    assert isinstance(store, EntryScanner)
    assert isinstance(store, TagCounter)
    assert store.search(MemoryQuery()).items == []
    assert store.list_scopes() == []
    assert store.get("x") is None
    assert store.find(SCOPE, "a") is None
    assert store.count_tags() == {}
    assert list(store.scan_entries()) == []
    assert store.get_version("x", 1) is None
    for call in (
        lambda: store.update("x", author=user_author(), content="y"),
        lambda: store.delete("x", author=user_author()),
        lambda: store.purge("x"),
        lambda: store.history("x"),
        lambda: store.move("x", author=user_author(), to_key="b"),
    ):
        with pytest.raises(EntryNotFoundError):
            call()
    assert store.opened is None
    assert opener.calls == 0
    assert not opener.path.parent.exists()

    made = store.write(SCOPE, "a", "hello", author=user_author())
    assert made.created
    assert opener.calls == 1
    assert opener.path.is_file()
    assert store.get(made.entry.id) is not None
    store.close()


def test_existing_store_opens_for_reads_and_policy_follows(tmp_path: Path) -> None:
    pytest.importorskip("sqlalchemy")
    opener = _Opener(tmp_path)
    first = opener()
    first.write(SCOPE, "a", "hello", author=user_author())
    getattr(first, "close")()  # noqa: B009 - SQLite 저장소 선택 메서드

    store = DeferredMemoryStore(opener, exists=opener.exists)
    policy = MemoryPolicy(max_versions_per_entry=3)
    store.policy = policy
    assert [e.key for e in store.search(MemoryQuery()).items] == ["a"]
    assert store.opened is not None
    assert store.opened.policy is policy
    newer = MemoryPolicy(max_versions_per_entry=4)
    store.policy = newer
    assert store.opened.policy is newer
    assert store.warnings() == []  # MemoryStore 밖 속성은 연 저장소로 넘긴다
    store.close()


def test_close_stops_new_opens() -> None:
    made: list[MemoryStore] = []

    def opener() -> MemoryStore:
        made.append(InMemoryMemoryStore())
        return made[-1]

    store = DeferredMemoryStore(opener, exists=lambda: bool(made))
    store.close()
    assert store.search(MemoryQuery()).items == []
    with pytest.raises(RuntimeError):
        store.write(SCOPE, "a", "x", author=user_author())
    assert made == []
