"""`check_folder`·`normalize` 표 테스트(가짜 파일 시스템)."""

from __future__ import annotations

import pytest

from agent_console_local_folders import (
    FolderErrorCode,
    FolderStatus,
    MemoryFileSystem,
    check_folder,
    nearest_existing,
    normalize,
)

ENV = {"HOME": "/home/me"}


def posix_fs() -> MemoryFileSystem:
    return (
        MemoryFileSystem()
        .add_dir("/home/me/work/app")
        .add_dir("/home/me/.config")
        .add_dir("/home/me/readonly", writable=False)
        .add_dir("/home/me/secret", readable=False)
        .add_dir("/home/me/secret/inner")
        .add_file("/home/me/notes.txt")
        .add_link("/home/me/app-link", "/home/me/work/app")
        .add_dir("/srv/locked", writable=False)
    )


@pytest.mark.parametrize(
    ("raw", "status", "path"),
    [
        ("/home/me/work/app", FolderStatus.OK, "/home/me/work/app"),
        ("~/work/app/", FolderStatus.OK, "/home/me/work/app"),
        ("/home/me/readonly", FolderStatus.OK_READONLY, "/home/me/readonly"),
        ("/home/me/new", FolderStatus.MISSING, "/home/me/new"),
        ("/home/me/no/such/thing", FolderStatus.MISSING_PARENT, "/home/me/no/such/thing"),
        ("/srv/locked/new", FolderStatus.MISSING_PARENT, "/srv/locked/new"),
        ("/home/me/notes.txt", FolderStatus.NOT_DIRECTORY, "/home/me/notes.txt"),
        ("/home/me/secret", FolderStatus.NO_ACCESS, "/home/me/secret"),
        ("/home/me/secret/inner", FolderStatus.NO_ACCESS, "/home/me/secret/inner"),
        ("/home/me/app-link", FolderStatus.OK, "/home/me/work/app"),
        ("work/app", FolderStatus.INVALID, None),
        ("", FolderStatus.INVALID, None),
        ("C:\\Work\\me", FolderStatus.INVALID, None),
    ],
)
def test_check_status_table(raw: str, status: str, path: str | None) -> None:
    check = check_folder(raw, fs=posix_fs(), environ=ENV)
    assert check.status == status
    assert check.path == path
    assert check.input == raw


def test_check_fields_ok_and_link() -> None:
    fs = posix_fs()
    plain = check_folder("/home/me/work/app", fs=fs)
    assert (plain.exists, plain.is_dir, plain.readable, plain.writable, plain.link) == (
        True,
        True,
        True,
        True,
        False,
    )
    assert plain.nearest_existing == "/home/me/work/app"
    linked = check_folder("/home/me/app-link", fs=fs)
    assert linked.link is True
    assert linked.path == "/home/me/work/app"
    # 링크를 거친 상위 폴더도 실제 경로로 저장
    under = check_folder("/home/me/app-link/sub", fs=fs)
    assert under.path == "/home/me/work/app/sub"
    assert under.link is True
    assert under.status == FolderStatus.MISSING


def test_check_missing_reports_nearest_existing() -> None:
    check = check_folder("/home/me/work/app/a/b/c", fs=posix_fs())
    assert check.status == FolderStatus.MISSING_PARENT
    assert check.nearest_existing == "/home/me/work/app"
    assert check.can_create is False
    one = check_folder("/home/me/work/app/a", fs=posix_fs())
    assert (one.can_create, one.nearest_existing) == (True, "/home/me/work/app")


def test_check_hidden_dot_and_windows_attr() -> None:
    assert check_folder("/home/me/.config", fs=posix_fs()).hidden is True
    win = MemoryFileSystem("windows").add_dir("C:\\Work\\Hid", hidden=True).add_dir("C:\\Work\\Vis")
    assert check_folder("C:\\Work\\Hid", fs=win).hidden is True
    assert check_folder("c:/work/vis", fs=win).hidden is False


def test_windows_case_insensitive_check() -> None:
    fs = MemoryFileSystem("windows").add_dir("C:\\Work\\App")
    check = check_folder("c:\\work\\app\\", fs=fs)
    assert check.status == FolderStatus.OK
    assert check.path == "C:\\Work\\App"  # 저장된 표기(실제 경로)


@pytest.mark.parametrize(
    ("flavor", "raw"),
    [
        ("posix", "C:\\Work\\me"),
        ("posix", "c:/a/b"),
        ("posix", "\\\\server\\share\\x"),
        ("windows", "/home/me/work"),
    ],
)
def test_foreign_path_is_invalid_without_translation(flavor: str, raw: str) -> None:
    fs = MemoryFileSystem("windows" if flavor == "windows" else "posix")
    check = check_folder(raw, fs=fs)
    assert check.problem == FolderErrorCode.FOREIGN_PATH
    assert check.status == FolderStatus.INVALID
    assert check.path is None
    assert "suggestion" not in check.to_dict()  # 다른 OS 경로를 바꿔 주지 않는다


def test_check_outside_roots() -> None:
    fs = posix_fs()
    check = check_folder("/srv/locked", fs=fs, roots=["/home/me"])
    assert check.problem == FolderErrorCode.OUTSIDE_ROOTS
    assert check.status == FolderStatus.INVALID
    # 링크로 범위 밖을 가리키면 밖이다
    fs.add_link("/home/me/out", "/srv/locked")
    assert check_folder("/home/me/out", fs=fs, roots=["/home/me"]).problem == (
        FolderErrorCode.OUTSIDE_ROOTS
    )
    assert check_folder("/home/me/work", fs=fs, roots=["/home/me"]).status == FolderStatus.OK


def test_normalize_real_and_nearest() -> None:
    fs = posix_fs()
    assert normalize("~/app-link", fs=fs, environ=ENV) == "/home/me/work/app"
    assert normalize("~/app-link", fs=fs, environ=ENV, real=False) == "/home/me/app-link"
    assert nearest_existing("/home/me/work/zzz/yyy", fs=fs) == "/home/me/work"
    assert nearest_existing("/", fs=fs) == "/"
    assert nearest_existing("/nope", fs=MemoryFileSystem()) == "/"


def test_check_never_reads_contents() -> None:
    fs = posix_fs()
    check_folder("/home/me/work/app", fs=fs)
    check_folder("/home/me/new", fs=fs)
    assert fs.scan_calls == []  # 확인은 목록을 읽지 않는다


def test_to_dict_has_status() -> None:
    data = check_folder("/home/me/readonly", fs=posix_fs()).to_dict()
    assert data["status"] == "ok_readonly"
    assert data["path"] == "/home/me/readonly"
