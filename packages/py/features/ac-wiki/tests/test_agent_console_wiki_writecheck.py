"""쓰기 판단·비밀 검사·점검(7R.8, design §7R.1.1·§7R.18 Q18)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_console_contracts.wiki import WikiAuthor, WikiRulesDefinition
from agent_console_wiki import (
    InMemoryWikiHistory,
    PageTimes,
    RulesDocument,
    WikiSecretPolicy,
    build_index,
    check_write,
    compile_syntax,
    effective_syntax,
    lint,
    merge_rules,
    parse_page,
    write_subject,
)
from agent_console_wiki.testing import WikiHistoryContractTests

AGENT = WikiAuthor(kind="agent", agent_id="writer", run_id="r1")
USER = WikiAuthor(kind="user")
SYNTAX = compile_syntax(effective_syntax())


def _merged(**body: Any) -> Any:
    rules = WikiRulesDefinition.model_validate(
        {"kind": "wiki-rules", "id": "r", "name": "r", **body}
    )
    return merge_rules(["r"], [RulesDocument("r", rules)])


RULES = _merged(
    write_rules=[
        {
            "id": "no-temp",
            "applies_to": ["**"],
            "deny_patterns": [r"(?i)\bTODO\b"],
            "action": "reject",
            "message": "임시 메모 금지",
        },
        {
            "id": "agents-cannot-delete",
            "when": {
                "all": [
                    {"path": "/change/op", "op": "eq", "value": "delete"},
                    {"path": "/author/kind", "op": "eq", "value": "agent"},
                ]
            },
            "action": "reject",
            "message": "에이전트는 지울 수 없음",
        },
        {
            "id": "needs-source",
            "applies_to": ["decisions/**"],
            "require": {"all": [{"path": "/page/front_matter/source", "op": "exists"}]},
            "action": "warn",
            "message": "근거를 적어 주세요",
        },
        {"id": "odd", "applies_to": ["odd/**"], "action": "shout", "message": "이상"},
    ],
    lint_rules=[
        {
            "id": "stale",
            "when": {"all": [{"path": "/idle_days", "op": "gte", "value": 90}]},
            "severity": "info",
            "message": "오래됨",
        }
    ],
)


def _subject(path: str, text: str, op: str = "update", author: WikiAuthor = USER) -> dict[str, Any]:
    page = parse_page(path, text, SYNTAX)
    facts = {
        "path": path,
        "title": page.title,
        "tags": page.tags,
        "aliases": page.aliases,
        "front_matter": page.front_matter,
        "bytes": page.bytes,
        "links_out": 0,
        "broken_links": 0,
    }
    return write_subject(op=op, author=author, page=facts, before=None)


def test_deny_pattern_rejects_with_line_numbers() -> None:
    text = "# 제목\n괜찮음\n할 일: todo 하나\n\nTODO 둘\n"
    decision = check_write(RULES, _subject("notes/a", text), content=text)
    assert decision.rejected
    (issue,) = decision.rejections
    assert (issue.code, issue.rule_id, issue.line) == ("wiki.rule_rejected", "no-temp", 3)
    assert issue.details["lines"] == [3, 5]
    assert decision.results[0].lines == [3, 5]
    assert "todo" not in issue.model_dump_json().lower().replace("no-temp", "")


def test_agent_delete_rejected_but_user_delete_allowed() -> None:
    text = "TODO 남은 페이지"
    agent = check_write(RULES, _subject("a", text, "delete", AGENT), content="")
    assert [i.rule_id for i in agent.rejections] == ["agents-cannot-delete"]
    user = check_write(RULES, _subject("a", text, "delete", USER), content="")
    assert not user.rejected
    assert user.issues == []  # 지우기에는 금지 패턴·require를 보지 않는다


def test_require_warns_only_in_scope_and_unknown_action() -> None:
    no_source = "---\ntitle: 결정\n---\n본문"
    warn = check_write(RULES, _subject("decisions/x", no_source), content=no_source)
    assert not warn.rejected
    assert [(i.code, i.rule_id) for i in warn.issues] == [("wiki.rule_warning", "needs-source")]
    with_source = "---\nsource: 회의\n---\n본문"
    assert (
        check_write(RULES, _subject("decisions/x", with_source), content=with_source).issues == []
    )
    assert check_write(RULES, _subject("notes/x", no_source), content=no_source).issues == []
    odd = check_write(RULES, _subject("odd/x", "a"), content="a")
    assert not odd.rejected
    assert [i.code for i in odd.issues] == ["wiki.rule_warning", "wiki.unknown_action"]
    assert odd.results[0].action == "warn"


def test_secret_policy_per_author_kind() -> None:
    text = "설정\nAPI_KEY=sk-abcdefghijklmnop1234\n"
    policy = WikiSecretPolicy()  # 계약 기본값: user warn, agent reject
    agent = policy.check(text, "agent", page="p")
    assert agent.rejected
    assert agent.issues[0].code == "wiki.secret_rejected"
    assert agent.issues[0].details["lines"] == [2]
    assert "sk-abc" not in agent.issues[0].model_dump_json()
    user = policy.check(text, "user")
    assert not user.rejected
    assert user.issues[0].code == "wiki.secret_suspect"
    assert policy.check(text, "system").issues[0].code == "wiki.secret_suspect"  # 없는 종류 = user
    off = WikiSecretPolicy(modes={"user": "off"})
    assert off.check(text, "agent").issues == []
    assert policy.check("평범한 글", "agent").issues == []
    assert "sk-abc" not in policy.redact(text)


def _index(files: dict[str, str], home: str | None = None) -> Any:
    return build_index([parse_page(p, t, SYNTAX) for p, t in files.items()], SYNTAX, home=home)


def test_lint_builtin_rules_and_write_rule_violation() -> None:
    files = {
        "home": "# 시작\n[[a]] [[없음]]\n",
        "a": "# 같은 제목\n[[home]]\n",
        "b": "# 같은 제목\n두 번째 줄\nTODO 직접 고친 메모\n",
    }
    index = _index(files, home="home")
    times = {"a": PageTimes(created_at=0.0, updated_at=0.0, updated_by=AGENT)}
    report = lint(index, RULES, now=100 * 86400.0, times=times, read=files.get)
    found = sorted((i.code, i.page, i.line) for i in report.issues)
    assert ("wiki.broken_link", "home", 2) in found
    assert ("wiki.orphan", "b", None) in found
    assert ("wiki.duplicate_title", "a", None) in found
    assert ("wiki.duplicate_title", "b", None) in found
    assert ("wiki.lint_rule", "a", None) in found  # idle_days 100 ≥ 90
    assert ("wiki.rule_violation", "b", 3) in found
    violation = next(i for i in report.issues if i.code == "wiki.rule_violation")
    assert violation.severity == "error"
    assert violation.rule_id == "no-temp"
    assert report.pages == 3
    assert report.generated_at == 100 * 86400.0
    assert sum(report.counts.values()) == len(report.issues)


def test_lint_builtin_off_and_write_rules_off() -> None:
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
                                "duplicate_title": None,
                            },
                            "write_rules": False,
                        }
                    },
                )
            ]
        )
    )
    files = {"a": "[[없음]]\nTODO\n", "b": "# a\n"}
    index = build_index([parse_page(p, t, syntax) for p, t in files.items()], syntax)
    assert lint(index, RULES, now=0.0, read=files.get).issues == []


class TestInMemoryHistory(WikiHistoryContractTests):
    def make_history(self, tmp_path: Path) -> InMemoryWikiHistory:
        return InMemoryWikiHistory()
