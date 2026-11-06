"""SQLite 구현: 검색 색인 `SqliteFtsSearchIndex`(X48 `sqlite-fts`, FTS5 trigram)와 페이지 기록
저장소 `SqliteWikiHistory`(X49, SQLAlchemy Core, 표 `wiki_page_versions`·`wiki_blobs`).

검색 색인은 표준 `sqlite3`만 쓰며 SQLAlchemy·계보와 무관한 **다시 만들 수 있는 캐시**다
(design `[7R.9 구현]`). 기록 저장소는 SQLAlchemy가 필요하다(`sqlite` 선택 의존 — ac-store가 이미
끌어온다). 계보 `wiki`의 리비전 폴더와 이름은 이 하위 모듈이 소유한다(`[7R.11 구현]`).
"""

from __future__ import annotations

from pathlib import Path

from ._fts import (
    FTS_BACKEND_ID,
    SCHEMA_VERSION,
    SqliteFtsSearchIndex,
    fts_tokenizer_available,
)
from ._history import SqliteWikiHistory

BRANCH_NAME = "wiki"
"""마이그레이션 계보 이름(버전 테이블 `alembic_version_wiki`)."""

MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "versions"
"""계보 `wiki`의 리비전 스크립트 폴더. 서버 모듈이 `MigrationBranch(BRANCH_NAME, MIGRATIONS_DIR,
scopes=("app", "project"))`로 감싼다(이 패키지는 서버 모듈 키트를 모른다)."""

__all__ = [
    "BRANCH_NAME",
    "FTS_BACKEND_ID",
    "MIGRATIONS_DIR",
    "SCHEMA_VERSION",
    "SqliteFtsSearchIndex",
    "SqliteWikiHistory",
    "fts_tokenizer_available",
]
