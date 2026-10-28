"""경로 문자열 규칙(파일 시스템을 읽지 않는 순수 함수)."""

from __future__ import annotations

import ntpath
import posixpath
import re
from collections.abc import Iterable, Mapping
from types import ModuleType

from ._types import FolderError, FolderErrorCode, PathFlavor

__all__ = [
    "home_dir",
    "is_within",
    "normalize_lexical",
    "path_key",
    "path_module",
    "validate_folder_name",
]

_WINDOWS_ABS = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2}[^\\/]+[\\/])")
_DRIVE_LOWER = re.compile(r"^[a-z]:")
_QUOTES = ('"', "'")
# 폴더 이름에 쓸 수 없는 글자. Windows 서버는 OS 규칙 전체, 그 밖은 구분자·드라이브 구분자만.
_BAD_NAME_CHARS: dict[PathFlavor, str] = {"posix": "/\\:", "windows": '/\\:<>"|?*'}
_WINDOWS_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?$", re.IGNORECASE)


def path_module(flavor: PathFlavor) -> ModuleType:
    """경로 방식 → `posixpath`/`ntpath`(호스트 OS와 무관하게 쓰려고)."""
    return ntpath if flavor == "windows" else posixpath


def home_dir(environ: Mapping[str, str], flavor: PathFlavor) -> str | None:
    """환경변수에서 홈 폴더(`HOME`, Windows는 `USERPROFILE` 또는 `HOMEDRIVE`+`HOMEPATH`).

    >>> home_dir({"HOME": "/home/me"}, "posix")
    '/home/me'
    >>> home_dir({"HOMEDRIVE": "C:", "HOMEPATH": "\\\\Users\\\\me"}, "windows")
    'C:\\\\Users\\\\me'
    """
    if flavor == "windows":
        if environ.get("USERPROFILE"):
            return environ["USERPROFILE"]
        drive, rest = environ.get("HOMEDRIVE"), environ.get("HOMEPATH")
        return drive + rest if drive and rest else None
    return environ.get("HOME") or None


def _clean(raw: str) -> str:
    text = raw.strip()
    # 탐색기 "경로로 복사"처럼 따옴표로 감싼 붙여 넣기
    if len(text) >= 2 and text[0] == text[-1] and text[0] in _QUOTES:
        text = text[1:-1].strip()
    return text


def normalize_lexical(raw: str, *, flavor: PathFlavor, environ: Mapping[str, str]) -> str:
    """입력 → 정규화한 절대 경로(파일 시스템을 읽지 않음, 링크는 풀지 않음).

    앞뒤 공백·감싼 따옴표 제거, `~` 펼치기(`environ`), `.`·`..`·끝 구분자 정리, Windows는
    구분자 `\\`·드라이브 대문자.

    Raises:
        FolderError: `empty`·`invalid_path`(제어 문자)·`relative`·`foreign_path`(다른 OS 경로)·
            `no_home`(`~`인데 홈을 모름).

    >>> normalize_lexical(' "~/work/app/" ', flavor="posix", environ={"HOME": "/home/me"})
    '/home/me/work/app'
    >>> normalize_lexical("c:/Work/../App\\\\", flavor="windows", environ={})
    'C:\\\\App'
    >>> normalize_lexical("C:\\\\x", flavor="posix", environ={})
    Traceback (most recent call last):
    ...
    agent_console_local_folders._types.FolderError: 이 서버에서 쓸 수 없는 다른 OS 경로입니다.
    """
    text = _clean(raw)
    if not text:
        raise FolderError(FolderErrorCode.EMPTY, "경로가 비어 있습니다.")
    if any(ord(ch) < 32 for ch in text):
        raise FolderError(FolderErrorCode.INVALID_PATH, "경로에 쓸 수 없는 글자가 있습니다.")
    seps = ("/", "\\") if flavor == "windows" else ("/",)
    if text == "~" or any(text.startswith("~" + s) for s in seps):
        home = home_dir(environ, flavor)
        if not home:
            raise FolderError(FolderErrorCode.NO_HOME, "홈 폴더를 알 수 없습니다.")
        text = home + text[1:]
    if flavor == "posix":
        if not text.startswith("/"):
            if _WINDOWS_ABS.match(text):
                raise FolderError(
                    FolderErrorCode.FOREIGN_PATH, "이 서버에서 쓸 수 없는 다른 OS 경로입니다."
                )
            raise FolderError(FolderErrorCode.RELATIVE, "절대 경로를 입력하세요.")
        out = posixpath.normpath(text)
        return "/" + out.lstrip("/") if out.startswith("//") else out
    drive, _ = ntpath.splitdrive(text)
    if not drive or not ntpath.isabs(text):
        if text.startswith("/") and not text.startswith("//"):
            raise FolderError(
                FolderErrorCode.FOREIGN_PATH, "이 서버에서 쓸 수 없는 다른 OS 경로입니다."
            )
        raise FolderError(FolderErrorCode.RELATIVE, "절대 경로를 입력하세요.")
    out = ntpath.normpath(text)
    return out[0].upper() + out[1:] if _DRIVE_LOWER.match(out) else out


def path_key(path: str, flavor: PathFlavor) -> str:
    """비교용 키. Windows는 대소문자 무시·구분자 `\\`, 끝 구분자 없음(루트 제외).

    `posix`는 대소문자를 구분한다(대소문자를 무시하는 파일 시스템이어도 문자열 그대로 비교).

    >>> path_key("C:\\\\Work\\\\App\\\\", "windows"), path_key("/a/b/", "posix")
    ('c:\\\\work\\\\app', '/a/b')
    """
    pm = path_module(flavor)
    sep = "\\" if flavor == "windows" else "/"
    key = pm.normcase(path) if flavor == "windows" else path
    if flavor == "windows":
        key = key.casefold()
    while len(key) > 1 and key.endswith(sep) and pm.dirname(key) != key:
        key = key[:-1]
    return key


def is_within(path: str, roots: Iterable[str], flavor: PathFlavor) -> bool:
    """`path`가 `roots` 중 하나와 같거나 그 아래인가(정규화한 경로끼리 비교).

    >>> is_within("/home/me/a", ["/home/me"], "posix")
    True
    >>> is_within("/home/mex", ["/home/me"], "posix")
    False
    >>> is_within("c:\\\\Work\\\\x", ["C:\\\\work"], "windows")
    True
    """
    sep = "\\" if flavor == "windows" else "/"
    key = path_key(path, flavor)
    for root in roots:
        rkey = path_key(root, flavor)
        if key == rkey or key.startswith(rkey.rstrip(sep) + sep):
            return True
    return False


def validate_folder_name(name: str, flavor: PathFlavor) -> str:
    """새 폴더 이름 검사. 앞뒤 공백을 뗀 이름을 돌려준다.

    Raises:
        FolderError: `invalid_name`(빈 값, `.`·`..`, 구분자·`:`·제어 문자,
            Windows 금지 글자·예약 이름·끝 점).

    >>> validate_folder_name(" 새 폴더 ", "posix")
    '새 폴더'
    >>> validate_folder_name("a/b", "posix")
    Traceback (most recent call last):
    ...
    agent_console_local_folders._types.FolderError: 폴더 이름에 쓸 수 없는 글자가 있습니다: /
    """
    text = name.strip()
    if not text:
        raise FolderError(FolderErrorCode.INVALID_NAME, "폴더 이름을 입력하세요.")
    if text in (".", ".."):
        raise FolderError(FolderErrorCode.INVALID_NAME, "쓸 수 없는 폴더 이름입니다.")
    bad = sorted({ch for ch in text if ch in _BAD_NAME_CHARS[flavor] or ord(ch) < 32})
    if bad:
        shown = " ".join(ch if ord(ch) >= 32 else repr(ch) for ch in bad)
        raise FolderError(
            FolderErrorCode.INVALID_NAME, f"폴더 이름에 쓸 수 없는 글자가 있습니다: {shown}"
        )
    if flavor == "windows" and (_WINDOWS_RESERVED.match(text) or text.endswith(".")):
        raise FolderError(FolderErrorCode.INVALID_NAME, "Windows에서 쓸 수 없는 폴더 이름입니다.")
    return text
