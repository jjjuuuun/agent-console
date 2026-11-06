"""페이지 경로 규칙(design §7R.1.2·§7R.13).

페이지 경로 = 위키 폴더 기준 POSIX 상대 경로에서 페이지 확장자를 뺀 것(예 `decisions/api-version`).
`..`·절대 경로·드라이브·역슬래시·제어 문자·Windows 금지 문자·예약 장치 이름은 정의 본문 경로와 같은
규칙(`ac-store` `check_content_path`)으로 거부하고, `.`로 시작하는 구성요소(숨김)는 페이지가 아니다.
"""

from __future__ import annotations

import posixpath
from collections.abc import Collection, Sequence

from agent_console_store import InvalidContentPath, check_content_path

from ._errors import WikiPathError

__all__ = [
    "check_page_path",
    "file_for_page",
    "page_path_for_file",
    "relative_file",
    "split_extension",
]


def check_page_path(path: str, *, reserved: Collection[str] = ()) -> str:
    """페이지 경로(또는 위키 폴더 안 파일 경로)를 검사하고 정규화한다.

    Args:
        path: 검사할 경로(`/` 구분).
        reserved: 첫 구성요소로 쓸 수 없는 이름(대소문자 무시).

    Returns:
        정규화한 경로.

    Raises:
        WikiPathError: `invalid`·`hidden`·`reserved`.
    """
    try:
        norm = check_content_path(path)
    except InvalidContentPath:
        raise WikiPathError(path, "invalid") from None
    parts = norm.split("/")
    if any(p.startswith(".") for p in parts):
        raise WikiPathError(path, "hidden")
    if reserved and parts[0].casefold() in {r.casefold() for r in reserved}:
        raise WikiPathError(path, "reserved")
    return norm


def split_extension(name: str, extensions: Sequence[str]) -> tuple[str, str] | None:
    """`name`이 페이지 확장자 중 하나로 끝나면 (앞부분, 그 확장자 원문). 대소문자 무시. 아니면
    None."""
    folded = name.casefold()
    for ext in extensions:
        if ext and folded.endswith(ext.casefold()) and len(name) > len(ext):
            return name[: -len(ext)], name[-len(ext) :]
    return None


def page_path_for_file(file: str, extensions: Sequence[str]) -> str | None:
    """위키 폴더 안 파일 경로 → 페이지 경로. 페이지 파일이 아니거나 경로 규칙에 어긋나면 None."""
    split = split_extension(file, extensions)
    if split is None:
        return None
    try:
        return check_page_path(split[0])
    except WikiPathError:
        return None


def file_for_page(path: str, extension: str) -> str:
    """페이지 경로 + 확장자 → 파일 경로(경로를 검사한다).

    Raises:
        WikiPathError: 경로 규칙에 어긋남.
    """
    return check_page_path(check_page_path(path) + extension)


def relative_file(from_page: str, target_file: str) -> str:
    """페이지 `from_page`의 폴더에서 위키 폴더 기준 파일 `target_file`까지의 상대 경로."""
    base = posixpath.dirname(from_page) or "."
    return posixpath.relpath(target_file, base)
