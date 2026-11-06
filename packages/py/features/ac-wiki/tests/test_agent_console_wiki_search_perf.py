"""검색 색인 성능(design §7R.14, 7R.9): 페이지 2,000개에서 검색 200ms 이하.

기본 실행은 작업량(페이지 수·결과 수)만 단언하고, `AGENT_CONSOLE_PERF=strict`일 때 가장 빠른 실행의
벽시계를 단언한다(부하가 큰 장비에서 벽시계가 흔들리므로).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from agent_console_wiki import ScanSearchIndex, WikiSearchDocument, WikiSearchIndex
from agent_console_wiki.sqlite import SqliteFtsSearchIndex, fts_tokenizer_available
from agent_console_wiki.testing import make_search_document

PAGES = 2000
SEARCH_BUDGET_S = 0.2


def _strict() -> bool:
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


def _docs() -> list[WikiSearchDocument]:
    out = []
    for i in range(PAGES):
        body = " ".join(
            f"문단{k} 위키 본문 글이 이어지는 곳이다 항목{i * 7 + k} common word{k % 13}"
            for k in range(60)
        )
        if i % 200 == 0:
            body += " 희귀낱말xyz"
        out.append(
            make_search_document(
                f"dir{i % 20}/page{i}", body, title=f"페이지 {i}", tags=(f"t{i % 10}",)
            )
        )
    return out


def _best[T](fn: Callable[[], T], runs: int = 5) -> tuple[float, T]:
    best, result = float("inf"), None
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - start)
    assert result is not None
    return best, result


def _check(idx: WikiSearchIndex, label: str) -> None:
    docs = _docs()
    start = time.perf_counter()
    assert idx.update(docs) == PAGES
    build = time.perf_counter() - start
    print(f"\n[{label}] 색인 {PAGES}쪽: {build * 1000:.0f}ms")
    queries = {
        "희귀(3자+)": "희귀낱말",
        "흔한 낱말": "위키 본문",
        "영어 부분": "ommon wor",
        "한 글자": "곳",
        "접두+태그": "common",
    }
    for name, q in queries.items():
        kwargs = {"prefix": "dir3/", "tags": ["t3"]} if name == "접두+태그" else {}
        took, res = _best(lambda q=q, kwargs=kwargs: idx.search(q, **kwargs))  # type: ignore[misc]
        print(f"[{label}] {name}: {took * 1000:.1f}ms, 결과 {len(res.items)}")
        assert res.items
        if _strict():
            assert took < SEARCH_BUDGET_S, (label, name, took)
    # 증분: 바뀐 것 없음
    took, n = _best(lambda: idx.update(docs), runs=3)
    assert n == 0
    print(f"[{label}] 변경 없는 갱신: {took * 1000:.0f}ms")


@pytest.mark.skipif(not fts_tokenizer_available("trigram"), reason="FTS5 trigram 없음")
def test_sqlite_fts_search_budget(tmp_path: Path) -> None:
    _check(SqliteFtsSearchIndex(tmp_path / "i.sqlite3"), "sqlite-fts")


def test_scan_search_budget() -> None:
    _check(ScanSearchIndex(), "scan")
