"""페이지 파일 접근(주입 지점 `WikiPages`)과 지금 컴퓨터 폴더 구현 `LocalWikiPages`(design §7R.13).

경로는 늘 **위키 폴더 기준 POSIX 상대 파일 경로**(확장자 포함)다. 페이지 경로(확장자 없음)와의
변환은 `page_path_for_file`·`file_for_page`가 한다(확장자는 문법 데이터라 파일 접근은 모른다).

`LocalWikiPages`는 경로를 먼저 검사하고(`..`·절대·드라이브·역슬래시·금지 문자·숨김·예약 이름),
루트에서 대상까지 있는 구성요소가 심볼릭 링크·정션이면 읽지도 쓰지도 않으며, 실제 경로가 루트 안인지
한 번 더 확인한다. 쓰기는 같은 폴더 임시 파일 + 원자적 바꾸기(`ac-store` `atomic_write_bytes`)다.
목록은 숨김 항목(`.`로 시작)·링크·페이지 확장자가 아닌 파일·경로 규칙에 어긋난 이름을 건너뛴다.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Collection, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiIssue
from agent_console_store import atomic_write_bytes

from ._compiled import CompiledWikiSyntax
from ._errors import WikiPageExistsError, WikiPathError
from ._parse import ParsedPage, parse_page
from ._paths import check_page_path, page_path_for_file, split_extension

__all__ = ["LocalWikiPages", "PageFile", "ParseCache", "WikiPages", "read_pages"]

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

    Args:
        root: 위키 페이지 폴더. 없으면 목록은 비고 첫 쓰기 때 만든다.
        reserved: 첫 구성요소로 쓸 수 없는 이름(대소문자 무시).
    """

    def __init__(self, root: str | os.PathLike[str], *, reserved: Collection[str] = ()) -> None:
        self._root = Path(root)
        self._reserved = tuple(reserved)
        self._reserved_folded = frozenset(r.casefold() for r in reserved)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, file: str) -> Path:
        norm = check_page_path(file, reserved=self._reserved)
        probe = self._root
        for part in norm.split("/"):
            probe = probe / part
            if probe.is_symlink() or probe.is_junction():
                raise WikiPathError(file, "link")
        target = self._root / norm
        real_root = os.path.realpath(self._root)
        real = os.path.realpath(target)
        if not real.startswith(real_root.rstrip(os.sep) + os.sep):
            raise WikiPathError(file, "link")
        return target

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        out: list[PageFile] = []
        if self._root.is_symlink() or not self._root.is_dir():
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
                if name.startswith("."):
                    continue
                rel = f"{prefix}{name}"
                if not prefix and name.casefold() in self._reserved_folded:
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

    def stat(self, file: str) -> PageFile | None:
        target = self._resolve(file)
        try:
            st = target.stat()
        except FileNotFoundError:
            return None
        if not target.is_file():
            return None
        return PageFile(file=check_page_path(file), size=st.st_size, mtime=st.st_mtime)

    def read(self, file: str) -> bytes | None:
        target = self._resolve(file)
        try:
            return target.read_bytes() if target.is_file() else None
        except FileNotFoundError:
            return None

    def write(self, file: str, data: bytes) -> None:
        atomic_write_bytes(self._resolve(file), data)

    def delete(self, file: str) -> bool:
        target = self._resolve(file)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        return True

    def move(self, src: str, dst: str) -> None:
        source = self._resolve(src)
        dest = self._resolve(dst)
        if not source.is_file():
            raise FileNotFoundError(src)
        if dest.exists() and not os.path.samefile(source, dest):
            raise WikiPageExistsError(check_page_path(dst))
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 대소문자만 바꾸는 옮기기(대소문자 무시 파일 시스템)도 되도록 os.replace를 쓴다. 대상이
        # 없음은 위에서 확인했다.
        os.replace(source, dest)


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
