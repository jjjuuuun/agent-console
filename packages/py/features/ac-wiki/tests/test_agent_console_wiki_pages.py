"""페이지 파일: 계약 묶음(로컬 폴더·메모리), 경로 공격·링크 거부, 숨김·링크 목록 제외, `read_pages`
한도."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_wiki import (
    LocalWikiPages,
    WikiPages,
    WikiPathError,
    build_index,
    check_page_path,
    compile_syntax,
    effective_syntax,
    file_for_page,
    page_path_for_file,
    read_pages,
)
from agent_console_wiki.testing import MemoryWikiPages, WikiPagesContractTests

SYNTAX = compile_syntax(effective_syntax())


class TestLocalPages(WikiPagesContractTests):
    def make_pages(self, tmp_path: Path) -> WikiPages:
        return LocalWikiPages(tmp_path / "pages")


class TestMemoryPages(WikiPagesContractTests):
    def make_pages(self, tmp_path: Path) -> WikiPages:
        return MemoryWikiPages()


def test_protocol_conformance() -> None:
    assert isinstance(LocalWikiPages("x"), WikiPages)
    assert isinstance(MemoryWikiPages(), WikiPages)


def _symlink(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("이 환경은 심볼릭 링크를 만들 수 없다")


def test_links_are_neither_read_written_nor_listed(tmp_path: Path) -> None:
    root = tmp_path / "pages"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret", encoding="utf-8")
    (root / "real.md").write_text("x", encoding="utf-8")
    _symlink(outside, root / "linked")
    _symlink(outside / "secret.md", root / "file-link.md")
    pages = LocalWikiPages(root)
    assert [f.file for f in pages.list([".md"])] == ["real.md"]
    for bad in ("linked/secret.md", "file-link.md", "linked/new.md"):
        with pytest.raises(WikiPathError) as err:
            pages.read(bad) if bad != "linked/new.md" else pages.write(bad, b"x")
        assert err.value.reason == "link"
    assert not (outside / "new.md").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="정션은 Windows만")
def test_junction_rejected(tmp_path: Path) -> None:  # pragma: no cover - Windows
    import subprocess

    root = tmp_path / "pages"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "j"), str(outside)], check=True)
    with pytest.raises(WikiPathError):
        LocalWikiPages(root).write("j/x.md", b"x")


def test_hidden_and_non_pages_and_reserved_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "pages"
    for rel in (
        "a.md",
        "B.MD",
        ".hidden.md",
        ".git/x.md",
        "sub/.draft.md",
        "sub/c.md",
        "notes.txt",
        "res/d.md",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    pages = LocalWikiPages(root, reserved=["res"])
    assert [f.file for f in pages.list([".md"])] == ["B.MD", "a.md", "sub/c.md"]
    with pytest.raises(WikiPathError) as err:
        pages.write("RES/e.md", b"x")
    assert err.value.reason == "reserved"


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    pages = LocalWikiPages(tmp_path)
    pages.write("deep/folder/p.md", b"one")
    pages.write("deep/folder/p.md", b"two")
    assert sorted(os.listdir(tmp_path / "deep/folder")) == ["p.md"]


def test_page_path_helpers() -> None:
    assert page_path_for_file("a/b.md", [".md"]) == "a/b"
    assert page_path_for_file("a/b.MD", [".md"]) == "a/b"
    assert page_path_for_file("a/b.txt", [".md"]) is None
    assert page_path_for_file(".md", [".md"]) is None
    assert file_for_page("a/b", ".md") == "a/b.md"
    assert check_page_path("a/b") == "a/b"
    for bad in ("..", "a/../b", "/a", "a\\b", "c:x", "a/.h", "aux", "a /b"):
        with pytest.raises(WikiPathError):
            check_page_path(bad)


def test_read_pages_limits_and_index_from_folder(tmp_path: Path) -> None:
    root = tmp_path / "wiki"
    pages = LocalWikiPages(root)
    pages.write("a.md", b"[[b]]")
    pages.write("b.md", b"[[a]]")
    pages.write("c.md", ("x" * 50).encode())
    parsed, issues = read_pages(pages, SYNTAX, max_page_bytes=20)
    assert [p.path for p in parsed] == ["a", "b"]
    assert [i.code for i in issues] == [KnownIssueCodes.WIKI_TOO_LARGE]
    parsed, issues = read_pages(pages, SYNTAX, max_pages=2)
    assert [p.path for p in parsed] == ["a", "b"]
    assert issues[0].code == KnownIssueCodes.WIKI_TOO_MANY_PAGES
    assert issues[0].details == {"limit": 2, "total": 3}
    index = build_index(read_pages(pages, SYNTAX)[0], SYNTAX)
    assert [b.path for b in index.backlinks("a")] == ["b"]


def test_missing_root_lists_nothing(tmp_path: Path) -> None:
    assert LocalWikiPages(tmp_path / "nope").list([".md"]) == []
