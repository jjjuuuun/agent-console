"""SQLite 메모리 저장소(X31): 공용 계약 묶음, 검색 폴백, 완전 삭제, 동시 쓰기, 열기."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import MemoryEntry, MemoryScopeRef
from agent_console_memory import MemoryPolicy, MemoryQuery, MemoryStore
from agent_console_memory.sqlite import (
    SqliteMemoryStore,
    fts5_trigram_available,
    open_sqlite_memory_store,
    schema,
)
from agent_console_memory.testing import FakeClock, user_author
from agent_console_memory.testing.contract import MemoryStoreContractTests

S1 = MemoryScopeRef(kind="k1", id="a")
S2 = MemoryScopeRef(kind="k1", id="b")
needs_fts = pytest.mark.skipif(not fts5_trigram_available(), reason="FTS5 trigram 없음")


class TestSqliteMemoryDb(MemoryStoreContractTests):
    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:
        return open_sqlite_memory_store(":memory:", policy=policy, clock=clock or FakeClock())


class TestSqliteFile(MemoryStoreContractTests):
    @pytest.fixture(autouse=True)
    def _dir(self, tmp_path: Path) -> None:
        self._tmp = tmp_path
        self._n = 0

    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:
        self._n += 1
        return open_sqlite_memory_store(
            self._tmp / f"m{self._n}.sqlite3", policy=policy, clock=clock or FakeClock()
        )


class TestSqliteLikeFallback(MemoryStoreContractTests):
    """FTS5를 끈 포함 검색도 같은 의미다."""

    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:
        return open_sqlite_memory_store(
            ":memory:", policy=policy, clock=clock or FakeClock(), use_fts=False
        )


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteMemoryStore]:
    opened = open_sqlite_memory_store(tmp_path / "m.sqlite3", clock=FakeClock())
    yield opened
    opened.close()


def test_satisfies_protocol_and_policy_attribute(store: SqliteMemoryStore) -> None:
    assert isinstance(store, MemoryStore)
    assert isinstance(store.policy, MemoryPolicy)
    store.policy = MemoryPolicy(max_versions_per_entry=2)
    for i in range(5):
        store.write(S1, "k", f"v{i}", author=user_author())
    entry = store.find(S1, "k")
    assert entry is not None
    assert [v.version for v in store.history(entry.id)] == [1, 5]


@needs_fts
def test_fts_backend_by_default_without_warning(store: SqliteMemoryStore) -> None:
    assert store.search_backend == "fts5"
    assert store.warnings() == []


def test_disabled_fts_reports_fallback_warning() -> None:
    off = open_sqlite_memory_store(":memory:", use_fts=False)
    assert off.search_backend == "like"
    [issue] = off.warnings()
    assert issue.code == KnownIssueCodes.MEMORY_SEARCH_FALLBACK
    assert issue.severity == "warning"
    off.write(S1, "k", "회의록 본문", author=user_author())
    assert off.search(MemoryQuery(text="회의록")).total == 1


def test_missing_fts5_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_console_memory.sqlite._store.fts5_trigram_available", lambda: False)
    fallback = open_sqlite_memory_store(":memory:")
    assert fallback.search_backend == "like"
    [issue] = fallback.warnings()
    assert issue.code == KnownIssueCodes.MEMORY_SEARCH_FALLBACK
    assert "FTS5" in issue.details["reason"]
    fallback.write(S1, "k", "Hello World", author=user_author())
    assert fallback.search(MemoryQuery(text="world")).total == 1


@needs_fts
def test_short_query_uses_like_and_long_uses_index(store: SqliteMemoryStore) -> None:
    store.write(S1, "a", "xy 회의록 ABC", author=user_author())
    store.write(S1, "b", "other", author=user_author(), tags=["xyz"])
    assert store.search(MemoryQuery(text="xy")).total == 2  # 2글자: 본문 + 태그
    assert store.search(MemoryQuery(text="회의록")).total == 1  # 3글자
    assert store.search(MemoryQuery(text="abc")).total == 1  # 대소문자 무시
    assert store.search(MemoryQuery(text='"회')).total == 0  # 따옴표도 글자
    store.write(S1, "q", 'say "hi" now', author=user_author())
    assert store.search(MemoryQuery(text='"hi"')).total == 1


@needs_fts
def test_fts_index_follows_update_move_delete(store: SqliteMemoryStore) -> None:
    entry = store.write(
        S1, "notes/alpha", "first body", author=user_author(), tags=["tagone"]
    ).entry
    assert store.search(MemoryQuery(text="first")).total == 1
    store.update(entry.id, author=user_author(), content="second body", tags=["tagtwo"])
    assert store.search(MemoryQuery(text="first")).total == 0
    assert store.search(MemoryQuery(text="second")).total == 1
    assert store.search(MemoryQuery(text="tagone")).total == 0
    assert store.search(MemoryQuery(text="tagtwo")).total == 1
    store.move(entry.id, author=user_author(), to_key="notes/omega")
    assert store.search(MemoryQuery(text="alpha")).total == 0
    assert store.search(MemoryQuery(text="omega")).total == 1
    store.delete(entry.id, author=user_author())
    assert store.search(MemoryQuery(text="second")).total == 0
    assert store.search(MemoryQuery(text="second", include_deleted=True)).total == 1
    store.restore(entry.id, author=user_author(), version=1)
    assert store.search(MemoryQuery(text="first")).total == 1


def _all_text(db: Path) -> str:
    """모든 표(가상 표의 그림자 표 포함)의 모든 값을 이어 붙인다."""
    parts: list[str] = []
    with sqlite3.connect(db) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in names:
            for row in conn.execute(f'SELECT * FROM "{name}"'):
                for value in row:
                    if isinstance(value, bytes):
                        parts.append(value.decode("latin-1"))
                    elif value is not None:
                        parts.append(str(value))
    return "\n".join(parts)


def test_purge_leaves_no_trace_in_any_table(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite3"
    marker = "UNIQUE-MARKER-quokka-7788"
    opened = open_sqlite_memory_store(db)
    kept = opened.write(S1, "keep", "keep-body-text", author=user_author(), tags=["keeptag"]).entry
    gone = opened.write(
        S1, "gone/key-zebra", f"first {marker}", author=user_author(), tags=["goner"]
    )
    opened.write(S1, "gone/key-zebra", f"second {marker}", author=user_author())
    assert marker in _all_text(db)
    opened.purge(gone.entry.id)
    text = _all_text(db)
    assert marker not in text
    assert "gone/key-zebra" not in text
    assert "goner" not in text
    assert opened.search(MemoryQuery(text="quokka", include_deleted=True)).total == 0
    still = opened.get(kept.id)
    assert still is not None
    assert opened.search(MemoryQuery(text="keep-body")).total == 1
    opened.close()


def test_purge_of_soft_deleted_entry(store: SqliteMemoryStore) -> None:
    entry = store.write(S1, "k", "to-be-purged", author=user_author()).entry
    store.delete(entry.id, author=user_author())
    purged = store.purge(entry.id)
    assert purged.deleted_at is not None
    assert store.get(entry.id, include_deleted=True) is None


def test_reopen_keeps_data_and_search(tmp_path: Path) -> None:
    db = tmp_path / "sub" / "m.sqlite3"
    first = open_sqlite_memory_store(db)
    first.write(S1, "k", "persisted 본문", author=user_author(), tags=["t1"])
    first.close()
    second = open_sqlite_memory_store(db)
    found = second.find(S1, "k")
    assert found is not None
    assert found.tags == ["t1"]
    assert second.search(MemoryQuery(text="persisted")).total == 1
    assert second.search(MemoryQuery(tags=["t1"])).total == 1
    second.close()


@needs_fts
def test_search_index_is_built_when_missing(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite3"
    no_fts = open_sqlite_memory_store(db, use_fts=False)
    no_fts.write(S1, "k", "indexed later", author=user_author())
    no_fts.close()
    again = open_sqlite_memory_store(db)
    assert again.search_backend == "fts5"
    assert again.search(MemoryQuery(text="indexed")).total == 1
    assert again.reindex() == 1
    assert again.search(MemoryQuery(text="indexed")).total == 1
    again.close()


def test_two_stores_on_one_file_do_not_lose_versions(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite3"
    left = open_sqlite_memory_store(db)
    right = open_sqlite_memory_store(db)
    n = 30

    def work(i: int) -> None:
        target = left if i % 2 else right
        target.write(S1, "k", f"v{i}", author=user_author())
        target.write(S2, f"own/{i}", "x", author=user_author())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(n)))
    entry = left.find(S1, "k")
    assert entry is not None
    assert entry.version == n
    assert [v.version for v in right.history(entry.id)] == list(range(1, n + 1))
    assert right.search(MemoryQuery(scopes=[S2], limit=100)).total == n
    left.close()
    right.close()


def test_failed_write_leaves_nothing(store: SqliteMemoryStore) -> None:
    from agent_console_memory import InvalidKeyError

    with pytest.raises(InvalidKeyError):
        store.write(S1, "../x", "body", author=user_author())
    assert store.search(MemoryQuery()).total == 0
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_versions").fetchone() == (0,)


def test_schema_has_designed_tables_and_indexes(store: SqliteMemoryStore) -> None:
    with sqlite3.connect(store.path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {schema.ENTRIES_TABLE, schema.VERSIONS_TABLE, schema.TAGS_TABLE} <= tables
    assert {
        "ux_memory_entries_live_key",
        "ix_memory_entries_live_summary",
        "ix_memory_entries_author_run",
        "ix_memory_entries_deleted",
        "ix_memory_versions_run",
        "ix_memory_tags_tag",
    } <= indexes
    if fts5_trigram_available():
        assert schema.SEARCH_TABLE in tables


def test_live_key_index_is_partial_unique(store: SqliteMemoryStore) -> None:
    entry = store.write(S1, "k", "a", author=user_author()).entry
    store.delete(entry.id, author=user_author())
    store.write(S1, "k", "b", author=user_author())  # 지운 항목과 같은 키 허용
    with sqlite3.connect(store.path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM memory_entries WHERE key = 'k'").fetchone()
    assert rows == (2,)


def test_list_preview_is_stored_and_follows_updates(store: SqliteMemoryStore) -> None:
    entry = store.write(S1, "k", "첫 본문 " * 100, author=user_author()).entry
    first = store.search(MemoryQuery()).items[0]
    assert first.preview == ("첫 본문 " * 100)[:200]
    store.update(entry.id, author=user_author(), content="바뀐 본문")
    assert store.search(MemoryQuery()).items[0].preview == "바뀐 본문"
    with sqlite3.connect(store.path) as conn:
        assert conn.execute("SELECT preview FROM memory_entries").fetchone() == ("바뀐 본문",)


def test_preview_is_redacted_again_with_rules_added_later() -> None:
    from agent_console_memory import MemorySecretGuard, SecretScanner

    class Later:
        def __init__(self, word: str) -> None:
            self.word = word

        def find(self, text: str) -> list[str]:
            return ["later"] if self.word and self.word in text else []

        def redact(self, text: str) -> str:
            return text.replace(self.word, "[가림]") if self.word else text

    scanner = Later("")
    guard = MemorySecretGuard(scanner=scanner)
    assert isinstance(scanner, SecretScanner)
    opened = open_sqlite_memory_store(":memory:", policy=MemoryPolicy(secrets=guard))
    opened.write(S1, "k", "앞 비밀값-xyz 뒤", author=user_author())
    assert "비밀값-xyz" in opened.search(MemoryQuery()).items[0].preview
    scanner.word = "비밀값-xyz"  # 규칙이 나중에 늘었다
    assert "비밀값-xyz" not in opened.search(MemoryQuery()).items[0].preview
    opened.close()


def test_scan_entries_pages_by_row_number_and_skips_deleted(store: SqliteMemoryStore) -> None:
    from agent_console_memory import EntryScanner

    assert isinstance(store, EntryScanner)
    for i in range(25):
        store.write(S1, f"k/{i:02d}", f"body {i}", author=user_author())
    gone = store.find(S1, "k/03")
    assert gone is not None
    store.delete(gone.id, author=user_author())
    got = list(store.scan_entries(page_size=4))
    assert len(got) == 24
    assert all(e.content.startswith("body") for e in got)
    assert [e.key for e in got] == sorted(e.key for e in got if e.key != "k/03")
    assert list(store.scan_entries(scopes=[S2])) == []


def test_scan_heads_skip_content_and_page_like_scan_entries(store: SqliteMemoryStore) -> None:
    from agent_console_memory import EntryHead, HeadScanner, iter_entries

    assert isinstance(store, HeadScanner)
    for i in range(11):
        store.write(S1 if i % 2 else S2, f"k/{i:02d}", f"body {i}", author=user_author())
    full = list(store.scan_entries(page_size=3))
    heads = list(store.scan_heads(page_size=3))
    assert [h.id for h in heads] == [e.id for e in full]
    assert all(type(h) is EntryHead for h in heads)
    assert [h.bytes for h in heads] == [e.bytes for e in full]
    assert list(iter_entries(store, with_content=False)) == heads
    assert [e.id for e in iter_entries(store)] == [e.id for e in full]  # 본문 길은 그대로
    assert all(isinstance(e, MemoryEntry) for e in iter_entries(store))
    assert [h.key for h in store.scan_heads(scopes=[S1])] == [f"k/{i:02d}" for i in range(1, 11, 2)]


class _Hide:
    """선택 능력 몇 개를 숨긴 감싸기(정리 계획이 길마다 같은지 비교)."""

    def __init__(self, store: SqliteMemoryStore, *hidden: str) -> None:
        self._store = store
        self._hidden = hidden

    def __getattr__(self, name: str) -> Any:
        if name in self._hidden:
            raise AttributeError(name)
        return getattr(self._store, name)


def test_retention_plan_is_the_same_on_every_scan_path(store: SqliteMemoryStore) -> None:
    from agent_console_conditions import builtin_operators
    from agent_console_memory import retention_plan

    for i in range(40):
        written = store.write(
            S1 if i % 3 else S2,
            f"draft/{i}" if i % 4 == 0 else f"k/{i}",
            "x" * (10 + i * 7),
            author=user_author(),
            tags=["tmp"] if i % 2 else ["keep"],
            pinned=i % 9 == 0,
        ).entry
        if i % 5 == 0:
            store.archive(written.id, author=user_author())
    ops = {op.descriptor.id: op for op in builtin_operators()}
    rules = [
        {
            "id": "a",
            "action": "archive",
            "when": {
                "all": [
                    {"path": "/tags", "op": "contains", "value": "tmp"},
                    {"path": "/bytes", "op": "gt", "value": 100},
                ]
            },
        },
        {
            "id": "d",
            "action": "delete",
            "when": {
                "all": [
                    {"path": "/archived", "op": "eq", "value": True},
                ]
            },
        },
        {
            "id": "k",
            "action": "delete",
            "when": {
                "all": [
                    {"path": "/key", "op": "matches", "value": "^draft/"},
                    {"path": "/scope/id", "op": "eq", "value": S1.id},
                ]
            },
        },
    ]
    now = 2_000_000_000.0

    def plan(target: Any) -> list[tuple[str, str, str]]:
        result = retention_plan(target, rules, now=now, operators=ops, page_size=7)
        assert result.issues == []
        return sorted((i.entry_id, i.rule, i.action) for i in result.items)

    summaries = plan(store)
    assert summaries
    assert plan(_Hide(store, "scan_heads")) == summaries
    assert plan(_Hide(store, "scan_heads", "scan_entries")) == summaries
