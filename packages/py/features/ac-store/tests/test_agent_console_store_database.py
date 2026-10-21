"""DatabaseHandle: legacy 동결 + 모듈 브랜치 분리 마이그레이션(design §3R.1.7, modularity §3.4)."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa

from agent_console_store import (
    LEGACY_BRANCH,
    SqliteDatabase,
    create_sqlite_engine,
    current_revision,
    open_sqlite,
    upgrade,
)

REVISION = '''"""테스트용 브랜치: 표 하나."""

import sqlalchemy as sa
from alembic import op

revision = "{rev}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("{table}", sa.Column("id", sa.Text, primary_key=True))


def downgrade() -> None:
    op.drop_table("{table}")
'''


@dataclass(frozen=True)
class Branch:
    name: str
    versions: Path


def make_branch(root: Path, name: str) -> Branch:
    versions = root / name / "versions"
    versions.mkdir(parents=True)
    body = REVISION.format(rev=f"{name}_0001", down="None", table=f"{name}_items")
    (versions / f"{name}_0001.py").write_text(body, encoding="utf-8")
    return Branch(name, versions)


def tables(db: SqliteDatabase) -> set[str]:
    return set(sa.inspect(db.engine).get_table_names())


def test_upgrade_runs_legacy_and_only_given_branches(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "d.sqlite3")
    a, b = make_branch(tmp_path, "alpha"), make_branch(tmp_path, "beta")
    assert db.revision() is None
    db.upgrade([a])
    assert db.revision() == "0003"
    assert db.revision("alpha") == "alpha_0001"
    assert db.revision("beta") is None
    assert "alpha_items" in tables(db)
    assert "beta_items" not in tables(db)
    assert {"alembic_version", "alembic_version_alpha"} <= tables(db)
    db.upgrade([a, b])
    db.upgrade([a, b])  # 멱등
    assert db.revision("beta") == "beta_0001"
    db.close()


def test_branch_not_given_this_time_does_not_block_others(tmp_path: Path) -> None:
    """꺼졌거나 설치되지 않은 모듈의 버전 행이 있어도 다른 계보의 upgrade는 된다."""
    db = SqliteDatabase.open(tmp_path / "d.sqlite3")
    a, b = make_branch(tmp_path, "alpha"), make_branch(tmp_path, "beta")
    db.upgrade([a, b])
    db.upgrade([b])  # alpha 모듈 꺼짐(스크립트 폴더도 모름)
    db.upgrade()  # 모듈 없이 legacy만
    assert db.revision("alpha") == "alpha_0001"
    assert "alpha_items" in tables(db)  # 켜지지 않아도 지우지 않는다
    db.close()


def test_downgrade_branch_leaves_legacy_and_others(tmp_path: Path) -> None:
    db = SqliteDatabase.open(tmp_path / "d.sqlite3")
    a, b = make_branch(tmp_path, "alpha"), make_branch(tmp_path, "beta")
    db.upgrade([a, b])
    db.downgrade_branch(a)
    assert "alpha_items" not in tables(db)
    assert db.revision("alpha") is None
    assert db.revision("beta") == "beta_0001"
    assert db.revision() == "0003"
    db.upgrade([a])  # 다시 적용
    assert "alpha_items" in tables(db)
    db.close()


@pytest.mark.parametrize("name", [LEGACY_BRANCH, "has-dash", ""])
def test_rejects_bad_branch_names(tmp_path: Path, name: str) -> None:
    db = SqliteDatabase.open(tmp_path / "d.sqlite3")
    with pytest.raises(ValueError, match="브랜치 이름"):
        db.upgrade([Branch(name, tmp_path)])
    db.close()


def test_existing_0003_database_keeps_data_after_branches(tmp_path: Path) -> None:
    """기존 DB(0003, 버전 테이블 `alembic_version`) 위에서 시작해도 데이터가 그대로다."""
    path = tmp_path / "old.sqlite3"
    engine = create_sqlite_engine(path)
    upgrade(engine)  # 지금까지의 배포와 같은 상태
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO usage_observations (source, window_id, observed_at, doc) "
            "VALUES ('sdk', 'five_hour', 1.0, '{}')"
        )
    assert current_revision(engine) == "0003"
    engine.dispose()
    db = SqliteDatabase.open(path)
    db.upgrade([make_branch(tmp_path, "alpha")])
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM usage_observations").scalar() == 1
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalars().all() == [
            "0003"
        ]
    db.close()


def test_open_sqlite_still_applies_legacy(tmp_path: Path) -> None:
    db = open_sqlite(tmp_path / "x.sqlite3")
    assert current_revision(db.engine) == "0003"
    db.close()
