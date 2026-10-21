"""DB 핸들: 엔진 하나 + 브랜치별 마이그레이션 실행기(design §3R.1.7, modularity §3.4·P9).

호스트(서버·단독 실행)가 만들어 모듈에 준다. 모듈은 엔진을 직접 만들지 않는다.
`upgrade(branches)`는 항상 legacy(0001~0003)를 먼저 올리고, 넘겨받은(= 켜진 모듈의) 브랜치만
올린다. 파일 하나(SQLite)를 유지하되 나중에 모듈별 DB로 바꾸려면 이 핸들만 바꾸면 된다.

modkit을 모른다. 브랜치는 `name`·`versions` 속성만 있으면 된다(`MigrationBranchLike`).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from sqlalchemy import Engine

from .migrate import branch_version_table, current_revision, downgrade, upgrade
from .sqlite import create_sqlite_engine

LEGACY_BRANCH = "legacy"
"""0001~0003 계보 이름(보고·`revisions()` 키). 항상 올린다."""


class MigrationBranchLike(Protocol):
    """모듈이 선언하는 마이그레이션 계보(구조적 타이핑)."""

    @property
    def name(self) -> str:
        """계보 이름(영숫자·`_`). 버전 테이블 `alembic_version_<name>`을 정한다."""
        ...

    @property
    def versions(self) -> Path:
        """리비전 스크립트 폴더(패키지 데이터)."""
        ...


class SqliteDatabase:
    """SQLite 파일 하나를 가리키는 핸들.

    Args:
        engine: SQLAlchemy 엔진(`create_sqlite_engine`).
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @classmethod
    def open(cls, target: str | Path, *, journal_mode: str = "WAL") -> SqliteDatabase:
        """파일(또는 `":memory:"`)을 연다. 마이그레이션은 하지 않는다(`upgrade`)."""
        return cls(create_sqlite_engine(target, journal_mode=journal_mode))

    @property
    def engine(self) -> Engine:
        return self._engine

    def upgrade(self, branches: Iterable[MigrationBranchLike] = ()) -> None:
        """legacy를 `head`까지, 이어서 `branches`를 각자 `head`까지 올린다(멱등).

        Raises:
            ValueError: 브랜치 이름이 `legacy`이거나 식별자로 쓸 수 없다.
        """
        listed = list(branches)
        for branch in listed:
            _check_name(branch.name)
        upgrade(self._engine)
        for branch in listed:
            upgrade(
                self._engine,
                versions=branch.versions,
                version_table=branch_version_table(branch.name),
            )

    def downgrade_branch(self, branch: MigrationBranchLike, revision: str = "base") -> None:
        """모듈 브랜치 하나만 되돌린다(legacy·다른 브랜치는 그대로)."""
        _check_name(branch.name)
        downgrade(
            self._engine,
            revision,
            versions=branch.versions,
            version_table=branch_version_table(branch.name),
        )

    def revision(self, branch: str = LEGACY_BRANCH) -> str | None:
        """브랜치의 적용된 리비전. 없으면 None."""
        table = "alembic_version" if branch == LEGACY_BRANCH else branch_version_table(branch)
        return current_revision(self._engine, version_table=table)

    def close(self) -> None:
        """엔진의 연결을 모두 닫는다."""
        self._engine.dispose()


def _check_name(name: str) -> None:
    if name == LEGACY_BRANCH or not name.isidentifier():
        raise ValueError(f"브랜치 이름으로 쓸 수 없습니다: {name!r}")


__all__ = ["LEGACY_BRANCH", "MigrationBranchLike", "SqliteDatabase"]
