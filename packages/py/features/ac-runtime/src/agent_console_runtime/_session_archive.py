"""X38 백엔드 세션 기록 보관·복원(선택 능력, design §PI.4.6.4·K33-29).

대화를 이어 가려면(R4.6) 백엔드가 세션 원본(예: Claude Code ``projects/<키>/<세션>.jsonl``)을
찾을 수 있어야 한다. 원본은 앱마다 다른 곳(앱 자격 폴더)에 있으므로, 다른 앱이나 경로를 다시 지정한
뒤에도 이어 갈 수 있게 백엔드가 세 가지를 알려 준다.

- ``SessionArchive.files``: 보관할 원본 파일(자격·설정·다른 세션 파일은 절대 넣지 않는다).
- ``SessionArchive.status``: 이 앱에서 지금 이어 갈 수 있나(``available``·``relocatable``·
  ``missing``, 계약 ``KnownSessionStates``).
- ``SessionArchive.restore``: 보관 사본(또는 이 앱 안의 옛 위치)에서 이어 갈 수 있는 곳으로 놓는다.

백엔드는 선택 메서드 ``session_archive()``(``SessionArchiveCapable``)로 이 객체를 준다. 없거나
None이면 그 백엔드는 이어 가기 상태를 모른다(``not_applicable``). 보관 위치(프로젝트 폴더의
``sessions/``)와 켜기·끄기는 조립(연동 모듈)이 정한다 — 이 모듈은 폴더 이름을 모른다.

``JsonlFolderSessionArchive``는 "루트/<cwd 키>/<세션>.jsonl + <세션>/" 모양의 공용 구현이다
(Claude 구현과 fake 구현이 키 함수만 바꿔 쓴다).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from agent_console_contracts import KnownSessionStates

SESSION_ARCHIVE_HOOK = "session_archive"
"""``SessionArchiveCapable``의 메서드 이름(앱이 duck typing으로 찾는다)."""

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class SessionKey(Protocol):
    """세션 참조의 쓰는 부분(``SessionRef`` — 엔진·계약 둘 다 만족)."""

    @property
    def backend(self) -> str: ...

    @property
    def session_id(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ArchiveFile:
    """보관할 원본 파일 하나.

    Attributes:
        source: 원본 절대 경로.
        name: 보관 폴더 안 상대 이름(POSIX, ``..``·절대 경로 없음). 복원할 때 같은 이름으로 놓는다.
    """

    source: Path
    name: str


@runtime_checkable
class SessionArchive(Protocol):
    """백엔드 세션 기록 보관·복원(X38). 모든 메서드는 동기·파일 시스템만 쓴다(모델 호출 없음)."""

    def files(self, session: SessionKey, *, cwd: str | Path) -> list[ArchiveFile] | None:
        """보관할 원본 파일. 이 앱에 그 세션이 없으면 None.

        Args:
            session: 세션 참조.
            cwd: 그 세션을 돌린 작업 폴더(원본 위치를 정하는 데 쓴다).
        """
        ...

    def status(self, session: SessionKey, *, cwd: str | Path) -> str:
        """이 앱에서 지금 이어 갈 수 있나: ``available``(지금 위치에 있음)·``relocatable``(이 앱
        안 옛 위치에 있음)·``missing``(없음). 파일을 쓰지 않는다."""
        ...

    def restore(self, archive_dir: Path | None, session: SessionKey, *, cwd: str | Path) -> bool:
        """이어 갈 수 있게 놓는다.

        Args:
            archive_dir: 보관 사본 폴더(``files``가 준 이름 그대로 들어 있음). None이면 이 앱 안의
                옛 위치에서 지금 위치로 복사한다(경로 다시 지정).
            session: 세션 참조.
            cwd: 다음 실행의 작업 폴더.

        Returns:
            이제 이어 갈 수 있으면 True.
        """
        ...


@runtime_checkable
class SessionArchiveCapable(Protocol):
    """선택 능력: 세션 기록 보관·복원을 주는 백엔드."""

    def session_archive(self) -> SessionArchive | None:
        """이 백엔드의 보관 기능. 지금 쓸 수 없으면(예: 앱 전용 자격 폴더가 없음) None."""
        ...


def session_archive_of(backend: object) -> SessionArchive | None:
    """백엔드의 보관 기능(없거나 실패하면 None)."""
    if not isinstance(backend, SessionArchiveCapable):
        return None
    try:
        found = backend.session_archive()
    except Exception:
        return None
    return found if isinstance(found, SessionArchive) else None


def safe_name(text: str) -> bool:
    """폴더·파일 이름 한 조각으로 쓸 수 있나(영문자·숫자로 시작, ``._-``, 200자 이하).

    >>> safe_name("2f0c-aa"), safe_name("../x"), safe_name(".hidden"), safe_name("")
    (True, False, False, False)
    """
    return bool(_SAFE_NAME.match(text)) and ".." not in text


def safe_relative(name: str) -> bool:
    """보관 폴더 안 상대 이름으로 안전한가(절대 경로·``..``·빈 조각·역슬래시 없음).

    >>> safe_relative("s1.jsonl"), safe_relative("s1/subagents/a.jsonl")
    (True, True)
    >>> safe_relative("../x"), safe_relative("/etc/x"), safe_relative("a\\\\b"), safe_relative("")
    (False, False, False, False)
    """
    if not name or "\\" in name or name.startswith("/"):
        return False
    parts = PurePosixPath(name).parts
    return bool(parts) and all(p not in ("", ".", "..") for p in parts)


def copy_files(files: Iterable[ArchiveFile], dest: Path, *, dir_mode: int = 0o700) -> int:
    """파일을 ``dest/<name>``으로 복사한다(같은 폴더 임시 파일 → 바꿔치기, 수정 시각 유지).

    안전하지 않은 이름·링크·파일이 아닌 원본은 건너뛴다. ``dest`` 밖으로 나가지 않는다.

    Returns:
        복사한 파일 수.

    Raises:
        OSError: 폴더를 만들거나 쓸 수 없을 때.
    """
    count = 0
    root = Path(os.path.abspath(dest))
    for item in files:
        if not safe_relative(item.name):
            continue
        src = item.source
        if src.is_symlink() or not src.is_file():
            continue
        target = root.joinpath(*PurePosixPath(item.name).parts)
        target.parent.mkdir(parents=True, exist_ok=True, mode=dir_mode)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
        os.close(fd)
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        count += 1
    return count


def session_files_in(folder: Path, session_id: str, *, suffix: str = ".jsonl") -> list[ArchiveFile]:
    """``folder/<세션><suffix>``와 ``folder/<세션>/`` 아래 파일(링크 제외). 세션 파일이 없으면
    빈 목록.

    이름은 ``folder`` 기준 상대 이름이다. 그 밖의 파일(자격·설정·다른 세션)은 보지 않는다.
    """
    if not safe_name(session_id):
        return []
    main = folder / f"{session_id}{suffix}"
    if main.is_symlink() or not main.is_file():
        return []
    found = [ArchiveFile(main, main.name)]
    sub = folder / session_id
    if sub.is_dir() and not sub.is_symlink():
        for base, dirs, names in os.walk(sub, followlinks=False):
            here = Path(base)
            dirs[:] = sorted(d for d in dirs if not (here / d).is_symlink())
            for name in sorted(names):
                path = here / name
                if path.is_symlink() or not path.is_file():
                    continue
                found.append(ArchiveFile(path, path.relative_to(folder).as_posix()))
    return found


class BackendSessionArchives:
    """백엔드 id → 보관 기능(``runs.session_archive`` 포트 모양).

    Args:
        backend: 백엔드 id → 백엔드 객체(없으면 None). 부를 때마다 지금 레지스트리를 본다.
    """

    def __init__(self, backend: Callable[[str], object | None]) -> None:
        self._backend = backend

    def get(self, backend_id: str) -> SessionArchive | None:
        """그 백엔드의 보관 기능. 백엔드가 없거나 능력이 없으면 None(= ``not_applicable``)."""
        try:
            found = self._backend(backend_id)
        except Exception:
            return None
        return None if found is None else session_archive_of(found)


class JsonlFolderSessionArchive:
    """``<root>/<key(cwd)>/<세션><suffix>`` + ``<세션>/`` 모양 세션 기록의 보관·복원.

    - ``files``·``status``: 지금 키 폴더를 먼저 보고, 없으면 루트 아래 다른 키 폴더에서 같은 세션
      파일을 찾는다(세션 id는 앱 안에서 하나뿐이라 가정 — 경로를 다시 지정한 경우).
    - ``restore``: ``<root>/<key(cwd)>/``에만 쓴다. 보관 사본에서는 그 세션 이름의 파일만 가져온다
      (보관 폴더에 다른 파일이 있어도 쓰지 않는다).

    Args:
        root: 세션 기록 루트(예: 앱 자격 폴더의 ``projects``).
        key: 작업 폴더 → 키 폴더 이름.
        suffix: 세션 파일 확장자.
    """

    def __init__(self, root: Path, key: Callable[[str], str], *, suffix: str = ".jsonl") -> None:
        self.root = Path(os.path.abspath(root))
        self._key = key
        self._suffix = suffix

    def _current(self, cwd: str | Path) -> Path | None:
        name = self._key(os.path.abspath(str(cwd)))
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            return None
        return self.root / name

    def _locate(self, session_id: str, cwd: str | Path) -> tuple[Path | None, bool]:
        """(세션이 있는 키 폴더, 지금 키인가)."""
        if not safe_name(session_id):
            return None, False
        current = self._current(cwd)
        file_name = f"{session_id}{self._suffix}"
        if current is not None and _plain_file(current / file_name):
            return current, True
        try:
            folders = sorted(p for p in self.root.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return None, False
        for folder in folders:
            if folder != current and _plain_file(folder / file_name):
                return folder, False
        return None, False

    def files(self, session: SessionKey, *, cwd: str | Path) -> list[ArchiveFile] | None:
        folder, _ = self._locate(session.session_id, cwd)
        if folder is None:
            return None
        return session_files_in(folder, session.session_id, suffix=self._suffix) or None

    def status(self, session: SessionKey, *, cwd: str | Path) -> str:
        folder, current = self._locate(session.session_id, cwd)
        if folder is None:
            return KnownSessionStates.MISSING
        return KnownSessionStates.AVAILABLE if current else KnownSessionStates.RELOCATABLE

    def restore(self, archive_dir: Path | None, session: SessionKey, *, cwd: str | Path) -> bool:
        target = self._current(cwd)
        if target is None or not safe_name(session.session_id):
            return False
        if archive_dir is None:
            folder, current = self._locate(session.session_id, cwd)
            if folder is None:
                return False
            if current:
                return True
            source = folder
        else:
            source = archive_dir
        items = session_files_in(source, session.session_id, suffix=self._suffix)
        if not items:
            return False
        copy_files(items, target)
        return _plain_file(target / f"{session.session_id}{self._suffix}")


def _plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


__all__ = [
    "SESSION_ARCHIVE_HOOK",
    "ArchiveFile",
    "BackendSessionArchives",
    "JsonlFolderSessionArchive",
    "SessionArchive",
    "SessionArchiveCapable",
    "SessionKey",
    "copy_files",
    "safe_name",
    "safe_relative",
    "session_archive_of",
    "session_files_in",
]
