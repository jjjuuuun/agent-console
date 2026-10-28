"""파일 시스템 접근(주입 지점). 매니페스트·`.gitignore`·쓰기 가능 판정이 이것만 쓴다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from agent_console_store import atomic_write_bytes


class SpaceFiles(Protocol):
    """공간이 쓰는 파일 작업. 실패는 `OSError`로 알린다(없는 파일 읽기만 `None`)."""

    def read_bytes(self, path: Path) -> bytes | None:
        """파일 내용. 없으면 None."""
        ...

    def write_bytes(self, path: Path, data: bytes) -> None:
        """상위 폴더를 만들고 원자적으로 쓴다(있으면 바꾼다)."""
        ...

    def create_bytes(self, path: Path, data: bytes) -> bool:
        """없을 때만 만든다. 만들었으면 True, 이미 있으면 False(건드리지 않는다)."""
        ...

    def is_dir(self, path: Path) -> bool: ...

    def is_link(self, path: Path) -> bool:
        """심볼릭 링크나 정션이다."""
        ...

    def is_writable(self, path: Path) -> bool:
        """그 폴더에 쓸 수 있다. 폴더가 없으면 가장 가까운 기존 상위 폴더로 판단한다."""
        ...


class LocalFiles:
    """지금 컴퓨터의 파일 시스템(`SpaceFiles` 기본 구현)."""

    def read_bytes(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def write_bytes(self, path: Path, data: bytes) -> None:
        atomic_write_bytes(path, data)

    def create_bytes(self, path: Path, data: bytes) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            return False
        return True

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def is_link(self, path: Path) -> bool:
        return path.is_symlink() or path.is_junction()

    def is_writable(self, path: Path) -> bool:
        probe = path
        while not probe.exists():
            if probe.parent == probe:
                return False
            probe = probe.parent
        return probe.is_dir() and os.access(probe, os.W_OK | os.X_OK)
