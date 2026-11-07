"""계약 0.14.2(7R.19·7R.20·7R.21 서버 후속, 더하기만): `common` 1.12.0, `wiki` 1.2.0.

- `WikiInfo.rules_kind`, `WikiRuleEntry.applies_to`·`path`·`title`, `WikiLintReport.partial`·
  `skipped`·`enabled_checks`, `WikiGraphNode.scheme_target` — 모두 선택이고 0.14.1 응답이 그대로
  읽힌다.
- 문서 상수 `KnownIssueCodes.WIKI_LINT_FAILED`, `KnownWikiLintChecks`.
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    KnownIssueCodes,
    KnownWikiLintChecks,
    wiki,
)
from agent_console_contracts.schema import build_schema

LIMITS = {"max_page_bytes": 1, "max_pages": 1, "graph_max_nodes": 1}


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_2() -> None:
    """0.14.2에서 정한 버전 이상이다(정확한 지금 값은 0.14.8 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 2)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0142 = {
        "common": "1.12.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.3.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.5.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0142)
    for sub, version in v0142.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_old_responses_still_read() -> None:
    info = wiki.WikiInfo.model_validate({"limits": LIMITS})
    assert info.rules_kind is None
    entry = wiki.WikiRuleEntry.model_validate({"kind": "write", "id": "a", "rule_id": "r"})
    assert (entry.applies_to, entry.path, entry.title) == (None, None, None)
    report = wiki.WikiLintReport.model_validate({"issues": [], "pages": 2})
    assert report.partial is False
    assert report.skipped == []
    assert report.enabled_checks is None
    node = wiki.WikiGraphNode.model_validate({"path": "run:abc", "scheme": "run"})
    assert node.scheme_target is None


def test_new_fields_round_trip() -> None:
    info = wiki.WikiInfo(limits=wiki.WikiLimits(**LIMITS), rules_kind="wiki-rules")
    assert info.model_dump(mode="json")["rules_kind"] == "wiki-rules"
    entry = wiki.WikiRuleEntry(
        kind="template", id="note", rule_id="r", path="notes/{slug}", title="메모"
    )
    assert entry.model_dump(mode="json", exclude_none=True)["path"] == "notes/{slug}"
    write = wiki.WikiRuleEntry(kind="write", id="w", rule_id="r", applies_to=[])
    assert write.model_dump(mode="json")["applies_to"] == []
    report = wiki.WikiLintReport(
        partial=True,
        skipped=["a"],
        enabled_checks=["orphan", KnownWikiLintChecks.WRITE_RULES],
    )
    again = wiki.WikiLintReport.model_validate(report.model_dump(mode="json"))
    assert again == report
    node = wiki.WikiGraphNode.model_validate(
        {"path": "run:abc", "scheme": "run", "scheme_target": {"role": "run", "id_from": "abc"}}
    )
    assert node.scheme_target is not None
    assert node.scheme_target.id_from == "abc"


def test_constants_in_schema() -> None:
    assert KnownIssueCodes.WIKI_LINT_FAILED == "wiki.lint_failed"
    assert KnownWikiLintChecks.LINT_RULES == "lint_rules"
    constants = build_schema()["x-constants"]
    assert constants["KNOWN_WIKI_LINT_CHECKS"] == {
        "LINT_RULES": "lint_rules",
        "WRITE_RULES": "write_rules",
    }
    defs = build_schema()["$defs"]
    assert "scheme_target" in defs["WikiGraphNode"]["properties"]
    assert {"partial", "skipped", "enabled_checks"} <= set(defs["WikiLintReport"]["properties"])
    assert {"applies_to", "path", "title"} <= set(defs["WikiRuleEntry"]["properties"])
    assert "rules_kind" in defs["WikiInfo"]["properties"]
