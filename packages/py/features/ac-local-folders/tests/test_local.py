"""`LocalFileSystem` — 실제 디스크(임시 폴더)에서 같은 규칙이 도는지."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console_local_folders import (
    FolderError,
    FolderErrorCode,
    FolderStatus,
    LocalFileSystem,
    check_folder,
    list_dirs,
    make_folder,
)

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX 권한·링크")


def test_local_list_check_make(tmp_path: Path) -> None:
    fs = LocalFileSystem()
    (tmp_path / "b").mkdir()
    (tmp_path / "A").mkdir()
    (tmp_path / ".hid").mkdir()
    (tmp_path / "file.txt").write_text("secret", encoding="utf-8")
    listing = list_dirs(str(tmp_path), fs=fs)
    assert [e.name for e in listing.entries] == ["A", "b"]
    assert listing.hidden_count == 1
    assert check_folder(str(tmp_path / "A"), fs=fs).status == FolderStatus.OK
    assert check_folder(str(tmp_path / "file.txt"), fs=fs).status == FolderStatus.NOT_DIRECTORY
    assert check_folder(str(tmp_path / "new"), fs=fs).status == FolderStatus.MISSING
    made = make_folder(str(tmp_path), name="new", fs=fs)
    assert made.status == FolderStatus.OK
    assert (tmp_path / "new").is_dir()
    with pytest.raises(FolderError) as info:
        make_folder(str(tmp_path), name="new", fs=fs)
    assert info.value.code == FolderErrorCode.EXISTS


@posix_only
def test_local_symlink_resolves(tmp_path: Path) -> None:
    fs = LocalFileSystem()
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    check = check_folder(str(tmp_path / "link"), fs=fs)
    assert check.link is True
    assert check.path == os.path.realpath(real)
    entry = {e.name: e for e in list_dirs(str(tmp_path), fs=fs).entries}["link"]
    assert entry.link is True


@posix_only
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root는 권한 무시")
def test_local_locked(tmp_path: Path) -> None:
    fs = LocalFileSystem()
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        entry = {e.name: e for e in list_dirs(str(tmp_path), fs=fs).entries}["locked"]
        assert entry.locked is True
        assert check_folder(str(locked), fs=fs).status == FolderStatus.NO_ACCESS
        with pytest.raises(FolderError) as info:
            list_dirs(str(locked), fs=fs)
        assert info.value.code == FolderErrorCode.NO_ACCESS
    finally:
        locked.chmod(0o755)
