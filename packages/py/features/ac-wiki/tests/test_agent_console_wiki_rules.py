"""위키 규칙 합치기·검사·틀 렌더(7R.8, design §7R.1.1·§7R.18 Q5·Q7)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from agent_console_contracts.wiki import WikiPageTemplate, WikiRulesDefinition
from agent_console_store import FileDefinitionStore
from agent_console_wiki import (
    RulesDocument,
    check_rules,
    definition_kinds,
    load_wiki_rules,
    merge_rules,
    render_page_template,
    slugify,
)


def _rules(rule_id: str, **body: Any) -> WikiRulesDefinition:
    return WikiRulesDefinition.model_validate(
        {"kind": "wiki-rules", "id": rule_id, "name": body.pop("name", rule_id.upper()), **body}
    )


def _codes(issues: list[Any]) -> list[str]:
    return [i.code for i in issues]


def test_merge_rules_concatenates_and_keeps_sources() -> None:
    first = RulesDocument(
        "r1",
        _rules(
            "r1",
            name="결정만",
            instructions={"file": "i.md"},
            write_rules=[{"id": "w", "deny_patterns": ["TODO"], "message": "임시 메모 금지"}],
            lint_rules=[
                {"id": "stale", "when": {"all": [{"path": "/idle_days", "op": "gte", "value": 9}]}}
            ],
            page_templates=[{"id": "t", "title": "결정", "file": "t.md"}],
            syntax={"case_insensitive": False},
        ),
        {"i.md": "결정만 적습니다.\n", "t.md": b"# {title}\n"},
    )
    second = RulesDocument(
        "r2",
        _rules(
            "r2",
            instructions={"file": "i.md"},
            write_rules=[
                {"id": "w", "action": "warn", "message": "겹침"},
                {"id": "w2", "action": "warn"},
            ],
        ),
        {"i.md": "둘째 지침"},
    )
    merged = merge_rules(["r1", "missing", "r2", "r1"], [first, second], header="## {name}")
    assert [(r.id, r.missing) for r in merged.refs] == [
        ("r1", False),
        ("missing", True),
        ("r2", False),
    ]
    assert merged.instructions == "## 결정만\n\n결정만 적습니다.\n\n## R2\n\n둘째 지침"
    assert [(s.rule_id, s.item.id) for s in merged.write_rules] == [("r1", "w"), ("r2", "w2")]
    assert [(e.kind, e.id, e.rule_id) for e in merged.entries] == [
        ("write", "w", "r1"),
        ("lint", "stale", "r1"),
        ("template", "t", "r1"),
        ("write", "w2", "r2"),
    ]
    assert merged.entries[0].label == "임시 메모 금지"
    assert _codes(merged.issues) == ["wiki.rules_missing", "wiki.duplicate_rule_id"]
    assert merged.syntax_layers[0][0] == "r1"
    summary = merged.summary()
    assert (summary.write_rules, summary.lint_rules, summary.page_templates) == (2, 1, 1)
    (info,) = merged.template_infos()
    assert info.rule_id == "r1"
    assert info.content == "# {title}\n"
    assert [(v.name, v.builtin) for v in info.variables] == [("title", True)]


def test_merge_rules_default_header_comes_from_package_data() -> None:
    doc = RulesDocument("a", _rules("a", name="이름", instructions={"file": "x"}), {"x": "본문"})
    merged = merge_rules(["a"], {"a": doc})
    assert "이름" in merged.instructions
    assert merged.instructions.endswith("본문")


def test_check_rules_issues() -> None:
    doc = {
        "kind": "wiki-rules",
        "id": "r",
        "name": "r",
        "instructions": {"file": "nope.md"},
        "write_rules": [
            {"id": "all", "action": "reject"},
            {"id": "all", "applies_to": ["/abs", "a\\b"], "deny_patterns": ["(a+)+", "("]},
            {"id": "odd", "action": "shout", "when": {"all": [{"path": "/x", "op": "zz"}]}},
            {"id": "scoped", "applies_to": ["archive/**"], "action": "reject"},
        ],
        "lint_rules": [{"id": "e", "when": {}}],
        "page_templates": [{"id": "t", "file": "t.md", "path": "d/{slug}-{owner}-{nope}"}],
        "page_templates_extra": "모르는 키 보존",
    }
    issues = check_rules(doc, files=["t.md"])
    codes = _codes(issues)
    assert "wiki.always_rejects" in codes
    always = [i for i in issues if i.code == "wiki.always_rejects"]
    assert [i.rule_id for i in always] == ["all"]  # 범위가 정해진 규칙(scoped)은 걸리지 않음
    assert codes.count("wiki.invalid_glob") == 2
    assert codes.count("wiki.invalid_pattern") == 2
    assert "wiki.duplicate_rule_id" in codes
    assert "wiki.unknown_action" in codes
    assert "condition.unknown_operator" in codes
    assert "condition.empty" in codes
    assert "wiki.template_missing" in codes  # 지침 파일
    unknown = [i for i in issues if i.code == "wiki.unknown_variable"]
    assert sorted(i.details["name"] for i in unknown) == ["nope", "owner"]
    declared = dict(doc)
    declared["page_templates"] = [
        {"id": "t", "file": "t.md", "path": "d/{slug}-{owner}", "variables": [{"name": "owner"}]}
    ]
    assert "wiki.unknown_variable" not in _codes(check_rules(declared, files=["t.md"]))


def test_check_rules_syntax_and_shape() -> None:
    bad_syntax = {
        "kind": "wiki-rules",
        "id": "r",
        "name": "r",
        "syntax": {"links": [{"id": "p", "kind": "pattern", "pattern": "((x"}]},
    }
    issues = check_rules(bad_syntax)
    assert [i.code for i in issues] == ["wiki.link_pattern_invalid"]
    assert issues[0].path is not None
    assert issues[0].path.startswith("/syntax")
    assert _codes(check_rules({"kind": "wiki-rules"})) == ["validation_failed"]


def test_render_page_template() -> None:
    tpl = WikiPageTemplate.model_validate(
        {"id": "d", "file": "d.md", "path": "decisions/{date}-{slug}", "variables": [{"name": "o"}]}
    )
    out = render_page_template(
        tpl, "# {title}\n담당: {o}\n{unknown}", title="API 버전", today=dt.date(2026, 11, 7)
    )
    assert out.path == "decisions/2026-11-07-api-버전"
    assert out.content == "# API 버전\n담당: \n"
    assert out.missing == ["o", "unknown"]
    filled = render_page_template(
        tpl, "{o}", title="x", values={"o": "홍", "title": "무시"}, today=dt.date(2026, 1, 2)
    )
    assert filled.content == "홍"
    assert filled.missing == []
    slug_only = tpl.model_copy(update={"path": "decisions/{slug}"})
    no_title = render_page_template(slug_only, "", today=dt.date(2026, 1, 2))
    assert no_title.path is None
    assert [i.code for i in no_title.issues] == ["wiki.invalid_path"]
    assert "slug" in no_title.missing


def test_slugify() -> None:
    assert slugify("Hello  World") == "hello-world"
    assert slugify("..") == ""
    assert slugify("a/b\\c:d") == "abcd"


def test_definition_kinds_and_load_rules(tmp_path: Path) -> None:
    wiki_kind, rules_kind = definition_kinds(
        wiki_kind="wk", wiki_dir="wikis-x", rules_kind="rk", rules_dir="rules-x"
    )
    assert wiki_kind.library is False
    assert wiki_kind.is_portable
    assert rules_kind.multi_file
    assert rules_kind.library
    store = FileDefinitionStore(tmp_path, kinds=[wiki_kind, rules_kind])
    created = store.create(
        "rk",
        {
            "kind": "rk",
            "id": "r1",
            "name": "규칙",
            "instructions": {"file": "i.md"},
            "content": {"file": "i.md"},
        },
    )
    store.write_files("rk", "r1", {"i.md": "지침".encode()}, expected_version=created.version_hash)
    store.create("wk", {"kind": "wk", "id": "w", "name": "위키", "rules": ["r1", "zz"]})
    assert (tmp_path / "rules-x" / "r1.yaml").exists()
    assert (tmp_path / "wikis-x" / "w.yaml").exists()
    docs = load_wiki_rules(store, ["r1", "zz"], kind="rk")
    assert [d.id for d in docs] == ["r1"]
    merged = merge_rules(["r1", "zz"], docs)
    assert merged.instructions.endswith("지침")
    assert [r.missing for r in merged.refs] == [False, True]
