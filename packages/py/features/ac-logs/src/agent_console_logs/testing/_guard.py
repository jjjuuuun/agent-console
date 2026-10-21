"""원본 읽기 전용 확인 도구(출처 테스트용): 열기 기록, 쓰기 감시, 폴더 해시."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO
from unittest import mock

from agent_console_logs._source import read_only_open

__all__ = ["RecordingOpen", "WriteAttempt", "no_writes_under", "tree_digest"]

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


class WriteAttempt(AssertionError):  # noqa: N818 - 테스트 실패로 읽히게 AssertionError
    """감시 중인 폴더에 쓰기·지우기·옮기기를 시도했다."""


class RecordingOpen:
    """`open_read` 대역: 연 경로를 기록하고 읽기 전용으로 연다."""

    def __init__(self, inner: Callable[[Path], BinaryIO] = read_only_open) -> None:
        self.opened: list[Path] = []
        self._inner = inner

    def __call__(self, path: Path) -> BinaryIO:
        self.opened.append(Path(path))
        return self._inner(path)


def _under(path: Any, root: Path) -> bool:
    try:
        return Path(os.fsdecode(path)).resolve().is_relative_to(root)
    except (TypeError, ValueError, OSError):
        return False


@contextmanager
def no_writes_under(root: Path) -> Iterator[None]:
    """블록 안에서 `root` 아래 파일을 쓰기 모드로 열거나 지우거나 옮기면 `WriteAttempt`를 낸다.

    `builtins.open`·`io.open`·`os.open`·`os.remove`·`os.unlink`·`os.rename`·`os.replace`·
    `os.rmdir`·`os.mkdir`을 감싼다(`Path` 메서드도 이것들을 거친다).
    """
    base = Path(root).resolve()
    real_open = builtins.open
    real_os_open = os.open

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        writing = any(ch in mode for ch in "wax+")
        if writing and isinstance(file, str | bytes | os.PathLike) and _under(file, base):
            raise WriteAttempt(f"쓰기 시도: {os.fsdecode(file)} ({mode})")
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & _WRITE_FLAGS and _under(path, base):
            raise WriteAttempt(f"쓰기 시도: {path} (os.open)")
        return real_os_open(path, flags, *args, **kwargs)

    def forbid(name: str) -> Callable[..., Any]:
        real = getattr(os, name)

        def wrapper(path: Any, *args: Any, **kwargs: Any) -> Any:
            if _under(path, base):
                raise WriteAttempt(f"{name} 시도: {path}")
            return real(path, *args, **kwargs)

        return wrapper

    patches: list[Any] = [
        mock.patch.object(builtins, "open", guarded_open),
        mock.patch.object(io, "open", guarded_open),
        mock.patch.object(os, "open", guarded_os_open),
        *(
            mock.patch.object(os, n, forbid(n))
            for n in ("remove", "unlink", "rename", "replace", "rmdir", "mkdir")
        ),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


def tree_digest(root: Path) -> dict[str, str]:
    """폴더 아래 파일별 sha256(상대 경로 → 해시). 수집 전후 비교용."""
    out: dict[str, str] = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out
