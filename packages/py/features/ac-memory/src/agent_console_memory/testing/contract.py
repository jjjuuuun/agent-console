"""저장소 계약 테스트 묶음(X31). 구현마다 상속해 `make_store`만 채운다.

```python
class TestSqliteStore(MemoryStoreContractTests):
    def make_store(self, *, policy=None, clock=None) -> MemoryStore:
        return open_sqlite_memory_store(":memory:", policy=policy, clock=clock)
```
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from agent_console_contracts.memory import MemoryScopeRef
from agent_console_memory._errors import (
    EntryExistsError,
    EntryNotFoundError,
    InvalidKeyError,
    SecretRejectedError,
    TooLargeError,
    VersionConflictError,
)
from agent_console_memory._policy import MemoryLimits, MemoryPolicy, MemorySecretGuard
from agent_console_memory._store import MemoryQuery, MemoryStore

from ._samples import FakeClock, agent_author_sample, user_author

__all__ = ["MemoryStoreContractTests"]

S1 = MemoryScopeRef(kind="k1", id="a")
S2 = MemoryScopeRef(kind="k1", id="b")
S3 = MemoryScopeRef(kind="k2", id="")
SECRET = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8" * 3
BAD_KEYS = ["", "/a", "a/", "a//b", "a/./b", "a/../b", "..", "a\\b", "a\nb", " a", "x" * 257]


class MemoryStoreContractTests:
    """`MemoryStore` 구현이 지켜야 할 의미(메모리·SQLite가 같다)."""

    def make_store(
        self, *, policy: MemoryPolicy | None = None, clock: FakeClock | None = None
    ) -> MemoryStore:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def _store(self, **limits: int) -> tuple[MemoryStore, FakeClock]:
        clock = FakeClock(1000.0)
        policy = MemoryPolicy(limits=replace(MemoryLimits(), **limits)) if limits else None
        return self.make_store(policy=policy, clock=clock), clock

    # ---- 버전·충돌 ----------------------------------------------------------------------

    def test_create_then_update_bumps_version_and_records_history(self) -> None:
        store, clock = self._store()
        first = store.write(S1, "d/x", "one", author=agent_author_sample(), tags=["t"])
        assert first.created
        assert first.entry.version == 1
        assert first.entry.bytes == 3
        assert len(first.entry.sha256) == 64
        clock.advance(10)
        second = store.write(S1, "d/x", "two", author=user_author())
        assert not second.created
        assert second.entry.id == first.entry.id
        assert second.entry.version == 2
        assert second.entry.tags == ["t"]  # 생략 = 그대로
        assert second.entry.updated_at == 1010.0
        assert second.entry.created_at == 1000.0
        assert second.entry.updated_by.kind == "user"
        history = store.history(first.entry.id)
        assert [(v.version, v.op) for v in history] == [(1, "create"), (2, "update")]
        old = store.get_version(first.entry.id, 1)
        assert old is not None
        assert old.content == "one"

    def test_if_version_conflict_reports_current_version(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        store.write(S1, "k", "b", author=user_author(), if_version=1)
        with pytest.raises(VersionConflictError) as info:
            store.write(S1, "k", "c", author=user_author(), if_version=1)
        assert info.value.current_version == 2
        with pytest.raises(VersionConflictError):
            store.update(entry.id, author=user_author(), content="x", if_version=5)
        with pytest.raises(VersionConflictError):
            store.write(S1, "missing", "x", author=user_author(), if_version=3)
        found = store.find(S1, "k")
        assert found is not None
        assert found.content == "b"

    def test_create_only_rejects_existing(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        with pytest.raises(EntryExistsError) as info:
            store.write(S1, "k", "b", author=user_author(), create_only=True)
        assert info.value.entry_id == entry.id

    def test_append_mode(self) -> None:
        store, _ = self._store()
        store.write(S1, "log", "a", author=user_author(), mode="append")
        entry = store.write(S1, "log", "b", author=user_author(), mode="append").entry
        assert entry.content == "a\nb"
        assert entry.version == 2

    def test_parallel_writes_keep_every_version(self) -> None:
        store, _ = self._store()
        n = 40
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: store.write(S1, "k", f"v{i}", author=user_author()), range(n)))
        entry = store.find(S1, "k")
        assert entry is not None
        assert entry.version == n
        assert [v.version for v in store.history(entry.id)] == list(range(1, n + 1))

    # ---- 키·한도·비밀 -------------------------------------------------------------------

    @pytest.mark.parametrize("key", BAD_KEYS)
    def test_bad_keys_rejected(self, key: str) -> None:
        store, _ = self._store()
        with pytest.raises(InvalidKeyError):
            store.write(S1, key, "x", author=user_author())

    def test_size_limits(self) -> None:
        store, _ = self._store(max_entry_bytes=8, max_entries_per_scope=2, max_total_bytes=12)
        with pytest.raises(TooLargeError) as info:
            store.write(S1, "big", "123456789", author=user_author())
        assert info.value.limit == "max_entry_bytes"
        store.write(S1, "a", "12345", author=user_author())
        store.write(S1, "b", "12345", author=user_author())
        with pytest.raises(TooLargeError) as info:
            store.write(S1, "c", "1", author=user_author())
        assert info.value.limit == "max_entries_per_scope"
        with pytest.raises(TooLargeError) as info:
            store.write(S2, "c", "123", author=user_author())
        assert info.value.limit == "max_total_bytes"
        store.write(S2, "c", "12", author=user_author())

    @pytest.mark.parametrize(
        ("key", "content", "tags", "field"),
        [
            ("k", f"token {SECRET}", [], "content"),
            (f"k/{SECRET}", "x", [], "key"),
            ("k", "x", [SECRET], "tags"),
        ],
    )
    def test_secret_rejected(self, key: str, content: str, tags: list[str], field: str) -> None:
        store, _ = self._store()
        with pytest.raises(SecretRejectedError) as info:
            store.write(S1, key, content, author=user_author(), tags=tags)
        assert info.value.field == field
        assert SECRET not in str(info.value)
        assert SECRET not in repr(info.value.details())
        assert store.search(MemoryQuery()).total == 0

    def test_secret_redacted(self) -> None:
        store = self.make_store(policy=MemoryPolicy(secrets=MemorySecretGuard(mode="redact")))
        entry = store.write(S1, "k", f"token {SECRET}", author=user_author()).entry
        assert SECRET not in entry.content
        version = store.get_version(entry.id, 1)
        assert version is not None
        assert SECRET not in version.content
        with pytest.raises(SecretRejectedError):  # 키는 가림 방식에서도 거부
            store.write(S1, f"k/{SECRET}", "x", author=user_author())

    def test_preview_is_redacted_and_short(self) -> None:
        store = self.make_store(policy=MemoryPolicy(secrets=MemorySecretGuard(mode="redact")))
        store.write(S1, "k", "x" * 500, author=user_author())
        item = store.search(MemoryQuery()).items[0]
        assert item.preview == "x" * 200

    # ---- 지우기·되돌리기·보관·옮기기 -----------------------------------------------------

    def test_soft_delete_restore_and_rewrite(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        deleted = store.delete(entry.id, author=user_author())
        assert deleted.deleted_at is not None
        assert deleted.version == 2
        assert store.find(S1, "k") is None
        assert store.get(entry.id) is None
        assert store.get(entry.id, include_deleted=True) is not None
        with pytest.raises(EntryNotFoundError):
            store.delete(entry.id, author=user_author())
        restored = store.restore(entry.id, author=user_author())
        assert restored.deleted_at is None
        assert restored.version == 3
        assert store.find(S1, "k") is not None
        store.delete(entry.id, author=user_author())
        fresh = store.write(S1, "k", "b", author=user_author())
        assert fresh.created
        assert fresh.entry.id != entry.id
        with pytest.raises(EntryExistsError):
            store.restore(entry.id, author=user_author())

    def test_restore_version_content(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "one", author=user_author()).entry
        store.write(S1, "k", "two", author=user_author())
        back = store.restore(entry.id, author=user_author(), version=1)
        assert back.content == "one"
        assert back.version == 3
        assert store.history(entry.id)[-1].op == "restore"
        with pytest.raises(EntryNotFoundError):
            store.restore(entry.id, author=user_author(), version=99)

    def test_archive_toggle(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        archived = store.archive(entry.id, author=user_author())
        assert archived.archived
        assert archived.version == 2
        assert store.archive(entry.id, author=user_author()).version == 2  # 이미 보관
        assert store.search(MemoryQuery()).total == 0
        assert store.search(MemoryQuery(include_archived=True)).total == 1
        back = store.archive(entry.id, author=user_author(), archived=False)
        assert not back.archived
        assert [v.op for v in store.history(entry.id)] == ["create", "archive", "unarchive"]

    def test_move_scope_and_key(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        store.write(S2, "taken", "b", author=user_author())
        with pytest.raises(EntryExistsError):
            store.move(entry.id, author=user_author(), to_scope=S2, to_key="taken")
        moved = store.move(entry.id, author=user_author(), to_scope=S2, to_key="new/k")
        assert moved.id == entry.id
        assert moved.scope == S2
        assert moved.key == "new/k"
        assert store.find(S1, "k") is None
        assert store.find(S2, "new/k") is not None
        assert store.history(entry.id)[-1].op == "move"
        with pytest.raises(InvalidKeyError):
            store.move(entry.id, author=user_author(), to_key="../x")

    def test_purge_removes_versions(self) -> None:
        store, _ = self._store()
        entry = store.write(S1, "k", "secret-ish body", author=user_author()).entry
        store.write(S1, "k", "two", author=user_author())
        store.purge(entry.id)
        assert store.get(entry.id, include_deleted=True) is None
        assert store.get_version(entry.id, 1) is None
        with pytest.raises(EntryNotFoundError):
            store.history(entry.id)
        assert store.search(MemoryQuery(text="body", include_deleted=True)).total == 0
        assert store.write(S1, "k", "again", author=user_author()).created

    def test_version_retention_keeps_first(self) -> None:
        clock = FakeClock()
        store = self.make_store(policy=MemoryPolicy(max_versions_per_entry=3), clock=clock)
        entry = store.write(S1, "k", "v1", author=user_author()).entry
        for i in range(2, 7):
            store.write(S1, "k", f"v{i}", author=user_author())
        assert [v.version for v in store.history(entry.id)] == [1, 5, 6]

    def test_mark_read_does_not_bump_version(self) -> None:
        store, clock = self._store()
        entry = store.write(S1, "k", "a", author=user_author()).entry
        clock.advance(7)
        store.mark_read(entry.id)
        after = store.get(entry.id)
        assert after is not None
        assert after.version == 1
        assert after.last_read_at == 1007.0

    # ---- 목록·검색 ----------------------------------------------------------------------

    def test_search_filters_and_paging(self) -> None:
        store, clock = self._store()
        run_author = agent_author_sample(run_id="run-9")
        for i in range(5):
            clock.advance(1)
            store.write(S1, f"note/{i}", f"Body {i}", author=user_author(), tags=["a"])
        store.write(S2, "other", "Something", author=run_author, tags=["a", "b"])
        assert store.search(MemoryQuery(text="body")).total == 5  # 대소문자 무시
        assert store.search(MemoryQuery(text="note/3")).total == 1  # 키
        assert store.search(MemoryQuery(text="b")).total == 6  # 본문(대소문자 무시) 5 + 태그 1
        assert store.search(MemoryQuery(tags=["a", "b"])).total == 1
        assert store.search(MemoryQuery(scopes=[S2])).total == 1
        assert store.search(MemoryQuery(scopes=[S3])).total == 0
        assert store.search(MemoryQuery(author_run="run-9")).total == 1
        assert store.search(MemoryQuery(author_kind="user")).total == 5
        first = store.search(MemoryQuery(scopes=[S1], limit=2, sort="key", order="asc"))
        assert [i.key for i in first.items] == ["note/0", "note/1"]
        assert first.next_cursor is not None
        second = store.search(
            MemoryQuery(scopes=[S1], limit=2, sort="key", order="asc", cursor=first.next_cursor)
        )
        assert [i.key for i in second.items] == ["note/2", "note/3"]
        newest = store.search(MemoryQuery(scopes=[S1], limit=1))
        assert newest.items[0].key == "note/4"  # 기본 updated_at desc

    def test_list_scopes(self) -> None:
        store, _ = self._store()
        store.write(S1, "a", "12", author=user_author())
        entry = store.write(S1, "b", "345", author=user_author()).entry
        store.archive(entry.id, author=user_author())
        store.write(S3, "c", "x", author=user_author())
        gone = store.write(S2, "d", "x", author=user_author()).entry
        store.delete(gone.id, author=user_author())
        summaries = store.list_scopes()
        assert [(s.scope, s.entries, s.archived, s.bytes) for s in summaries] == [
            (S1, 2, 1, 5),
            (S3, 1, 0, 1),
        ]
        assert [s.scope for s in store.list_scopes(kind="k2")] == [S3]

    # ---- 훑기(선택 능력 EntryScanner) ---------------------------------------------------

    def test_scan_entries_matches_search_when_supported(self) -> None:
        """`scan_entries`를 가진 저장소는 `search` 길과 같은 항목을 본문까지 낸다."""
        from agent_console_memory._scan import EntryScanner

        store, _ = self._store()
        if not isinstance(store, EntryScanner):
            pytest.skip("선택 능력 EntryScanner 없음")
        for i in range(7):
            store.write(
                S1 if i % 2 else S2, f"n/{i}", f"본문 {i}", author=user_author(), tags=["t"]
            )
        store.write(S3, "x", "other", author=user_author())
        archived = store.write(S1, "arch", "old", author=user_author()).entry
        store.archive(archived.id, author=user_author())
        gone = store.write(S1, "gone", "bye", author=user_author()).entry
        store.delete(gone.id, author=user_author())
        for scopes in (None, [S1], [S1, S3], [S1, S1], []):
            for include in (True, False):
                found = list(store.scan_entries(scopes=scopes, include_archived=include))
                expected = store.search(
                    MemoryQuery(scopes=scopes, include_archived=include, limit=500)
                ).items
                assert sorted(e.id for e in found) == sorted(i.id for i in expected)
                assert len({e.id for e in found}) == len(found)
                for entry in found:
                    assert entry == store.get(entry.id)

    def test_scan_heads_match_entries_when_supported(self) -> None:
        """`scan_heads`를 가진 저장소는 `scan_entries`와 같은 항목을 본문 없는 머리로 낸다."""
        from agent_console_memory._scan import EntryHead, HeadScanner

        store, _ = self._store()
        if not isinstance(store, HeadScanner):
            pytest.skip("선택 능력 HeadScanner 없음")
        for i in range(5):
            store.write(S1 if i % 2 else S2, f"n/{i}", f"본문 {i}", author=user_author())
        archived = store.write(S1, "arch", "old", author=user_author(), tags=["a", "b"]).entry
        store.archive(archived.id, author=user_author())
        gone = store.write(S1, "gone", "bye", author=user_author()).entry
        store.delete(gone.id, author=user_author())
        for scopes in (None, [S1], [S1, S1], []):
            for include in (True, False):
                found = list(store.scan_heads(scopes=scopes, include_archived=include))
                expected = store.search(
                    MemoryQuery(scopes=scopes, include_archived=include, limit=500)
                ).items
                assert sorted(e.id for e in found) == sorted(i.id for i in expected)
                assert len({e.id for e in found}) == len(found)
                for head in found:
                    assert isinstance(head, EntryHead)
                    entry = store.get(head.id)
                    assert entry is not None
                    want = entry.model_dump(exclude={"content"})
                    want["tags"] = tuple(want["tags"])
                    got = head._asdict()
                    got["scope"] = head.scope.model_dump()
                    got["created_by"] = head.created_by.model_dump()
                    got["updated_by"] = head.updated_by.model_dump()
                    assert got == want

    def test_count_tags_matches_scanning_when_supported(self) -> None:
        """`count_tags`를 가진 저장소는 직접 훑어 센 결과와 같은 수를 낸다(쓰기·지우기·보관 뒤)."""
        from agent_console_memory._scan import TagCounter

        store, _ = self._store()
        if not isinstance(store, TagCounter):
            pytest.skip("선택 능력 TagCounter 없음")
        me = user_author()
        for i in range(9):
            store.write(
                (S1, S2, S3)[i % 3],
                f"t/{i}",
                f"본문 {i}",
                author=me,
                tags=["공통", f"t{i % 2}"] + (["드묾"] if i == 4 else []),
            )
        store.write(S1, "t/0", "바뀜", author=me, tags=["바뀐-태그"])  # 태그 교체
        archived = store.write(S2, "arch", "old", author=me, tags=["공통", "보관"]).entry
        store.archive(archived.id, author=me)
        gone = store.write(S1, "gone", "bye", author=me, tags=["지움"]).entry
        store.delete(gone.id, author=me)
        purged = store.write(S3, "purged", "bye", author=me, tags=["영구"]).entry
        store.delete(purged.id, author=me)
        store.purge(purged.id)
        restored = store.write(S3, "back", "x", author=me, tags=["되살림"]).entry
        store.delete(restored.id, author=me)
        store.restore(restored.id, author=me)

        def scanned(scopes: list[MemoryScopeRef] | None, include: bool) -> dict[str, int]:
            counts: dict[str, int] = {}
            items = store.search(MemoryQuery(scopes=scopes, include_archived=include, limit=500))
            for item in items.items:
                for tag in set(item.tags):
                    counts[tag] = counts.get(tag, 0) + 1
            return counts

        for scopes in (None, [S1], [S1, S3], [S2, S2], []):
            for include in (True, False):
                got = store.count_tags(scopes=scopes, include_archived=include)
                assert got == scanned(scopes, include), (scopes, include)
        everything = store.count_tags()
        assert everything["공통"] == 9  # t/0은 태그를 바꿨고 보관 항목은 센다
        assert "지움" not in everything
        assert "영구" not in everything
        assert everything["되살림"] == 1
        assert "보관" not in store.count_tags(include_archived=False)
