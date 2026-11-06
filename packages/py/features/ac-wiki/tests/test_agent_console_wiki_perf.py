"""성능(design §7R.14): 페이지 2,000개·20MB·링크 40,000개 `build_index`(차가운) 2초 이하, 그래프
주변 2단계 100ms 이하, 백링크 200개 이름 바꾸기 1초 이하.

기본 실행은 작업량(페이지·링크 수)만 단언하고, `AGENT_CONSOLE_PERF=strict`일 때 가장 빠른 실행의
벽시계를 단언한다(부하가 큰 장비에서 벽시계가 흔들리므로). 파싱은 병렬 없이 한다.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from agent_console_safe_regex import DEFAULT_TIMEOUT_SECONDS
from agent_console_wiki import (
    WikiIndex,
    build_index,
    compile_syntax,
    effective_syntax,
    neighborhood,
    parse_page,
    rewrite_links,
)

PAGES = 2000
LINKS_PER_PAGE = 20


def _strict() -> bool:
    return os.environ.get("AGENT_CONSOLE_PERF", "") == "strict"


def _best[T](fn: Callable[[], T], runs: int) -> tuple[float, T]:
    best, result = float("inf"), None
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - start)
    assert result is not None
    return best, result


def _page(i: int) -> str:
    parts = [f"---\ntitle: 페이지 {i}\ntags: [t{i % 10}]\n---\n# 제목 {i}\n"]
    for k in range(LINKS_PER_PAGE):
        j = (i * 7 + k * 13) % PAGES
        link = f"[[p{j}|라벨]]" if k % 2 else f"[상대](p{j}.md)"
        code = " `code [[x]]`" if k % 5 == 0 else ""
        parts.append(
            f"\n문단 {k}: 위키 본문 글이 이어지는 곳이다 {link}{code} 뒤에 더 많은 글자가 "
            + "본문 채우기 낱말 " * 17
            + "\n"
        )
    parts.append("\n```\n[[fence]]\n```\n")
    return "".join(parts)


def _wiki() -> dict[str, str]:
    return {f"p{i}": _page(i) for i in range(PAGES)}


def test_build_index_2000_pages_20mb() -> None:
    texts = _wiki()
    assert sum(len(t.encode()) for t in texts.values()) >= 20 * 1000 * 1000
    timeout = DEFAULT_TIMEOUT_SECONDS if _strict() else 600.0
    syntax = compile_syntax(effective_syntax(), regex_timeout=timeout)

    def run() -> WikiIndex:
        return build_index([parse_page(p, t, syntax) for p, t in texts.items()], syntax)

    seconds, index = _best(run, 3 if _strict() else 1)
    assert len(index.pages) == PAGES
    assert sum(len(v) for v in index.links.values()) == PAGES * LINKS_PER_PAGE
    assert not index.broken_links()
    graph_seconds, graph = _best(lambda: neighborhood(index, "p5", 2), 3)
    assert graph.nodes
    assert graph.nodes[0].path == "p5"
    if _strict():
        assert seconds <= 2.0, f"build_index {seconds:.3f}s"
        assert graph_seconds <= 0.1, f"neighborhood {graph_seconds:.3f}s"


def test_rename_with_200_backlinks() -> None:
    syntax = compile_syntax(effective_syntax())
    texts = {"target": "# 대상\n"}
    for i in range(200):
        texts[f"src/{i}"] = "\n\n".join(
            f"문단 [[target]] 와 [상대](../target.md) 글 {k}" for k in range(5)
        )
    index = build_index([parse_page(p, t, syntax) for p, t in texts.items()], syntax)
    assert len(index.backlinks("target")) == 200

    def run() -> int:
        total = 0
        for src in index.incoming["target"]:
            total += rewrite_links(
                texts[src],
                index.links[src],
                page=src,
                old="target",
                new="moved/target",
                syntax=syntax,
            ).count
        return total

    seconds, count = _best(run, 3 if _strict() else 1)
    assert count == 200 * 10
    if _strict():
        assert seconds <= 1.0, f"rewrite {seconds:.3f}s"
