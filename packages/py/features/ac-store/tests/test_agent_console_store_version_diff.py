"""정의 버전 비교 공용 함수 ``diff_versions`` (design §1.1 B-4)."""

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_store import (
    SECRET_MASK,
    DefinitionKind,
    InMemoryDefinitionStore,
    NotFound,
    diff_versions,
)

NOTE = DefinitionKind("note", "notes")
BOOK = DefinitionKind("book", "books", content_field="content", multi_file=True)


def _store() -> InMemoryDefinitionStore:
    return InMemoryDefinitionStore([NOTE, BOOK])


def test_document_changes_and_current_default() -> None:
    store = _store()
    a = store.create("note", {"id": "n", "name": "old", "tags": ["x"]}).version_hash
    b = store.save("note", {"id": "n", "name": "new", "tags": ["x", "y"]}, expected_version=a)
    diff = diff_versions(store, "note", "n", a)
    assert (diff.kind, diff.id, diff.from_hash, diff.to_hash) == ("note", "n", a, b.version_hash)
    ops = {(c.op, c.path): (c.before, c.after) for c in diff.changes}
    assert ops[("replace", "/name")] == ("old", "new")
    assert ops[("add", "/tags/1")] == (None, "y")
    assert diff.content_changes == []  # 본문 없는 종류
    same = diff_versions(store, "note", "n", a, a)
    assert same.changes == []
    assert same.to_hash == a


def test_secret_paths_are_masked_per_document() -> None:
    store = _store()
    a = store.create("note", {"id": "n", "key": "secret-1"}).version_hash
    store.save("note", {"id": "n", "key": "secret-2"}, expected_version=a)
    seen: list[Mapping[str, Any]] = []

    def secrets(doc: Mapping[str, Any]) -> list[str]:
        seen.append(doc)
        return ["/key"]

    diff = diff_versions(store, "note", "n", a, secret_paths=secrets, mask="<hidden>")
    assert len(seen) == 2
    (change,) = diff.changes
    assert change.secret is True
    assert (change.before, change.after) == ("<hidden>", "<hidden>")
    dumped = diff.model_dump_json()
    assert "secret-1" not in dumped
    assert "secret-2" not in dumped
    assert SECRET_MASK == "***"


def test_content_file_changes_by_hash() -> None:
    store = _store()
    a = store.create("book", {"id": "b", "content": {"file": "a.md"}}).version_hash
    s1 = store.write_files("book", "b", {"a.md": b"one", "b.md": b"two"}, expected_version=a)
    s2 = store.write_files(
        "book", "b", {"a.md": b"ONE", "b.md": None, "c.md": b"3"}, expected_version=s1.version_hash
    )
    diff = diff_versions(store, "book", "b", s1.version_hash, s2.version_hash)
    paths = {c.path: (c.before_hash is None, c.after_hash is None) for c in diff.content_changes}
    assert paths == {"a.md": (False, False), "b.md": (False, True), "c.md": (True, False)}
    assert diff.changes == []


def test_missing_version_or_deleted_definition() -> None:
    store = _store()
    a = store.create("note", {"id": "n"}).version_hash
    with pytest.raises(NotFound):
        diff_versions(store, "note", "n", "nope")
    store.delete("note", "n")
    with pytest.raises(NotFound):
        diff_versions(store, "note", "n", a)  # 현재 버전이 없다
    assert diff_versions(store, "note", "n", a, a).changes == []
