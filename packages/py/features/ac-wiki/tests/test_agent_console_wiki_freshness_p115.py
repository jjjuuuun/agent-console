"""P1.15: `WikiRepository(freshness_seconds=)` 신선도 창(design §1.1 B-1).

시계를 주입해 창 안 재사용·창 지남·쓰기 즉시 무효화·0이면 매번 확인·외부 변경·동시 요청을 본다.
페이지 파일 나열 횟수는 `MemoryWikiPages.list`를 세는 감싸개로 잰다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from typing import Any

import pytest

import agent_console_wiki._repository as repository_module
from agent_console_wiki import (
    InMemoryWikiHistory,
    PageFile,
    WikiPathError,
    WikiRepository,
    check_page_path,
    compile_syntax,
    effective_syntax,
    page_path_for_file,
)
from agent_console_wiki.testing import FakeClock, MemoryWikiPages

SYNTAX = compile_syntax(effective_syntax())
WINDOW = 5.0


class CountingPages(MemoryWikiPages):
    """`list` 호출 수를 세는 메모리 페이지(``delay``초 만큼 느리게 나열할 수 있다)."""

    def __init__(self, *args: Any, delay: float = 0.0, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.lists = 0
        self.delay = delay
        self._count_lock = threading.Lock()

    def list(self, extensions: Sequence[str]) -> list[PageFile]:
        with self._count_lock:
            self.lists += 1
        if self.delay:
            time.sleep(self.delay)
        return super().list(extensions)

    def edit(self, file: str, text: str) -> None:
        """바깥 편집기처럼 저장소를 거치지 않고 파일을 바꾼다."""
        self.write(file, text.encode("utf-8"))


def _repo(
    pages: CountingPages, clock: FakeClock, *, window: float = WINDOW, history: bool = True
) -> WikiRepository:
    return WikiRepository(
        pages,
        wiki_id="w",
        syntax=SYNTAX,
        history=InMemoryWikiHistory() if history else None,
        clock=clock,
        freshness_seconds=window,
    )


def _paths(repo: WikiRepository) -> list[str]:
    return [p.path for p in repo.list_pages().items]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(step=0.0)


def test_window_reuses_listing_and_expires(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n[[b]]\n", "b.md": "# B\n"})
    repo = _repo(pages, clock)
    assert _paths(repo) == ["a", "b"]
    assert pages.lists == 1
    repo.list_pages()
    repo.graph()
    repo.lint()
    repo.page_files()
    assert pages.lists == 1  # 창 안: 다시 나열하지 않는다
    clock.advance(WINDOW)
    repo.list_pages()
    assert pages.lists == 2  # 창이 지나면 한 번 다시 확인
    repo.list_pages()
    assert pages.lists == 2


def test_zero_window_lists_every_request(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock, window=0)
    for expected in (1, 2, 3):
        repo.list_pages()
        assert pages.lists == expected
    repo.graph()
    repo.page_files()
    assert pages.lists == 5


def test_negative_window_rejected(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="freshness_seconds"):
        _repo(CountingPages(), clock, window=-1)


def test_clock_going_back_expires(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    repo.list_pages()
    clock.advance(-1)
    repo.list_pages()
    assert pages.lists == 2


def test_external_edit_shows_after_window(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    assert _paths(repo) == ["a"]
    pages.edit("b.md", "# B\n")
    assert _paths(repo) == ["a"]  # 바깥 편집은 창만큼 늦게 보일 수 있다
    clock.advance(WINDOW + 0.1)
    assert _paths(repo) == ["a", "b"]


def test_same_process_writes_invalidate_at_once(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    assert _paths(repo) == ["a"]
    repo.write("b", "# B\n[[a]]\n")
    assert _paths(repo) == ["a", "b"]
    assert repo.view("a").backlinks[0].path == "b"
    repo.move("b", "c")
    assert _paths(repo) == ["a", "c"]
    repo.delete("c")
    assert _paths(repo) == ["a"]
    version = repo.page_history("c").items[-1].version
    repo.restore("c", version)
    assert _paths(repo) == ["a", "c"]
    repo.import_page("d", b"# D\n", author=repo.page_history("a").items[0].author)
    assert _paths(repo) == ["a", "c", "d"]


def test_scan_ignores_window(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    repo.scan()
    assert _paths(repo) == ["a"]
    pages.edit("b.md", "# B\n")
    result = repo.scan()
    assert result.imported == ["b"]
    assert _paths(repo) == ["a", "b"]  # 창 안이어도 scan 뒤에는 지금 파일
    # 기록이 없는 저장소도 scan은 스냅숏을 버린다
    plain = _repo(CountingPages({"a.md": "# A\n"}), clock, history=False)
    plain.list_pages()
    plain.pages.write("b.md", b"# B\n")
    plain.scan()
    assert _paths(plain) == ["a", "b"]


def test_invalidate_drops_snapshot(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    repo.list_pages()
    pages.edit("b.md", "# B\n")
    repo.invalidate()
    assert _paths(repo) == ["a", "b"]


def test_view_rebuilds_when_viewed_page_changed_outside(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n", "b.md": "# B\n"})
    repo = _repo(pages, clock)
    assert [link.target for link in repo.view("a").links] == []
    pages.edit("a.md", "# A\n[[b]]\n")
    view = repo.view("a")  # 창 안이어도 보는 페이지가 바뀌었으면 다시 짓는다
    assert [(link.target, link.status) for link in view.links] == [("b", "ok")]
    assert view.content == "# A\n[[b]]\n"
    assert [p.path for p in repo.view("b").backlinks] == ["a"]


def test_write_decisions_use_current_files(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"})
    repo = _repo(pages, clock)
    repo.list_pages()
    pages.edit("b.md", "# B\n")  # 창 안에 바깥에서 만든 페이지
    preview = repo.preview("c", "# C\n[[b]]\n")
    assert preview.page.broken_links == 0  # 판단은 창과 무관하게 지금 파일로
    assert repo.page_files()[-1].file == "b.md"  # 판단이 확인한 목록이 스냅숏이 된다


def test_unchanged_listing_keeps_built_index(
    clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = CountingPages({"a.md": "# A\n[[b]]\n", "b.md": "# B\n"})
    repo = _repo(pages, clock)
    calls = {"build": 0}
    original = repository_module.build_index  # type: ignore[attr-defined]  # 측정용 감싸기

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls["build"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(repository_module, "build_index", counting)
    repo.graph()
    clock.advance(WINDOW)
    repo.graph()
    assert (pages.lists, calls["build"]) == (2, 1)  # 다시 나열했지만 목록이 같아 색인은 그대로
    pages.edit("b.md", "# B 고침\n")
    clock.advance(WINDOW)
    repo.graph()
    assert calls["build"] == 2


def test_concurrent_requests_check_once(clock: FakeClock) -> None:
    pages = CountingPages({"a.md": "# A\n"}, delay=0.05)
    repo = _repo(pages, clock)
    barrier = threading.Barrier(6)
    errors: list[BaseException] = []

    def read() -> None:
        try:
            barrier.wait()
            repo.list_pages()
        except BaseException as exc:  # pragma: no cover - 실패 보고
            errors.append(exc)

    threads = [threading.Thread(target=read) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert pages.lists == 1


def test_history_summaries_read_once_per_window(clock: FakeClock) -> None:
    pages = CountingPages()
    history = InMemoryWikiHistory()
    repo = WikiRepository(
        pages, wiki_id="w", syntax=SYNTAX, history=history, clock=clock, freshness_seconds=WINDOW
    )
    repo.write("a", "# A\n")
    reads = {"n": 0}
    original = history.summaries

    def counting(wiki: str) -> Any:
        reads["n"] += 1
        return original(wiki)

    history.summaries = counting  # type: ignore[method-assign]
    repo.list_pages()
    repo.list_pages()
    repo.lint()
    assert reads["n"] == 1
    assert repo.list_pages().items[0].updated_by is not None  # 기록 요약이 채워져 있다


def test_path_checks_are_memoized_but_still_reject() -> None:
    assert check_page_path("x/y") == "x/y"
    assert check_page_path("x/y") == "x/y"
    for _ in range(2):  # 거부는 기억하지 않고 매번 같은 오류
        with pytest.raises(WikiPathError):
            check_page_path("../x")
        with pytest.raises(WikiPathError):
            check_page_path(".hidden/x")
    with pytest.raises(WikiPathError):
        check_page_path("History/x", reserved=["history"])
    assert check_page_path("History/x") == "History/x"
    assert page_path_for_file("a/b.md", [".md"]) == "a/b"
    assert page_path_for_file("a/b.md", (".txt",)) is None
    assert page_path_for_file("../b.md", [".md"]) is None
