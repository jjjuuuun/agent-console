"""페이지 파싱: 머리말·제목 출처·태그·별칭·제목들·링크 원문 위치(코드 블록·인라인 코드 무시,
UTF-16)."""

from __future__ import annotations

import random
from typing import Any

import pytest
from ruamel.yaml import YAML

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_wiki import (
    build_index,
    compile_syntax,
    effective_syntax,
    merge_syntax,
    parse_page,
)
from agent_console_wiki._frontmatter import _simple_yaml, read_front_matter
from agent_console_wiki._inline import _code_spans, _code_spans_scan, scan_inline

SYNTAX = compile_syntax(effective_syntax())


def _raws(text: str, syntax: Any = SYNTAX) -> list[str]:
    return [link.raw for link in parse_page("p", text, syntax).links]


# ---------------------------------------------------------------- 머리말·제목


def test_front_matter_roles_title_tags_aliases() -> None:
    text = (
        "---\ntitle: 결정 기록\ntags: [api, 버전]\naliases: [결정]\nsource: RFC 1\n---\n"
        "# 본문 제목\n"
    )
    page = parse_page("decisions/api", text, SYNTAX)
    assert page.title == "결정 기록"
    assert page.title_source == "front_matter"
    assert page.tags == ["api", "버전"]
    assert page.aliases == ["결정"]
    assert page.front_matter["source"] == "RFC 1"
    assert page.headings[0].text == "본문 제목"
    assert page.headings[0].line == 7
    assert page.issues == []


def test_title_falls_back_to_heading_then_file_name() -> None:
    assert parse_page("a/b", "intro\n\n## h2\n\n# 첫 제목\n", SYNTAX).title == "첫 제목"
    page = parse_page("a/b-c", "no heading here\n", SYNTAX)
    assert (page.title, page.title_source) == ("b-c", "file_name")


def test_title_sources_order_is_data() -> None:
    syntax = compile_syntax(effective_syntax(rules=[("r", {"title_sources": ["file_name"]})]))
    page = parse_page("x/name", "---\ntitle: T\n---\n# H\n", syntax)
    assert page.title == "name"
    none = compile_syntax(effective_syntax(rules=[("r", {"title_sources": []})]))
    assert parse_page("x/name", "# H\n", none).title == ""


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("---\ntitle: [unclosed\n---\nbody\n", 3),
        ("---\n- just\n- a list\n---\nbody\n", 2),
        ("---\ntitle: no closing line\nbody\n", 1),
    ],
)
def test_broken_front_matter_is_issue_and_body(text: str, line: int) -> None:
    page = parse_page("p", text + "[[x]]\n", SYNTAX)
    assert [i.code for i in page.issues] == [KnownIssueCodes.WIKI_FRONT_MATTER_INVALID]
    assert page.issues[0].page == "p"
    assert page.issues[0].line == line
    assert page.front_matter == {}
    assert page.body_start == 0
    assert "[[x]]" in [link.raw for link in page.links]


def test_front_matter_dates_become_strings_and_crlf_ok() -> None:
    page = parse_page(
        "p", "---\r\nupdated: 2026-11-07\r\ntitle: T\r\n---\r\nbody [[x]]\r\n", SYNTAX
    )
    assert page.front_matter == {"updated": "2026-11-07", "title": "T"}
    assert page.title == "T"
    assert [link.line for link in page.links] == [5]


def test_simple_front_matter_fast_path_equals_yaml() -> None:
    yaml = YAML(typ="safe")
    samples = [
        "title: 위키 페이지\ntags: [a, b c, 한글]\n",
        "title: x\n\naliases: []\n",
        "a: plain text with spaces\nb: [x]\n",
    ]
    for source in samples:
        fast = _simple_yaml(source)
        assert fast is not None, source
        assert fast == yaml.load(source)
    # 평이한 글자가 아니면 빠른 길을 쓰지 않는다(일반 YAML 결과와 어긋날 수 있는 값)
    for ambiguous in [
        "n: 1\n",
        "b: true\n",
        "y: yes\n",
        "d: 2026-01-01\n",
        "q: 'quoted'\n",
        "c: a # comment\n",
        "nested:\n  k: v\n",
        "t: ~\n",
        "list: [1, 2]\n",
        "dup: a\ndup: b\n",
        "k:  two spaces\n",
    ]:
        assert _simple_yaml(ambiguous) is None, ambiguous


def test_front_matter_delimiter_is_data() -> None:
    syntax = compile_syntax(effective_syntax(rules=[("r", {"front_matter": {"delimiter": "+++"}})]))
    page = parse_page("p", "+++\ntitle: T\n+++\n[[a]]\n", syntax)
    assert page.title == "T"
    assert read_front_matter("---\ntitle: T\n---\n", None).data == {}


# ---------------------------------------------------------------- 링크 원문


def test_links_skip_code_blocks_and_inline_code() -> None:
    text = (
        "[[a]] and `[[inline]]` and ``x `[[double]]` y`` ok\n"
        "\n"
        "```\n[[fenced]]\n```\n"
        "\n"
        "    [[indented code]]\n"
        "\n"
        "<div>\n[[html block]]\n</div>\n"
        "\n"
        "> quote [[b]]\n"
        "- item [[c]]\n"
        "## heading [[d]]\n"
    )
    assert _raws(text) == ["[[a]]", "[[b]]", "[[c]]", "[[d]]"]


def test_unclosed_backticks_are_literal() -> None:
    assert _raws("a ` b [[x]] c\n") == ["[[x]]"]
    # 이스케이프한 백틱은 글자 → 뒤 백틱 하나는 닫는 짝이 없어 글자
    assert _raws("\\`[[y]]` [[z]]\n") == ["[[y]]", "[[z]]"]
    # 여는 묶음 앞 역슬래시는 백틱 하나만 글자로 만든다 → 나머지 한 개가 코드 조각을 연다
    assert _raws("\\``[[q]]` [[r]]\n") == ["[[r]]"]
    # 코드 조각 안 역슬래시는 이스케이프가 아니다
    assert _raws("`a\\`[[s]]`\n") == ["[[s]]"]


def test_pattern_groups_label_anchor_and_spans() -> None:
    page = parse_page("p", "see [[  folder/page #sec | 라벨 ]] now\n", SYNTAX)
    (link,) = page.links
    assert link.target == "folder/page"
    assert link.label == "라벨"
    assert link.anchor == "sec"
    assert link.target_start is not None
    assert link.target_end is not None
    assert (
        "see [[  folder/page #sec | 라벨 ]] now\n"[link.target_start : link.target_end]
        == "folder/page"
    )


def test_markdown_links_relative_page_files_only() -> None:
    text = (
        '[a](a.md) [b](sub/b.md#part) [c](<c d.md> "title") [e](e%20f.md)\n'
        "[web](https://x.test/a.md) [abs](/root.md) [anchor](#here) [img](pic.png)\n"
        "![image](g.md) [mail](mailto:x@y) [win](C:/w.md) [empty]()\n"
        "[nested [label]](n.md) [![img](p.png)](linked.md)\n"
    )
    page = parse_page("p", text, SYNTAX)
    got = [(link.target, link.label, link.anchor) for link in page.links]
    assert got == [
        ("a.md", "a", None),
        ("sub/b.md", "b", "part"),
        ("c d.md", "c", None),
        ("e f.md", "e", None),
        ("n.md", "nested [label]", None),
        ("linked.md", "![img](p.png)", None),
    ]
    (e,) = [link for link in page.links if link.target == "e f.md"]
    assert e.target_start is not None
    assert e.target_end is not None
    assert text[e.target_start : e.target_end] == "e%20f.md"


def test_markdown_link_hides_pattern_inside_it() -> None:
    assert _raws("[see [[x]]](y.md) [[z]]\n") == ["[see [[x]]](y.md)", "[[z]]"]


def test_first_rule_wins_on_overlap() -> None:
    syntax = compile_syntax(
        merge_syntax(
            (
                "s",
                {
                    "links": [
                        {"id": "a", "kind": "pattern", "pattern": r"\[\[(?P<target>[^\]]+)\]\]"},
                        {"id": "b", "kind": "pattern", "pattern": r"\[(?P<target>[^\]]+)\]"},
                    ]
                },
            )
        )
    )
    page = parse_page("p", "[[one]] [two]\n", syntax)
    assert [(link.rule_id, link.raw) for link in page.links] == [("a", "[[one]]"), ("b", "[two]")]


def test_utf16_ranges_slice_the_original_link() -> None:
    text = "😀 한글 [[대상|라벨]] 👩‍💻 [링크](b.md) 𝄞 [[끝]]\n"
    syntax = SYNTAX
    page = parse_page("p", text, syntax)
    index = build_index([page], syntax)
    links = index.page_links("p")
    assert len(links) == 3
    u16 = text.encode("utf-16-le")
    for link in links:
        assert u16[link.start * 2 : link.end * 2].decode("utf-16-le") == link.raw
    # 코드 포인트 위치와는 다르다(BMP 밖 글자가 앞에 있음)
    assert links[0].start != page.links[0].start


def test_bytes_input_and_hash() -> None:
    import hashlib

    data = b"# T\r\n\r\n[[a]]\r\n"
    page = parse_page("p", data, SYNTAX)
    assert page.content_hash == hashlib.sha256(data).hexdigest()
    assert page.bytes == len(data)
    assert [link.raw for link in page.links] == ["[[a]]"]


def test_parse_timeout_drops_links_only() -> None:
    ticks = iter([0.0, 0.0, 10.0, 10.0, 10.0])
    page = parse_page(
        "p",
        "---\ntitle: T\n---\n[[a]]\n\n[[b]]\n",
        SYNTAX,
        timeout_ms=1,
        clock=lambda: next(ticks),
    )
    assert page.links == []
    assert page.title == "T"
    assert [i.code for i in page.issues] == [KnownIssueCodes.WIKI_PARSE_TIMEOUT]


def test_default_syntax_off_gives_no_links() -> None:
    syntax = compile_syntax(effective_syntax(settings_off()))
    page = parse_page("p", "[[a]] [b](b.md)\n", syntax)
    assert page.links == []


def settings_off() -> Any:
    from agent_console_contracts.wiki import WikiSettings

    return WikiSettings(include_default_syntax=False)


def test_code_span_fast_path_equals_slow_path() -> None:
    rng = random.Random(7)
    alphabet = "`a b\n[]"
    for _ in range(3000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        assert _code_spans(text) == _code_spans_scan(text), repr(text)


def test_scan_inline_excludes_autolinks() -> None:
    scan = scan_inline("<https://x.test/[[a]]> [[b]]")
    assert scan.overlaps(10, 15)
    assert not scan.overlaps(23, 28)
