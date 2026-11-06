"""메모리 페이지 파일(`WikiPages` 시험용 구현). 경로 규칙은 `LocalWikiPages`와 같다(링크는 없다)."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence

from agent_console_wiki._errors import WikiPageExistsError
from agent_console_wiki._pages import PageFile
from agent_console_wiki._paths import check_page_path, page_path_for_file

__all__ = ["MemoryWikiPages"]


class MemoryWikiPages:
    """파일 경로 → 바이트를 메모리에 두는 `WikiPages`.

    Args:
        files: 처음 파일(경로 → 글 또는 바이트).
        clock: 수정 시각에 쓰는 시계(초). 기본은 쓸 때마다 1씩 느는 가짜 시계.
        reserved: 첫 구성요소로 쓸 수 없는 이름.
    """

    def __init__(
        self,
        files: Mapping[str, str | bytes] | None = None,
        *,
        clock: Callable[[], float] | None = None,
        reserved: Collection[str] = (),
    ) -> None:
        self._tick = 0.0
        self._clock = clock or self._next
        self._reserved = tuple(reserved)
        self._files: dict[str, tuple[bytes, float]] = {}
        for path, data in (files or {}).items():
            self.write(path, data.encode("utf-8") if isinstance(data, str) else data)

    def _next(self) -> float:
        self._tick += 1.0
        return self._tick

    def _norm(self, file: str) -> str:
        return check_page_path(file, reserved=self._reserved)

    @property
    def files(self) -> dict[str, bytes]:
        """지금 파일들(사본)."""
        return {k: v for k, (v, _) in self._files.items()}

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        return [
            PageFile(file=f, size=len(data), mtime=mtime)
            for f, (data, mtime) in sorted(self._files.items())
            if page_path_for_file(f, extensions) is not None
        ]

    def stat(self, file: str) -> PageFile | None:
        norm = self._norm(file)
        item = self._files.get(norm)
        return None if item is None else PageFile(file=norm, size=len(item[0]), mtime=item[1])

    def read(self, file: str) -> bytes | None:
        item = self._files.get(self._norm(file))
        return None if item is None else item[0]

    def write(self, file: str, data: bytes) -> None:
        self._files[self._norm(file)] = (bytes(data), self._clock())

    def delete(self, file: str) -> bool:
        return self._files.pop(self._norm(file), None) is not None

    def move(self, src: str, dst: str) -> None:
        source, dest = self._norm(src), self._norm(dst)
        if source not in self._files:
            raise FileNotFoundError(src)
        if dest in self._files and dest != source:
            raise WikiPageExistsError(dest)
        data, _ = self._files.pop(source)
        self._files[dest] = (data, self._clock())
