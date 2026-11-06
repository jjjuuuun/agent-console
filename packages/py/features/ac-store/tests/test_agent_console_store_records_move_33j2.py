"""5.7R.33j2: 표 단위 옮기기 도구(`RecordsMove`·`run_moves`) - 복사 -> 확인 -> 원본 삭제, 롤백."""

from __future__ import annotations

import hashlib
import time
from typing import Any

import pytest
import sqlalchemy as sa

from agent_console_store import (
    MoveDependent,
    MovePartialError,
    MoveSpec,
    MoveVerifyError,
    RecordsMove,
    run_moves,
)

DDL = (
    "create table parent (id text primary key, grp text, doc text not null)",
    "create table child (pid text not null, n integer not null, body text, primary key (pid, n))",
)
SPEC = MoveSpec("parent", dependents=(MoveDependent("child", "pid"),))


def make() -> sa.Engine:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool)
    with engine.begin() as c:
        for ddl in DDL:
            c.exec_driver_sql(ddl)
    return engine


def seed(engine: sa.Engine, parents: int, children: int = 2) -> None:
    with engine.begin() as c:
        c.execute(
            sa.text("insert into parent values (:id, 'g', :doc)"),
            [{"id": f"p{i:05d}", "doc": f'{{"i":{i}}}'} for i in range(parents)],
        )
        c.execute(
            sa.text("insert into child values (:pid, :n, :body)"),
            [
                {"pid": f"p{i:05d}", "n": n, "body": f"b{i}-{n}"}
                for i in range(parents)
                for n in range(children)
            ],
        )


def digest(engine: sa.Engine) -> str:
    h = hashlib.sha256()
    with engine.connect() as c:
        for sql in ("select * from parent order by id", "select * from child order by pid, n"):
            for row in c.exec_driver_sql(sql):
                h.update(repr(tuple(row)).encode())
    return h.hexdigest()


def count(engine: sa.Engine, table: str) -> int:
    with engine.connect() as c:
        return int(c.exec_driver_sql(f"select count(*) from {table}").scalar() or 0)


def test_move_preserves_rows_and_removes_source() -> None:
    src, dst = make(), make()
    seed(src, 5)
    before = digest(src)
    counts = run_moves([RecordsMove(src, dst, SPEC, ["p00000", "p00001", "p00002"])])
    assert (counts[0].moved, counts[0].skipped, counts[0].rows) == (3, 0, 9)
    assert (count(src, "parent"), count(src, "child")) == (2, 4)
    assert (count(dst, "parent"), count(dst, "child")) == (3, 6)
    run_moves([RecordsMove(src, dst, SPEC, ["p00003", "p00004"])])
    assert digest(dst) == before
    assert count(src, "parent") == 0


def test_second_run_skips_and_does_not_duplicate() -> None:
    src, dst = make(), make()
    seed(src, 2)
    run_moves([RecordsMove(src, dst, SPEC, ["p00000", "p00001"])], remove_source=False)
    again = run_moves([RecordsMove(src, dst, SPEC, ["p00000", "p00001"])], remove_source=False)
    assert (again[0].moved, again[0].skipped, again[0].rows) == (0, 2, 0)
    assert (count(dst, "parent"), count(dst, "child")) == (2, 4)
    assert count(src, "parent") == 2  # remove_source=False -> 원본 남음


def test_transform_and_missing_columns() -> None:
    src, dst = make(), make()
    seed(src, 1)
    with dst.begin() as c:  # 대상에만 있는 열은 기본값, 원본에만 있는 열은 버린다
        c.exec_driver_sql("alter table parent add column extra text default 'x'")
    with src.begin() as c:
        c.exec_driver_sql("alter table parent add column only_src text")

    def transform(table: str, row: dict[str, Any]) -> dict[str, Any]:
        if table == "parent":
            row["grp"] = "moved"
        return row

    spec = MoveSpec("parent", dependents=SPEC.dependents, transform=transform)
    run_moves([RecordsMove(src, dst, spec, ["p00000"])])
    with dst.connect() as c:
        row = c.exec_driver_sql("select grp, extra from parent").one()
    assert tuple(row) == ("moved", "x")


def test_expand_moves_members() -> None:
    src, dst = make(), make()
    seed(src, 3)

    def expand(conn: sa.Connection, units):  # type: ignore[no-untyped-def]
        return [*units, "p00002"]

    spec = MoveSpec("parent", dependents=SPEC.dependents, expand=expand)
    counts = run_moves([RecordsMove(src, dst, spec, ["p00000"])])
    assert counts[0].moved == 2
    assert count(dst, "child") == 4


def test_copy_failure_leaves_both_sides_unchanged() -> None:
    src, dst = make(), make()
    seed(src, 3)
    with dst.begin() as c:
        c.exec_driver_sql("drop table child")  # 딸린 표가 없다 -> 복사 도중 실패
    before = digest(src) if False else count(src, "parent")
    with pytest.raises(Exception, match="target table not found"):
        run_moves([RecordsMove(src, dst, SPEC, ["p00000", "p00001"])])
    assert count(dst, "parent") == 0  # 대상 트랜잭션 롤백
    assert count(src, "parent") == before == 3
    assert count(src, "child") == 6


def test_verify_failure_rolls_back_all_moves() -> None:
    src, dst = make(), make()
    seed(src, 2)
    good = RecordsMove(src, dst, MoveSpec("parent", dependents=SPEC.dependents), ["p00000"])

    class Bad(RecordsMove):
        def verify(self) -> None:
            raise MoveVerifyError("parent", 1, 0)

    bad = Bad(src, dst, MoveSpec("parent", dependents=SPEC.dependents), ["p00001"])
    with pytest.raises(MoveVerifyError):
        run_moves([good, bad])
    assert count(dst, "parent") == 0
    assert count(dst, "child") == 0
    assert count(src, "parent") == 2


def test_verify_detects_changed_value() -> None:
    src, dst = make(), make()
    seed(src, 1)
    move = RecordsMove(src, dst, SPEC, ["p00000"])
    move.copy()
    with dst.begin() as c:
        c.exec_driver_sql("update child set body='tampered' where n=0")
    with pytest.raises(MoveVerifyError):
        move.verify()
    move.rollback()
    assert count(dst, "parent") == 0
    assert count(dst, "child") == 0


def test_first_delete_failure_rolls_back_target_later_failure_is_partial() -> None:
    src, dst = make(), make()
    seed(src, 2)

    class FailDelete(RecordsMove):
        def delete_source(self) -> int:
            raise RuntimeError("boom")

    first = FailDelete(src, dst, SPEC, ["p00000"])
    with pytest.raises(RuntimeError):
        run_moves([first])
    assert count(dst, "parent") == 0
    assert count(src, "parent") == 2

    a = RecordsMove(src, dst, SPEC, ["p00000"])
    b = FailDelete(src, dst, SPEC, ["p00001"])
    with pytest.raises(MovePartialError):  # 뒤에서부터: a가 먼저 지워지고... b가 실패
        run_moves([b, a])
    assert count(dst, "parent") == 2  # 사본은 지킨다
    assert count(src, "parent") == 1


def test_ten_thousand_rows_time() -> None:
    src, dst = make(), make()
    seed(src, 10_000, children=1)
    before = digest(src)
    started = time.perf_counter()
    run_moves([RecordsMove(src, dst, SPEC, [f"p{i:05d}" for i in range(10_000)])])
    elapsed = time.perf_counter() - started
    print(f"records_move 10k parents + 10k children: {elapsed:.2f}s")
    assert digest(dst) == before
    assert count(src, "parent") == 0
    assert elapsed < 30
