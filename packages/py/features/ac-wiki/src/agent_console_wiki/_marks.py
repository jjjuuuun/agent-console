"""검색 강조 범위(design §7R.18 Q11): 조각 문자열 안에서 질의 낱말이 나온 곳(UTF-16 범위).

검색 색인(X48, 7R.9) 구현마다 강조를 만들지 않도록 위키 라이브러리 한 곳에서 계산한다. 색인 구현이
범위를 주면 그것을 쓴다(호출자 몫).
"""

from __future__ import annotations

import re

from agent_console_contracts.wiki import WikiTextRange

from ._text import Utf16Map

__all__ = ["query_terms", "search_marks"]

_QUOTES = "\"'"


def query_terms(query: str) -> list[str]:
    """질의 → 낱말(공백으로 나눔, 앞뒤 따옴표 뺌, 겹침 제거, 긴 것부터)."""
    seen: list[str] = []
    for raw in query.split():
        term = raw.strip(_QUOTES)
        if term and term not in seen:
            seen.append(term)
    return sorted(seen, key=len, reverse=True)


def search_marks(snippet: str, query: str, *, case_insensitive: bool = True) -> list[WikiTextRange]:
    """조각 안 질의 낱말 범위(UTF-16 코드 단위, 겹치면 합침, 시작 순).

    Args:
        snippet: 검색 결과 조각(가림 뒤 자른 것).
        query: 검색어.
        case_insensitive: 대소문자 무시(위키 문법 `case_insensitive`).
    """
    terms = query_terms(query)
    if not terms or not snippet:
        return []
    flags = re.IGNORECASE if case_insensitive else 0
    pattern = re.compile("|".join(re.escape(t) for t in terms), flags)
    spans: list[tuple[int, int]] = []
    for m in pattern.finditer(snippet):
        if m.end() == m.start():
            continue
        if spans and m.start() <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], m.end()))
        else:
            spans.append((m.start(), m.end()))
    u16 = Utf16Map(snippet)
    return [WikiTextRange(start=u16(s), end=u16(e)) for s, e in spans]
