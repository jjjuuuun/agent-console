"""페이지 기록 표 정의(design §7R.6). 단독 `create_all`과 계보 `wiki`가 같은 모양을 지킨다.

- `wiki_page_versions`: 페이지 버전 한 줄(지우기·옮기기 포함). 본문은 여기 두지 않는다 — 목록은
  이 표만 읽고(작은 열뿐), 본문은 `wiki_blobs`에서 해시로 찾는다("큰 원문과 목록용 요약 분리").
- `wiki_blobs`: 해시(sha256)마다 본문 한 행. 같은 본문은 한 번만 둔다.

`seq`는 행 번호 겸 최근 변경의 정렬·커서 기준이다(삽입 순서 = 시간 순서, 위키를 가로질러 하나의
순서). 페이지·버전 조회는 유일 색인 `(wiki_id, path, version)`이 맡는다. design은 이 세 열을
기본키로 적었지만, 위키 전체에 걸친 최근 변경 커서가 필요해 정수 기본키를 따로 둔다
(`[7R.11 구현]`).
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    Column,
    Float,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    text,
)

VERSIONS_TABLE: Final = "wiki_page_versions"
BLOBS_TABLE: Final = "wiki_blobs"

metadata = MetaData()

versions = Table(
    VERSIONS_TABLE,
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("wiki_id", String, nullable=False),
    Column("path", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("op", String, nullable=False),
    Column("sha256", String, nullable=False),
    Column("bytes", Integer, nullable=False),
    Column("at", Float, nullable=False),
    # `author_json`에서 뽑은 조회용 열(실행에서 쓴 페이지, 루트 실행 아래 하위 실행 쓰기).
    Column("author_run_id", String, nullable=True),
    Column("author_root_run_id", String, nullable=True),
    Column("from_path", String, nullable=True),  # op move_in의 옛 경로
    Column("to_path", String, nullable=True),  # op move_out의 새 경로
    Column("message", Text, nullable=True),
    Column("author_json", Text, nullable=False),  # WikiAuthor(label 포함, 기록 시점 그대로)
    Index("ux_wiki_page_versions_key", "wiki_id", "path", "version", unique=True),
    # 위키 하나의 최근 변경(`seq` 내림차순). 위키 전체는 기본키 순서로 답한다.
    Index("ix_wiki_page_versions_wiki_seq", "wiki_id", "seq"),
    Index(
        "ix_wiki_page_versions_author_run",
        "author_run_id",
        sqlite_where=text("author_run_id IS NOT NULL"),
    ),
    Index(
        "ix_wiki_page_versions_author_root",
        "author_root_run_id",
        sqlite_where=text("author_root_run_id IS NOT NULL"),
    ),
    # 정리할 때 "다른 버전이 아직 이 본문을 가리키나"를 색인으로 답한다.
    Index("ix_wiki_page_versions_sha256", "sha256"),
    sqlite_autoincrement=True,
)

blobs = Table(
    BLOBS_TABLE,
    metadata,
    Column("sha256", String, primary_key=True),
    Column("content", LargeBinary, nullable=False),
)

__all__ = ["BLOBS_TABLE", "VERSIONS_TABLE", "blobs", "metadata", "versions"]
