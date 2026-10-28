"""`list_dirs` 표 테스트(숨김·링크·권한·개수·시간 상한·범위)."""

from __future__ import annotations

import itertools

import pytest

from agent_console_local_folders import (
    DEFAULT_LIST_LIMIT,
    FolderError,
    FolderErrorCode,
    MemoryFileSystem,
    list_dirs,
    load_browse_defaults,
)


def tree() -> MemoryFileSystem:
    return (
        MemoryFileSystem()
        .add_dir("/w/beta")
        .add_dir("/w/Alpha")
        .add_dir("/w/.git")
        .add_dir("/w/locked", readable=False)
        .add_file("/w/README.md")
        .add_file("/w/secret.env")
        .add_link("/w/to-alpha", "/w/Alpha")
        .add_link("/w/to-file", "/w/README.md")
        .add_link("/w/broken", "/nowhere")
    )


def test_only_folder_names_sorted_hidden_skipped() -> None:
    listing = list_dirs("/w/", fs=tree())
    assert listing.path == "/w"
    assert listing.parent == "/"
    assert [e.name for e in listing.entries] == ["Alpha", "beta", "locked", "to-alpha"]
    assert listing.hidden_count == 1
    assert (listing.truncated, listing.timed_out) == (False, False)
    names = {e.name for e in listing.entries}
    assert "README.md" not in names
    assert "secret.env" not in names


def test_flags_link_locked_hidden() -> None:
    listing = list_dirs("/w", fs=tree(), show_hidden=True)
    by = {e.name: e for e in listing.entries}
    assert by[".git"].hidden is True
    assert listing.hidden_count == 0
    assert by["to-alpha"].link is True
    assert by["to-alpha"].locked is False
    assert by["to-alpha"].path == "/w/to-alpha"
    assert by["locked"].locked is True
    assert by["Alpha"].link is False
    assert by["Alpha"].hidden is False


def test_windows_hidden_attribute_and_names() -> None:
    fs = (
        MemoryFileSystem("windows")
        .add_dir("C:\\Users\\me\\AppData", hidden=True)
        .add_dir("C:\\Users\\me\\Documents")
        .add_dir("C:\\Users\\me\\.vscode")
    )
    fs.add_dir("C:\\$Recycle.Bin", hidden=True).add_dir("C:\\Users")
    assert [e.name for e in list_dirs("c:\\users\\me", fs=fs).entries] == ["Documents"]
    shown = list_dirs("C:\\Users\\me", fs=fs, show_hidden=True)
    assert [(e.name, e.hidden) for e in shown.entries] == [
        (".vscode", True),
        ("AppData", True),
        ("Documents", False),
    ]
    assert shown.entries[0].path == "C:\\Users\\me\\.vscode"
    root = list_dirs("C:\\", fs=fs)
    assert root.parent is None
    assert [e.name for e in root.entries] == ["Users"]


def test_hidden_names_are_data_and_empty_by_default() -> None:
    fs = MemoryFileSystem().add_dir("/srv/data/Build-Cache").add_dir("/srv/data/Tmp")
    fs.add_dir("/srv/data/src")
    assert len(list_dirs("/srv/data", fs=fs).entries) == 3  # 기본 데이터는 이름으로 숨기지 않음
    custom = load_browse_defaults({"hidden_names": ["build-cache", "TMP"], "roots": {}})
    listing = list_dirs("/srv/data", fs=fs, defaults=custom)
    assert [e.name for e in listing.entries] == ["src"]
    assert listing.hidden_count == 2


@pytest.mark.parametrize(
    ("count", "limit", "shown", "truncated"),
    [
        (2500, DEFAULT_LIST_LIMIT, 2000, True),
        (2000, DEFAULT_LIST_LIMIT, 2000, False),
        (5, 3, 3, True),
        (3, 3, 3, False),
        (1, 0, 0, True),
    ],
)
def test_limit(count: int, limit: int, shown: int, truncated: bool) -> None:
    fs = MemoryFileSystem().add_dir("/big")
    for i in range(count):
        fs.add_dir(f"/big/d{i:05d}")
    listing = list_dirs("/big", fs=fs, limit=limit)
    assert len(listing.entries) == shown
    assert listing.truncated is truncated
    assert listing.timed_out is False


def test_timeout_with_injected_clock() -> None:
    fs = MemoryFileSystem().add_dir("/slow")
    for i in range(50):
        fs.add_dir(f"/slow/d{i:02d}")
    ticks = itertools.count()
    listing = list_dirs("/slow", fs=fs, timeout=10, clock=lambda: float(next(ticks)))
    assert listing.truncated is True
    assert listing.timed_out is True
    assert 0 < len(listing.entries) < 50
    unlimited = list_dirs("/slow", fs=fs, timeout=None, clock=lambda: float(next(ticks)))
    assert len(unlimited.entries) == 50


def test_files_count_toward_time_not_entries() -> None:
    fs = MemoryFileSystem().add_dir("/f")
    for i in range(30):
        fs.add_file(f"/f/file{i}")
    ticks = itertools.count()
    listing = list_dirs("/f", fs=fs, timeout=5, clock=lambda: float(next(ticks)))
    assert listing.entries == ()
    assert listing.timed_out is True


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/nope", FolderErrorCode.NOT_FOUND),
        ("/w/README.md", FolderErrorCode.NOT_DIRECTORY),
        ("/w/locked", FolderErrorCode.NO_ACCESS),
        ("relative", FolderErrorCode.RELATIVE),
        ("", FolderErrorCode.EMPTY),
    ],
)
def test_errors(path: str, code: str) -> None:
    with pytest.raises(FolderError) as info:
        list_dirs(path, fs=tree())
    assert info.value.code == code


def test_permission_under_unreadable_parent() -> None:
    fs = MemoryFileSystem().add_dir("/p", readable=False).add_dir("/p/child")
    with pytest.raises(FolderError) as info:
        list_dirs("/p/child", fs=fs)
    assert info.value.code == FolderErrorCode.NO_ACCESS


def test_roots_limit_scope() -> None:
    fs = tree().add_dir("/home/me/a").add_link("/home/me/escape", "/w")
    listing = list_dirs("/home/me", fs=fs, roots=["/home/me"])
    assert listing.parent is None  # 범위 위로 못 올라감
    assert list_dirs("/home/me/a", fs=fs, roots=["/home/me"]).parent == "/home/me"
    for outside in ("/w", "/home", "/home/me/escape"):
        with pytest.raises(FolderError) as info:
            list_dirs(outside, fs=fs, roots=["/home/me"])
        assert info.value.code == FolderErrorCode.OUTSIDE_ROOTS


def test_tilde_and_link_listing_path_kept() -> None:
    fs = tree().add_dir("/home/me/x")
    assert list_dirs("~", fs=fs, environ={"HOME": "/home/me"}).path == "/home/me"
    listing = list_dirs("/w/to-alpha", fs=fs.add_dir("/w/Alpha/sub"))
    assert listing.path == "/w/to-alpha"
    assert [e.path for e in listing.entries] == ["/w/to-alpha/sub"]


def test_negative_limit_rejected() -> None:
    with pytest.raises(ValueError, match="limit"):
        list_dirs("/w", fs=tree(), limit=-1)
