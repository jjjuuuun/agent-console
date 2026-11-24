"""페이지 파일: 계약 묶음(로컬 폴더·메모리), 경로 공격·링크 거부, 숨김·링크 목록 제외, `read_pages`
한도, 링크 바꿔치기(TOCTOU) 막기(디렉터리 fd 방식·연 뒤 다시 확인 방식)."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_wiki import (
    LocalWikiPages,
    WikiPages,
    WikiPathError,
    _pages,
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


@pytest.fixture(params=["fd", "path"])
def fs_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """두 방식을 모두 돈다: 디렉터리 fd(`openat`) · 경로 검사 + 연 뒤 다시 확인(Windows 방식)."""
    if request.param == "fd" and not _pages._FD_OPS:
        pytest.skip("이 OS는 디렉터리 fd 방식을 지원하지 않는다")
    monkeypatch.setattr(_pages, "_FD_OPS", request.param == "fd")
    return str(request.param)


@pytest.mark.usefixtures("fs_mode")
class TestLocalPages(WikiPagesContractTests):
    def make_pages(self, tmp_path: Path) -> WikiPages:
        return LocalWikiPages(tmp_path / "pages")


@pytest.mark.usefixtures("fs_mode")
class TestLocalPagesWithin(WikiPagesContractTests):
    def make_pages(self, tmp_path: Path) -> WikiPages:
        (tmp_path / "proj").mkdir()
        return LocalWikiPages(tmp_path / "proj/.cfg/pages/w", within=tmp_path / "proj")


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


@pytest.mark.usefixtures("fs_mode")
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
    with pytest.raises(WikiPathError):
        pages.stat("file-link.md")
    with pytest.raises(WikiPathError):
        pages.delete("file-link.md")
    with pytest.raises(WikiPathError):
        pages.move("real.md", "linked/moved.md")
    assert (outside / "secret.md").exists()
    assert not (outside / "moved.md").exists()


@pytest.mark.usefixtures("fs_mode")
def test_within_allows_root_link_inside_and_rejects_outside(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "real-wiki").mkdir(parents=True)
    (project / "real-wiki/a.md").write_bytes(b"inside")
    (project / "pages").mkdir()
    _symlink(project / "real-wiki", project / "pages/w")
    pages = LocalWikiPages(project / "pages/w", within=project)
    assert pages.read("a.md") == b"inside"
    assert [f.file for f in pages.list([".md"])] == ["a.md"]
    pages.write("b.md", b"new")
    assert (project / "real-wiki/b.md").read_bytes() == b"new"

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.md").write_bytes(b"SECRET")
    _symlink(outside, project / "pages/x")
    escaped = LocalWikiPages(project / "pages/x", within=project)
    with pytest.raises(WikiPathError) as err:
        escaped.read("a.md")
    assert err.value.reason == "link"
    with pytest.raises(WikiPathError):
        escaped.write("new.md", b"x")
    assert escaped.list([".md"]) == []
    assert not (outside / "new.md").exists()


@pytest.mark.usefixtures("fs_mode")
def test_within_folder_is_never_created(tmp_path: Path) -> None:
    """기준 폴더(예: 지워진 프로젝트 폴더)가 없으면 쓰기는 실패하고 폴더를 다시 만들지 않는다."""
    gone = tmp_path / "gone"
    pages = LocalWikiPages(gone / ".cfg/pages/w", within=gone)
    assert pages.read("a.md") is None
    assert pages.list([".md"]) == []
    with pytest.raises(FileNotFoundError):
        pages.write("a.md", b"x")
    assert not gone.exists()


def _swap_to_link(folder: Path, outside: Path) -> None:
    """`folder`를 옆 이름으로 치우고 그 자리에 `outside`를 가리키는 링크를 둔다."""
    folder.rename(folder.with_name(folder.name + "-real"))
    folder.symlink_to(outside, target_is_directory=True)


def _race_setup(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "pages"
    (root / "sub").mkdir(parents=True)
    (root / "sub/a.md").write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.md").write_bytes(b"SECRET")
    try:
        (tmp_path / "probe").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("이 환경은 심볼릭 링크를 만들 수 없다")
    return root, outside


@pytest.mark.skipif(not _pages._FD_OPS, reason="디렉터리 fd 방식이 있는 OS만")
def test_fd_mode_swap_between_check_and_open_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """경로 글자 검사는 통과한 뒤, 폴더를 열기 직전에 링크로 바뀌어도 밖을 읽거나 쓰지 않는다."""
    root, outside = _race_setup(tmp_path)
    pages = LocalWikiPages(root)
    real_open = os.open
    swapped: list[bool] = []

    def swap_then_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "sub" and kwargs.get("dir_fd") is not None and not swapped:
            swapped.append(True)
            _swap_to_link(root / "sub", outside)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    with pytest.raises(WikiPathError) as err:
        pages.read("sub/a.md")
    assert err.value.reason == "link"
    assert swapped
    with pytest.raises(WikiPathError):
        pages.write("sub/w.md", b"x")
    assert not (outside / "w.md").exists()
    assert (outside / "a.md").read_bytes() == b"SECRET"


def test_path_mode_swap_after_check_is_caught_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows 방식: 검사 뒤 파일을 열기 직전에 폴더가 링크로 바뀌면 연 뒤 다시 확인에서
    거부한다."""
    root, outside = _race_setup(tmp_path)
    monkeypatch.setattr(_pages, "_FD_OPS", False)
    pages = LocalWikiPages(root)
    real_open = os.open
    target = str(root / "sub/a.md")

    def swap_then_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if str(path) == target and not (root / "sub").is_symlink():
            _swap_to_link(root / "sub", outside)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    with pytest.raises(WikiPathError) as err:
        pages.read("sub/a.md")
    assert err.value.reason == "link"


def test_path_mode_write_swap_after_temp_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows 방식 쓰기: 임시 파일을 만든 직후 폴더가 링크로 바뀌면 밖에 쓰지 않고 거부한다."""
    import tempfile

    root, outside = _race_setup(tmp_path)
    monkeypatch.setattr(_pages, "_FD_OPS", False)
    pages = LocalWikiPages(root)
    real_mkstemp = tempfile.mkstemp

    def swap_after(*args: Any, **kwargs: Any) -> tuple[int, str]:
        made = real_mkstemp(*args, **kwargs)
        if not (root / "sub").is_symlink():
            _swap_to_link(root / "sub", outside)
        return made

    monkeypatch.setattr(tempfile, "mkstemp", swap_after)
    with pytest.raises(WikiPathError) as err:
        pages.write("sub/w.md", b"x")
    assert err.value.reason == "link"
    assert sorted(os.listdir(outside)) == ["a.md"]  # 밖에 새 파일 없음
    assert (outside / "a.md").read_bytes() == b"SECRET"


@pytest.mark.skipif(not _pages._FD_OPS, reason="디렉터리 fd 방식이 있는 OS만")
def test_concurrent_link_swaps_never_escape(tmp_path: Path) -> None:
    """다른 스레드가 폴더를 링크로 계속 바꿔치기해도 밖의 파일을 읽거나 밖에 쓰지 않는다."""
    root, outside = _race_setup(tmp_path)
    sub, real = root / "sub", root / "sub-real"
    stop = threading.Event()

    def racer() -> None:
        while not stop.is_set():
            try:
                os.rename(sub, real)
                os.symlink(outside, sub, target_is_directory=True)
                os.unlink(sub)
            except OSError:
                if sub.is_symlink():
                    os.unlink(sub)
                elif sub.is_dir() and real.exists():
                    shutil.rmtree(sub, ignore_errors=True)
            with contextlib.suppress(OSError):
                if real.exists():
                    os.rename(real, sub)

    thread = threading.Thread(target=racer, daemon=True)
    thread.start()
    pages = LocalWikiPages(root)
    deadline = time.monotonic() + 1.5
    rounds = 0
    try:
        while time.monotonic() < deadline and rounds < 5000:
            rounds += 1
            with contextlib.suppress(WikiPathError, OSError):
                assert pages.read("sub/a.md") != b"SECRET"
            with contextlib.suppress(WikiPathError, OSError):
                pages.write("sub/w.md", b"x")
            assert not (outside / "w.md").exists()
            assert sorted(os.listdir(outside)) == ["a.md"]
    finally:
        stop.set()
        thread.join(timeout=5)
    assert rounds > 0


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
