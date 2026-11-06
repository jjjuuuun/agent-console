"""프로젝트 폴더 안만 읽고 쓰는 ``SpecFiles``(design §6R.13, §PI.5 경로 지킴).

``agent_console_sdd.LocalSpecFiles``(경로 문자열 검사 + realpath가 루트 안인지) 위에 세 가지를
더한다.

1. **예약 경로**: 앱 구성 폴더(``.agent-console`` 등, 공간이 알려 준 값)와 설치자 옵션의 폴더는
   읽기·쓰기·목록·존재 확인 모두 ``SpecPathError(reason="reserved")``(422 ``folders.invalid_path``).
   구성 폴더는 정의 저장소 몫이고 가져오기·내보내기로 손대지 않는다. 경로 앞부분 비교는 대소문자를
   무시한다(대소문자를 무시하는 파일 시스템에서 우회되지 않게).
2. **폴더 안 확인 한 번 더**: 링크를 푼 실제 경로가 프로젝트 폴더 안인지를 ``ac-projects``의
   ``FolderGuard``(§PI.5 경로 지킴 — 예약 비교와 함께 ``link-projects-wiki``와 같은 규칙)로 본다.
   밖이면 ``reason="link"``.
3. **쓰기 불가**: ``writable=False``거나 쓰기가 ``PermissionError``면 ``ConfigReadonly``
   (409 ``project.config_readonly``). 앱이 쓰지 못하는 폴더에서 서버 오류(500)가 나지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path

from agent_console_project_space import ConfigReadonly
from agent_console_projects import FolderGuard, normalize_reserved
from agent_console_sdd import LocalSpecFiles, SpecFileEntry, SpecPathError, check_project_path

__all__ = ["ProjectSpecFiles", "normalize_reserved"]


class ProjectSpecFiles:
    """프로젝트 폴더 하나의 ``SpecFiles``(``agent_console_sdd.SpecFiles`` 프로토콜).

    경로는 폴더 기준 POSIX 상대 경로(빈 값 = 폴더 루트)다.

    Args:
        folder: 프로젝트 폴더.
        reserved: 손대지 않을 폴더(폴더 기준 상대 경로, 그 아래 전부). 보통 앱 구성 폴더.
        writable: 거짓이면 쓰기를 ``ConfigReadonly``로 거부한다(보통 공간의 ``config_writable``).
        realpath: 링크 풀기(주입, 기본 ``os.path.realpath``).

    >>> import tempfile
    >>> folder = Path(tempfile.mkdtemp())
    >>> files = ProjectSpecFiles(folder, reserved=[".agent-console"])
    >>> files.write("docs/a.md", b"# A")
    >>> files.read("docs/a.md")
    b'# A'
    >>> try:
    ...     files.write(".Agent-Console/x.md", b"x")
    ... except SpecPathError as exc:
    ...     exc.details["reason"]
    'reserved'
    """

    def __init__(
        self,
        folder: str | os.PathLike[str],
        *,
        reserved: Iterable[str] = (),
        writable: bool = True,
        realpath: Callable[[str], str] = os.path.realpath,
    ) -> None:
        self._folder = Path(folder)
        self._local = LocalSpecFiles(self._folder)
        self._guard = FolderGuard(self._folder, reserved=reserved, realpath=realpath)
        self._writable = writable

    @property
    def folder(self) -> Path:
        """프로젝트 폴더."""
        return self._folder

    @property
    def reserved(self) -> tuple[str, ...]:
        """예약 경로(정리한 값)."""
        return self._guard.reserved

    @property
    def writable(self) -> bool:
        """쓰기를 받는가."""
        return self._writable

    # ---- 검사 ------------------------------------------------------------------

    def _check(self, path: str, *, allow_root: bool = True) -> str:
        norm = check_project_path(path, allow_root=allow_root)
        reason = self._guard.violation(norm)
        if reason is not None:
            raise SpecPathError(path, reason)
        return norm

    # ---- SpecFiles --------------------------------------------------------------

    def read(self, path: str) -> bytes | None:
        """파일 내용(없거나 파일이 아니면 None)."""
        return self._local.read(self._check(path, allow_root=False))

    def write(self, path: str, data: bytes) -> None:
        """상위 폴더를 만들고 원자적으로 쓴다.

        Raises:
            SpecPathError: 경로가 틀렸거나 예약·폴더 밖이다.
            ConfigReadonly: 폴더에 쓸 수 없다.
        """
        norm = self._check(path, allow_root=False)
        if not self._writable:
            raise ConfigReadonly("프로젝트 폴더에 쓸 수 없습니다")
        try:
            self._local.write(norm, data)
        except PermissionError:
            raise ConfigReadonly("프로젝트 폴더에 쓸 수 없습니다") from None

    def exists(self, path: str) -> bool:
        """파일이나 폴더가 있다."""
        return self._local.exists(self._check(path))

    def is_link(self, path: str) -> bool:
        """심볼릭 링크·정션이다(예약 경로는 ``SpecPathError``)."""
        norm = check_project_path(path, allow_root=True)
        if self._guard.is_reserved(norm):
            raise SpecPathError(path, "reserved")
        return self._local.is_link(norm)

    def list(self, path: str) -> list[SpecFileEntry]:
        """폴더 바로 아래 항목(재귀 없음). 예약 경로 항목은 뺀다.

        하위 폴더는 링크를 푼 실제 경로가 프로젝트 폴더 안인지 한 번 더 보고, 밖이면 링크로 표시한다
        (``is_link=True`` — 가져오기 목록이 빼고, 그 경로를 열면 ``SpecPathError(link)``). 링크로
        알아보지 못하는 재분석 지점(일부 Windows 정션 등)이 폴더 밖을 가리켜도 고를 수 없게 한다.
        """
        norm = self._check(path)
        out: list[SpecFileEntry] = []
        for entry in self._local.list(norm):
            rel = f"{norm}/{entry.name}" if norm else entry.name
            if self._guard.is_reserved(rel):
                continue
            if entry.is_dir and not entry.is_link and not self._guard.resolves_inside(rel):
                entry = replace(entry, is_link=True)
            out.append(entry)
        return out
