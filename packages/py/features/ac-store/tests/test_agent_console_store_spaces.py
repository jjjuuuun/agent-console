"""5.7R.33x: 공간 고르기(`SpaceStores`), 기록 DB 위 버전 기록소, `field_issues` 오류 본문."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_console_contracts import Issue
from agent_console_store import (
    DEFINITIONS_SPACES_PORT,
    DefinitionSpaces,
    DefinitionStore,
    FileDefinitionStore,
    InMemoryDefinitionStore,
    InMemoryVersionRepository,
    NotFound,
    ObservedVersionRepository,
    RecordsUnavailable,
    RecordsVersionRepository,
    SpaceStores,
    SpacesUnavailable,
    StoreError,
    UnknownSpace,
    VersionWriteCheck,
    open_records_db,
    store_error_body,
)


class Spaces:  # MappedSpaces와 같지만 연 이름을 남긴다
    """`DefinitionSpaces` 예제 구현: 이름 → 저장소 표."""

    def __init__(self, stores: dict[str, DefinitionStore]) -> None:
        self.stores = stores
        self.opened: list[str] = []

    def open(self, space: str) -> DefinitionStore:
        self.opened.append(space)
        return self.stores[space]  # 모르면 KeyError(LookupError)


def test_port_name_and_protocol() -> None:
    assert DEFINITIONS_SPACES_PORT == "definitions.spaces"
    assert isinstance(Spaces({}), DefinitionSpaces)


def test_no_space_is_default_even_without_provider() -> None:
    library = InMemoryDefinitionStore()
    stores = SpaceStores(library, lambda: None)
    assert stores.get(None) is library
    assert stores.get("") is library
    assert not stores.available


def test_space_without_provider_is_feature_unavailable() -> None:
    stores = SpaceStores(InMemoryDefinitionStore(), lambda: None)
    with pytest.raises(SpacesUnavailable) as err:
        stores.get("p1")
    body = store_error_body(err.value)
    assert body.code == "feature_unavailable"


def test_space_picks_provider_store_and_unknown_is_not_found() -> None:
    library, a = InMemoryDefinitionStore(), InMemoryDefinitionStore()
    spaces = Spaces({"a": a})
    stores = SpaceStores(library, lambda: spaces)
    assert stores.available
    assert stores.get("a") is a
    with pytest.raises(UnknownSpace) as err:
        stores.get("zzz")
    assert err.value.space == "zzz"
    assert store_error_body(err.value).code == "project.not_found"


def test_provider_store_errors_pass_through_and_none_is_unknown() -> None:
    class Failing:
        def open(self, space: str) -> DefinitionStore:
            raise NotFound("folder gone")

    class Nothing:
        def open(self, space: str) -> DefinitionStore:
            return None  # type: ignore[return-value]

    with pytest.raises(NotFound):
        SpaceStores(InMemoryDefinitionStore(), lambda: Failing()).get("x")
    with pytest.raises(UnknownSpace):
        SpaceStores(InMemoryDefinitionStore(), lambda: Nothing()).get("x")


def test_cast_narrows_provider_store() -> None:
    a = InMemoryDefinitionStore()
    seen: list[DefinitionStore] = []

    def cast(store: DefinitionStore) -> InMemoryDefinitionStore:
        seen.append(store)
        assert isinstance(store, InMemoryDefinitionStore)
        return store

    stores = SpaceStores(InMemoryDefinitionStore(), lambda: Spaces({"a": a}), cast=cast)
    assert stores.get("a") is a
    assert seen == [a]


def test_store_error_body_uses_field_issues_for_validation_failed() -> None:
    class RejectedError(StoreError):
        code = "validation_failed"

        def field_issues(self) -> list[Issue]:
            return [Issue(severity="error", code="secret.plain_found", message="m", path="/x")]

    body = store_error_body(RejectedError("no"))
    assert body.code == "validation_failed"
    assert body.details["issues"][0]["path"] == "/x"
    assert body.details["issues"][0]["code"] == "secret.plain_found"

    # 기본 예외는 그대로 빈 목록(기존 동작).
    class PlainError(StoreError):
        code = "validation_failed"

    assert store_error_body(PlainError("x")).details == {"issues": []}


# ---------------------------------------------------------------- 기록 DB 위 버전 기록소


def _records(root: Path):  # type: ignore[no-untyped-def]
    return open_records_db(root / "records.sqlite3", (), backup_dir=root / ".state" / "backups")


def test_records_versions_read_without_creating_then_write_creates(tmp_path: Path) -> None:
    db = _records(tmp_path)
    repo = RecordsVersionRepository(lambda: db)
    assert isinstance(repo, VersionWriteCheck)
    assert repo.list("agent", "a") == []
    assert repo.get("agent", "a", "h") is None
    assert repo.saved_at("agent", "a", "h") is None
    assert repo.files("agent", "a", "h") is None
    assert repo.trim("agent", "a", keep=1) == 0
    assert repo.prune_blobs() == 0
    assert not (tmp_path / "records.sqlite3").exists()

    repo.record("agent", "a", "h1", {"id": "a"}, saved_at=1.0, message="first", files={"x": b"1"})
    assert (tmp_path / "records.sqlite3").exists()
    assert [v.version_hash for v in repo.list("agent", "a")] == ["h1"]
    got = repo.get("agent", "a", "h1")
    assert got is not None
    assert got.content == {"id": "a"}
    sha = (repo.files("agent", "a", "h1") or {})["x"]
    assert repo.read_blob(sha) == b"1"
    assert repo.blob_size(sha) == 1
    db.close()


def test_store_on_records_versions_keeps_history_in_that_file(tmp_path: Path) -> None:
    db = _records(tmp_path / "p")
    (tmp_path / "p").mkdir()
    store = FileDefinitionStore(
        tmp_path / "p" / "defs", versions=RecordsVersionRepository(lambda: db)
    )
    store.create("agent", {"id": "a", "name": "one"})
    store.save("agent", {"id": "a", "name": "two"})
    assert len(store.list_versions("agent", "a")) == 2
    db.close()
    # 다시 열어도(다른 경로로 복사해도) 같은 기록.
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "records.sqlite3").write_bytes((tmp_path / "p" / "records.sqlite3").read_bytes())
    again = _records(copy)
    assert len(RecordsVersionRepository(lambda: again).list("agent", "a")) == 2
    again.close()


def test_newer_records_db_refuses_writes(tmp_path: Path) -> None:
    seed = _records(tmp_path)
    seed.writable_engine()
    seed.close()
    raw = sqlite3.connect(tmp_path / "records.sqlite3")
    raw.execute("UPDATE alembic_version SET version_num = 'legacy_9999'")
    raw.commit()
    raw.close()
    db = _records(tmp_path)
    repo = RecordsVersionRepository(lambda: db)
    assert repo.list("agent", "a") == []  # 읽기는 된다
    with pytest.raises(RecordsUnavailable) as err:
        repo.ensure_writable()
    assert err.value.reason == "newer"
    assert store_error_body(err.value).code == "project.records_unavailable"
    db.close()


def test_observed_repository_forwards_ensure_writable() -> None:
    calls: list[str] = []

    class Checked(InMemoryVersionRepository):
        def ensure_writable(self) -> None:
            calls.append("x")

    observed = ObservedVersionRepository(Checked(), lambda *_: None)
    assert isinstance(observed, VersionWriteCheck)
    observed.ensure_writable()
    assert calls == ["x"]
    ObservedVersionRepository(InMemoryVersionRepository(), lambda *_: None).ensure_writable()


def test_mapped_spaces_example_implementation() -> None:
    from agent_console_store import MappedSpaces

    a = InMemoryDefinitionStore()
    spaces = MappedSpaces({"a": a})
    assert isinstance(spaces, DefinitionSpaces)
    stores = SpaceStores(InMemoryDefinitionStore(), lambda: spaces)
    assert stores.get("a") is a
    with pytest.raises(UnknownSpace):
        stores.get("b")
