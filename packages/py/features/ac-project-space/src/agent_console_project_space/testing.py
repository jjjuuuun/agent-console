"""테스트 지원(다른 패키지 테스트도 쓸 수 있다): 쓸 수 없는 폴더를 흉내 내는 가짜 파일 시스템."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._files import LocalFiles


class ReadOnlyFiles(LocalFiles):
    """쓸 수 없는 폴더를 흉내 낸다: `is_writable`이 거짓이고 쓰기는 `PermissionError`.

    `writes`에 쓰려던 경로가 남는다(아무것도 쓰지 않았는지 확인용).
    """

    def __init__(self) -> None:
        self.writes: list[Path] = []

    def write_bytes(self, path: Path, data: bytes) -> None:
        self.writes.append(path)
        raise PermissionError(path.name)

    def create_bytes(self, path: Path, data: bytes) -> bool:
        self.writes.append(path)
        raise PermissionError(path.name)

    def is_writable(self, path: Path) -> bool:
        return False


class WriteFailsFiles(LocalFiles):
    """판정은 쓸 수 있다고 하지만 실제 쓰기가 실패한다(권한 판정이 틀린 폴더)."""

    def write_bytes(self, path: Path, data: bytes) -> None:
        raise PermissionError(path.name)

    def create_bytes(self, path: Path, data: bytes) -> bool:
        raise PermissionError(path.name)


def snapshot_tree(root: Path) -> dict[str, bytes]:
    """폴더 아래 모든 파일의 내용(상대 경로 -> 바이트). 바뀌지 않았는지 비교할 때 쓴다."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def sample_agent(id: str = "a1", **extra: Any) -> dict[str, Any]:
    """최소 에이전트 문서(`agent` 종류)."""
    return {"kind": "agent", "id": id, "name": "에이전트", **extra}
