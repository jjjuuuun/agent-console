"""프로젝트 폴더 파일 접근(주입 지점 `SpecFiles`)과 경로 검사.

가져오기·내보내기·가져오기 파일 목록·파일을 읽는 검증 출처는 `SpecFiles`만 쓴다. 경로는 늘
**프로젝트
폴더 기준 POSIX 상대 경로**(빈 값 = 폴더 루트)다. 이 패키지는 경로를 먼저 검사하고(`..`·절대 경로·
드라이브·금지 문자·링크), 구현(`LocalSpecFiles`, 또는 `link-projects-sdd`의 공간 파일)은 폴더 밖으로
나가지 않음을 한 번 더 지킨다.
"""

from __future__ import annotations

import os
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_console_store import InvalidContentPath, atomic_write_bytes, check_content_path

from ._errors import SpecPathError

__all__ = [
    "LocalSpecFiles",
    "SpecFileEntry",
    "SpecFiles",
    "check_project_path",
]


@dataclass(frozen=True, slots=True)
class SpecFileEntry:
    """폴더 안 항목 하나(`SpecFiles.list`)."""

    name: str
    is_dir: bool = False
    is_link: bool = False
    size: int = 0


@runtime_checkable
class SpecFiles(Protocol):
    """프로젝트 폴더 안 파일 작업. 경로는 폴더 기준 POSIX 상대 경로(빈 값 = 루트).

    실패는 `OSError`(폴더 밖·링크는 `SpecPathError`도 가능)로 알린다. 없는 파일 읽기만 None.
    """

    def read(self, path: str) -> bytes | None:
        """파일 내용. 없거나 파일이 아니면 None."""
        ...

    def write(self, path: str, data: bytes) -> None:
        """상위 폴더를 만들고 원자적으로 쓴다(있으면 바꾼다)."""
        ...

    def exists(self, path: str) -> bool:
        """파일이나 폴더가 있다."""
        ...

    def is_link(self, path: str) -> bool:
        """심볼릭 링크·정션이다(없으면 False)."""
        ...

    def list(self, path: str) -> list[SpecFileEntry]:
        """폴더 바로 아래 항목(재귀하지 않음). 폴더가 아니면 `NotADirectoryError`, 없으면
        `FileNotFoundError`."""
        ...


def check_project_path(
    path: str,
    files: SpecFiles | None = None,
    *,
    allow_root: bool = False,
    reserved: Collection[str] = (),
) -> str:
    """프로젝트 폴더 기준 상대 경로를 검사하고 정규화한다.

    Args:
        path: 검사할 경로(`/` 구분, 역슬래시는 거부).
        files: 주면 경로의 각 구성요소(앞부분 포함)가 링크인지 확인해 링크면 거부한다.
        allow_root: 빈 경로(폴더 루트)를 허락한다.
        reserved: 첫 구성요소로 쓸 수 없는 이름(예: 앱 구성 폴더 `.agent-console`). 대소문자 무시.

    Returns:
        정규화한 경로(빈 값 = 루트).

    Raises:
        SpecPathError: `invalid`(`..`·절대·드라이브·금지 문자·빈 구성요소), `reserved`, `link`.
    """
    if path in ("", ".") and allow_root:
        return ""
    try:
        norm = check_content_path(path)
    except InvalidContentPath:
        raise SpecPathError(path, "invalid") from None
    parts = norm.split("/")
    folded = {r.casefold() for r in reserved}
    if parts[0].casefold() in folded:
        raise SpecPathError(path, "reserved")
    if files is not None:
        for i in range(1, len(parts) + 1):
            if files.is_link("/".join(parts[:i])):
                raise SpecPathError(path, "link")
    return norm


class LocalSpecFiles:
    """폴더 하나를 루트로 하는 `SpecFiles` 기본 구현(지금 컴퓨터 파일 시스템).

    경로를 `check_project_path`로 검사하고, 링크를 푼 실제 경로가 루트 안인지 한 번 더 확인한다.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, path: str, *, allow_root: bool = True) -> Path:
        norm = check_project_path(path, allow_root=allow_root)
        target = self._root / norm if norm else self._root
        real_root = os.path.realpath(self._root)
        real = os.path.realpath(target)
        if real != real_root and not real.startswith(real_root.rstrip(os.sep) + os.sep):
            raise SpecPathError(path, "link")
        return target

    def read(self, path: str) -> bytes | None:
        target = self._resolve(path, allow_root=False)
        try:
            return target.read_bytes() if target.is_file() else None
        except FileNotFoundError:
            return None

    def write(self, path: str, data: bytes) -> None:
        atomic_write_bytes(self._resolve(path, allow_root=False), data)

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def is_link(self, path: str) -> bool:
        norm = check_project_path(path, allow_root=True)
        if not norm:
            return False
        target = self._root / norm
        return target.is_symlink() or target.is_junction()

    def list(self, path: str) -> list[SpecFileEntry]:
        target = self._resolve(path)
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_dir():
            raise NotADirectoryError(path)
        out: list[SpecFileEntry] = []
        with os.scandir(target) as it:
            for entry in it:
                link = entry.is_symlink() or Path(entry.path).is_junction()
                is_dir = entry.is_dir(follow_symlinks=False)
                size = 0
                if not is_dir and not link:
                    try:
                        size = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        size = 0
                out.append(SpecFileEntry(name=entry.name, is_dir=is_dir, is_link=link, size=size))
        return out
