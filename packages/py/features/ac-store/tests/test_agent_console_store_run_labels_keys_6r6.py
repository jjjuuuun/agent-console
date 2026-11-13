"""`run_labels` 표가 없는 계보(`runs_0003` 미만)에서 특수 문자가 든 라벨 키로 거르기(6R.6 후속).

예전에는 키를 JSON 경로(`$.labels."<키>"`)에 넣어 따옴표·역슬래시가 든 키를 SQLite가 찾지 못했다.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_console_contracts import Run
from agent_console_store import SqliteStorage, open_sqlite
from agent_console_store.schema import runs_labels_active

KEYS = ['a"b', "a\\b", "a.b", "a b", 'q"\\. x', "x"]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteStorage]:
    db = open_sqlite(tmp_path / "c.sqlite3")
    assert not runs_labels_active(db.engine)
    impl = SqliteStorage(db.engine)
    yield impl
    impl.close()


def _run(id: str, created_at: float, labels: dict[str, str]) -> Run:
    return Run(
        id=id, graph_id="g", graph_version="h", status="running", input={}, origin="api",
        created_at=created_at, labels=labels,
    )  # fmt: skip


@pytest.mark.parametrize("key", KEYS)
def test_label_filter_matches_special_keys_without_label_table(
    store: SqliteStorage, key: str
) -> None:
    store.runs.save(_run("hit", 1.0, {key: "v"}))
    store.runs.save(_run("other-value", 2.0, {key: "w"}))
    store.runs.save(_run("other-key", 3.0, {"zz": "v"}))
    store.runs.save(_run("none", 4.0, {}))
    page, _ = store.runs.page(labels={key: "v"})
    assert [r.id for r in page] == ["hit"]


def test_label_filter_requires_every_pair(store: SqliteStorage) -> None:
    store.runs.save(_run("both", 1.0, {'a"b': "1", "a.b": "2"}))
    store.runs.save(_run("one", 2.0, {'a"b': "1"}))
    page, _ = store.runs.page(labels={'a"b': "1", "a.b": "2"})
    assert [r.id for r in page] == ["both"]
