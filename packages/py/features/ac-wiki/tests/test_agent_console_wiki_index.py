"""링크 색인: 해석 순서·대소문자·백링크·끊긴 링크·바깥 링크·스킴·고아·제목 겹침, 요약, 그래프
주변."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_wiki import (
    CompiledWikiSyntax,
    WikiIndex,
    WikiPageNotFoundError,
    build_index,
    compile_syntax,
    effective_syntax,
    neighborhood,
    parse_page,
)

SYNTAX = compile_syntax(effective_syntax())


def _index(files: Mapping[str, str], syntax: CompiledWikiSyntax = SYNTAX, **kw: Any) -> WikiIndex:
    return build_index([parse_page(p, t, syntax) for p, t in files.items()], syntax, **kw)


def _status(index: WikiIndex, path: str) -> list[tuple[str, str, str | None]]:
    return [(link.raw, link.status, link.resolved) for link in index.page_links(path)]


def test_resolution_order_path_title_alias_case_insensitive() -> None:
    index = _index(
        {
            "Home": "[[docs/Guide]] [[가이드 제목]] [[별칭]] [[DOCS/guide.md]] [[/docs/guide]]",
            "docs/guide": "---\ntitle: 가이드 제목\naliases: [별칭]\n---\n",
        }
    )
    assert _status(index, "Home") == [
        ("[[docs/Guide]]", "ok", "docs/guide"),
        ("[[가이드 제목]]", "ok", "docs/guide"),
        ("[[별칭]]", "ok", "docs/guide"),
        ("[[DOCS/guide.md]]", "ok", "docs/guide"),
        ("[[/docs/guide]]", "ok", "docs/guide"),
    ]
    assert index.find("가이드 제목") == "docs/guide"
    assert index.find("nothing") is None


def test_case_sensitive_when_data_says_so() -> None:
    syntax = compile_syntax(effective_syntax(rules=[("r", {"case_insensitive": False})]))
    index = _index({"a": "[[B]] [[b]]", "b": ""}, syntax)
    assert [s for _, s, _ in _status(index, "a")] == ["broken", "ok"]


def test_broken_links_get_suggested_path_only_with_path_resolvers() -> None:
    syntax = compile_syntax(
        effective_syntax(
            rules=[
                (
                    "r",
                    {
                        "links": [
                            {
                                "id": "w",
                                "kind": "pattern",
                                "pattern": r"\[\[(?P<target>[^\]]+)\]\]",
                                "resolve": ["path"],
                            },
                            {
                                "id": "t",
                                "kind": "pattern",
                                "pattern": r"\{\{(?P<target>[^}]+)\}\}",
                                "resolve": ["title"],
                            },
                            {"id": "m", "kind": "markdown", "resolve": ["relative_path"]},
                        ]
                    },
                )
            ]
        )
    )
    index = _index({"dir/a": "[[new/page]] {{없는 제목}} [x](../made.md) [[bad:name]]"}, syntax)
    links = index.page_links("dir/a")
    assert [(link.status, link.suggested_path) for link in links] == [
        ("broken", "new/page"),
        ("broken", None),
        ("broken", "made"),
        ("broken", None),  # 경로 규칙(`:`)에 어긋남
    ]
    assert [p for p, _ in index.broken_links()] == ["dir/a"] * 4


def test_outside_relative_link_is_not_read_or_broken() -> None:
    index = _index({"a": "[up](../../secret.md) [ok](b.md)", "b": ""})
    links = index.page_links("a")
    assert (links[0].status, links[0].outside, links[0].broken, links[0].resolved) == (
        "outside",
        True,
        False,
        None,
    )
    assert links[0].suggested_path is None
    assert links[1].status == "ok"


def test_schemes_are_data_and_win_over_everything() -> None:
    syntax = compile_syntax(
        effective_syntax(
            rules=[
                (
                    "r",
                    {
                        "schemes": [
                            {"prefix": "run:", "target": {"role": "runs", "query": "tab={value}"}},
                            {"prefix": "r", "target": {"role": "other"}},
                        ]
                    },
                )
            ]
        )
    )
    index = _index({"a": "[[run:abc]] [x](run:def) [[run:]]", "run": ""}, syntax)
    links = index.page_links("a")
    assert [link.status for link in links] == ["scheme", "scheme", "scheme"]
    assert links[0].scheme_target is not None
    assert links[0].scheme_target.role == "runs"
    assert links[0].scheme_target.id_from == "abc"
    assert links[0].scheme_target.query == "tab=abc"
    assert links[1].scheme_target is not None
    assert links[1].scheme_target.id_from == "def"
    assert links[2].scheme_target is None
    graph = neighborhood(index, "a", 1)
    assert {n.path: n.scheme for n in graph.nodes if n.scheme} == {
        "run:abc": "run:",
        "run:def": "run:",
        "run:": "run:",
    }


def test_backlinks_orphans_home_and_ignore() -> None:
    syntax = compile_syntax(
        effective_syntax(rules=[("r", {"lint": {"orphan_ignore": ["archive/**"]}})])
    )
    index = _index(
        {
            "home": "[[a]] [[a]] [[home]]",
            "a": "[[b]]",
            "b": "[[a]]",
            "lonely": "",
            "archive/old": "",
        },
        syntax,
        home="home",
    )
    assert [(b.path, b.count) for b in index.backlinks("a")] == [("b", 1), ("home", 2)]
    assert index.backlinks("home") == []  # 자기 링크는 백링크가 아님
    assert index.orphans == {"lonely"}
    summary = index.summary("home", updated_at=5.0)
    assert (summary.home, summary.orphan, summary.links_out, summary.backlinks) == (
        True,
        False,
        3,
        0,
    )
    assert index.summary("lonely").orphan is True
    assert index.summary("a").backlinks == 2


def test_home_missing_and_empty_home_q21() -> None:
    index = _index({"a": ""}, home="index")
    assert KnownIssueCodes.WIKI_HOME_MISSING in [i.code for i in index.issues]
    no_home = _index({"a": ""}, home="")
    assert no_home.home is None
    assert no_home.orphans == {"a"}  # 첫 페이지가 없으면 뺄 것이 없다


def test_duplicate_titles() -> None:
    index = _index({"a": "# 같은 제목", "b": "---\ntitle: 같은 제목\n---\n", "c": "# 다른"})
    assert index.duplicate_titles == [["a", "b"]]
    assert index.find("같은 제목") == "a"  # 경로 순 앞


def test_facts_shape() -> None:
    index = _index({"a": "---\ntitle: T\ntags: [x]\nsource: s\n---\n[[b]] [[missing]]", "b": ""})
    facts = index.facts("a")
    assert facts == {
        "path": "a",
        "title": "T",
        "tags": ["x"],
        "aliases": [],
        "front_matter": {"title": "T", "tags": ["x"], "source": "s"},
        "bytes": index.pages["a"].bytes,
        "links_out": 2,
        "broken_links": 1,
    }


def test_neighborhood_depth_limit_and_flags() -> None:
    files = {"c": "[[n1]] [[gone]]", "n1": "[[n2]]", "n2": "[[n3]]", "n3": "", "back": "[[c]]"}
    index = _index(files, home="c")
    g1 = neighborhood(index, "c", 1)
    assert {(n.path, n.depth) for n in g1.nodes} == {("c", 0), ("n1", 1), ("gone", 1), ("back", 1)}
    assert next(n for n in g1.nodes if n.path == "c").home is True
    assert next(n for n in g1.nodes if n.path == "gone").broken is True
    assert {(e.from_, e.to) for e in g1.edges} == {("c", "n1"), ("c", "gone"), ("back", "c")}
    g2 = neighborhood(index, "c", 2)
    assert ("n2", 2) in {(n.path, n.depth) for n in g2.nodes}
    small = neighborhood(index, "c", 3, limit=2)
    assert (len(small.nodes), small.truncated, small.total) == (2, True, 6)
    whole = neighborhood(index)
    assert all(n.depth is None for n in whole.nodes)
    assert whole.total == 6
    with pytest.raises(WikiPageNotFoundError):
        neighborhood(index, "nope")


def test_edges_are_merged_with_count() -> None:
    index = _index({"a": "[[b]] [[b]] [b](b.md)", "b": ""})
    graph = neighborhood(index, "a", 1)
    assert [(e.from_, e.to, e.count) for e in graph.edges] == [("a", "b", 3)]
    dumped = graph.model_dump(by_alias=True)
    assert dumped["edges"][0]["from"] == "a"
