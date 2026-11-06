"""6R.6: 실행 라벨 표(`runs_0004`)·커서 페이지·자손 질의 - 마이그레이션 up/down, 경계, 성능."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_contracts import Run
from agent_console_mod_runs.storage import BRANCH
from agent_console_store import (
    InMemoryStorage,
    InvalidCursor,
    SqliteDatabase,
    SqliteStorage,
    create_sqlite_engine,
    upgrade,
)


def mk(id: str, at: float, **kw: Any) -> Run:
    fields: dict[str, Any] = {
        "id": id, "graph_id": "g", "graph_version": "h", "status": "completed",
        "input": {}, "origin": "api", "created_at": at,
    }  # fmt: skip
    fields.update(kw)
    return Run(**fields)


def label_rows(engine: sa.Engine) -> set[tuple[str, str, str]]:
    with engine.connect() as c:
        return {
            (str(r[0]), str(r[1]), str(r[2]))
            for r in c.exec_driver_sql("SELECT run_id, key, value FROM run_labels")
        }


def plan(engine: sa.Engine, sql: str) -> str:
    with engine.connect() as c:
        return " ".join(str(r[3]) for r in c.exec_driver_sql("EXPLAIN QUERY PLAN " + sql))


@pytest.fixture
def db(tmp_path: Path) -> Any:
    found = SqliteDatabase.open(tmp_path / "l.sqlite3")
    found.upgrade([BRANCH])
    yield found
    found.close()


@pytest.fixture(params=["sqlite", "memory"])
def storage(request: pytest.FixtureRequest, db: SqliteDatabase) -> Any:
    return SqliteStorage(db.engine) if request.param == "sqlite" else InMemoryStorage()


# ---- 마이그레이션 ------------------------------------------------------------


def test_table_pk_and_index(db: SqliteDatabase) -> None:
    insp = sa.inspect(db.engine)
    assert list(insp.get_pk_constraint("run_labels")["constrained_columns"]) == ["run_id", "key"]
    [idx] = [i for i in insp.get_indexes("run_labels") if i["name"] == "ix_run_labels_kv"]
    assert idx["column_names"] == ["key", "value", "run_id"]


def test_downgrade_drops_table_and_reupgrade_backfills_from_doc(db: SqliteDatabase) -> None:
    store = SqliteStorage(db.engine)
    store.runs.save(mk("a", 1.0, labels={"k": "v", "z": ""}))
    store.runs.save(mk("c", 2.0, root_run_id="a", parent_run_id="a", labels={"k": "child"}))
    assert label_rows(db.engine) == {("a", "k", "v"), ("a", "z", "")}  # 자식 라벨은 표에 없다
    db.downgrade_branch(BRANCH, "runs_0003")
    assert db.revision("runs") == "runs_0003"
    assert "run_labels" not in sa.inspect(db.engine).get_table_names()
    old = SqliteStorage(db.engine)  # 표 없는 DB: doc만으로 읽고 거른다
    got = old.runs.get("a")
    assert got is not None
    assert got.labels == {"k": "v", "z": ""}
    items, _ = old.runs.page(labels={"k": "v"})
    assert [r.id for r in items] == ["a"]
    db.upgrade([BRANCH])
    assert label_rows(db.engine) == {("a", "k", "v"), ("a", "z", "")}
    db.downgrade_branch(BRANCH)
    assert db.revision("runs") is None
    db.upgrade([BRANCH])
    assert label_rows(db.engine) == {("a", "k", "v"), ("a", "z", "")}


def test_5r_style_database_without_labels_reads_empty(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "old.sqlite3")
    upgrade(engine)  # legacy만
    store = SqliteStorage(engine)
    store.runs.save(mk("a", 1.0))
    got = store.runs.get("a")
    assert got is not None
    assert got.labels == {}


# ---- 저장·삭제 ---------------------------------------------------------------


def test_save_replaces_label_rows_and_delete_removes_them(db: SqliteDatabase) -> None:
    store = SqliteStorage(db.engine)
    store.runs.save(mk("a", 1.0, labels={"k": "v", "x": "1"}))
    store.runs.save(mk("a", 1.0, labels={"k": "w"}))  # 전체 교체
    assert label_rows(db.engine) == {("a", "k", "w")}
    store.runs.save(mk("a", 1.0))
    assert label_rows(db.engine) == set()
    store.runs.save(mk("a", 1.0, labels={"k": "v"}))
    assert store.runs.delete("a")
    assert label_rows(db.engine) == set()


# ---- 커서 페이지 -------------------------------------------------------------


def walk(store: Any, limit: int, **kw: Any) -> list[list[str]]:
    pages, cursor = [], None
    while True:
        items, cursor = store.runs.page(cursor=cursor, limit=limit, **kw)
        pages.append([r.id for r in items])
        if cursor is None:
            return pages


def test_page_walks_everything_once_with_same_timestamps(storage: Any) -> None:
    for i in range(7):  # 같은 시각 5개 + 앞뒤
        storage.runs.save(mk(f"r{i}", 5.0 if 1 <= i <= 5 else float(i)))
    pages = walk(storage, 2)
    flat = [i for p in pages for i in p]
    assert flat == ["r6", "r5", "r4", "r3", "r2", "r1", "r0"]  # created_at desc, id desc
    assert [len(p) for p in pages] == [2, 2, 2, 1]
    assert walk(storage, 7) == [flat]  # 딱 맞으면 다음 커서 없음
    assert walk(storage, 50) == [flat]


def test_page_boundary_when_runs_inserted_and_deleted_between_pages(storage: Any) -> None:
    for i in range(6):
        storage.runs.save(mk(f"r{i}", float(i)))
    first, cursor = storage.runs.page(limit=2)
    assert [r.id for r in first] == ["r5", "r4"]
    assert cursor
    storage.runs.save(mk("new", 100.0))  # 맨 앞에 새로 들어옴 -> 겹치지 않음
    storage.runs.delete("r4")  # 읽은 행 삭제 -> 빠지지 않음
    storage.runs.delete("r3")  # 아직 안 읽은 행 삭제
    second, cursor = storage.runs.page(cursor=cursor, limit=2)
    assert [r.id for r in second] == ["r2", "r1"]
    third, cursor = storage.runs.page(cursor=cursor, limit=2)
    assert [r.id for r in third] == ["r0"]
    assert cursor is None


def test_page_filters_and_label_and(storage: Any) -> None:
    storage.runs.save(mk("a", 1.0, project_id="p", labels={"sdd.spec": "s1", "sdd.task": "t1"}))
    storage.runs.save(mk("b", 2.0, project_id="p", labels={"sdd.spec": "s1", "sdd.task": "t2"}))
    storage.runs.save(mk("c", 3.0, project_id="q", labels={"sdd.spec": "s1"}))
    storage.runs.save(mk("d", 4.0, project_id="p", status="failed"))
    storage.runs.save(mk("e", 5.0, project_id="p", root_run_id="a", parent_run_id="a"))

    def ids(**kw: Any) -> list[str]:
        return [i for p in walk(storage, 2, **kw) for i in p]

    assert ids(labels={"sdd.spec": "s1"}) == ["c", "b", "a"]
    assert ids(labels={"sdd.spec": "s1", "sdd.task": "t2"}) == ["b"]  # AND
    assert ids(labels={"sdd.spec": "s1"}, project_id="p") == ["b", "a"]
    assert ids(labels={"sdd.spec": "s2"}) == []
    assert ids(labels={"sdd.spec": "s1", "no": "x"}) == []
    assert ids(root_only=True, project_id="p") == ["d", "b", "a"]
    assert ids(status=["failed"]) == ["d"]
    assert ids(graph_id="nope") == []
    assert ids() == ["e", "d", "c", "b", "a"]


def test_label_with_odd_characters(storage: Any) -> None:
    storage.runs.save(mk("a", 1.0, labels={"한글 키": '값 "인용"'}))
    items, _ = storage.runs.page(labels={"한글 키": '값 "인용"'})
    assert [r.id for r in items] == ["a"]


def test_invalid_cursor(storage: Any) -> None:
    for bad in ("###", "e30", "W10", "bm90LWpzb24"):
        with pytest.raises(InvalidCursor):
            storage.runs.page(cursor=bad)


def test_descendants_in_creation_order(storage: Any) -> None:
    storage.runs.save(mk("root", 1.0))
    storage.runs.save(mk("c2", 3.0, root_run_id="root", parent_run_id="c1"))
    storage.runs.save(mk("c1", 2.0, root_run_id="root", parent_run_id="root"))
    storage.runs.save(mk("other", 2.5, root_run_id="x"))
    assert [r.id for r in storage.runs.descendants("root")] == ["c1", "c2"]
    assert storage.runs.descendants("none") == []


# ---- 성능·질의 계획 ----------------------------------------------------------


def test_label_query_100k_runs_uses_index_and_is_fast(db: SqliteDatabase) -> None:
    n = 100_000
    with db.engine.begin() as c:
        rows = [
            (
                f"r{i:06d}", "g", "h", "completed", "api", float(i), None, None,
                f'{{"id":"r{i:06d}","labels":{{"sdd.spec":"s{i % 1000}"}}}}',
            )
            for i in range(n)
        ]  # fmt: skip
        raw = c.connection
        raw.executemany(
            "INSERT INTO runs (id, graph_id, graph_version, status, origin, created_at,"
            " started_at, ended_at, doc) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        raw.executemany(
            "INSERT INTO run_labels (run_id, key, value) VALUES (?,?,?)",
            [(f"r{i:06d}", "sdd.spec", f"s{i % 1000}") for i in range(n)],
        )
    store = SqliteStorage(db.engine)

    def real_doc(i: int) -> str:
        return mk(f"r{i:06d}", float(i), labels={"sdd.spec": f"s{i % 1000}"}).model_dump_json()

    with db.engine.begin() as c:  # 읽을 행만 진짜 doc으로(검증 통과)
        for i in range(7, n, 1000):
            c.exec_driver_sql("UPDATE runs SET doc=? WHERE id=?", (real_doc(i), f"r{i:06d}"))
    started = time.perf_counter()
    items, cursor = store.runs.page(labels={"sdd.spec": "s7"}, limit=20)
    elapsed = time.perf_counter() - started
    assert [r.id for r in items][:2] == ["r099007", "r098007"]
    assert len(items) == 20
    assert cursor is not None
    assert elapsed < 0.1
    sql = (
        "SELECT doc FROM runs WHERE id IN (SELECT run_id FROM run_labels"
        " WHERE key='sdd.spec' AND value='s7') ORDER BY created_at DESC, id DESC LIMIT 21"
    )
    assert "ix_run_labels_kv" in plan(db.engine, sql)


def test_descendants_1000_in_100ms_with_root_index(db: SqliteDatabase) -> None:
    store = SqliteStorage(db.engine)
    store.runs.save(mk("root", 0.0))
    with db.engine.begin() as c:
        for i in range(1000):
            doc = mk(
                f"c{i:04d}", float(i + 1), root_run_id="root", parent_run_id="root"
            ).model_dump_json()
            c.exec_driver_sql(
                "INSERT INTO runs (id, graph_id, graph_version, status, origin, created_at,"
                " parent_run_id, root_run_id, doc) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"c{i:04d}", "g", "h", "completed", "api", float(i + 1), "root", "root", doc),
            )
    started = time.perf_counter()
    found = store.runs.descendants("root")
    assert time.perf_counter() - started < 0.1
    assert len(found) == 1000
    sql = "SELECT doc FROM runs WHERE root_run_id='root' ORDER BY created_at, id"
    assert "ix_runs_root" in plan(db.engine, sql)
