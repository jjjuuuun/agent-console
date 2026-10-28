"""실제 파일 시스템(`os` 위). 이 모듈만 디스크에 닿는다."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator

from ._types import PathFlavor, PathInfo, ScanEntry

__all__ = ["LocalFileSystem"]


def _hidden_attr(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_HIDDEN)


class LocalFileSystem:
    """이 프로세스가 도는 OS의 파일 시스템(`FileSystem` 구현).

    권한은 `os.access`로 본다(Windows는 읽기 전용 속성만 반영된다).
    경로 방식은 `os.name`으로 정한다.
    """

    @property
    def flavor(self) -> PathFlavor:
        """`windows`(os.name == "nt") 또는 `posix`."""
        return "windows" if os.name == "nt" else "posix"

    def info(self, path: str) -> PathInfo | None:
        """`os.stat`(링크를 따라감) + `os.access`. 없으면 `None`."""
        try:
            st = os.stat(path)
        except (FileNotFoundError, NotADirectoryError, ValueError):
            return None
        is_dir = stat.S_ISDIR(st.st_mode)
        enter = os.X_OK if is_dir else 0
        return PathInfo(
            is_dir=is_dir,
            is_link=os.path.islink(path) or _is_junction(path),
            hidden_attr=_hidden_attr(st),
            readable=os.access(path, os.R_OK | enter),
            writable=os.access(path, os.W_OK | enter),
        )

    def scan(self, path: str) -> Iterator[ScanEntry]:
        """`os.scandir`를 지연 반복(폴더만 숨김 속성을 읽는다)."""
        with os.scandir(path) as it:
            for entry in it:
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False
                try:
                    is_link = entry.is_symlink() or entry.is_junction()
                except OSError:
                    is_link = False
                hidden = False
                if is_dir and self.flavor == "windows":
                    try:
                        hidden = _hidden_attr(entry.stat(follow_symlinks=False))
                    except OSError:
                        hidden = False
                yield ScanEntry(name=entry.name, is_dir=is_dir, is_link=is_link, hidden_attr=hidden)

    def realpath(self, path: str) -> str:
        """`os.path.realpath`(엄격하지 않음)."""
        return os.path.realpath(path)

    def mkdir(self, path: str) -> None:
        """`os.mkdir`(상위는 만들지 않음)."""
        os.mkdir(path)


def _is_junction(path: str) -> bool:
    try:
        return os.path.isjunction(path)
    except OSError:
        return False
