"""폴더 안 이름 배치. 이름은 전부 데이터(인자)이고 기본값만 여기 있다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

DEFAULT_CONFIG_DIR = ".agent-console"
"""프로젝트 폴더 안 구성 폴더 이름의 기본값(설치자가 바꿀 수 있다, design §PI.4.1)."""


def check_relative(name: str, *, what: str) -> str:
    """폴더 밖으로 나가지 않는 상대 경로인지 확인한다.

    Raises:
        ValueError: 비었거나, 절대 경로이거나, `..`·드라이브·역슬래시가 있다.
    """
    posix = PurePosixPath(name)
    if (
        not name.strip()
        or "\\" in name
        or posix.is_absolute()
        or PureWindowsPath(name).drive
        or ".." in posix.parts
        or "." in posix.parts
    ):
        raise ValueError(f"{what} must be a plain relative path inside the folder: {name!r}")
    return name


@dataclass(frozen=True, slots=True)
class SpaceLayout:
    """구성 폴더(`<folder>/<config_dir>/`) 안의 파일 이름. 모두 상대 경로다."""

    manifest_file: str = "project.yaml"
    gitignore_file: str = ".gitignore"
    memory_file: str = "memory.sqlite3"
    records_file: str = "records.sqlite3"
    sessions_dir: str = "sessions"
    state_dir: str = ".state"

    def __post_init__(self) -> None:
        for what in (
            "manifest_file",
            "gitignore_file",
            "memory_file",
            "records_file",
            "sessions_dir",
            "state_dir",
        ):
            check_relative(getattr(self, what), what=what)
