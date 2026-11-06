"""`WikiHistory`(X49) 계약 묶음: 구현(메모리·SQLite·사용자 구현)이 지켜야 할 의미(`_history`
문서)."""

from __future__ import annotations

from pathlib import Path

from agent_console_contracts.wiki import WikiAuthor
from agent_console_wiki._history import HistoryEntry, WikiHistory

__all__ = ["FakeClock", "WikiHistoryContractTests"]


class FakeClock:
    """부를 때마다 `step`초씩 가는 가짜 시계(시작 `start`)."""

    def __init__(self, start: float = 1_700_000_000.0, step: float = 1.0) -> None:
        self.now = start
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value

    def advance(self, seconds: float) -> None:
        """시계를 앞으로 돌린다."""
        self.now += seconds


_USER = WikiAuthor(kind="user")


def _agent(run: str, root: str | None = None, label: str | None = None) -> WikiAuthor:
    return WikiAuthor(kind="agent", agent_id="a1", run_id=run, root_run_id=root, label=label)


def _entry(path: str, op: str, data: bytes, at: float, **kw: object) -> HistoryEntry:
    author = kw.pop("author", _USER)
    assert isinstance(author, WikiAuthor)
    wiki = kw.pop("wiki", "w")
    assert isinstance(wiki, str)
    return HistoryEntry.of(wiki, path, op, data, author=author, at=at, **kw)  # type: ignore[arg-type]


class WikiHistoryContractTests:
    """하위 클래스가 `make_history`를 채우면 pytest가 아래 시험을 돌린다."""

    def make_history(
        self, tmp_path: Path
    ) -> WikiHistory:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def test_versions_increase_per_page(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        a1, b1 = h.record([_entry("a", "create", b"1", 1.0), _entry("b", "create", b"x", 1.0)])
        (a2,) = h.record([_entry("a", "update", b"2", 2.0, message="고침")])
        assert (a1.version, b1.version, a2.version) == (1, 1, 2)
        assert a2.message == "고침"
        page = h.list("w", "a")
        assert [v.version for v in page.items] == [2, 1]
        assert page.pruned is False
        assert h.read("w", "a", 1) == b"1"
        assert h.read("w", "a", 2) == b"2"
        latest = h.latest("w", "a")
        assert latest is not None
        assert latest.version == 2
        assert h.latest("w", "nope") is None
        assert h.get("w", "a", 9) is None
        assert h.list("w", "a", limit=1).items[0].version == 2

    def test_delete_points_to_previous_content(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        (v1,) = h.record([_entry("a", "create", "본문".encode(), 1.0)])
        h.record(
            [
                HistoryEntry(
                    wiki="w",
                    path="a",
                    op="delete",
                    sha256=v1.sha256,
                    bytes=v1.bytes,
                    author=_USER,
                    at=2.0,
                )
            ]
        )
        latest = h.latest("w", "a")
        assert latest is not None
        assert latest.op == "delete"
        assert h.read("w", "a", 2) == "본문".encode()

    def test_move_records_two_rows_and_author_label(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        h.record([_entry("old", "create", b"m", 1.0)])
        out, inn = h.record(
            [
                _entry("old", "move_out", b"m", 2.0, to="new", author=_agent("r1", label="정리꾼")),
                _entry(
                    "new", "move_in", b"m", 2.0, from_="old", author=_agent("r1", label="정리꾼")
                ),
            ]
        )
        assert (out.op, out.to, inn.op, inn.from_) == ("move_out", "new", "move_in", "old")
        assert inn.version == 1
        got = h.get("w", "new", 1)
        assert got is not None
        assert got.author.label == "정리꾼"
        assert got.author.run_id == "r1"

    def test_prune_keeps_first_and_newest(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        for n in range(1, 7):
            h.record([_entry("a", "update" if n > 1 else "create", str(n).encode(), float(n))])
        assert h.prune("w", "a", keep=3) == 3
        page = h.list("w", "a")
        assert [v.version for v in page.items] == [6, 5, 1]
        assert page.pruned is True
        assert h.get("w", "a", 2) is None
        assert h.read("w", "a", 3) is None
        assert h.read("w", "a", 1) == b"1"
        (v7,) = h.record([_entry("a", "update", b"7", 7.0)])
        assert v7.version == 7
        assert h.prune("w", "a", keep=10) == 0

    def test_same_content_shared(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        h.record([_entry("a", "create", b"same", 1.0), _entry("b", "create", b"same", 1.0)])
        h.prune("w", "a", keep=1)
        assert h.read("w", "b", 1) == b"same"

    def test_summaries(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        h.record([_entry("a", "create", b"1", 10.0)])
        h.record([_entry("a", "update", b"2", 20.0, author=_agent("r"))])
        h.record([_entry("x", "create", b"1", 5.0, wiki="other")])
        s = h.summaries("w")
        assert set(s) == {"a"}
        assert s["a"].first_at == 10.0
        assert s["a"].latest.version == 2
        assert s["a"].latest.author.kind == "agent"

    def test_changes_filters_and_cursor(self, tmp_path: Path) -> None:
        h = self.make_history(tmp_path)
        h.record([_entry("a", "create", b"1", 1.0, author=_agent("child", root="root"))])
        h.record([_entry("b", "create", b"2", 2.0, author=_agent("root"))])
        h.record([_entry("c", "create", b"3", 3.0, wiki="w2", author=_agent("root"))])
        h.record([_entry("a", "delete", b"1", 4.0)])
        everything = h.changes(None, limit=10)
        assert [(c.wiki, c.path) for c in everything.items] == [
            ("w", "a"),
            ("w2", "c"),
            ("w", "b"),
            ("w", "a"),
        ]
        by_run = h.changes(None, author_run="root", limit=10)
        assert [c.path for c in by_run.items] == ["c", "b", "a"]
        only_w = h.changes("w", author_run="root", limit=10)
        assert [c.path for c in only_w.items] == ["b", "a"]
        deletes = h.changes("w", ops=["delete"])
        assert [(c.path, c.op) for c in deletes.items] == [("a", "delete")]
        first = h.changes(None, limit=2)
        assert len(first.items) == 2
        assert first.next_cursor
        rest = h.changes(None, limit=2, cursor=first.next_cursor)
        assert [c.path for c in [*first.items, *rest.items]] == ["a", "c", "b", "a"]
        assert rest.next_cursor is None
