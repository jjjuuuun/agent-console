"""페이지 파일 접근(주입 지점 `WikiPages`)과 지금 컴퓨터 폴더 구현 `LocalWikiPages`(design §7R.13).

경로는 늘 **위키 폴더 기준 POSIX 상대 파일 경로**(확장자 포함)다. 페이지 경로(확장자 없음)와의
변환은 `page_path_for_file`·`file_for_page`가 한다(확장자는 문법 데이터라 파일 접근은 모른다).

`LocalWikiPages`는 경로를 먼저 검사하고(`..`·절대·드라이브·역슬래시·금지 문자·숨김·예약 이름),
루트에서 대상까지 있는 구성요소가 심볼릭 링크·정션이면 읽지도 쓰지도 않는다. 검사한 뒤 열기 전에
폴더가 링크로 바뀌는 경우(TOCTOU)도 막는다: 디렉터리 fd를 쓸 수 있는 OS는 한 칸씩 `O_NOFOLLOW`로
열어 내려가며 그 fd 기준으로 열고 쓰고(`openat` 방식), Windows는 연 뒤 다시 확인한다. 쓰기는 같은
폴더 임시 파일 + 원자적 바꾸기다.
목록은 숨김 항목(`.`로 시작)·링크·페이지 확장자가 아닌 파일·경로 규칙에 어긋난 이름을 건너뛴다.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
import tempfile
import time
from collections.abc import Callable, Collection, Iterator, MutableMapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiIssue

from ._compiled import CompiledWikiSyntax
from ._errors import WikiPageExistsError, WikiPathError
from ._parse import ParsedPage, parse_page
from ._paths import check_page_path, page_path_for_file, split_extension

__all__ = ["LocalWikiPages", "PageFile", "ParseCache", "WikiPages", "read_pages"]

_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC: Final = getattr(os, "O_CLOEXEC", 0)
_BINARY: Final = getattr(os, "O_BINARY", 0)
_NONBLOCK: Final = getattr(os, "O_NONBLOCK", 0)
_DIR_FLAGS: Final = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _CLOEXEC
_READ_FLAGS: Final = os.O_RDONLY | _CLOEXEC | _BINARY
_CREATE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _CLOEXEC | _BINARY

_FD_OPS = (
    bool(getattr(os, "O_DIRECTORY", 0))
    and bool(_NOFOLLOW)
    and all(f in os.supports_dir_fd for f in (os.open, os.stat, os.mkdir, os.unlink, os.rename))
    and os.scandir in os.supports_fd
)
"""디렉터리 fd 방식(`openat`)을 쓸 수 있나(리눅스·macOS 참, Windows 거짓). 시험이 거짓으로 바꿔
경로 방식도 확인한다."""

type ParseCache = MutableMapping[str, tuple[int, float, ParsedPage]]
"""`read_pages` 파싱 캐시: 파일 경로 → (크기, 수정 시각, 파싱 결과). 크기·시각이 같으면 다시 읽지
않는다. 같은 문법으로만 쓴다(문법이 바뀌면 비운다)."""


@dataclass(frozen=True, slots=True)
class PageFile:
    """페이지 파일 하나의 정보.

    Attributes:
        file: 위키 폴더 기준 파일 경로(확장자 포함).
        size: 바이트 수.
        mtime: 마지막 수정 시각(유닉스 초).
    """

    file: str
    size: int
    mtime: float


@runtime_checkable
class WikiPages(Protocol):
    """위키 폴더 하나의 페이지 파일 작업. 경로는 폴더 기준 POSIX 상대 파일 경로.

    실패는 `OSError`(경로 규칙·링크는 `WikiPathError`)로 알린다. 없는 파일 읽기·정보만 None.
    """

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        """확장자가 `extensions` 중 하나인 페이지 파일 전부(하위 폴더 포함, 파일 경로 순)."""
        ...

    def stat(self, file: str) -> PageFile | None:
        """파일 정보. 없거나 파일이 아니면 None."""
        ...

    def read(self, file: str) -> bytes | None:
        """파일 내용. 없거나 파일이 아니면 None."""
        ...

    def write(self, file: str, data: bytes) -> None:
        """상위 폴더를 만들고 원자적으로 쓴다(있으면 바꾼다)."""
        ...

    def delete(self, file: str) -> bool:
        """파일을 지운다. 없었으면 False."""
        ...

    def move(self, src: str, dst: str) -> None:
        """파일을 옮긴다. `dst`가 있으면 `WikiPageExistsError`, `src`가 없으면
        `FileNotFoundError`."""
        ...


class LocalWikiPages:
    """폴더 하나를 루트로 하는 `WikiPages` 기본 구현(지금 컴퓨터 파일 시스템).

    링크 바꿔치기(검사한 뒤 열기 전에 폴더가 링크로 바뀜, TOCTOU)를 막는다:

    - 디렉터리 fd를 지원하는 OS(리눅스·macOS)는 기준 폴더를 연 fd에서 한 칸씩
      `O_NOFOLLOW`로 열어 내려가고, 파일 열기·임시 파일·바꾸기·지우기·옮기기를 모두 그 fd 기준으로
      한다(`openat` 방식). 검사와 열기가 같은 시스템 호출이라 사이가 없다.
    - 지원하지 않는 OS(Windows)는 경로로 검사한 뒤 열고, **연 뒤에 다시** 링크·실제 경로를 확인하고
      연 파일과 경로의 파일이 같은지(`fstat` 동일성) 비교한다. 다르면 `WikiPathError(link)`.

    Args:
        root: 위키 페이지 폴더. 없으면 목록은 비고 첫 쓰기 때 만든다.
        reserved: 첫 구성요소로 쓸 수 없는 이름(대소문자 무시).
        within: 루트가 들어 있어야 하는 기준 폴더(예: 프로젝트 폴더). 주면 루트의 실제 경로가 그
            안이어야 하고, 기준 폴더에서 루트까지도 링크 바꿔치기를 막으며 내려간다(루트가 기준 폴더
            안을 가리키는 링크인 것은 된다). 기준 폴더는 있어야 한다(만들지 않는다 — 사라진 프로젝트
            폴더를 다시 만들지 않게). 루트와 그 사이 폴더는 첫 쓰기 때 만든다. 없으면 루트 자체가
            기준이다(루트가 링크면 따라가고, 없으면 첫 쓰기 때 만든다).
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        reserved: Collection[str] = (),
        within: str | os.PathLike[str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._within = Path(within) if within is not None else None
        self._reserved = tuple(reserved)
        self._reserved_folded = frozenset(r.casefold() for r in reserved)

    @property
    def root(self) -> Path:
        return self._root

    # -- 디렉터리 fd 방식 ---------------------------------------------------------------------

    def _anchor_parts(self, file: str) -> tuple[Path, list[str]]:
        """처음 열 기준 폴더와 거기서 루트까지 내려갈 이름들."""
        if self._within is None:
            return self._root, []
        base = os.path.realpath(self._within)
        real = os.path.realpath(self._root)
        try:
            rel = Path(real).relative_to(base)
        except ValueError:
            raise WikiPathError(file, "link") from None
        return Path(base), [p for p in rel.parts if p]

    def _open_root(self, file: str, *, create: bool, stack: ExitStack) -> int | None:
        """루트 폴더 fd(닫기는 `stack`). 없으면 None(`create`면 만든다)."""
        anchor, parts = self._anchor_parts(file)
        if create and self._within is None:
            anchor.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(anchor, _DIR_FLAGS)
        except (FileNotFoundError, NotADirectoryError):
            return None
        stack.callback(os.close, fd)
        for part in parts:
            child = _open_dir_at(fd, part, create=create, file=file)
            if child is None:
                return None
            stack.callback(os.close, child)
            fd = child
        return fd

    def _open_parent(self, norm: str, file: str, *, create: bool, stack: ExitStack) -> int | None:
        """`norm`(검사한 경로)의 부모 폴더 fd. 없으면 None(`create`면 만든다)."""
        fd = self._open_root(file, create=create, stack=stack)
        for part in norm.split("/")[:-1]:
            if fd is None:
                return None
            child = _open_dir_at(fd, part, create=create, file=file)
            if child is None:
                return None
            stack.callback(os.close, child)
            fd = child
        return fd

    def _list_fd(self, extensions: Sequence[str]) -> list[PageFile]:
        out: list[PageFile] = []
        with ExitStack() as stack:
            try:
                root_fd = self._open_root("", create=False, stack=stack)
            except (WikiPathError, OSError):
                return out
            if root_fd is None:
                return out
            root_entries = _scan_fd(root_fd)
            if root_entries is None:
                return out
            # 깊이만큼만 fd를 연다: 폴더를 다 돌면 닫고 부모로 돌아간다.
            walk: list[tuple[int, str, Iterator[os.DirEntry[str]]]] = [
                (root_fd, "", iter(root_entries))
            ]
            stack.callback(_close_walk, walk, root_fd)
            while walk:
                folder_fd, prefix, entries = walk[-1]
                entry = next(entries, None)
                if entry is None:
                    walk.pop()
                    if folder_fd != root_fd:
                        os.close(folder_fd)
                    continue
                name = entry.name
                rel = f"{prefix}{name}"
                if not self._listable_name(name, prefix):
                    continue
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        child = os.open(name, _DIR_FLAGS | _NOFOLLOW, dir_fd=folder_fd)
                        child_entries = _scan_fd(child)
                        if child_entries is None:
                            os.close(child)
                            continue
                        walk.append((child, rel + "/", iter(child_entries)))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if split_extension(name, extensions) is None:
                        continue
                    if page_path_for_file(rel, extensions) is None:
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                out.append(PageFile(file=rel, size=st.st_size, mtime=st.st_mtime))
        out.sort(key=lambda f: f.file)
        return out

    def _stat_fd(self, file: str) -> PageFile | None:
        norm = check_page_path(file, reserved=self._reserved)
        with ExitStack() as stack:
            parent = self._open_parent(norm, file, create=False, stack=stack)
            if parent is None:
                return None
            st = _lstat_at(parent, norm.rsplit("/", 1)[-1], file)
        if st is None or not stat.S_ISREG(st.st_mode):
            return None
        return PageFile(file=norm, size=st.st_size, mtime=st.st_mtime)

    def _read_fd(self, file: str) -> bytes | None:
        norm = check_page_path(file, reserved=self._reserved)
        name = norm.rsplit("/", 1)[-1]
        with ExitStack() as stack:
            parent = self._open_parent(norm, file, create=False, stack=stack)
            if parent is None:
                return None
            st = _lstat_at(parent, name, file)
            if st is None or not stat.S_ISREG(st.st_mode):
                return None
            try:
                fd = os.open(name, _READ_FLAGS | _NOFOLLOW | _NONBLOCK, dir_fd=parent)
            except FileNotFoundError:
                return None
            except OSError:
                if _is_link_at(parent, name):
                    raise WikiPathError(file, "link") from None
                raise
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    return None
                return handle.read()

    def _write_fd(self, file: str, data: bytes) -> None:
        norm = check_page_path(file, reserved=self._reserved)
        name = norm.rsplit("/", 1)[-1]
        with ExitStack() as stack:
            parent = self._open_parent(norm, file, create=True, stack=stack)
            if parent is None:  # 기준 폴더(`within`)가 없다 — 만들지 않는다
                raise FileNotFoundError(file)
            _lstat_at(parent, name, file)  # 끝 칸이 링크면 거부
            tmp = f".{name}.{secrets.token_hex(6)}.tmp"
            fd = os.open(tmp, _CREATE_FLAGS | _NOFOLLOW, 0o600, dir_fd=parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, name, src_dir_fd=parent, dst_dir_fd=parent)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp, dir_fd=parent)
                raise

    def _delete_fd(self, file: str) -> bool:
        norm = check_page_path(file, reserved=self._reserved)
        name = norm.rsplit("/", 1)[-1]
        with ExitStack() as stack:
            parent = self._open_parent(norm, file, create=False, stack=stack)
            if parent is None or _lstat_at(parent, name, file) is None:
                return False
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                return False
        return True

    def _move_fd(self, src: str, dst: str) -> None:
        src_norm = check_page_path(src, reserved=self._reserved)
        dst_norm = check_page_path(dst, reserved=self._reserved)
        src_name = src_norm.rsplit("/", 1)[-1]
        dst_name = dst_norm.rsplit("/", 1)[-1]
        with ExitStack() as stack:
            src_parent = self._open_parent(src_norm, src, create=False, stack=stack)
            src_st = None if src_parent is None else _lstat_at(src_parent, src_name, src)
            if src_parent is None or src_st is None or not stat.S_ISREG(src_st.st_mode):
                raise FileNotFoundError(src)
            dst_parent = self._open_parent(dst_norm, dst, create=True, stack=stack)
            if dst_parent is None:  # 기준 폴더(`within`)가 없다 — 만들지 않는다
                raise FileNotFoundError(dst)
            dst_st = _lstat_at(dst_parent, dst_name, dst)
            if dst_st is not None and not os.path.samestat(src_st, dst_st):
                raise WikiPageExistsError(dst_norm)
            # 대소문자만 바꾸는 옮기기(대소문자 무시 파일 시스템)도 되도록 replace를 쓴다. 대상이
            # 없음은 위에서 확인했다.
            os.replace(src_name, dst_name, src_dir_fd=src_parent, dst_dir_fd=dst_parent)

    # -- 경로 방식(디렉터리 fd가 없는 OS): 검사 → 열기 → 연 뒤 다시 확인 -------------------------

    def _resolve(self, file: str) -> Path:
        norm = check_page_path(file, reserved=self._reserved)
        probe = self._root
        for part in norm.split("/"):
            probe = probe / part
            if probe.is_symlink() or probe.is_junction():
                raise WikiPathError(file, "link")
        target = self._root / norm
        real_root = os.path.realpath(self._root)
        if self._within is not None and not _inside(real_root, os.path.realpath(self._within)):
            raise WikiPathError(file, "link")
        if not _inside(os.path.realpath(target), real_root):
            raise WikiPathError(file, "link")
        return target

    def _verify_opened(self, file: str, fd: int) -> None:
        """연 뒤 다시 확인: 경로가 여전히 링크 없이 루트 안이고, 연 파일이 그 경로의 파일이다."""
        target = self._resolve(file)
        try:
            same = os.path.samestat(os.fstat(fd), os.stat(os.path.realpath(target)))
        except OSError:
            same = False
        if not same:
            raise WikiPathError(file, "link")

    def _list_path(self, extensions: Sequence[str]) -> list[PageFile]:
        out: list[PageFile] = []
        if not self._root.is_dir():
            return out
        if self._within is not None and not _inside(
            os.path.realpath(self._root), os.path.realpath(self._within)
        ):
            return out
        stack: list[tuple[Path, str]] = [(self._root, "")]
        while stack:
            folder, prefix = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                rel = f"{prefix}{name}"
                if not self._listable_name(name, prefix):
                    continue
                try:
                    if entry.is_symlink() or Path(entry.path).is_junction():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), rel + "/"))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if split_extension(name, extensions) is None:
                        continue
                    if page_path_for_file(rel, extensions) is None:
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                out.append(PageFile(file=rel, size=st.st_size, mtime=st.st_mtime))
        out.sort(key=lambda f: f.file)
        return out

    def _read_path(self, file: str) -> bytes | None:
        target = self._resolve(file)
        if not target.is_file():
            return None
        try:
            fd = os.open(target, _READ_FLAGS | _NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as handle:
            self._verify_opened(file, handle.fileno())
            return handle.read()

    def _require_within(self, file: str) -> None:
        """기준 폴더(`within`)가 없으면 `FileNotFoundError`(만들지 않는다)."""
        if self._within is not None and not self._within.is_dir():
            raise FileNotFoundError(file)

    def _write_path(self, file: str, data: bytes) -> None:
        target = self._resolve(file)
        self._require_within(file)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                # 임시 파일을 만든 폴더가 여전히 루트 안 그 폴더인지 쓰기 전에 다시 확인한다.
                self._resolve(file)
                tmp_real = os.path.realpath(tmp_name)
                if os.path.dirname(tmp_real) != os.path.realpath(target.parent):
                    raise WikiPathError(file, "link")
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self._resolve(file)
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # -- 공개 메서드 -----------------------------------------------------------------------------

    def _listable_name(self, name: str, prefix: str) -> bool:
        if name.startswith("."):
            return False
        return bool(prefix) or name.casefold() not in self._reserved_folded

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        return self._list_fd(extensions) if _FD_OPS else self._list_path(extensions)

    def stat(self, file: str) -> PageFile | None:
        if _FD_OPS:
            return self._stat_fd(file)
        target = self._resolve(file)
        try:
            st = target.stat(follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError):
            return None
        if stat.S_ISLNK(st.st_mode):
            raise WikiPathError(file, "link")
        if not stat.S_ISREG(st.st_mode):
            return None
        return PageFile(file=check_page_path(file), size=st.st_size, mtime=st.st_mtime)

    def read(self, file: str) -> bytes | None:
        return self._read_fd(file) if _FD_OPS else self._read_path(file)

    def write(self, file: str, data: bytes) -> None:
        if _FD_OPS:
            self._write_fd(file, data)
        else:
            self._write_path(file, data)

    def delete(self, file: str) -> bool:
        if _FD_OPS:
            return self._delete_fd(file)
        target = self._resolve(file)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        return True

    def move(self, src: str, dst: str) -> None:
        if _FD_OPS:
            self._move_fd(src, dst)
            return
        source = self._resolve(src)
        dest = self._resolve(dst)
        if not source.is_file():
            raise FileNotFoundError(src)
        if dest.exists() and not os.path.samefile(source, dest):
            raise WikiPageExistsError(check_page_path(dst))
        self._require_within(dst)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._resolve(src)
        self._resolve(dst)
        # 대소문자만 바꾸는 옮기기(대소문자 무시 파일 시스템)도 되도록 os.replace를 쓴다. 대상이
        # 없음은 위에서 확인했다.
        os.replace(source, dest)


def _inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _scan_fd(fd: int) -> list[os.DirEntry[str]] | None:
    try:
        with os.scandir(fd) as it:
            return list(it)
    except OSError:
        return None


def _close_walk(walk: list[tuple[int, str, Iterator[os.DirEntry[str]]]], root_fd: int) -> None:
    for fd, _prefix, _entries in walk:
        if fd != root_fd:
            with contextlib.suppress(OSError):
                os.close(fd)


def _is_link_at(dir_fd: int, name: str) -> bool:
    try:
        return stat.S_ISLNK(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
    except OSError:
        return False


def _lstat_at(dir_fd: int, name: str, file: str) -> os.stat_result | None:
    """`dir_fd` 안 `name`의 정보(링크를 따라가지 않음). 없으면 None, 링크면 `WikiPathError`."""
    try:
        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if stat.S_ISLNK(st.st_mode):
        raise WikiPathError(file, "link")
    return st


def _open_dir_at(dir_fd: int, name: str, *, create: bool, file: str) -> int | None:
    """`dir_fd` 안 폴더 `name`을 링크를 따라가지 않고 연다(`create`면 없을 때 만든다).

    없거나(만들지 않을 때) 폴더가 아니면 None(만들 때는 예외), 링크면 `WikiPathError(link)`.
    """
    for _ in range(2):
        try:
            return os.open(name, _DIR_FLAGS | _NOFOLLOW, dir_fd=dir_fd)
        except FileNotFoundError:
            if not create:
                return None
            with contextlib.suppress(FileExistsError):
                os.mkdir(name, dir_fd=dir_fd)
        except OSError:
            if _is_link_at(dir_fd, name):
                raise WikiPathError(file, "link") from None
            if create:
                raise
            return None
    raise FileNotFoundError(file)  # pragma: no cover - 만든 직전에 사라짐


def read_pages(
    pages: WikiPages,
    syntax: CompiledWikiSyntax,
    *,
    max_pages: int | None = None,
    max_page_bytes: int | None = None,
    timeout_ms: float | None = None,
    clock: Callable[[], float] = time.perf_counter,
    cache: ParseCache | None = None,
) -> tuple[list[ParsedPage], list[WikiIssue]]:
    """위키 폴더의 페이지를 모두 읽어 파싱한다(캐시 없는 간단한 길 — 서버 모듈은 파일 해시로
    캐시한다).

    Args:
        pages: 페이지 파일 접근.
        syntax: 컴파일 문법(페이지 확장자·파싱).
        max_pages: 페이지 수 상한. 넘으면 경로 순 앞만 읽고 `wiki.too_many_pages`.
        max_page_bytes: 페이지 하나 크기 상한. 넘는 파일은 읽지 않고 `wiki.too_large`.
        timeout_ms: 페이지 하나 링크 찾기 시간 상한(`parse_page`).
        clock: 시간 상한에 쓰는 시계.
        cache: 파싱 캐시(`ParseCache`). 주면 크기·수정 시각이 같은 파일은 다시 읽지 않고, 없어진
            파일 항목은 뺀다.

    Returns:
        (파싱한 페이지들, 폴더 수준 이슈).
    """
    files = pages.list(syntax.page_extensions)
    issues: list[WikiIssue] = []
    if max_pages is not None and len(files) > max_pages:
        issues.append(
            WikiIssue(
                severity="warning",
                code=KnownIssueCodes.WIKI_TOO_MANY_PAGES,
                message=f"페이지가 상한({max_pages}개)을 넘어 뒤를 읽지 않았습니다.",
                details={"limit": max_pages, "total": len(files)},
            )
        )
        files = files[:max_pages]
    parsed: dict[str, ParsedPage] = {}
    for info in files:
        path = page_path_for_file(info.file, syntax.page_extensions)
        if path is None or path in parsed:
            continue
        if max_page_bytes is not None and info.size > max_page_bytes:
            issues.append(
                WikiIssue(
                    severity="warning",
                    code=KnownIssueCodes.WIKI_TOO_LARGE,
                    message="페이지가 크기 상한을 넘어 읽지 않았습니다.",
                    page=path,
                    details={"limit": max_page_bytes},
                )
            )
            continue
        if cache is not None:
            hit = cache.get(info.file)
            if hit is not None and hit[0] == info.size and hit[1] == info.mtime:
                parsed[path] = hit[2]
                continue
        data = pages.read(info.file)
        if data is None:
            continue
        page = parse_page(path, data, syntax, timeout_ms=timeout_ms, clock=clock)
        parsed[path] = page
        if cache is not None:
            cache[info.file] = (info.size, info.mtime, page)
    if cache is not None:
        present = {info.file for info in files}
        for stale in [f for f in cache if f not in present]:
            del cache[stale]
    return list(parsed.values()), issues
