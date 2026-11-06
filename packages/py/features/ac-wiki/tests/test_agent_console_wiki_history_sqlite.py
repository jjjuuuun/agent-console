"""SQLite 기록 저장소(X49, 7R.11): 계약 묶음 + 계보 `wiki`(모양·up/down/재up) + 블롭·정리."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from agent_console_contracts.wiki import WikiAuthor
from agent_console_store import branch_version_table, current_revision, downgrade, upgrade
from agent_console_wiki import HistoryEntry, WikiHistory
from agent_console_wiki.sqlite import BRANCH_NAME, MIGRATIONS_DIR, SqliteWikiHistory, schema
from agent_console_wiki.testing import WikiHistoryContractTests

USER = WikiAuthor(kind="user")


def entry(
    path: str, op: str, data: bytes, at: float, wiki: str = "w", **kw: object
) -> HistoryEntry:
    author = kw.pop("author", USER)
    assert isinstance(author, WikiAuthor)
    return HistoryEntry.of(wiki, path, op, data, author=author, at=at, **kw)  # type: ignore[arg-type]


class TestSqliteContract(WikiHistoryContractTests):
    def make_history(self, tmp_path: Path) -> WikiHistory:
        return SqliteWikiHistory(tmp_path / "h.sqlite3")


class TestSqliteMemoryContract(WikiHistoryContractTests):
    def make_history(self, tmp_path: Path) -> WikiHistory:
        return SqliteWikiHistory(":memory:")


def _migrated(tmp_path: Path) -> Path:
    path = tmp_path / "m.sqlite3"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    upgrade(engine, versions=MIGRATIONS_DIR, version_table=branch_version_table(BRANCH_NAME))
    engine.dispose()
    return path


def test_migration_matches_schema_and_roundtrips(tmp_path: Path) -> None:
    path = _migrated(tmp_path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    table = branch_version_table(BRANCH_NAME)
    assert table == "alembic_version_wiki"
    assert current_revision(engine, version_table=table) == "wiki_0001"
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), schema.metadata)
    assert [d for d in diff if d[0] != "remove_table"] == []
    names = {i["name"] for i in inspect(engine).get_indexes("wiki_page_versions")}
    assert {
        "ux_wiki_page_versions_key",
        "ix_wiki_page_versions_wiki_seq",
        "ix_wiki_page_versions_author_run",
        "ix_wiki_page_versions_author_root",
        "ix_wiki_page_versions_sha256",
    } <= names
    downgrade(engine, versions=MIGRATIONS_DIR, version_table=table)
    assert {"wiki_page_versions", "wiki_blobs"}.isdisjoint(inspect(engine).get_table_names())
    upgrade(engine, versions=MIGRATIONS_DIR, version_table=table)
    assert "wiki_blobs" in inspect(engine).get_table_names()
    engine.dispose()


def test_store_on_migrated_file_and_create_all_idempotent(tmp_path: Path) -> None:
    path = _migrated(tmp_path)
    with SqliteWikiHistory(path) as h:  # create=True지만 이미 있으면 그대로
        h.record([entry("a", "create", b"1", 1.0)])
    with SqliteWikiHistory(path, create=False) as h:
        assert h.latest("w", "a") is not None


def test_blob_shared_and_content_none_adds_no_blob(tmp_path: Path) -> None:
    path = tmp_path / "b.sqlite3"
    with SqliteWikiHistory(path) as h:
        h.record([entry("a", "create", b"same", 1.0), entry("b", "create", b"same", 1.0)])
        gone = HistoryEntry(
            wiki="w",
            path="a",
            op="delete",
            sha256=entry("a", "x", b"same", 0).sha256,
            bytes=4,
            author=USER,
            at=2.0,
            content=None,
        )
        h.record([gone])
        assert h.read("w", "a", 2) == b"same"
    with sqlite3.connect(path) as con:
        assert con.execute("select count(*) from wiki_blobs").fetchone() == (1,)


def test_prune_deletes_orphan_blobs_and_pruned_flag(tmp_path: Path) -> None:
    path = tmp_path / "p.sqlite3"
    with SqliteWikiHistory(path) as h:
        for n in range(1, 6):
            h.record([entry("a", "update", f"v{n}".encode(), float(n))])
        assert h.list("w", "a").pruned is False
        assert h.prune("w", "a", keep=2) == 3
        assert h.list("w", "a").pruned is True
    with sqlite3.connect(path) as con:
        shas = con.execute("select count(*) from wiki_blobs").fetchone()
        versions = con.execute("select count(*) from wiki_page_versions").fetchone()
        assert shas == versions == (2,)  # keep=2 = 첫 버전 + 최근 1개


def test_record_is_atomic(tmp_path: Path) -> None:
    with SqliteWikiHistory(tmp_path / "a.sqlite3") as h:
        h.record([entry("a", "create", b"1", 1.0)])
        rows: list[HistoryEntry | None] = [
            entry("c", "create", b"3", 3.0),
            None,
        ]  # 둘째 행에서 실패
        with pytest.raises(AttributeError):
            h.record(rows)  # type: ignore[arg-type]
        assert h.latest("w", "c") is None
        assert [c.path for c in h.changes(None).items] == ["a"]


def test_changes_across_wikis_one_cursor_and_root_run(tmp_path: Path) -> None:
    child = WikiAuthor(kind="agent", run_id="child", root_run_id="root", label="정리꾼")
    with SqliteWikiHistory(tmp_path / "c.sqlite3") as h:
        h.record([entry("a", "create", b"1", 1.0, wiki="w1", author=child)])
        h.record([entry("b", "create", b"2", 2.0, wiki="w2", author=child)])
        h.record([entry("c", "update", b"3", 3.0, wiki="w1")])
        page1 = h.changes(None, limit=2)
        page2 = h.changes(None, limit=2, cursor=page1.next_cursor)
        assert [(c.wiki, c.path) for c in [*page1.items, *page2.items]] == [
            ("w1", "c"),
            ("w2", "b"),
            ("w1", "a"),
        ]
        assert page2.next_cursor is None
        by_root = h.changes(None, author_run="root")
        assert [c.path for c in by_root.items] == ["b", "a"]
        assert by_root.items[0].author.label == "정리꾼"
        assert [c.path for c in h.changes(None, ops=["update"]).items] == ["c"]


def test_author_queries_use_indexes(tmp_path: Path) -> None:
    path = _migrated(tmp_path)
    with sqlite3.connect(path) as con:
        plan = " ".join(
            str(r)
            for r in con.execute(
                "explain query plan select * from wiki_page_versions "
                "where author_run_id = ? or author_root_run_id = ?",
                ("x", "x"),
            )
        )
        assert "ix_wiki_page_versions_author_run" in plan
        assert "ix_wiki_page_versions_author_root" in plan


def test_list_1000_versions_fast(tmp_path: Path) -> None:
    with SqliteWikiHistory(tmp_path / "f.sqlite3") as h:
        h.record([entry("a", "update", f"v{n}".encode(), float(n)) for n in range(1000)])
        start = time.perf_counter()
        page = h.list("w", "a")
        elapsed = time.perf_counter() - start
        assert len(page.items) == 1000
        assert elapsed < 0.1
        assert len(h.summaries("w")) == 1
