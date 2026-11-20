"""5.7R.33x: 공간 예외가 저장소 예외(`StoreError`)라 공용 오류 매핑으로 응답되고, 기록 DB를 쓸 수
없으면 정의 파일도 쓰지 않는다."""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from agent_console_project_space import (
    ConfigReadonly,
    FolderMissing,
    ManifestInvalid,
    SecretRejected,
    SpaceError,
    UnsafeConfigDir,
    open_space,
)
from agent_console_project_space.testing import ReadOnlyFiles, sample_agent, snapshot_tree
from agent_console_store import (
    RecordsUnavailable,
    RecordsVersionRepository,
    StoreError,
    open_records_db,
    store_error_body,
)


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (FolderMissing("x"), "project.folder_missing"),
        (ConfigReadonly("x"), "project.config_readonly"),
        (UnsafeConfigDir("x"), "bad_request"),
        (ManifestInvalid("yaml"), "project.manifest_invalid"),
    ],
)
def test_space_errors_are_store_errors(exc: SpaceError, code: str) -> None:
    assert isinstance(exc, StoreError)
    assert store_error_body(exc).code == code


def test_secret_rejection_carries_field_issues_without_values(folder: Path) -> None:
    space = open_space(folder)
    with pytest.raises(SecretRejected) as caught:
        space.definitions.create("agent", sample_agent(attributes={"API_KEY": "abcd1234efgh5678"}))
    body = store_error_body(caught.value)
    assert body.code == "validation_failed"
    [issue] = body.details["issues"]
    assert issue["path"] == "/attributes/API_KEY"
    assert issue["code"] == "secret.plain_found"
    assert issue["severity"] == "error"
    assert "secret://" in issue["message"]
    assert "abcd1234efgh5678" not in str(body)


def test_readonly_space_maps_to_config_readonly(folder: Path) -> None:
    space = open_space(folder, files=ReadOnlyFiles())
    with pytest.raises(ConfigReadonly) as caught:
        space.definitions.create("agent", sample_agent())
    assert store_error_body(caught.value).code == "project.config_readonly"


def _records(folder: Path):  # type: ignore[no-untyped-def]
    root = folder / ".agent-console"
    return open_records_db(root / "records.sqlite3", (), backup_dir=root / ".state" / "backups")


def test_versions_go_to_the_folder_records_db(folder: Path) -> None:
    db = _records(folder)
    space = open_space(folder, versions=RecordsVersionRepository(lambda: db))
    space.definitions.create("agent", sample_agent())
    space.definitions.save("agent", sample_agent(name="둘"))
    assert len(space.definitions.list_versions("agent", "a1")) == 2
    assert (folder / ".agent-console" / "records.sqlite3").exists()
    db.close()


def test_newer_records_db_blocks_definition_write_before_any_file(folder: Path) -> None:
    db = _records(folder)
    space = open_space(folder, versions=RecordsVersionRepository(lambda: db))
    space.definitions.create("agent", sample_agent())
    db.close()
    raw = sqlite3.connect(folder / ".agent-console" / "records.sqlite3")
    raw.execute("UPDATE alembic_version SET version_num = 'legacy_9999'")
    raw.commit()
    raw.close()
    agents_before = snapshot_tree(folder / ".agent-console" / "agents")

    newer = _records(folder)
    space = open_space(folder, versions=RecordsVersionRepository(lambda: newer))
    current = space.definitions.get("agent", "a1")
    with pytest.raises(RecordsUnavailable) as caught:
        space.definitions.save(
            "agent", sample_agent(name="바뀜"), expected_version=current.version_hash
        )
    assert caught.value.reason == "newer"
    assert store_error_body(caught.value).code == "project.records_unavailable"
    assert snapshot_tree(folder / ".agent-console" / "agents") == agents_before
    with pytest.raises(RecordsUnavailable):
        space.definitions.create("agent", sample_agent("a2"))
    assert not (folder / ".agent-console" / "agents" / "a2.yaml").exists()
    newer.close()


def _lock(folder: Path) -> list[Path]:
    locked = [p for p in (folder, *folder.rglob("*")) if p.is_dir()]
    for d in locked:
        d.chmod(d.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return locked


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 쓰기 권한 검사를 통과한다")
def test_folder_turned_read_only_after_open_raises_config_readonly(folder: Path) -> None:
    """5.7R.33n: 열 때 쓸 수 있던 공간도 실제 쓰기·삭제가 권한 오류면 `ConfigReadonly`(409)다."""
    space = open_space(folder)
    assert space.config_writable
    space.definitions.create("agent", sample_agent())
    current = space.definitions.get("agent", "a1")
    before = snapshot_tree(folder)
    locked = _lock(folder)
    try:
        with pytest.raises(ConfigReadonly) as caught:
            space.definitions.create("agent", sample_agent("a2"))
        assert store_error_body(caught.value).code == "project.config_readonly"
        assert str(folder) not in str(caught.value)
        with pytest.raises(ConfigReadonly):
            space.definitions.save(
                "agent", sample_agent(name="둘"), expected_version=current.version_hash
            )
        with pytest.raises(ConfigReadonly):
            space.definitions.delete("agent", "a1")
    finally:
        for d in locked:
            d.chmod(d.stat().st_mode | stat.S_IWUSR)
    assert snapshot_tree(folder) == before
    assert space.definitions.get("agent", "a1").version_hash == current.version_hash
