"""mod-usage 저장소: 관측값 규칙, 마이그레이션 계보, 기존 DB(0003) 호환(design §3R.1.7)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from agent_console_contracts import UsageWindowSnapshot
from agent_console_mod_usage.storage import (
    BRANCH,
    TABLE_NAME,
    InMemoryUsageObservationRepository,
    SqliteUsageObservationRepository,
    metadata,
)
from agent_console_store import SqliteDatabase, create_sqlite_engine, upgrade


@pytest.fixture(params=["sqlite", "memory"])
def repo(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Any]:
    if request.param == "memory":
        yield InMemoryUsageObservationRepository()
        return
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])
    yield SqliteUsageObservationRepository(db.engine)
    db.close()


def snap(source: str, window: str, at: float, **kw: Any) -> UsageWindowSnapshot:
    return UsageWindowSnapshot(source=source, window=window, observed_at=at, **kw)


def test_latest_per_source_and_window(repo: Any) -> None:
    repo.record(snap("sdk", "five_hour", 1.0, used_ratio=0.1))
    repo.record(snap("sdk", "five_hour", 3.0, used_ratio=0.3, status="allowed"))
    repo.record(snap("sdk", "seven_day", 2.0, used_ratio=0.5, raw={"a": [1]}))
    repo.record(snap("statusline-file", "five_hour", 2.5, used_ratio=0.2))
    latest = repo.latest()
    assert [(s.source, s.window, s.observed_at) for s in latest] == [
        ("sdk", "five_hour", 3.0),
        ("sdk", "seven_day", 2.0),
        ("statusline-file", "five_hour", 2.5),
    ]
    assert latest[0].status == "allowed"
    assert latest[1].raw == {"a": [1]}
    assert [s.window for s in repo.latest(source="sdk")] == ["five_hour", "seven_day"]
    assert repo.latest(source="none") == []


def test_keeps_missing_values_as_none_and_is_idempotent(repo: Any) -> None:
    repo.record(snap("fake", "w", 1.0))
    repo.record(snap("fake", "w", 1.0, used_ratio=0.5))  # 같은 키 = 교체
    got = repo.history("fake", "w")
    assert len(got) == 1
    assert got[0].used_ratio == 0.5
    repo.record(snap("fake", "w2", 1.0))
    only = repo.latest(source="fake")
    assert only[1].used_ratio is None
    assert only[1].used_tokens is None


def test_history_order_since_limit_and_prune(repo: Any) -> None:
    for at in (1.0, 2.0, 3.0, 4.0):
        repo.record(snap("s", "w", at, used_ratio=at / 10))
    assert [h.observed_at for h in repo.history("s", "w")] == [4.0, 3.0, 2.0, 1.0]
    assert [h.observed_at for h in repo.history("s", "w", since=3.0)] == [4.0, 3.0]
    assert [h.observed_at for h in repo.history("s", "w", limit=1)] == [4.0]
    assert repo.prune(3.0) == 2
    assert [h.observed_at for h in repo.history("s", "w")] == [4.0, 3.0]
    assert repo.prune(3.0) == 0


def test_sqlite_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "u.sqlite3"
    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    SqliteUsageObservationRepository(db.engine).record(snap("s", "w", 1.0, used_ratio=0.2))
    db.close()
    again = SqliteDatabase.open(path)
    again.upgrade([BRANCH])
    assert SqliteUsageObservationRepository(again.engine).latest()[0].used_ratio == 0.2
    again.close()


# ---- 마이그레이션 계보 ----------------------------------------------------


def test_table_definition_matches_legacy_migration(tmp_path: Path) -> None:
    """테이블은 불변: legacy 0002가 만든 모양과 이 모듈의 정의가 같다."""
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])

    def only_usage(obj: object, name: str | None, type_: str, *_: object) -> bool:
        table = obj if type_ == "table" else getattr(obj, "table", None)
        return getattr(table, "name", name) == TABLE_NAME

    with db.engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"include_object": only_usage})
        assert compare_metadata(context, metadata) == []
    db.close()


def test_upgrade_on_empty_db_creates_table_and_branch_version(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])
    assert TABLE_NAME in sa.inspect(db.engine).get_table_names()
    assert db.revision() == "0003"
    assert db.revision("usage") == "usage_0001"
    index_names = {i["name"] for i in sa.inspect(db.engine).get_indexes(TABLE_NAME)}
    assert "ix_usage_observations_observed" in index_names
    db.close()


def test_branch_downgrade_and_reapply_keeps_table_and_data(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "u.sqlite3")
    db.upgrade([BRANCH])
    repo = SqliteUsageObservationRepository(db.engine)
    repo.record(snap("s", "w", 1.0))
    db.downgrade_branch(BRANCH)
    assert db.revision("usage") is None
    assert len(repo.latest()) == 1  # 테이블은 legacy 소유라 그대로
    db.upgrade([BRANCH])
    assert db.revision("usage") == "usage_0001"
    db.close()


def test_existing_0003_database_keeps_observations(tmp_path: Path) -> None:
    """3R.11 이전에 만든 DB(0003 + 관측값 행)를 새 구성이 그대로 읽는다."""
    path = tmp_path / "old.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)
    doc = snap("sdk", "five_hour", 5.0, used_ratio=0.4).model_dump_json()
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO usage_observations "
            "(source, window_id, observed_at, used_ratio, doc) "
            "VALUES ('sdk', 'five_hour', 5.0, 0.4, ?)",
            (doc,),
        )
    engine.dispose()
    db = SqliteDatabase.open(path)
    db.upgrade([BRANCH])
    [row] = SqliteUsageObservationRepository(db.engine).latest()
    assert (row.source, row.window, row.used_ratio) == ("sdk", "five_hour", 0.4)
    assert db.revision() == "0003"
    db.close()


def test_migration_scripts_are_package_data_and_work_after_copy(tmp_path: Path) -> None:
    """스크립트가 패키지 안에 있고, 폴더를 다른 곳에 복사해도 빈 DB에서 upgrade 된다(P9)."""
    assert BRANCH.versions.is_dir()
    assert list(BRANCH.versions.glob("usage_0001*.py"))
    copied = tmp_path / "elsewhere" / "versions"
    shutil.copytree(BRANCH.versions, copied, ignore=shutil.ignore_patterns("__pycache__"))
    db = SqliteDatabase.open(tmp_path / "empty.sqlite3")
    db.upgrade([type("B", (), {"name": "usage", "versions": copied})()])
    assert db.revision("usage") == "usage_0001"
    db.close()
