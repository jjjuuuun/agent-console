"""REL.1: 첫 색인 이어 읽기(`LocalWikiPages.reading`)와 요청 하나에 폴더 나열 한 번.

- `reading()`은 `read`와 같은 결과·같은 거부(끝 칸 링크·폴더 링크, 폴더·없는 파일 = None)다.
  디렉터리 fd 방식이면 기준 폴더 실제 경로 확인(`realpath`)을 파일마다가 아니라 한 번만 한다.
- `read_pages`는 `reading()`이 있으면 그 안에서 읽고, 없으면 `read`를 쓴다. `files`를 주면
  다시 나열하지 않는다.
- `WikiRepository.list_pages`·`view`·`lint`는 폴더를 한 번만 나열한다(시각 채우기가 같은 목록을
  쓴다).
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from agent_console_wiki import (
    InMemoryWikiHistory,
    LocalWikiPages,
    PageFile,
    WikiPathError,
    WikiRepository,
    _pages,
    compile_syntax,
    effective_syntax,
    read_pages,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

SYNTAX = compile_syntax(effective_syntax())


@pytest.fixture(params=["fd", "path"])
def fs_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    if request.param == "fd" and not _pages._FD_OPS:
        pytest.skip("이 OS는 디렉터리 fd 방식을 지원하지 않는다")
    monkeypatch.setattr(_pages, "_FD_OPS", request.param == "fd")
    return str(request.param)


def _symlink(target: Path, link: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("이 환경은 심볼릭 링크를 만들 수 없다")


def _outcome(read: Callable[[str], bytes | None], file: str) -> object:
    try:
        return read(file)
    except WikiPathError as exc:
        return ("refused", exc.reason)


@pytest.mark.usefixtures("fs_mode")
@pytest.mark.parametrize("within", [False, True], ids=["root", "within"])
def test_reading_matches_read(tmp_path: Path, within: bool) -> None:
    project = tmp_path / "proj"
    root = project / "cfg/pages"
    (root / "a/b").mkdir(parents=True)
    (root / "a/b/deep.md").write_bytes(b"deep")
    (root / "a/x.md").write_bytes(b"x")
    (root / "top.md").write_bytes(b"top")
    (root / "folder.md").mkdir()  # 폴더 = 페이지가 아님
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_bytes(b"SECRET")
    _symlink(outside / "secret.md", root / "file-link.md")
    _symlink(outside, root / "linked")
    pages = LocalWikiPages(root, within=project if within else None)
    files = [
        "a/b/deep.md",
        "a/x.md",
        "a/none.md",
        "file-link.md",
        "folder.md",
        "linked/secret.md",
        "missing/none.md",
        "top.md",
        "a/b/deep.md",  # 앞으로 돌아가도 같다
    ]
    expected = [_outcome(pages.read, f) for f in files]
    assert expected[:3] == [b"deep", b"x", None]
    assert expected[3] == ("refused", "link")
    assert expected[5] == ("refused", "link")
    with pages.reading() as read:
        assert [_outcome(read, f) for f in files] == expected


@pytest.mark.skipif(not _pages._FD_OPS, reason="디렉터리 fd 방식이 있는 OS만")
def test_reading_resolves_the_anchor_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    root = project / "pages"
    names = [f"d{i % 3}/p{i}.md" for i in range(12)]
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(name.encode())
    pages = LocalWikiPages(root, within=project)
    calls: list[str] = []
    real = os.path.realpath

    def counting(path: Any, *args: Any, **kwargs: Any) -> str:
        calls.append(str(path))
        return str(real(path, *args, **kwargs))

    monkeypatch.setattr(os.path, "realpath", counting)
    assert [pages.read(n) for n in names] == [n.encode() for n in names]
    per_file = len(calls)
    calls.clear()
    with pages.reading() as read:
        assert [read(n) for n in sorted(names)] == [n.encode() for n in sorted(names)]
    assert per_file == 2 * len(names)  # 파일마다 기준 폴더·루트 실제 경로
    assert len(calls) == 2  # 이어 읽기는 한 번


class _Counting:
    """`WikiPages` 감싸기: 나열·읽기·이어 읽기 횟수를 센다(`reading` 없는 모양도 만든다)."""

    def __init__(self, inner: Any, *, batch: bool) -> None:
        self.inner = inner
        self.lists = 0
        self.reads = 0
        self.batches = 0
        if batch:
            self.reading = self._reading

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        self.lists += 1
        found: list[PageFile] = self.inner.list(extensions)
        return found

    def read(self, file: str) -> bytes | None:
        self.reads += 1
        data: bytes | None = self.inner.read(file)
        return data

    @contextlib.contextmanager
    def _reading(self) -> Iterator[Callable[[str], bytes | None]]:
        self.batches += 1
        yield self.read

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@pytest.mark.parametrize("batch", [True, False], ids=["reading", "read-only"])
def test_read_pages_uses_reading_and_given_files(batch: bool) -> None:
    memory = MemoryWikiPages()
    memory.write("a.md", b"[[b]]")
    memory.write("b.md", b"[[a]]")
    pages = _Counting(memory, batch=batch)
    parsed, _ = read_pages(pages, SYNTAX)
    assert [p.path for p in parsed] == ["a", "b"]
    assert (pages.lists, pages.reads, pages.batches) == (1, 2, 1 if batch else 0)
    files = memory.list(SYNTAX.page_extensions)
    cache: dict[str, Any] = {}
    parsed, _ = read_pages(pages, SYNTAX, files=files, cache=cache)
    assert [p.path for p in parsed] == ["a", "b"]
    assert pages.lists == 1  # 받은 목록을 쓴다
    read_pages(pages, SYNTAX, files=files, cache=cache)
    assert pages.reads == 4  # 캐시가 맞으면 다시 읽지 않는다


def test_repository_lists_the_folder_once_per_request() -> None:
    memory = MemoryWikiPages()
    pages = _Counting(memory, batch=False)
    repo = WikiRepository(
        pages, wiki_id="w", syntax=SYNTAX, history=InMemoryWikiHistory(), clock=FakeClock()
    )
    repo.write("index", "# 처음\n[[guide]]\n")
    memory.write("guide.md", b"# outside\n")  # 기록 없는 페이지 = 파일 수정 시각을 쓴다
    for call in (repo.list_pages, lambda: repo.view("index"), repo.lint, repo.graph):
        pages.lists = 0
        call()
        assert pages.lists == 1, call
    listing = repo.list_pages()
    times = {s.path: s.updated_at for s in listing.items}
    assert times["guide"] is not None  # 같은 목록에서 시각을 채웠다
