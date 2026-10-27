"""색인 비우기(`PurgeableLogIndex`) 계약 테스트 묶음. 구현마다 상속해 `make_index`만 채운다.

```python
class TestSqlitePurge(PurgeContractTests):
    def make_index(self) -> LogIndex:
        return open_log_index(":memory:")
```
"""

from __future__ import annotations

from datetime import UTC

from agent_console_contracts.logs import LogLane, TokenSample
from agent_console_logs._filter import LogFilter, QueryContext
from agent_console_logs._index import IndexBatch, LogIndex, StoredCursor
from agent_console_logs._purge import PurgeableLogIndex, PurgeResult, purge_index, reset_index

from ._contract import make_record

__all__ = ["PurgeContractTests"]


def _ctx() -> QueryContext:
    return QueryContext(error_categories=frozenset({"error"}), tz=UTC)


class PurgeContractTests:
    """`purge_index`·`reset_index`가 지켜야 할 의미(메모리·SQLite가 같다)."""

    def make_index(self) -> LogIndex:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def _sample(self) -> LogIndex:
        """출처 a(llm 2·blob 1)·b(llm 1), 응답 m1(a, llm+blob 공유)·m2(a)·m3(b), 커서·에이전트."""
        index = self.make_index()
        index.write(
            IndexBatch(
                records=[
                    make_record(
                        "llm",
                        source="a",
                        thread="T",
                        message_id="m1",
                        time=100.0,
                        title="hello",
                        usage=TokenSample(output_tokens=5),
                        agent=LogLane(id="T", label="main"),
                    ),
                    make_record(
                        "blob",
                        source="a",
                        thread="T",
                        message_id="m1",
                        time=101.0,
                        detail={"secret": "request body"},
                    ),
                    make_record(
                        "llm",
                        source="a",
                        thread="T",
                        message_id="m2",
                        time=200.0,
                        usage=TokenSample(output_tokens=7, time=200.0),
                    ),
                    make_record(
                        "llm",
                        source="b",
                        thread="U",
                        message_id="m3",
                        time=300.0,
                        usage=TokenSample(output_tokens=9, time=300.0),
                        agent=LogLane(id="U", label="other"),
                    ),
                ],
                cursors=[
                    StoredCursor(source="a", ref="a1.jsonl", offset=10),
                    StoredCursor(source="a", ref="a2.jsonl", offset=20),
                    StoredCursor(source="b", ref="b1.jsonl", offset=30),
                ],
            )
        )
        return index

    @staticmethod
    def _categories(index: LogIndex) -> list[tuple[str, str]]:
        page = index.query_events(LogFilter(), _ctx())
        return sorted((e.source, e.category) for e in page.items)

    @staticmethod
    def _usage(index: LogIndex) -> list[str]:
        return sorted(s.message_id for s in index.token_samples(LogFilter(), _ctx()))

    def test_protocol(self) -> None:
        assert isinstance(self.make_index(), PurgeableLogIndex)

    def test_dry_run_deletes_nothing(self) -> None:
        index = self._sample()
        before = (self._categories(index), self._usage(index), len(index.list_cursors("a")))
        result = purge_index(index, sources=["a"], dry_run=True)
        assert result == PurgeResult(dry_run=True, events=3, usage=2, cursors=2, agents=1)
        after = (self._categories(index), self._usage(index), len(index.list_cursors("a")))
        assert after == before
        assert [lane.id for lane in index.lanes()] == ["T", "U"]

    def test_category_keeps_shared_usage_and_resets_cursors(self) -> None:
        index = self._sample()
        result = purge_index(index, categories=["blob"])
        # m1 표본은 남는 llm 이벤트도 가리켜 남는다. 출처 조건이 없으니 커서는 전부.
        assert result == PurgeResult(dry_run=False, events=1, usage=0, cursors=3, agents=0)
        assert self._categories(index) == [("a", "llm"), ("a", "llm"), ("b", "llm")]
        assert self._usage(index) == ["m1", "m2", "m3"]
        assert index.list_cursors("a") == []
        assert index.list_cursors("b") == []
        page = index.query_events(LogFilter(q="request body"), _ctx())
        assert page.items == []

    def test_source_and_category(self) -> None:
        index = self._sample()
        result = purge_index(index, sources=["a"], categories=["llm"])
        # m1은 blob이 남아 표본이 남고, m2는 마지막 이벤트가 지워져 표본도 지운다.
        assert result == PurgeResult(dry_run=False, events=2, usage=1, cursors=2, agents=0)
        assert self._categories(index) == [("a", "blob"), ("b", "llm")]
        assert self._usage(index) == ["m1", "m3"]
        assert [c.ref for c in index.list_cursors("b")] == ["b1.jsonl"]

    def test_before(self) -> None:
        index = self._sample()
        result = purge_index(index, before=250.0, rescan=False)
        assert result == PurgeResult(dry_run=False, events=3, usage=2, cursors=0, agents=0)
        assert self._categories(index) == [("b", "llm")]
        assert self._usage(index) == ["m3"]
        assert len(index.list_cursors("a")) == 2

    def test_source_and_before(self) -> None:
        index = self._sample()
        result = purge_index(index, sources=["b"], before=250.0)
        assert result == PurgeResult(dry_run=False, events=0, usage=0, cursors=1, agents=0)
        assert len(self._categories(index)) == 4

    def test_whole_source(self) -> None:
        index = self._sample()
        result = purge_index(index, sources=["b"])
        assert result == PurgeResult(dry_run=False, events=1, usage=1, cursors=1, agents=1)
        assert self._categories(index) == [("a", "blob"), ("a", "llm"), ("a", "llm")]
        assert [lane.id for lane in index.lanes()] == ["T"]

    def test_unknown_names_match_nothing(self) -> None:
        index = self._sample()
        result = purge_index(index, sources=["zzz"], categories=["blob"])
        assert result == PurgeResult(dry_run=False, events=0, usage=0, cursors=0, agents=0)
        assert len(self._categories(index)) == 4

    def test_reset(self) -> None:
        index = self._sample()
        top = index.max_seq()
        assert reset_index(index, dry_run=True).events == 4
        assert len(self._categories(index)) == 4
        result = reset_index(index)
        assert result == PurgeResult(dry_run=False, events=4, usage=3, cursors=3, agents=2)
        assert self._categories(index) == []
        assert self._usage(index) == []
        assert index.lanes() == []
        assert index.max_seq() is None
        # seq는 이어진다(웹의 seq 기준 새로 고침이 거꾸로 가지 않는다).
        again = index.write(IndexBatch(records=[make_record("llm", source="a")]))
        assert top is not None
        assert again.max_seq is not None
        assert again.max_seq > top

    def test_rejects_empty_lists(self) -> None:
        index = self._sample()
        for kwargs, error in (
            ({"sources": []}, ValueError),
            ({"categories": [""]}, ValueError),
            ({"sources": "a"}, TypeError),
        ):
            try:
                purge_index(index, **kwargs)
            except error:
                pass
            else:  # pragma: no cover - 실패 경로
                raise AssertionError(f"{kwargs} 거부 안 됨")
        assert len(self._categories(index)) == 4
