"""링크 넣기 글(Q3): 규칙의 `insert` 틀, 상대 경로 계산, 틀이 없으면
`wiki.link_insert_unavailable`."""

from __future__ import annotations

import pytest

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiSettings
from agent_console_wiki import (
    WikiLinkInsertUnavailableError,
    WikiPathError,
    compile_syntax,
    effective_syntax,
    render_link_text,
)

SYNTAX = compile_syntax(effective_syntax())


def test_default_rules_insert() -> None:
    first = render_link_text(SYNTAX, from_page="a/b", target="c/d", label="라벨")
    assert (first.rule_id, first.text) == ("wikilink", "[[c/d|라벨]]")
    rel = render_link_text(SYNTAX, from_page="a/b", target="c/d", rule_id="relative")
    assert rel.text == "[c/d](../c/d.md)"
    spaced = render_link_text(SYNTAX, from_page="a", target="my page", rule_id="relative")
    assert spaced.text == "[my page](my%20page.md)"


def test_default_off_or_rule_without_insert_is_unavailable() -> None:
    off = compile_syntax(effective_syntax(WikiSettings(include_default_syntax=False)))
    with pytest.raises(WikiLinkInsertUnavailableError) as err:
        render_link_text(off, from_page="a", target="b")
    assert err.value.code == KnownIssueCodes.WIKI_LINK_INSERT_UNAVAILABLE
    no_insert = compile_syntax(
        effective_syntax(
            rules=[
                ("r", {"links": [{"id": "m", "kind": "markdown", "resolve": ["relative_path"]}]})
            ]
        )
    )
    with pytest.raises(WikiLinkInsertUnavailableError):
        render_link_text(no_insert, from_page="a", target="b", rule_id="m")
    with pytest.raises(WikiLinkInsertUnavailableError):
        render_link_text(SYNTAX, from_page="a", target="b", rule_id="unknown")


def test_changed_syntax_with_own_insert() -> None:
    syntax = compile_syntax(
        effective_syntax(
            WikiSettings(include_default_syntax=False),
            rules=[
                (
                    "r",
                    {
                        "links": [
                            {
                                "id": "paren",
                                "kind": "pattern",
                                "pattern": r"\(\((?P<target>[^)]+)\)\)",
                                "resolve": ["path"],
                                "insert": "(({target}))",
                            }
                        ],
                        "page_extensions": [".markdown"],
                    },
                )
            ],
        )
    )
    assert render_link_text(syntax, from_page="x", target="y/z").text == "((y/z))"


def test_paths_are_checked() -> None:
    with pytest.raises(WikiPathError):
        render_link_text(SYNTAX, from_page="a", target="../outside")
