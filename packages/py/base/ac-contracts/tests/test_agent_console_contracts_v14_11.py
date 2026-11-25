"""계약 0.14.11(FU.17, 더하기만): `common` 1.16.0.

- 문서 상수 `KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE`(`wiki.unknown_title_source`, warning) —
  위키 문법 `title_sources`의 모르는 값.
- 문서 상수 `KnownIssueCodes.WIKI_REDACTED_CONTENT`(`wiki.redacted_content`) — 읽을 때 가린 비밀
  자리 표시가 든 본문 쓰기 거부 사유. 이벤트 상태 `WikiEventStatus`는 넓히지 않는다
  (`secret_rejected` + 사유 코드).
"""

from typing import get_args

from agent_console_contracts import CONTRACT_VERSIONS, CONTRACTS_VERSION, KnownIssueCodes
from agent_console_contracts.schema import build_schema
from agent_console_contracts.wiki import WikiEventStatus


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_11() -> None:
    """0.14.11에서 정한 버전 이상이다(정확한 지금 값은 0.15.0 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 11)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v01411 = {
        "common": "1.16.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "3.7.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.2.0",
        "sdd": "1.3.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v01411)
    for sub, version in v01411.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_new_wiki_issue_codes() -> None:
    assert KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE == "wiki.unknown_title_source"
    assert KnownIssueCodes.WIKI_REDACTED_CONTENT == "wiki.redacted_content"


def test_codes_are_exported_to_schema_constants() -> None:
    table = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    assert table["WIKI_UNKNOWN_TITLE_SOURCE"] == "wiki.unknown_title_source"
    assert table["WIKI_REDACTED_CONTENT"] == "wiki.redacted_content"


def test_event_status_stays_closed() -> None:
    """가린 본문 거부는 새 이벤트 상태가 아니라 `secret_rejected` + 사유 코드다."""
    statuses = get_args(WikiEventStatus)
    assert "secret_rejected" in statuses
    assert "redacted_content" not in statuses
