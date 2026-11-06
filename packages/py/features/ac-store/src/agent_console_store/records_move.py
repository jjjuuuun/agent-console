"""앱 DB 기록을 프로젝트 기록 DB로 옮기는 표 단위 도구(design §PI.4.6.7, K33-32, 5.7R.33j2).

도메인(Run·대화)을 모른다. 호출자가 "기본 표 + 딸린 표 + 한 묶음(unit)의 id 목록"을 정하면
`RecordsMove`가 두 엔진 사이에서 아래 순서로 옮긴다.

1. `copy()` - 대상에 같은 기본 키가 이미 있는 묶음은 `skipped`로 두고, 나머지의 기본 표 행과 딸린 표
   행을 **대상 한 트랜잭션**으로 넣는다(중간에 실패하면 아무것도 남지 않는다).
2. `verify()` - 대상에서 다시 읽어 행 수와 값이 원본(변환 적용)과 같은지 본다.
   다르면 `MoveVerifyError`.
3. `delete_source()` - 원본의 같은 행을 **원본 한 트랜잭션**으로 지운다(`remove_source`일 때만).
4. `rollback()` - 1에서 넣은 행을 대상에서 지운다(2·3이 실패했을 때 되돌리기).

표 모양은 두 DB에서 읽어 **공통 열만** 옮긴다(타입 처리를 거치지 않고 값을 그대로 옮긴다).
원본에 없는 열은 대상의 기본값, 대상에 없는 열은 버린다. `transform`이 행을 고칠 수 있다
(예: `project_id` 바꾸기, 새 열 채우기).

>>> import sqlalchemy as sa
>>> src, dst = sa.create_engine("sqlite://"), sa.create_engine("sqlite://")
>>> for e in (src, dst):
...     with e.begin() as c:
...         _ = c.exec_driver_sql("create table a (id text primary key, v text)")
...         _ = c.exec_driver_sql("create table b (a_id text, n integer, primary key (a_id, n))")
>>> with src.begin() as c:
...     _ = c.exec_driver_sql("insert into a values ('x', '1'), ('y', '2')")
...     _ = c.exec_driver_sql("insert into b values ('x', 1), ('x', 2)")
>>> spec = MoveSpec("a", dependents=(MoveDependent("b", "a_id"),))
>>> move = RecordsMove(src, dst, spec, ["x", "y"])
>>> move.copy()
MoveCounts(moved=2, skipped=0, rows=4)
>>> move.verify()
>>> move.delete_source()
4
>>> with src.connect() as c:
...     c.exec_driver_sql("select count(*) from a").scalar()
0
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .errors import StoreError

CHUNK = 500
"""`IN` 목록 한 번에 다루는 최대 개수(SQLite 변수 한도 아래)."""

type Row = dict[str, Any]
type Transform = Callable[[str, Row], Row]
type Expand = Callable[[Connection, Sequence[str]], list[str]]


class MoveError(StoreError):
    """옮기기 실패(표가 없음 등) -> `internal`."""


class MoveVerifyError(MoveError):
    """복사 뒤 확인에서 원본과 다르다. `table`·`expected`·`actual`로 어디가 다른지 알린다."""

    def __init__(self, table: str, expected: int, actual: int, message: str = "") -> None:
        super().__init__(message or f"move verify failed: {table} expected={expected} got={actual}")
        self.table = table
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class MoveDependent:
    """기본 표 행에 딸린 표: `column`의 값이 옮길 기본 표 행의 키이면 함께 옮긴다."""

    table: str
    column: str


@dataclass(frozen=True, slots=True)
class MoveSpec:
    """옮길 표 구성.

    Attributes:
        table: 기본 표(묶음 id가 `key` 열의 값이다).
        key: 기본 표의 키 열.
        dependents: 딸린 표(없는 표는 원본에 행이 없을 때만 건너뛴다).
        expand: 묶음 id -> 함께 옮길 기본 표 행 키(묶음 자신 포함). 없으면 묶음 자신만.
            예: 루트 Run -> 자손 Run까지.
        transform: `(표 이름, 행) -> 행`. 대상 표에 있는 열만 쓰인다.
    """

    table: str
    key: str = "id"
    dependents: Sequence[MoveDependent] = ()
    expand: Expand | None = None
    transform: Transform | None = None


@dataclass(frozen=True, slots=True)
class MoveCounts:
    """`copy()` 결과: 옮긴 기본 표 행 수, 건너뛴 묶음 수, 옮긴 전체 행 수(딸린 표 포함)."""

    moved: int
    skipped: int
    rows: int


@dataclass(slots=True)
class _Plan:
    members: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _chunks(items: Sequence[str]) -> Iterator[list[str]]:
    for i in range(0, len(items), CHUNK):
        yield list(items[i : i + CHUNK])


def _columns(engine: Engine | Connection, table: str) -> list[str] | None:
    inspector = sa.inspect(engine)
    if table not in inspector.get_table_names():
        return None
    return [c["name"] for c in inspector.get_columns(table)]


def _pk(engine: Engine | Connection, table: str, columns: Sequence[str]) -> list[str]:
    got = sa.inspect(engine).get_pk_constraint(table).get("constrained_columns") or []
    return list(got) or list(columns)


def _untyped(name: str, columns: Sequence[str]) -> sa.TableClause:
    """타입 처리가 없는 가벼운 표(JSON·날짜 열도 저장된 값 그대로 오간다)."""
    return sa.table(name, *[sa.column(c) for c in columns])


class RecordsMove:
    """묶음(unit) id 목록을 `source` 엔진에서 `target` 엔진으로 옮기는 한 번의 작업.

    Args:
        source: 원본(앱 DB) 엔진.
        target: 대상(프로젝트 기록 DB) 쓰기 엔진.
        spec: 표 구성.
        units: 옮길 묶음 id(중복은 한 번만).
    """

    def __init__(self, source: Engine, target: Engine, spec: MoveSpec, units: Sequence[str]):
        self._source = source
        self._target = target
        self._spec = spec
        self._units = list(dict.fromkeys(units))
        self._plan: _Plan | None = None
        self._copied = False

    # ------------------------------------------------------------------ 조회

    @property
    def skipped_units(self) -> list[str]:
        """`copy()`가 대상에 같은 키가 있어 건너뛴 묶음 id."""
        return list(self._plan.skipped) if self._plan else []

    @property
    def members(self) -> list[str]:
        """`copy()`가 옮긴 기본 표 행 키(묶음 + 확장)."""
        return list(self._plan.members) if self._plan else []

    def conflicts(self) -> list[str]:
        """대상에 이미 같은 키가 있어 `copy()`가 건너뛸 묶음 id(아무것도 쓰지 않는다)."""
        spec = self._spec
        with self._target.connect() as dst:
            if _columns(dst, spec.table) is None:
                return []
            found = self._existing_keys(dst, spec.table, spec.key, self._units)
        return [u for u in self._units if u in found]

    def _tables(self) -> list[tuple[str, str, str]]:
        """(표, 선택 열, 종류) - 기본 표가 먼저."""
        spec = self._spec
        out = [(spec.table, spec.key, "main")]
        out.extend((d.table, d.column, "dep") for d in spec.dependents)
        return out

    # ------------------------------------------------------------------ 1. 복사

    def copy(self) -> MoveCounts:
        """대상에 넣는다(한 트랜잭션). 이미 `copy()`했으면 `MoveError`.

        Raises:
            MoveError: 기본 표가 없거나, 딸린 표 행이 있는데 대상에 그 표가 없다.
        """
        if self._copied:
            raise MoveError("copy() was already called")
        spec = self._spec
        with self._source.connect() as src, self._target.begin() as dst:
            src_cols = _columns(src, spec.table)
            dst_cols = _columns(dst, spec.table)
            if src_cols is None or dst_cols is None:
                raise MoveError(f"table not found: {spec.table}")
            existing = self._existing_keys(dst, spec.table, spec.key, self._units)
            fresh = [u for u in self._units if u not in existing]
            members = spec.expand(src, fresh) if spec.expand is not None and fresh else fresh
            members = list(dict.fromkeys(members))
            plan = _Plan(members=members, skipped=[u for u in self._units if u in existing])
            rows = 0
            for table, column, kind in self._tables():
                rows += self._copy_table(src, dst, table, column, members, main=kind == "main")
            self._plan = plan
            self._copied = True
        return MoveCounts(moved=len(members), skipped=len(plan.skipped), rows=rows)

    @staticmethod
    def _existing_keys(conn: Connection, table: str, key: str, ids: Sequence[str]) -> set[str]:
        out: set[str] = set()
        tbl = _untyped(table, [key])
        for chunk in _chunks(ids):
            out.update(
                str(r[0]) for r in conn.execute(sa.select(tbl.c[key]).where(tbl.c[key].in_(chunk)))
            )
        return out

    def _transform(self, table: str, row: Row) -> Row:
        fn = self._spec.transform
        return fn(table, dict(row)) if fn is not None else row

    def _prepare(
        self, src: Connection, dst: Connection, table: str
    ) -> tuple[sa.TableClause, sa.TableClause, list[str]] | None:
        """(원본 표, 대상 표, 공통 열). 원본에 표가 없으면 None."""
        src_cols = _columns(src, table)
        if src_cols is None:
            return None
        dst_cols = _columns(dst, table)
        if dst_cols is None:
            return None
        return _untyped(table, src_cols), _untyped(table, dst_cols), dst_cols

    def _copy_table(
        self,
        src: Connection,
        dst: Connection,
        table: str,
        column: str,
        members: Sequence[str],
        *,
        main: bool,
    ) -> int:
        prepared = self._prepare(src, dst, table)
        if prepared is None:
            if _columns(src, table) is not None:  # 원본에는 있는데 대상에 표가 없다
                has = any(True for _ in self._select(src, table, column, members, limit_one=True))
                if has:
                    raise MoveError(f"target table not found: {table}")
            return 0
        s_tbl, d_tbl, d_cols = prepared
        copied = 0
        for rows in self._select_chunks(src, s_tbl, column, members):
            payload = [self._project(self._transform(table, r), d_cols) for r in rows]
            if not payload:
                continue
            stmt = sqlite_insert(d_tbl)
            if not main:
                stmt = stmt.on_conflict_do_nothing()
            result = dst.execute(stmt, payload)
            copied += max(result.rowcount, 0)
        return copied

    @staticmethod
    def _project(row: Row, columns: Sequence[str]) -> Row:
        return {c: row[c] for c in columns if c in row}

    @staticmethod
    def _select_chunks(
        conn: Connection, tbl: sa.TableClause, column: str, members: Sequence[str]
    ) -> Iterator[list[Row]]:
        for chunk in _chunks(members):
            rows = conn.execute(sa.select(tbl).where(tbl.c[column].in_(chunk)))
            yield [dict(r._mapping) for r in rows]

    def _select(
        self,
        conn: Connection,
        table: str,
        column: str,
        members: Sequence[str],
        *,
        limit_one: bool = False,
    ) -> Iterator[Row]:
        cols = _columns(conn, table) or []
        tbl = _untyped(table, cols)
        for chunk in _chunks(members):
            stmt = sa.select(tbl).where(tbl.c[column].in_(chunk))
            if limit_one:
                stmt = stmt.limit(1)
            for r in conn.execute(stmt):
                yield dict(r._mapping)

    # ------------------------------------------------------------------ 2. 확인

    def verify(self) -> None:
        """대상의 행 수와 값이 원본(변환 적용)과 같은지 본다.

        Raises:
            MoveVerifyError: 다르다.
        """
        plan = self._need_plan()
        if not plan.members:
            return
        with self._source.connect() as src, self._target.connect() as dst:
            for table, column, _ in self._tables():
                prepared = self._prepare(src, dst, table)
                if prepared is None:
                    continue
                s_tbl, d_tbl, d_cols = prepared
                pk = _pk(dst, table, d_cols)
                expected = 0
                actual = 0
                for chunk in _chunks(plan.members):
                    want = {
                        self._key(row, pk): row
                        for row in (
                            self._project(self._transform(table, dict(r._mapping)), d_cols)
                            for r in src.execute(sa.select(s_tbl).where(s_tbl.c[column].in_(chunk)))
                        )
                    }
                    got = {
                        self._key(dict(r._mapping), pk): dict(r._mapping)
                        for r in dst.execute(sa.select(d_tbl).where(d_tbl.c[column].in_(chunk)))
                    }
                    expected += len(want)
                    actual += len(got)
                    for k, row in want.items():
                        found = got.get(k)
                        if found is None or any(found.get(c) != v for c, v in row.items()):
                            raise MoveVerifyError(
                                table, expected, actual, f"move verify failed: {table} row {k}"
                            )
                if expected != actual:
                    raise MoveVerifyError(table, expected, actual)

    @staticmethod
    def _key(row: Row, pk: Sequence[str]) -> tuple[Any, ...]:
        return tuple(row.get(c) for c in pk)

    # ------------------------------------------------------------------ 3·4. 지우기

    def delete_source(self) -> int:
        """원본의 옮긴 행을 한 트랜잭션으로 지운다. 지운 전체 행 수를 돌려준다."""
        plan = self._need_plan()
        return self._delete(self._source, plan.members, deps_first=True)

    def rollback(self) -> int:
        """`copy()`가 대상에 넣은 행을 지운다(한 트랜잭션). 지운 전체 행 수."""
        plan = self._plan
        if plan is None or not plan.members:
            return 0
        return self._delete(self._target, plan.members, deps_first=True)

    def _delete(self, engine: Engine, members: Sequence[str], *, deps_first: bool) -> int:
        order = list(reversed(self._tables())) if deps_first else self._tables()
        removed = 0
        with engine.begin() as conn:
            for table, column, _ in order:
                cols = _columns(conn, table)
                if cols is None:
                    continue
                tbl = _untyped(table, cols)
                for chunk in _chunks(members):
                    removed += max(
                        conn.execute(sa.delete(tbl).where(tbl.c[column].in_(chunk))).rowcount, 0
                    )
        return removed

    def _need_plan(self) -> _Plan:
        if self._plan is None:
            raise MoveError("copy() was not called")
        return self._plan


class MovePartialError(MoveError):
    """원본 지우기가 일부만 끝났다(대상 사본은 남아 있다). 다시 옮기면 이미 있어 건너뛴다."""


def run_moves(moves: Sequence[RecordsMove], *, remove_source: bool = True) -> list[MoveCounts]:
    """여러 `RecordsMove`를 하나로 옮긴다: 모두 복사 -> 모두 확인 -> 원본 지우기.

    복사나 확인이 실패하면 이미 넣은 대상 행을 모두 되돌리고(원본은 그대로) 예외를 다시 던진다.
    원본 지우기는 `moves`의 **뒤에서부터** 한다. 첫 지우기가 실패하면 대상을 되돌리고, 그 뒤에
    실패하면(일부 원본만 지워진 상태) 대상 사본을 지키고 `MovePartialError`를 던진다.

    Returns:
        `moves`와 같은 순서의 `MoveCounts`.
    """
    counts: list[MoveCounts] = []
    try:
        for move in moves:
            counts.append(move.copy())
        for move in moves:
            move.verify()
    except Exception:
        for move in moves:
            move.rollback()
        raise
    if not remove_source:
        return counts
    for deleted, move in enumerate(reversed(moves)):
        try:
            move.delete_source()
        except Exception as exc:
            if deleted == 0:
                for each in moves:
                    each.rollback()
                raise
            raise MovePartialError(f"source delete incomplete: {exc}") from exc
    return counts


__all__ = [
    "MoveCounts",
    "MoveDependent",
    "MoveError",
    "MovePartialError",
    "MoveSpec",
    "MoveVerifyError",
    "RecordsMove",
    "run_moves",
]
