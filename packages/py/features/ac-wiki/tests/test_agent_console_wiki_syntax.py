"""문법 데이터: 패키지 기본, 층 병합(값마다 출처·None 상속·빈 목록), 끄기, 컴파일 이슈."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import (
    WIKI_LINK_INSERT_VARIABLES,
    KnownWikiSyntaxSources,
    WikiSettings,
    WikiSyntax,
)
from agent_console_text_template import template_variables
from agent_console_wiki import (
    compile_syntax,
    effective_syntax,
    load_default_syntax,
    merge_syntax,
    rules_source,
)


def _codes(issues: list[Any]) -> list[str]:
    return [i.code for i in issues]


def test_default_syntax_data_matches_design() -> None:
    syntax = load_default_syntax()
    assert [r.id for r in syntax.links or ()] == ["wikilink", "relative"]
    inserts = {r.id: r.insert for r in syntax.links or ()}
    assert inserts == {"wikilink": "[[{target}|{label}]]", "relative": "[{label}]({relative_path})"}
    for text in inserts.values():
        assert text is not None
        assert template_variables(text) <= set(WIKI_LINK_INSERT_VARIABLES)
    assert syntax.lint is not None
    assert syntax.lint.write_rules is True
    assert syntax.lint.builtin == {
        "broken_link": "warning",
        "orphan": "info",
        "duplicate_title": "warning",
    }
    assert syntax.front_matter is not None
    assert syntax.front_matter.roles == {"title": "title", "tags": "tags", "aliases": "aliases"}
    # 새 객체(호출자가 고쳐도 다음 호출에 영향 없음)
    syntax.links = []
    assert load_default_syntax().links


def test_default_compiles_without_issues() -> None:
    compiled = compile_syntax(effective_syntax())
    assert compiled.issues == []
    assert [r.id for r in compiled.links] == ["wikilink", "relative"]
    assert compiled.lint_write_rules is True
    assert compiled.page_extensions == (".md",)


def test_merge_sources_none_inherits_and_empty_list_overrides() -> None:
    eff = merge_syntax(
        (KnownWikiSyntaxSources.DEFAULT, load_default_syntax()),
        (
            KnownWikiSyntaxSources.SETTINGS,
            {"case_insensitive": False, "front_matter": {"delimiter": "+++"}},
        ),
        (rules_source("r1"), WikiSyntax(schemes=[], lint={"orphan_ignore": ["archive/**"]})),  # type: ignore[arg-type]
        (rules_source("r2"), None),
    )
    syntax = eff.syntax
    assert syntax.case_insensitive is False
    assert syntax.front_matter is not None
    assert syntax.front_matter.delimiter == "+++"
    # 같은 객체 안의 다른 키는 아래 층 그대로
    assert syntax.front_matter.roles == {"title": "title", "tags": "tags", "aliases": "aliases"}
    assert syntax.lint is not None
    assert syntax.lint.orphan_ignore == ["archive/**"]
    assert syntax.lint.write_rules is True
    assert eff.sources["/links"] == "default"
    assert eff.sources["/case_insensitive"] == "settings"
    assert eff.sources["/front_matter/delimiter"] == "settings"
    assert eff.sources["/front_matter/roles"] == "default"
    assert eff.sources["/schemes"] == "rules:r1"
    assert eff.sources["/lint/orphan_ignore"] == "rules:r1"
    assert eff.empty is False


def test_empty_links_list_in_upper_layer_means_none() -> None:
    eff = effective_syntax(rules=[("r", WikiSyntax(links=[]))])
    assert eff.empty is True
    assert eff.sources["/links"] == "rules:r"
    assert _codes(eff.issues) == [KnownIssueCodes.WIKI_SYNTAX_MISSING]


def test_include_default_off_gives_empty_syntax() -> None:
    eff = effective_syntax(WikiSettings(include_default_syntax=False))
    assert eff.empty is True
    assert "default" not in eff.sources.values()
    compiled = compile_syntax(eff)
    assert compiled.links == ()
    assert compiled.page_extensions == ()
    assert KnownIssueCodes.WIKI_SYNTAX_MISSING in _codes(compiled.issues)


def test_unknown_keys_are_preserved() -> None:
    eff = merge_syntax(("settings", {"links": [], "future_key": {"a": 1}}))
    assert eff.syntax.model_dump()["future_key"] == {"a": 1}


def test_compile_issues_drop_only_the_broken_part() -> None:
    eff = merge_syntax(
        (
            "settings",
            {
                "links": [
                    {"id": "bad", "kind": "pattern", "pattern": "(unclosed"},
                    {"id": "nogroup", "kind": "pattern", "pattern": r"\(\((.+?)\)\)"},
                    {"id": "empty", "kind": "pattern"},
                    {"id": "weird", "kind": "telepathy"},
                    {
                        "id": "ok",
                        "kind": "pattern",
                        "pattern": r"\{\{(?P<target>[^}]+)\}\}",
                        "resolve": ["path", "guess"],
                    },
                    {"id": "ok", "kind": "markdown"},
                ],
                "title_sources": ["nope", "file_name"],
                "lint": {"orphan_ignore": ["/abs", "ok/**"]},
            },
        )
    )
    compiled = compile_syntax(eff)
    assert [r.id for r in compiled.links] == ["ok"]
    assert compiled.links[0].resolve == ("path",)
    codes = _codes(compiled.issues)
    assert codes.count(KnownIssueCodes.WIKI_LINK_PATTERN_INVALID) == 3
    assert codes.count(KnownIssueCodes.WIKI_UNKNOWN_LINK_KIND) == 2
    assert KnownIssueCodes.WIKI_DUPLICATE_RULE_ID in codes
    assert KnownIssueCodes.WIKI_INVALID_GLOB in codes
    assert compiled.title_sources == ("file_name",)
    assert compiled.orphan_ignore == ("ok/**",)
    pointers = {i.path for i in compiled.issues}
    assert "/links/0/pattern" in pointers
    assert compiled.effective.issues == compiled.issues


def test_all_patterns_invalid_marks_compiled_empty() -> None:
    eff = merge_syntax(("settings", {"links": [{"id": "x", "kind": "pattern", "pattern": "("}]}))
    assert eff.empty is False
    compiled = compile_syntax(eff)
    assert compiled.empty is True
    assert compiled.effective.empty is True
    assert KnownIssueCodes.WIKI_SYNTAX_MISSING in _codes(compiled.issues)
