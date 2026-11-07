"""7R 서버 후속(계약 0.14.2): 합친 규칙 항목의 글롭·경로 틀·이름, 점검 부분 실패·켜진 점검,
그래프 스킴 칸의 열 화면."""

from __future__ import annotations

from typing import Any

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import KnownWikiLintChecks, WikiRulesDefinition
from agent_console_wiki import (
    RulesDocument,
    build_index,
    compile_syntax,
    effective_syntax,
    lint,
    merge_rules,
    neighborhood,
    parse_page,
)

SYNTAX = compile_syntax(effective_syntax())


def _merged(**body: Any) -> Any:
    rules = WikiRulesDefinition.model_validate(
        {"kind": "wiki-rules", "id": "r", "name": "r", **body}
    )
    return merge_rules(["r"], [RulesDocument("r", rules, {"t.md": "# {title}\n"})])


RULES = _merged(
    write_rules=[
        {"id": "w", "applies_to": ["decisions/**"], "deny_patterns": ["TODO"], "message": "m"},
        {"id": "all", "deny_patterns": ["FIXME"], "action": "warn"},
    ],
    lint_rules=[
        {"id": "big", "when": {"all": [{"path": "/bytes", "op": "gte", "value": 0}]}},
    ],
    page_templates=[
        {"id": "t", "title": "결정", "file": "t.md", "path": "decisions/{slug}"},
        {"id": "plain", "file": "t.md"},
    ],
)


def _index(files: dict[str, str], syntax: Any = SYNTAX) -> Any:
    return build_index([parse_page(p, t, syntax) for p, t in files.items()], syntax)


def test_rule_entries_carry_glob_path_and_title() -> None:
    by_id = {e.id: e for e in RULES.entries}
    assert by_id["w"].applies_to == ["decisions/**"]
    assert by_id["all"].applies_to == []  # 빈 목록 = 모든 페이지
    assert by_id["big"].applies_to is None  # 점검 규칙은 글롭이 없다
    t, plain, w = by_id["t"], by_id["plain"], by_id["w"]
    assert (t.path, t.title, t.label) == ("decisions/{slug}", "결정", "결정")
    assert (plain.path, plain.title, plain.label) == (None, None, "plain")
    assert (w.path, w.title) == (None, None)


def test_lint_reports_enabled_checks_and_not_partial() -> None:
    files = {"a": "# a\n[[b]]\n", "b": "# b\n"}
    report = lint(_index(files), RULES, now=0.0, read=files.get)
    assert report.partial is False
    assert report.skipped == []
    assert report.enabled_checks == [
        "broken_link",
        "orphan",
        "duplicate_title",
        KnownWikiLintChecks.LINT_RULES,
        KnownWikiLintChecks.WRITE_RULES,
    ]
    # 기본 점검을 끄고 규칙도 없으면 빈 목록
    syntax = compile_syntax(
        effective_syntax(
            rules=[
                (
                    "x",
                    {
                        "lint": {
                            "builtin": {
                                "broken_link": None,
                                "orphan": None,
                                "duplicate_title": "info",
                            },
                            "write_rules": False,
                        }
                    },
                )
            ]
        )
    )
    assert lint(_index(files, syntax), None, now=0.0).enabled_checks == ["duplicate_title"]


def test_lint_skips_failing_page_and_keeps_others() -> None:
    files = {"a": "# a\n[[없음]]\n", "b": "# b\nTODO\n", "decisions/c": "# c\nTODO\n"}

    def read(path: str) -> str | None:
        if path == "b":
            raise OSError("cannot read /secret/path")
        return files.get(path)

    report = lint(_index(files), RULES, now=0.0, read=read)
    assert report.partial is True
    assert report.skipped == ["b"]
    failed = [i for i in report.issues if i.code == KnownIssueCodes.WIKI_LINT_FAILED]
    assert [(i.page, i.severity, i.details) for i in failed] == [
        ("b", "warning", {"reason": "OSError"})
    ]
    # 실패한 페이지의 다른 이슈는 섞지 않는다(반쯤 본 결과 없음)
    assert {i.code for i in report.issues if i.page == "b"} == {KnownIssueCodes.WIKI_LINT_FAILED}
    # 나머지 페이지는 그대로 점검했다
    codes = {(i.code, i.page) for i in report.issues}
    assert ("wiki.broken_link", "a") in codes
    assert ("wiki.rule_violation", "decisions/c") in codes
    assert report.pages == 3
    assert sum(report.counts.values()) == len(report.issues)
    assert "secret" not in report.model_dump_json()


def test_graph_scheme_node_has_scheme_target() -> None:
    syntax = compile_syntax(
        effective_syntax(
            rules=[
                (
                    "r",
                    {
                        "schemes": [
                            {"prefix": "run:", "target": {"role": "runs", "query": "tab={value}"}}
                        ]
                    },
                )
            ]
        )
    )
    index = _index({"a": "[[run:abc]] [[run:]] [[없음]] [[b]]", "b": ""}, syntax)
    nodes = {n.path: n for n in neighborhood(index, "a", 1).nodes}
    target = nodes["run:abc"].scheme_target
    assert target is not None
    assert (target.role, target.id_from, target.query) == ("runs", "abc", "tab=abc")
    assert nodes["run:"].scheme == "run:"
    assert nodes["run:"].scheme_target is None  # 접두 뒤가 비면 열 항목이 없다
    assert nodes["없음"].scheme_target is None
    assert nodes["b"].scheme_target is None
    # 전체 보기도 같다
    full = {n.path: n for n in neighborhood(index).nodes}
    assert full["run:abc"].scheme_target == target
