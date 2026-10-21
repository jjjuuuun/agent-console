"""저장소 예외 → 오류 응답 재료(`store_error_body`, 3R.16 공용화)와 호스트 DB 공장 entry point."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

from agent_console_contracts import VersionConflictDetails
from agent_console_store import (
    DefinitionCorrupt,
    NotFound,
    SqliteDatabase,
    VersionConflict,
    store_error_body,
)


def test_version_conflict_carries_details_and_etag() -> None:
    body = store_error_body(VersionConflict(VersionConflictDetails(current_version_hash="h1")))
    assert body.code == "version_conflict"
    assert body.details["current_version_hash"] == "h1"
    assert body.headers == {"ETag": '"h1"'}


def test_validation_failed_always_has_issues() -> None:
    body = store_error_body(DefinitionCorrupt("bad yaml"))
    assert (body.code, body.details, body.headers) == ("validation_failed", {"issues": []}, {})


def test_other_errors_have_code_and_message_only() -> None:
    body = store_error_body(NotFound("agent x"))
    assert (body.code, body.message, body.details, body.headers) == ("not_found", "agent x", {}, {})


def test_host_database_entry_point_opens_sqlite(tmp_path: Path) -> None:
    eps = importlib.metadata.entry_points(group="agent_console.host_database")
    found = {ep.name: ep for ep in eps}
    assert "sqlite" in found
    factory = found["sqlite"].load()
    db = factory(tmp_path / "x.sqlite3")
    try:
        assert isinstance(db, SqliteDatabase)
    finally:
        db.close()
