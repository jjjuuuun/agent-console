"""`WikiPages` 계약 묶음: 구현(로컬 폴더·메모리·공간 페이지 파일)이 지켜야 할 의미."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_wiki._errors import WikiPageExistsError, WikiPathError
from agent_console_wiki._pages import WikiPages

__all__ = ["WikiPagesContractTests"]

EXT = (".md",)
BAD_PATHS = (
    "../escape.md",
    "a/../../escape.md",
    "/abs.md",
    "C:/drive.md",
    "c:drive.md",
    "a\\b.md",
    ".hidden.md",
    "a/.git/x.md",
    "con.md",
    "a/nul.txt.md",
    "a//b.md",
    "bad\x01.md",
    "",
)


class WikiPagesContractTests:
    """하위 클래스가 `make_pages`를 채우면 pytest가 아래 시험을 돌린다."""

    def make_pages(self, tmp_path: Path) -> WikiPages:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def test_write_read_stat_list(self, tmp_path: Path) -> None:
        pages = self.make_pages(tmp_path)
        assert pages.list(EXT) == []
        assert pages.read("a.md") is None
        assert pages.stat("a.md") is None
        pages.write("a.md", b"# A\r\n")
        pages.write("dir/sub/b.md", "본문".encode())
        pages.write("dir/note.txt", b"not a page")
        assert pages.read("a.md") == b"# A\r\n"
        info = pages.stat("dir/sub/b.md")
        assert info is not None
        assert info.size == len("본문".encode())
        assert [f.file for f in pages.list(EXT)] == ["a.md", "dir/sub/b.md"]

    def test_overwrite_and_delete(self, tmp_path: Path) -> None:
        pages = self.make_pages(tmp_path)
        pages.write("a.md", b"1")
        pages.write("a.md", b"22")
        assert pages.read("a.md") == b"22"
        assert pages.delete("a.md") is True
        assert pages.delete("a.md") is False
        assert pages.read("a.md") is None

    def test_move(self, tmp_path: Path) -> None:
        pages = self.make_pages(tmp_path)
        pages.write("a.md", b"x")
        pages.write("b.md", b"y")
        with pytest.raises(WikiPageExistsError):
            pages.move("a.md", "b.md")
        with pytest.raises(FileNotFoundError):
            pages.move("missing.md", "c.md")
        pages.move("a.md", "new/place.md")
        assert pages.read("a.md") is None
        assert pages.read("new/place.md") == b"x"

    @pytest.mark.parametrize("bad", BAD_PATHS)
    def test_rejects_bad_paths(self, tmp_path: Path, bad: str) -> None:
        pages = self.make_pages(tmp_path)
        with pytest.raises(WikiPathError):
            pages.write(bad, b"x")
        with pytest.raises(WikiPathError):
            pages.read(bad)
