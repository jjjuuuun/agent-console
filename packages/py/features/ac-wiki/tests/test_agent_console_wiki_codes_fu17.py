"""FU.17: `WikiIssueCodes`는 계약 `KnownIssueCodes`(0.14.11, `common` 1.16.0)의 별칭이다."""

from typing import get_args

from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.wiki import WikiEventStatus
from agent_console_wiki import WikiIssueCodes, WikiRedactedContentError


def test_wiki_issue_codes_are_contract_aliases() -> None:
    assert WikiIssueCodes.UNKNOWN_TITLE_SOURCE == KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE
    assert WikiIssueCodes.REDACTED_CONTENT == KnownIssueCodes.WIKI_REDACTED_CONTENT
    assert WikiIssueCodes.UNKNOWN_TITLE_SOURCE == "wiki.unknown_title_source"
    assert WikiIssueCodes.REDACTED_CONTENT == "wiki.redacted_content"


def test_redacted_error_uses_contract_code() -> None:
    err = WikiRedactedContentError("a.md", [2])
    assert err.code == KnownIssueCodes.WIKI_REDACTED_CONTENT
    assert err.details == {"path": "a.md", "lines": [2]}


def test_event_status_vocabulary_is_not_widened() -> None:
    """이벤트 상태는 닫힌 어휘 그대로 — 가린 본문 거부는 `secret_rejected` + 사유 코드."""
    statuses = get_args(WikiEventStatus)
    assert "secret_rejected" in statuses
    assert "redacted_content" not in statuses
