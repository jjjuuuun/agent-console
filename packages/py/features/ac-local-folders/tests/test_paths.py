"""경로 문자열 규칙 표 테스트(파일 시스템 없음)."""

from __future__ import annotations

import pytest

from agent_console_local_folders import (
    FolderError,
    FolderErrorCode,
    PathFlavor,
    is_within,
    normalize_lexical,
    path_key,
    validate_folder_name,
)

POSIX_ENV = {"HOME": "/home/me"}
WIN_ENV = {"USERPROFILE": "C:\\Users\\me"}


@pytest.mark.parametrize(
    ("flavor", "raw", "expected"),
    [
        ("posix", "/home/me/app", "/home/me/app"),
        ("posix", "  /home/me/app/  ", "/home/me/app"),
        ("posix", '"/home/me/my app"', "/home/me/my app"),
        ("posix", "'/x/y'", "/x/y"),
        ("posix", "~", "/home/me"),
        ("posix", "~/work/../app", "/home/me/app"),
        ("posix", "//double//slash", "/double/slash"),
        ("posix", "/", "/"),
        ("posix", "/home/me/work/", "/home/me/work"),
        ("posix", "/home/me/한글 폴더", "/home/me/한글 폴더"),
        ("windows", "C:\\Work\\App\\", "C:\\Work\\App"),
        ("windows", "c:/work/app", "C:\\work\\app"),
        ("windows", "C:\\", "C:\\"),
        ("windows", "~", "C:\\Users\\me"),
        ("windows", "~\\docs", "C:\\Users\\me\\docs"),
        ("windows", "~/docs", "C:\\Users\\me\\docs"),
        ("windows", "\\\\server\\share\\x", "\\\\server\\share\\x"),
        ("windows", '"D:\\a b\\c"', "D:\\a b\\c"),
    ],
)
def test_normalize_ok(flavor: PathFlavor, raw: str, expected: str) -> None:
    env = WIN_ENV if flavor == "windows" else POSIX_ENV
    assert normalize_lexical(raw, flavor=flavor, environ=env) == expected


@pytest.mark.parametrize(
    ("flavor", "raw", "code"),
    [
        ("posix", "", FolderErrorCode.EMPTY),
        ("posix", "   ", FolderErrorCode.EMPTY),
        ("posix", '""', FolderErrorCode.EMPTY),
        ("posix", "work/app", FolderErrorCode.RELATIVE),
        ("posix", "./app", FolderErrorCode.RELATIVE),
        ("posix", "~other/x", FolderErrorCode.RELATIVE),
        ("posix", "C:\\Users\\me", FolderErrorCode.FOREIGN_PATH),
        ("posix", "c:/x", FolderErrorCode.FOREIGN_PATH),
        ("posix", "\\\\server\\share\\x", FolderErrorCode.FOREIGN_PATH),
        ("posix", "/a\x00b", FolderErrorCode.INVALID_PATH),
        ("posix", "/a\nb", FolderErrorCode.INVALID_PATH),
        ("windows", "/home/me/x", FolderErrorCode.FOREIGN_PATH),
        ("windows", "C:x", FolderErrorCode.RELATIVE),
        ("windows", "work\\app", FolderErrorCode.RELATIVE),
    ],
)
def test_normalize_errors(flavor: PathFlavor, raw: str, code: str) -> None:
    with pytest.raises(FolderError) as info:
        normalize_lexical(raw, flavor=flavor, environ={"HOME": "/home/me"})
    assert info.value.code == code


def test_tilde_without_home() -> None:
    with pytest.raises(FolderError) as info:
        normalize_lexical("~/x", flavor="posix", environ={})
    assert info.value.code == FolderErrorCode.NO_HOME


@pytest.mark.parametrize(
    ("flavor", "a", "b", "same"),
    [
        ("windows", "C:\\Work\\App", "c:\\work\\app\\", True),
        ("windows", "C:\\Work", "C:\\Work2", False),
        ("posix", "/home/Me", "/home/me", False),
        ("posix", "/a/b/", "/a/b", True),
        ("posix", "/", "/", True),
        ("windows", "C:\\", "c:\\", True),
    ],
)
def test_path_key(flavor: PathFlavor, a: str, b: str, same: bool) -> None:
    assert (path_key(a, flavor) == path_key(b, flavor)) is same


@pytest.mark.parametrize(
    ("flavor", "path", "roots", "inside"),
    [
        ("posix", "/home/me", ["/home/me"], True),
        ("posix", "/home/me/a/b", ["/srv", "/home/me"], True),
        ("posix", "/home/meow", ["/home/me"], False),
        ("posix", "/anything", ["/"], True),
        ("posix", "/x", [], False),
        ("windows", "C:\\Work\\X", ["c:\\work"], True),
        ("windows", "D:\\Work", ["C:\\"], False),
        ("windows", "C:\\Work", ["C:\\"], True),
    ],
)
def test_is_within(flavor: PathFlavor, path: str, roots: list[str], inside: bool) -> None:
    assert is_within(path, roots, flavor) is inside


@pytest.mark.parametrize(
    ("flavor", "name", "ok"),
    [
        ("posix", "새 폴더", True),
        ("posix", ".hidden", True),
        ("posix", "a?b", True),
        ("posix", "", False),
        ("posix", "  ", False),
        ("posix", ".", False),
        ("posix", "..", False),
        ("posix", "a/b", False),
        ("posix", "a\\b", False),
        ("posix", "a:b", False),
        ("posix", "a\tb", False),
        ("windows", "a?b", False),
        ("windows", 'a"b', False),
        ("windows", "CON", False),
        ("windows", "lpt1.txt", False),
        ("windows", "trailing.", False),
        ("windows", "보통 이름", True),
    ],
)
def test_validate_folder_name(flavor: PathFlavor, name: str, ok: bool) -> None:
    if ok:
        assert validate_folder_name(name, flavor) == name.strip()
    else:
        with pytest.raises(FolderError) as info:
            validate_folder_name(name, flavor)
        assert info.value.code == FolderErrorCode.INVALID_NAME
