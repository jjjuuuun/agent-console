"""`make_folder` 테스트."""

from __future__ import annotations

import pytest

from agent_console_local_folders import (
    FolderError,
    FolderErrorCode,
    FolderStatus,
    MemoryFileSystem,
    make_folder,
)


def fs() -> MemoryFileSystem:
    return (
        MemoryFileSystem()
        .add_dir("/home/me/work")
        .add_dir("/home/me/ro", writable=False)
        .add_dir("/home/me/hidden-parent", readable=False)
        .add_file("/home/me/file.txt")
    )


def test_make_path_and_named_child() -> None:
    f = fs()
    made = make_folder("/home/me/work/new", fs=f)
    assert made.status == FolderStatus.OK
    assert made.path == "/home/me/work/new"
    child = make_folder("~/work", name=" 하위 폴더 ", fs=f, environ={"HOME": "/home/me"})
    assert child.path == "/home/me/work/하위 폴더"
    assert f.mkdir_calls == ["/home/me/work/new", "/home/me/work/하위 폴더"]


@pytest.mark.parametrize(
    ("path", "name", "code"),
    [
        ("/home/me/work", "..", FolderErrorCode.INVALID_NAME),
        ("/home/me/work", "a/b", FolderErrorCode.INVALID_NAME),
        ("/home/me/work", "", FolderErrorCode.INVALID_NAME),
        ("/home/me", "work", FolderErrorCode.EXISTS),
        ("/home/me/file.txt", None, FolderErrorCode.EXISTS),
        ("/home/me/no/such", None, FolderErrorCode.MISSING_PARENT),
        ("/home/me/file.txt", "x", FolderErrorCode.MISSING_PARENT),
        ("/home/me/ro", "x", FolderErrorCode.NO_ACCESS),
        ("/home/me/hidden-parent/x", None, FolderErrorCode.NO_ACCESS),
        ("/", None, FolderErrorCode.EXISTS),
        ("rel", None, FolderErrorCode.RELATIVE),
    ],
)
def test_make_errors(path: str, name: str | None, code: str) -> None:
    f = fs()
    with pytest.raises(FolderError) as info:
        make_folder(path, name=name, fs=f)
    assert info.value.code == code
    assert f.mkdir_calls == []


def test_make_respects_roots_and_windows() -> None:
    f = fs()
    with pytest.raises(FolderError) as info:
        make_folder("/home/me/work/x", fs=f, roots=["/srv"])
    assert info.value.code == FolderErrorCode.OUTSIDE_ROOTS
    win = MemoryFileSystem("windows").add_dir("C:\\Work")
    assert make_folder("c:\\work", name="New", fs=win).path == "C:\\Work\\New"
    with pytest.raises(FolderError) as bad:
        make_folder("C:\\Work", name="what?", fs=win)
    assert bad.value.code == FolderErrorCode.INVALID_NAME
    with pytest.raises(FolderError) as dup:
        make_folder("C:\\Work", name="NEW", fs=win)  # 대소문자 무시
    assert dup.value.code == FolderErrorCode.EXISTS
