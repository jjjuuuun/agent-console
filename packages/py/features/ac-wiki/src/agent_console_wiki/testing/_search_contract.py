"""`WikiSearchIndex` 계약 묶음: 검색 색인 구현(`scan`·`sqlite-fts`·플러그인)이 지켜야 할 의미.

```python
class TestMyIndex(WikiSearchContractTests):
    def make_index(self, tmp_path, **options) -> WikiSearchIndex:
        return MyIndex(tmp_path / "idx", **options)
```

`options`는 `case_insensitive`(bool)·`limits`(`SearchLimits`)·`redact`(함수)이며,
구현이 같은 이름으로
받아야 한다. 이 묶음은 페이지 내용을 코드에 고정하지 않고 시험 안에서 임시로 만든다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agent_console_wiki._search import (
    SearchLimits,
    WikiSearchDocument,
    WikiSearchIndex,
    sync_search_index,
)

__all__ = ["WikiSearchContractTests", "make_search_document"]


def make_search_document(
    path: str,
    text: str = "",
    *,
    title: str = "",
    tags: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
) -> WikiSearchDocument:
    """시험용 색인 문서(해시 = 제목·태그·별칭·본문의 sha256)."""
    raw = "\x00".join([title, *tags, *aliases, text]).encode("utf-8", "surrogatepass")
    return WikiSearchDocument(
        path=path,
        title=title,
        tags=tags,
        aliases=aliases,
        text=text,
        content_hash=hashlib.sha256(raw).hexdigest(),
    )


class WikiSearchContractTests:
    """하위 클래스가 `make_index`를 채우면 pytest가 아래 시험을 돌린다."""

    def make_index(
        self, tmp_path: Path, **options: Any
    ) -> WikiSearchIndex:  # pragma: no cover - 하위 클래스가 채운다
        raise NotImplementedError

    def _filled(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        idx = self.make_index(tmp_path, **options)
        idx.update(
            [
                make_search_document("guide/intro", "이 위키는 팀의 약속을 적는다.", title="소개"),
                make_search_document("guide/setup", "Install the Toolchain first.", title="Setup"),
                make_search_document(
                    "notes/alpha",
                    "알파 노트. 위키 링크 [[guide/intro]]",
                    title="알파",
                    tags=("draft",),
                ),
                make_search_document("notes/beta", "베타 노트", title="베타", tags=("draft", "ko")),
            ]
        )
        return idx

    def test_empty_and_blank_query(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        assert idx.search("anything").items == []
        assert idx.hashes() == {}
        idx2 = self._filled(tmp_path / "x")
        assert idx2.search("").items == []
        assert idx2.search('  "  ').items == []

    def test_korean_partial_match(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        paths = [h.path for h in idx.search("위키").items]
        assert "guide/intro" in paths  # "위키는" 안의 "위키"
        assert "notes/alpha" in paths  # "위키 링크"
        assert idx.search("약속").items[0].path == "guide/intro"

    def test_english_partial_and_case(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        assert [h.path for h in idx.search("toolch").items] == ["guide/setup"]
        assert [h.path for h in idx.search("TOOLCHAIN").items] == ["guide/setup"]
        sensitive = self._filled(tmp_path / "cs", case_insensitive=False)
        assert sensitive.search("TOOLCHAIN").items == []
        assert [h.path for h in sensitive.search("Toolchain").items] == ["guide/setup"]

    def test_short_queries(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        assert "notes/alpha" in [h.path for h in idx.search("알").items]
        assert [h.path for h in idx.search("베타").items] == ["notes/beta"]
        assert [h.path for h in idx.search("to").items] == ["guide/setup"]

    def test_all_terms_must_match(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        assert [h.path for h in idx.search("위키 링크").items] == ["notes/alpha"]
        assert idx.search("위키 없는낱말").items == []

    def test_fields_path_title_tags_aliases(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        idx.update(
            [
                make_search_document("a/one", "본문", title="제목문자", tags=("태그가나다",)),
                make_search_document("a/two", "본문", aliases=("별칭라마바",)),
            ]
        )
        assert [h.path for h in idx.search("제목문").items] == ["a/one"]
        assert [h.path for h in idx.search("가나다").items] == ["a/one"]
        assert [h.path for h in idx.search("라마바").items] == ["a/two"]
        assert [h.path for h in idx.search("a/tw").items] == ["a/two"]

    def test_title_ranks_above_body(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        idx.update(
            [
                make_search_document("a", "여기에 가나다라 가 있다", title="무관"),
                make_search_document("b", "무관", title="가나다라"),
            ]
        )
        hits = idx.search("가나다라").items
        assert [h.path for h in hits] == ["b", "a"]
        assert hits[0].score is not None
        assert hits[1].score is not None
        assert hits[0].score > hits[1].score

    def test_prefix_and_tags(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        assert {h.path for h in idx.search("노트", prefix="notes/").items} == {
            "notes/alpha",
            "notes/beta",
        }
        assert idx.search("노트", prefix="guide/").items == []
        assert {h.path for h in idx.search("노트", tags=["draft"]).items} == {
            "notes/alpha",
            "notes/beta",
        }
        assert [h.path for h in idx.search("노트", tags=["draft", "ko"]).items] == ["notes/beta"]
        assert idx.search("노트", tags=["none"]).items == []

    def test_limit_and_truncated(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path, limits=SearchLimits(max_results=5))
        idx.update([make_search_document(f"p/{i:02d}", "공통어휘 본문") for i in range(8)])
        res = idx.search("공통어휘", limit=3)
        assert [h.path for h in res.items] == ["p/00", "p/01", "p/02"]
        assert res.truncated is True
        capped = idx.search("공통어휘", limit=50)
        assert len(capped.items) == 5
        assert capped.truncated is True
        assert idx.search("공통어휘", limit=8).truncated is True  # 상한 5가 더 작다
        small = self.make_index(tmp_path / "s")
        small.update([make_search_document("only", "공통어휘")])
        assert small.search("공통어휘").truncated is False

    def test_incremental_update_skips_same_hash(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        docs = [make_search_document("a", "첫째 본문"), make_search_document("b", "둘째 본문")]
        assert idx.update(docs) == 2
        assert idx.update(docs) == 0
        changed = make_search_document("a", "고친 본문")
        assert idx.update([changed, docs[1]]) == 1
        assert idx.hashes() == {"a": changed.content_hash, "b": docs[1].content_hash}
        assert idx.search("첫째").items == []
        assert [h.path for h in idx.search("고친").items] == ["a"]

    def test_remove_rebuild_sync(self, tmp_path: Path) -> None:
        idx = self._filled(tmp_path)
        assert idx.remove(["guide/intro", "missing"]) == 1
        assert "guide/intro" not in [h.path for h in idx.search("약속").items]
        docs = [make_search_document("x", "새 본문"), make_search_document("y", "다른 본문")]
        assert idx.rebuild(docs) == 2
        assert set(idx.hashes()) == {"x", "y"}
        assert idx.search("약속").items == []
        result = sync_search_index(idx, [docs[0], make_search_document("z", "셋째")])
        assert (result.updated, result.removed) == (1, 1)
        assert set(idx.hashes()) == {"x", "z"}

    def test_special_characters_do_not_break(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        idx.update([make_search_document("a", 'say "hi" AND (x) OR NEAR* y-z \\ %_')])
        for q in ('"hi"', "AND", "(x)", "NEAR*", "y-z", "\\", "%_", "'", '"', "a b\x00c", "OR"):
            idx.search(q)
        assert [h.path for h in idx.search('"hi"').items] == ["a"]
        assert [h.path for h in idx.search("(x)").items] == ["a"]

    def test_snippet_and_marks_utf16(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        text = "앞 글자 😀😀 위키는 여기 😀 그리고 Wiki 둘째 위키 끝"
        idx.update([make_search_document("p", text, title="제목")])
        hit = idx.search("위키 wiki").items[0]
        assert hit.snippet
        assert hit.marks
        units = hit.snippet.encode("utf-16-le")
        spans = []
        for m in hit.marks:
            piece = units[m.start * 2 : m.end * 2].decode("utf-16-le")
            spans.append(piece.casefold())
            assert piece.casefold() in {"위키", "wiki"}
        assert spans.count("위키") == 2
        assert spans.count("wiki") == 1
        sensitive = self.make_index(tmp_path / "cs", case_insensitive=False)
        sensitive.update([make_search_document("p", text)])
        hit2 = sensitive.search("Wiki").items[0]
        assert [
            hit2.snippet.encode("utf-16-le")[m.start * 2 : m.end * 2].decode("utf-16-le")
            for m in hit2.marks
        ] == ["Wiki"]

    def test_snippet_long_body_is_cut_around_match(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path, limits=SearchLimits(snippet_chars=40))
        body = "가" * 300 + " 목표낱말 " + "나" * 300
        idx.update([make_search_document("p", body)])
        hit = idx.search("목표낱말").items[0]
        assert "목표낱말" in hit.snippet
        assert len(hit.snippet) <= 40 + 2
        assert hit.snippet.startswith("…")
        assert hit.snippet.endswith("…")

    def test_secret_not_in_snippet_or_searchable(self, tmp_path: Path) -> None:
        secret = "sk-ant-api03-" + "A1b2C3d4" * 6
        idx = self.make_index(tmp_path)
        idx.update(
            [
                make_search_document(
                    "s", f"설정 메모\napi_key = {secret}\n그 다음 줄 설정", title="키"
                )
            ]
        )
        res = idx.search("설정")
        assert res.items
        assert secret not in res.items[0].snippet
        assert "A1b2C3d4A1b2C3d4" not in res.items[0].snippet
        assert idx.search(secret[:20]).items == []

    def test_idempotent_ids(self, tmp_path: Path) -> None:
        idx = self.make_index(tmp_path)
        assert idx.id
        res = idx.search("x")
        assert res.backend == idx.id or res.backend  # 대체 방식이면 실제로 쓴 id
        assert res.degraded == idx.degraded
        idx.close()
        idx.close()
