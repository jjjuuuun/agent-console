"""`project.yaml`: 읽기, If-Match 쓰기, 모르는 키·주석 보존, 깨짐, 초기화."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_console_contracts import PROJECT_MANIFEST_FORMAT, ProjectManifest
from agent_console_project_space import (
    ConfigReadonly,
    ManifestInvalid,
    SecretRejected,
    open_space,
    read_manifest,
    reset_manifest,
    write_manifest,
)
from agent_console_project_space.testing import ReadOnlyFiles
from agent_console_store import NotFound, VersionConflict, VersionRequired


def test_create_then_read(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder)
    assert read_manifest(space) is None
    written = write_manifest(space, manifest)
    assert written.manifest.id == "payments"
    assert written.manifest.format == PROJECT_MANIFEST_FORMAT
    text = space.manifest_path.read_text(encoding="utf-8")
    assert "name: 결제 서비스" in text
    assert read_manifest(space) == written


def test_unknown_keys_and_comments_round_trip(folder: Path) -> None:
    space = open_space(folder)
    space.root.mkdir()
    space.manifest_path.write_text(
        "# 팀 메모\nformat: 1\nid: payments\nname: 결제\nfuture_field:\n  deep: [1, 2]\n",
        encoding="utf-8",
    )
    record = read_manifest(space)
    assert record is not None
    assert record.manifest.model_extra == {"future_field": {"deep": [1, 2]}}
    renamed = record.manifest.model_copy(update={"name": "결제 v2"})
    write_manifest(space, renamed, expected_version=record.version)
    text = space.manifest_path.read_text(encoding="utf-8")
    assert text.startswith("# 팀 메모")
    assert "name: 결제 v2" in text
    assert "deep:" in text


def test_if_match_rules(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder)
    first = write_manifest(space, manifest)
    with pytest.raises(VersionRequired):
        write_manifest(space, manifest)
    other = manifest.model_copy(update={"description": "a"})
    second = write_manifest(space, other, expected_version=first.version)
    assert second.version != first.version
    with pytest.raises(VersionConflict) as caught:
        write_manifest(space, manifest, expected_version=first.version)
    assert caught.value.details.current_version_hash == second.version


def test_expected_version_on_missing_file(folder: Path, manifest: ProjectManifest) -> None:
    with pytest.raises(NotFound):
        write_manifest(open_space(folder), manifest, expected_version="abc")


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("id: [unclosed", "yaml"),
        ("- a\n- b\n", "yaml"),
        ("format: 1\nname: x\n", "schema"),
        ("format: 1\nid: Not A Slug!\nname: x\n", "schema"),
    ],
)
def test_broken_manifest(
    folder: Path, manifest: ProjectManifest, content: str, reason: str
) -> None:
    space = open_space(folder)
    space.root.mkdir()
    space.manifest_path.write_text(content, encoding="utf-8")
    with pytest.raises(ManifestInvalid) as caught:
        read_manifest(space)
    assert caught.value.reason == reason
    with pytest.raises(ManifestInvalid):
        write_manifest(space, manifest, expected_version="x")
    assert space.manifest_path.read_text(encoding="utf-8") == content


def test_not_utf8(folder: Path) -> None:
    space = open_space(folder)
    space.root.mkdir()
    space.manifest_path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ManifestInvalid) as caught:
        read_manifest(space)
    assert caught.value.reason == "not_utf8"


def test_newer_format_is_read_but_not_overwritten(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder)
    space.root.mkdir()
    space.manifest_path.write_text("format: 99\nid: payments\nname: x\n", encoding="utf-8")
    record = read_manifest(space)
    assert record is not None
    with pytest.raises(ManifestInvalid) as caught:
        write_manifest(space, manifest, expected_version=record.version)
    assert caught.value.reason == "newer_format"


def test_secret_in_manifest_is_refused(folder: Path) -> None:
    space = open_space(folder)
    bad = ProjectManifest.model_validate(
        {"id": "p", "name": "p", "attributes": {"api_key": "abcd1234efgh5678"}}
    )
    with pytest.raises(SecretRejected):
        write_manifest(space, bad)
    assert not space.manifest_path.exists()


def test_read_only_refuses_manifest_write(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder, files=ReadOnlyFiles())
    with pytest.raises(ConfigReadonly):
        write_manifest(space, manifest)
    with pytest.raises(ConfigReadonly):
        reset_manifest(space, manifest)


def test_reset_backs_up_each_time(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder)
    space.root.mkdir()
    space.manifest_path.write_text("broken: [", encoding="utf-8")
    when = datetime(2026, 10, 28, 9, 30, 5, tzinfo=UTC)
    first = reset_manifest(space, manifest, now=when)
    assert first == space.state_dir / "backups" / "project-20261028T093005Z.yaml"
    assert first.read_text(encoding="utf-8") == "broken: ["
    assert read_manifest(space) is not None
    second = reset_manifest(space, manifest, now=when)
    assert second == space.state_dir / "backups" / "project-20261028T093005Z-2.yaml"
    assert len(list((space.state_dir / "backups").iterdir())) == 2


def test_reset_without_old_file_makes_no_backup(folder: Path, manifest: ProjectManifest) -> None:
    space = open_space(folder)
    assert reset_manifest(space, manifest) is None
    assert not space.state_dir.exists()
