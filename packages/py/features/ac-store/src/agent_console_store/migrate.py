"""Alembic 마이그레이션 실행 헬퍼. 설정 파일 없이 코드로 적용한다.

계보(브랜치)는 둘로 나뉜다(design §3R.1.7).

- **legacy**: 이 패키지의 `migrations/versions`(0001~0003, 동결). 버전 테이블 `alembic_version`.
- **모듈 브랜치**: 모듈 패키지가 자기 `migrations/versions` 폴더를 가진다. 버전 테이블은
  브랜치마다 따로(`alembic_version_<이름>`)라서, 꺼졌거나 설치되지 않은 모듈의 행이 다른
  계보의 `upgrade`를 막지 않는다. 브랜치끼리는 서로의 리비전을 모른다(모듈 간 외래 키 금지).

의존: alembic. 대안: `metadata.create_all`(되돌리기·이력 없음) -> 채택하지 않음.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine

_SCRIPT_LOCATION = Path(__file__).parent / "migrations"
LEGACY_VERSION_TABLE = "alembic_version"
"""legacy 계보의 버전 테이블(0003까지 쓰던 이름 그대로 — 기존 DB 호환)."""


def branch_version_table(branch: str) -> str:
    """모듈 브랜치의 버전 테이블 이름."""
    return f"alembic_version_{branch}"


def _config(connection: Connection, versions: Path | None, version_table: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_SCRIPT_LOCATION))
    if versions is not None:
        config.set_main_option("path_separator", ";")
        config.set_main_option("version_locations", str(versions))
    config.attributes["connection"] = connection
    config.attributes["version_table"] = version_table
    config.attributes["legacy"] = versions is None
    return config


def upgrade(
    engine: Engine,
    revision: str = "head",
    *,
    versions: Path | None = None,
    version_table: str = LEGACY_VERSION_TABLE,
) -> None:
    """`revision`까지 마이그레이션을 적용한다(이미 적용돼 있으면 아무 일도 하지 않는다).

    Args:
        engine: 대상 DB.
        revision: 목표 리비전(기본 `head`).
        versions: 모듈 브랜치의 리비전 스크립트 폴더. None이면 legacy.
        version_table: 이 계보의 버전 테이블(모듈 브랜치는 `branch_version_table`).
    """
    with engine.begin() as connection:
        command.upgrade(_config(connection, versions, version_table), revision)


def downgrade(
    engine: Engine,
    revision: str = "base",
    *,
    versions: Path | None = None,
    version_table: str = LEGACY_VERSION_TABLE,
) -> None:
    """`revision`까지 되돌린다. 기본 `base`는 그 계보의 모든 변경 제거."""
    with engine.begin() as connection:
        command.downgrade(_config(connection, versions, version_table), revision)


def current_revision(engine: Engine, *, version_table: str = LEGACY_VERSION_TABLE) -> str | None:
    """적용된 리비전. 없으면 None."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"version_table": version_table})
        return context.get_current_revision()
