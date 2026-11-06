"""검색 강조(Q11): 조각 안 질의 낱말의 UTF-16 범위, 대소문자 규칙, 겹침 합치기."""

from __future__ import annotations

from agent_console_wiki import query_terms, search_marks


def _slices(snippet: str, query: str, **kw: bool) -> list[str]:
    u16 = snippet.encode("utf-16-le")
    return [
        u16[m.start * 2 : m.end * 2].decode("utf-16-le") for m in search_marks(snippet, query, **kw)
    ]


def test_korean_and_emoji_slices_match_terms() -> None:
    snippet = "😀 위키는 Wiki 문서 🧭 위키"
    assert _slices(snippet, "위키 wiki") == ["위키", "Wiki", "위키"]
    assert _slices(snippet, "위키 wiki", case_insensitive=False) == ["위키", "위키"]


def test_overlaps_merge_and_quotes() -> None:
    assert _slices("abcabc", "abc bca") == ["abcabc"]
    assert query_terms('"위키" 위키 a') == ["위키", "a"]
    assert search_marks("", "x") == []
    assert search_marks("text", "   ") == []
