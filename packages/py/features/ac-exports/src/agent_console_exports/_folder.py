"""허용한 폴더 루트 아래에만 쓰기(설치자 설정 `exports.roots`).

안전 규칙(CLAUDE.md 안전 규칙, design §2R.7):

- 루트는 설치자가 등록한 것만. 웹·요청은 루트 id와 그 아래 상대 폴더(`subdir`)만 고른다.
- 상대 경로 검사(`path_problem`): 탈출(`..`)·절대 경로·Windows 금지 이름 거부.
- 루트부터 대상 파일까지 이미 있는 구성요소가 심볼릭 링크·정션이면 거부(링크를 따라 밖에 쓰지 않음).
- 보호 위치(예: `~/.claude`, 외부 도구 원본) 안에는 쓰지 않는다 — 루트로 등록해도 그 루트는 쓸 수
  없고, 루트가 보호 위치의 상위 폴더면 보호 위치 안으로 들어가는 파일만 거부한다. 비교는 대소문자를
  무시한다(Windows·macOS 파일 시스템).
- 쓰기는 파일마다 같은 폴더의 임시 파일 → `os.replace`(중간 상태의 반쯤 쓴 파일을 남기지 않음).
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_console_contracts import (
    ExportConflictPolicy,
    ExportFile,
    ExportRootInfo,
    Issue,
)

from ._errors import ExportConflictError, ExportValidationError, UnknownExportRootError
from ._interfaces import ExportIssueCodes, OutputFile
from ._paths import path_problem

__all__ = ["ExportRoot", "FolderWriter"]

_log = logging.getLogger(__name__)

_TEMP_SUFFIX = ".ac-export-tmp"


@dataclass(frozen=True, slots=True)
class ExportRoot:
    """쓰기를 허용한 폴더 하나(설치자 설정).

    Attributes:
        id: 요청에서 고르는 id.
        path: 절대 경로(있는 폴더여야 쓸 수 있다).
        label: 화면 이름.
    """

    id: str
    path: Path
    label: str = ""


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _inside(child: Path, parent: Path) -> bool:
    """`child`가 `parent`이거나 그 아래면 참(대소문자 무시)."""
    c = [p.casefold() for p in child.parts]
    p = [q.casefold() for q in parent.parts]
    return len(c) >= len(p) and c[: len(p)] == p


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _path_issue(message: str, path: str, **details: str) -> Issue:
    return Issue(
        severity="error",
        code=ExportIssueCodes.UNSAFE_PATH,
        message=message,
        path=path,
        details=dict(details),
    )


class FolderWriter:
    """허용 루트 아래 폴더에 내보낸 파일을 쓴다.

    Args:
        roots: 허용 루트(같은 id는 앞의 것).
        protected: 쓰지 않을 보호 위치(예: `~/.claude`).
    """

    def __init__(self, roots: Sequence[ExportRoot] = (), *, protected: Sequence[Path] = ()) -> None:
        self._roots: dict[str, ExportRoot] = {}
        for root in roots:
            self._roots.setdefault(root.id, root)
        self._protected = [_real(p) for p in protected]

    # ------------------------------------------------------------ 루트

    def _unusable(self, root: ExportRoot) -> str | None:
        path = root.path
        if not path.is_absolute():
            return "루트는 절대 경로여야 합니다"
        if _is_link(path):
            return "루트가 링크입니다"
        if not path.is_dir():
            return "루트 폴더가 없습니다"
        real = _real(path)
        if any(_inside(real, p) for p in self._protected):
            return "보호 위치 안의 루트입니다"
        return None

    def roots(self) -> list[ExportRoot]:
        """지금 쓸 수 있는 루트(등록 순서). 쓸 수 없는 루트는 경고 로그만 남기고 뺀다."""
        usable: list[ExportRoot] = []
        for root in self._roots.values():
            reason = self._unusable(root)
            if reason is None:
                usable.append(root)
            else:
                _log.warning("내보내기 루트 %s를 쓸 수 없습니다: %s", root.id, reason)
        return usable

    def root_infos(self, *, expose_paths: bool = True) -> list[ExportRootInfo]:
        """`GET /exports/roots` 응답. `expose_paths=False`면 경로를 비운다."""
        return [
            ExportRootInfo(id=r.id, label=r.label or r.id, path=str(r.path) if expose_paths else "")
            for r in self.roots()
        ]

    def _root(self, root_id: str) -> ExportRoot:
        root = self._roots.get(root_id)
        if root is None:
            raise UnknownExportRootError(f"내보내기 루트가 없습니다: {root_id}")
        reason = self._unusable(root)
        if reason is not None:
            raise UnknownExportRootError(f"내보내기 루트 {root_id}를 쓸 수 없습니다: {reason}")
        return root

    # ------------------------------------------------------------ 경로

    def _check_chain(self, base: Path, parts: Sequence[str], *, pointer: str) -> None:
        """`base`부터 `parts`를 따라가며 이미 있는 구성요소가 링크가 아닌지·폴더 자리에 파일이
        없는지 검사한다(마지막은 파일 자리)."""
        current = base
        for index, part in enumerate(parts):
            current = current / part
            if not os.path.lexists(current):
                return
            if _is_link(current):
                raise ExportValidationError(
                    "링크가 있는 경로에는 쓰지 않습니다",
                    issues=[_path_issue("링크가 있는 경로에는 쓰지 않습니다", pointer)],
                )
            last = index == len(parts) - 1
            if not last and not current.is_dir():
                raise ExportValidationError(
                    "폴더 자리에 파일이 있습니다",
                    issues=[_path_issue("폴더 자리에 파일이 있습니다", pointer)],
                )
            if last and current.is_dir():
                raise ExportValidationError(
                    "파일 자리에 폴더가 있습니다",
                    issues=[_path_issue("파일 자리에 폴더가 있습니다", pointer)],
                )

    def _target(self, root_id: str, subdir: str) -> tuple[Path, list[str]]:
        root = self._root(root_id)
        problem = path_problem(subdir, allow_empty=True)
        if problem is not None:
            raise ExportValidationError(problem, issues=[_path_issue(problem, "/subdir")])
        parts = subdir.split("/") if subdir else []
        if parts:
            current = root.path
            for part in parts:
                current = current / part
                if os.path.lexists(current) and (_is_link(current) or not current.is_dir()):
                    message = "하위 폴더 경로에 링크나 파일이 있습니다"
                    raise ExportValidationError(message, issues=[_path_issue(message, "/subdir")])
        return root.path, parts

    def _dest(self, root: Path, sub: list[str], file: OutputFile) -> Path:
        problem = path_problem(file.path)
        if problem is not None:
            raise ExportValidationError(problem, issues=[_path_issue(problem, "", file=file.path)])
        parts = [*sub, *file.path.split("/")]
        self._check_chain(root, parts, pointer="/subdir")
        dest = root.joinpath(*parts)
        real = _real(dest)
        if not _inside(real, _real(root)):
            message = "루트 밖을 가리키는 경로입니다"
            raise ExportValidationError(message, issues=[_path_issue(message, "", file=file.path)])
        if any(_inside(real, p) for p in self._protected):
            message = "보호 위치(외부 도구 원본) 안에는 쓰지 않습니다"
            raise ExportValidationError(message, issues=[_path_issue(message, "", file=file.path)])
        return dest

    @staticmethod
    def _action(dest: Path, data: bytes) -> str:
        if not os.path.lexists(dest):
            return "create"
        try:
            same = dest.read_bytes() == data
        except OSError:
            same = False
        return "skip" if same else "conflict"

    def _check_duplicates(self, files: Sequence[OutputFile]) -> None:
        seen: dict[str, str] = {}
        for file in files:
            key = file.path.casefold()
            if key in seen:
                message = "대소문자만 다르거나 같은 경로가 두 번 있습니다"
                raise ExportValidationError(
                    message, issues=[_path_issue(message, "", file=file.path, other=seen[key])]
                )
            seen[key] = file.path

    # ------------------------------------------------------------ 공개

    def plan(self, files: Sequence[OutputFile], root_id: str, subdir: str = "") -> list[ExportFile]:
        """목적지 기준 동작: 없음 = create, 같은 내용 = skip, 다른 내용 = conflict(쓰지 않음).

        Raises:
            UnknownExportRootError: 루트가 없거나 쓸 수 없을 때.
            ExportValidationError: 경로가 안전하지 않을 때.
        """
        root, sub = self._target(root_id, subdir)
        self._check_duplicates(files)
        out: list[ExportFile] = []
        for file in files:
            dest = self._dest(root, sub, file)
            out.append(
                ExportFile(
                    path=file.path,
                    media_type=file.media_type,
                    size=len(file.data),
                    action=self._action(dest, file.data),  # type: ignore[arg-type]
                )
            )
        return out

    def write(
        self,
        files: Sequence[OutputFile],
        root_id: str,
        subdir: str = "",
        *,
        on_conflict: ExportConflictPolicy = "fail",
    ) -> list[ExportFile]:
        """파일을 쓴다. 반환 `action`은 실제로 한 동작(create·overwrite·skip).

        `on_conflict`: `fail`(기본) = 다른 내용의 파일이 하나라도 있으면 아무것도 쓰지 않고
        `ExportConflictError`, `skip` = 그 파일만 건너뜀, `overwrite` = 덮어씀.
        같은 내용은 항상 skip.

        Raises:
            UnknownExportRootError, ExportValidationError, ExportConflictError.
        """
        planned = self.plan(files, root_id, subdir)
        conflicts = [p.path for p in planned if p.action == "conflict"]
        if conflicts and on_conflict == "fail":
            raise ExportConflictError(
                f"이미 있는 파일 {len(conflicts)}개와 내용이 달라 쓰지 않았습니다",
                details={"paths": conflicts},
            )
        root, sub = self._target(root_id, subdir)
        result: list[ExportFile] = []
        for file, plan in zip(files, planned, strict=True):
            action = plan.action
            if action == "conflict":
                action = "overwrite" if on_conflict == "overwrite" else "skip"
            if action in ("create", "overwrite"):
                dest = self._dest(root, sub, file)
                self._write_file(root, sub, file, dest)
            result.append(plan.model_copy(update={"action": action}))
        return result

    def _write_file(self, root: Path, sub: list[str], file: OutputFile, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._dest(root, sub, file)  # 폴더를 만든 뒤 다시 확인(그사이 링크로 바뀐 경우)
        temp = dest.with_name(dest.name + _TEMP_SUFFIX)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )
        with contextlib.suppress(FileNotFoundError):
            if not _is_link(temp):
                temp.unlink()
        fd = os.open(temp, flags, 0o644)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(file.data)
            os.replace(temp, dest)
        except BaseException:
            with contextlib.suppress(OSError):
                temp.unlink()
            raise
