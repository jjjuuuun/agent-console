"""`SpecFiles` 위의 글롭 찾기(프로젝트 폴더 안만).

파일 시스템을 직접 보지 않고 주입받은 `SpecFiles.list`·`read`만 쓴다. 링크(심볼릭 링크·정션)는
따라가지 않고, `**`는 숨김 폴더(`.`으로 시작)로 내려가지 않는다. 찾은 경로는 `check_project_path`로
한 번 더 검사한다(경로 앞부분에 링크가 있으면 버린다).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

from agent_console_sdd import SddError, SpecFiles, check_project_path

from ._options import check_file_pattern

__all__ = ["FoundFiles", "find_files"]

_GLOB_CHARS = frozenset("*?[")


@dataclass
class FoundFiles:
    """찾기 결과. `truncated` = 상한에 걸려 더 찾지 않음."""

    paths: list[str] = field(default_factory=list)
    truncated: bool = False


class _LimitError(Exception):
    pass


def _is_glob(part: str) -> bool:
    return any(ch in _GLOB_CHARS for ch in part)


def find_files(
    files: SpecFiles,
    patterns: Sequence[str],
    *,
    max_files: int = 50,
    max_dirs: int = 2000,
) -> FoundFiles:
    """패턴에 맞는 파일 경로(폴더 기준 POSIX, 이름 순, 중복 없음).

    Args:
        files: 프로젝트 폴더 파일 접근.
        patterns: 파일 패턴(`check_file_pattern` 규칙).
        max_files: 찾을 파일 수 상한.
        max_dirs: 살펴볼 폴더 수 상한.

    Raises:
        ValueError: 폴더 밖을 가리키는 패턴.
    """
    checked = [check_file_pattern(p) for p in patterns]
    found: set[str] = set()
    visited = 0
    out = FoundFiles()

    def listing(directory: str) -> list[tuple[str, bool]]:
        nonlocal visited
        visited += 1
        if visited > max_dirs:
            raise _LimitError
        try:
            entries = files.list(directory)
        except (OSError, SddError):
            return []
        return [(e.name, e.is_dir) for e in entries if not e.is_link]

    def add(path: str) -> None:
        if path in found:
            return
        try:
            check_project_path(path, files)
        except SddError:
            return
        if len(found) >= max_files:
            raise _LimitError
        found.add(path)

    def join(directory: str, name: str) -> str:
        return f"{directory}/{name}" if directory else name

    def walk(directory: str, parts: list[str]) -> None:
        head, rest = parts[0], parts[1:]
        if head == "**":
            walk(directory, rest)
            for name, is_dir in listing(directory):
                if is_dir and not name.startswith("."):
                    walk(join(directory, name), parts)
            return
        if not _is_glob(head):
            target = join(directory, head)
            if not rest:
                if _is_file(files, target):
                    add(target)
            else:
                walk(target, rest)
            return
        for name, is_dir in listing(directory):
            if not fnmatchcase(name, head):
                continue
            if rest and is_dir:
                walk(join(directory, name), rest)
            elif not rest and not is_dir:
                add(join(directory, name))

    try:
        for pattern in checked:
            walk("", pattern.split("/"))
    except _LimitError:
        out.truncated = True
    out.paths = sorted(found)
    return out


def _is_file(files: SpecFiles, path: str) -> bool:
    """있고 링크가 아니다(파일인지는 읽을 때 `read`가 None으로 알린다)."""
    try:
        return files.exists(path) and not files.is_link(path)
    except (OSError, SddError):
        return False
