"""계약 0.14.6(요청 11/07 후속, 더하기만): `projects` 3.6.0.

- `CopyItem.version` — 항목 버전(종류 공통 삭제의 `If-Match`, 선택, 기본 null — 0.14.5 응답이
  그대로 읽힌다).
"""

from agent_console_contracts import CONTRACT_VERSIONS, CONTRACTS_VERSION, CopyItem
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_6() -> None:
    """0.14.6에서 정한 버전 이상이다(정확한 지금 값은 0.14.7 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 6)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0146 = {
        "common": "1.12.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.6.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0146)
    for sub, version in v0146.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_old_item_still_reads() -> None:
    item = CopyItem.model_validate({"kind": "agent", "id": "rev"})
    assert item.version is None


def test_version_round_trip() -> None:
    item = CopyItem(kind="agent", id="rev", version="abc123")
    assert CopyItem.model_validate(item.model_dump(mode="json")).version == "abc123"
