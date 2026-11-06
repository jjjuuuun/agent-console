"""검색 색인(X48, 7R.9): 계약 묶음 + 두 구현이 같은 결과·강조를 낸다 + 폴백·재생성·플러그인."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_console_registry import Registry
from agent_console_wiki import (
    ScanSearchIndex,
    SearchLimits,
    WikiSearchIndex,
    builtin_search_factories,
    compile_syntax,
    effective_syntax,
    load_search_plugins,
    new_search_registry,
    parse_page,
    register_builtin_search,
    search_document,
    sync_search_index,
)
from agent_console_wiki.sqlite import SqliteFtsSearchIndex, fts_tokenizer_available
from agent_console_wiki.testing import (
    MemoryWikiPages,
    WikiSearchContractTests,
    make_search_document,
)

needs_trigram = pytest.mark.skipif(
    not fts_tokenizer_available("trigram"), reason="이 SQLite에는 FTS5 trigram이 없다"
)


class TestScanContract(WikiSearchContractTests):
    def make_index(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        return ScanSearchIndex(**options)


@needs_trigram
class TestSqliteContract(WikiSearchContractTests):
    def make_index(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        idx = SqliteFtsSearchIndex(tmp_path / "idx" / "wiki.sqlite3", **options)
        assert idx.id == "sqlite-fts"
        assert not idx.degraded
        return idx


@needs_trigram
class TestSqliteMemoryContract(WikiSearchContractTests):
    def make_index(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        return SqliteFtsSearchIndex(None, **options)


class TestForcedFallbackContract(WikiSearchContractTests):
    """FTS5·trigram을 못 쓰는 SQLite를 흉내 낸다: 훑기로 대신하고 `degraded`."""

    def make_index(self, tmp_path: Path, **options: Any) -> WikiSearchIndex:
        idx = SqliteFtsSearchIndex(
            tmp_path / "idx.sqlite3", assume_missing={"trigram", "unicode61"}, **options
        )
        assert idx.degraded
        assert idx.id == "scan"
        return idx


def _docs() -> list[Any]:
    return [
        make_search_document("a/one", "이 위키는 😀 Wiki 테스트 본문입니다 위키", title="하나"),
        make_search_document("a/two", "둘째 페이지 위키 링크", title="Wiki 둘", tags=("t",)),
        make_search_document("b/three", "셋째 😀😀 wiki WIKI", aliases=("위키별칭",)),
    ]


@needs_trigram
@pytest.mark.parametrize("query", ["위키", "wiki", "위키 wiki", "Wi", "페", "별칭", "😀"])
@pytest.mark.parametrize("ci", [True, False])
def test_two_backends_same_hits_and_marks(tmp_path: Path, query: str, ci: bool) -> None:
    scan = ScanSearchIndex(case_insensitive=ci)
    fts = SqliteFtsSearchIndex(tmp_path / "i.sqlite3", case_insensitive=ci)
    for idx in (scan, fts):
        idx.update(_docs())
    a, b = scan.search(query), fts.search(query)
    assert [(h.path, h.score, h.snippet, h.marks) for h in a.items] == [
        (h.path, h.score, h.snippet, h.marks) for h in b.items
    ]
    assert a.truncated == b.truncated


@needs_trigram
def test_marks_slice_equals_query_terms_utf16(tmp_path: Path) -> None:
    idx = SqliteFtsSearchIndex(tmp_path / "i.sqlite3")
    idx.update(_docs())
    hit = next(h for h in idx.search("위키").items if h.path == "a/one")
    raw = hit.snippet.encode("utf-16-le")
    assert hit.marks
    for m in hit.marks:
        assert raw[m.start * 2 : m.end * 2].decode("utf-16-le") == "위키"


@needs_trigram
def test_index_file_is_recreated_after_delete(tmp_path: Path) -> None:
    path = tmp_path / "x" / "idx.sqlite3"
    docs = _docs()
    idx = SqliteFtsSearchIndex(path)
    sync_search_index(idx, docs)
    idx.close()
    path.unlink()
    again = SqliteFtsSearchIndex(path)
    assert again.hashes() == {}
    res = sync_search_index(again, docs)
    assert res.updated == 3
    assert again.search("위키").items
    again.close()
    # 닫은 뒤 그대로 다시 열면 이어서 쓴다(증분: 바뀐 것 없음)
    third = SqliteFtsSearchIndex(path)
    assert sync_search_index(third, docs).updated == 0


@needs_trigram
def test_corrupt_file_and_changed_settings_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "idx.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    idx = SqliteFtsSearchIndex(path)
    idx.update(_docs())
    assert idx.search("위키").items
    idx.close()
    # 설정(대소문자·비밀 서명)이 다르면 버리고 다시 짓는다
    other = SqliteFtsSearchIndex(path, case_insensitive=False)
    assert other.hashes() == {}
    other.update(_docs())
    other.close()
    sig = SqliteFtsSearchIndex(path, case_insensitive=False, redact_signature="v2")
    assert sig.hashes() == {}


@needs_trigram
def test_redact_function_and_signature(tmp_path: Path) -> None:
    idx = SqliteFtsSearchIndex(tmp_path / "i.sqlite3", redact=lambda t: t.replace("비밀값", "###"))
    idx.update([make_search_document("p", "앞 비밀값 뒤 공개", title="t")])
    assert idx.search("비밀값").items == []
    assert "###" in idx.search("공개").items[0].snippet


@needs_trigram
def test_body_char_limit(tmp_path: Path) -> None:
    for idx in (
        SqliteFtsSearchIndex(None, limits=SearchLimits(max_body_chars=10)),
        ScanSearchIndex(limits=SearchLimits(max_body_chars=10)),
    ):
        idx.update([make_search_document("p", "가" * 10 + "끝낱말")])
        assert idx.search("끝낱말").items == []
        assert idx.search("가가가").items


@needs_trigram
def test_term_count_cap(tmp_path: Path) -> None:
    lim = SearchLimits(max_terms=2)
    for idx in (SqliteFtsSearchIndex(None, limits=lim), ScanSearchIndex(limits=lim)):
        idx.update([make_search_document("p", "가나다 라마바 사아자")])
        assert idx.search("가나다 라마바 없다").items  # 가장 짧은 셋째 낱말은 버린다


@needs_trigram
def test_unicode61_is_degraded_prefix_match(tmp_path: Path) -> None:
    if not fts_tokenizer_available("unicode61"):  # pragma: no cover
        pytest.skip("unicode61 없음")
    idx = SqliteFtsSearchIndex(None, tokenizer="unicode61")
    assert idx.degraded
    assert idx.id == "sqlite-fts"
    idx.update([make_search_document("p", "Toolchain 설치", title="t")])
    assert idx.search("tool").items  # 앞부분 일치
    assert idx.search("chain").items == []  # 가운데 일치는 못 한다(그래서 degraded)
    assert idx.search("tool").degraded is True


def test_trigram_missing_falls_back_to_unicode61_then_scan() -> None:
    idx = SqliteFtsSearchIndex(None, assume_missing={"trigram"})
    if fts_tokenizer_available("unicode61"):
        assert idx.degraded
        assert idx.id == "sqlite-fts"
        assert idx.tokenizer == "unicode61"
    none = SqliteFtsSearchIndex(None, assume_missing={"fts5"})
    assert none.id == "scan"
    assert none.degraded
    none.update([make_search_document("p", "본문 위키")])
    res = none.search("위키")
    assert res.degraded
    assert res.backend == "scan"
    assert res.items


@needs_trigram
def test_concurrent_search_and_update(tmp_path: Path) -> None:
    import threading

    idx = SqliteFtsSearchIndex(tmp_path / "i.sqlite3")
    idx.update([make_search_document(f"p{i}", f"본문 {i} 위키") for i in range(50)])
    errors: list[BaseException] = []

    def reader() -> None:
        try:
            for _ in range(30):
                assert idx.search("위키").items
        except BaseException as exc:
            errors.append(exc)

    def writer() -> None:
        try:
            for n in range(10):
                idx.update([make_search_document(f"w{n}", f"쓴 글 {n} 위키")])
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=f) for f in (reader, reader, writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_search_document_from_parsed_page_and_sync() -> None:
    syntax = compile_syntax(effective_syntax(None, []))
    text = "---\ntitle: 제목\ntags: [x, y]\naliases: [별칭]\n---\n# 헤더\n본문 위키 글\n"
    parsed = parse_page("n/p", text, syntax)
    doc = search_document(parsed, text)
    assert doc.title == "제목"
    assert doc.tags == ("x", "y")
    assert doc.aliases == ("별칭",)
    assert doc.text.startswith("# 헤더")
    assert "title:" not in doc.text
    assert doc.content_hash == parsed.content_hash
    pages = MemoryWikiPages({"n/p.md": text})
    assert pages.read("n/p.md") is not None
    idx = ScanSearchIndex()
    assert sync_search_index(idx, [doc]).updated == 1
    assert idx.search("본문 위키").items[0].path == "n/p"


# ---------------------------------------------------------------- 플러그인


class _FakeEntryPoint:
    group = "agent_console.wiki_search_indexes"

    def __init__(self, name: str, obj: Any) -> None:
        self.name, self.value, self._obj, self.dist = name, f"fake:{name}", obj, None

    def load(self) -> Any:
        return self._obj


def test_builtin_registry_and_plugins() -> None:
    reg: Registry[Any] = new_search_registry()
    register_builtin_search(reg)
    assert {e.key for e in reg.list()} == {"scan", "sqlite-fts"}
    assert set(builtin_search_factories()) == {"scan", "sqlite-fts"}

    def custom() -> Any:
        return lambda root, options: ScanSearchIndex(backend_id="custom")

    eps = [
        _FakeEntryPoint("custom", custom),
        _FakeEntryPoint("broken", lambda: 42),
        _FakeEntryPoint("scan", custom),
    ]
    reports = load_search_plugins(reg, entry_points=eps)  # type: ignore[arg-type]
    status = {r.key: r.status for r in reports}
    assert status["custom"] == "loaded"
    assert status["broken"] == "failed"
    assert status["scan"] == "failed"  # 기본과 id 겹침
    made = reg.get("custom")(None, {})
    assert made.id == "custom"
    only = new_search_registry()
    skipped = load_search_plugins(only, enabled=set(), entry_points=eps)  # type: ignore[arg-type]
    assert {r.status for r in skipped} == {"skipped"}


@needs_trigram
def test_builtin_factories_build_indexes(tmp_path: Path) -> None:
    f = builtin_search_factories()
    idx = f["sqlite-fts"](tmp_path / "i.sqlite3", {"tokenizer": "trigram", "max_results": 3})
    idx.update([make_search_document(f"p{i}", "공통어") for i in range(5)])
    assert len(idx.search("공통어", limit=10).items) == 3
    scan = f["scan"](None, {"case_insensitive": False})
    assert scan.id == "scan"
