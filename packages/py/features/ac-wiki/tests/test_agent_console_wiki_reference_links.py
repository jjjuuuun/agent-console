"""참조 링크 `[글][이름]`(정의 `[이름]: 경로`) 읽기 — 그래프·백링크·이름 바꾸기 (FU.14 1).

인라인 링크·코드 블록·인라인 코드·이미지·정의 없는 이름은 회귀 확인이다.
"""

from __future__ import annotations

from pathlib import Path

from agent_console_wiki import (
    InMemoryWikiHistory,
    LocalWikiPages,
    WikiIndex,
    WikiRepository,
    build_index,
    compile_syntax,
    effective_syntax,
    neighborhood,
    parse_page,
    rewrite_links,
)
from agent_console_wiki._inline import LinkReference, reference_key, scan_inline
from agent_console_wiki.testing import FakeClock

SYNTAX = compile_syntax(effective_syntax())


def _index(files: dict[str, str]) -> WikiIndex:
    return build_index([parse_page(p, t, SYNTAX) for p, t in files.items()], SYNTAX)


def _targets(text: str) -> list[tuple[str, str, str | None]]:
    return [(link.raw, link.target, link.reference) for link in parse_page("p", text, SYNTAX).links]


def test_full_collapsed_and_shortcut_forms() -> None:
    text = '보기 [안내][Docs] · [docs][] · [DOCS] 끝\n\n[docs]: guides/setup.md "제목"\n'
    links = parse_page("p", text, SYNTAX).links
    assert [(link.raw, link.target, link.label) for link in links] == [
        ("[안내][Docs]", "guides/setup.md", "안내"),
        ("[docs][]", "guides/setup.md", "docs"),
        ("[DOCS]", "guides/setup.md", "DOCS"),
    ]
    # 대상 위치는 정의 줄의 경로(셋이 같은 자리)
    spans = {(link.target_start, link.target_end) for link in links}
    assert len(spans) == 1
    start, end = spans.pop()
    assert start is not None
    assert end is not None
    assert text[start:end] == "guides/setup.md"
    assert all(link.kind == "markdown" and link.rule_id == "relative" for link in links)


def test_label_matching_is_commonmark_normalized() -> None:
    text = "[글][  Multi   Word ]\n\n[multi word]:\n  <other page.md>\n"
    assert _targets(text) == [("[글][  Multi   Word ]", "other page.md", "MULTI WORD")]


def test_not_links_regression() -> None:
    text = (
        "정의 없음 [글][없음] · [혼자]\n"
        "코드 `[글][docs]` · 이미지 ![그림][docs] · 인라인 [x](a.md)\n"
        "바깥 [밖][ext] · 페이지 아님 [표][img]\n"
        "\n"
        "```\n[글][docs]\n```\n"
        "\n"
        "    [들여쓴][docs]\n"
        "\n"
        "[docs]: b.md\n"
        "[ext]: https://example.test/x.md\n"
        "[img]: pic.png\n"
    )
    assert _targets(text) == [("[x](a.md)", "a.md", None)]


def test_definition_inside_code_block_is_not_a_definition() -> None:
    text = "[글][d]\n\n```\n[d]: b.md\n```\n"
    assert _targets(text) == []


def test_definition_in_blockquote_and_first_definition_wins() -> None:
    text = "> [q]: q.md\n> 인용 안 [q]\n\n밖 [Q]\n\n[q]: second.md\n"
    assert [t for _, t, _ in _targets(text)] == ["q.md", "q.md"]


def test_wiki_pattern_link_unaffected_without_definition() -> None:
    assert _targets("[[page]] 그리고 [page]\n") == [("[[page]]", "page", None)]


def test_scan_inline_without_references_reads_no_reference_links() -> None:
    assert scan_inline("[글][d]").links == []
    refs = {reference_key("d"): LinkReference("b.md", 50, 54)}
    (link,) = scan_inline("[글][d]", refs).links
    assert (link.start, link.end, link.dest_start, link.reference) == (0, 6, 50, "D")


def test_graph_and_backlinks_include_reference_links() -> None:
    index = _index(
        {
            "home": "[설치][s] 그리고 [s][]\n\n[s]: guides/setup.md\n",
            "guides/setup": "# 설치\n",
        }
    )
    assert [(b.path, b.count) for b in index.backlinks("guides/setup")] == [("home", 2)]
    graph = neighborhood(index, "home")
    edges = {(e.from_, e.to, e.count) for e in graph.edges}
    assert ("home", "guides/setup", 2) in edges


def test_rewrite_updates_shared_definition_once() -> None:
    text = '[설치][s] · [s][] · [S]\n\n[s]: old.md#절 "제목"\n[t]: <old.md>\n[글][t]\n'
    index = _index({"note": text, "old": "# 옛\n"})
    result = rewrite_links(
        text, index.links["note"], page="note", old="old", new="new/place", syntax=SYNTAX
    )
    assert result.count == 4
    assert result.text == (
        '[설치][s] · [s][] · [S]\n\n[s]: new/place.md#절 "제목"\n[t]: <new/place.md>\n[글][t]\n'
    )


def test_repository_move_rewrites_reference_definitions(tmp_path: Path) -> None:
    repo = WikiRepository(
        LocalWikiPages(tmp_path),
        wiki_id="w",
        syntax=SYNTAX,
        history=InMemoryWikiHistory(),
        clock=FakeClock(),
    )
    repo.write("old", "# 옛\n")
    repo.write("sub/x", "[위로][up]\r\n\r\n[up]: ../old.md\r\n")
    result = repo.move("old", "new/place")
    assert result.moved
    assert [r.path for r in result.rewritten] == ["sub/x"]
    assert (tmp_path / "sub/x.md").read_bytes() == (
        "[위로][up]\r\n\r\n[up]: ../new/place.md\r\n".encode()
    )
    assert [b.path for b in repo.index().backlinks("new/place")] == ["sub/x"]
