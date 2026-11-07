"""계약 0.14.5(요청 11/07 후속, 더하기만): `projects` 3.5.0.

- `CopyKindInfo.deletable` — 종류 공통 항목 삭제 경로로 지울 수 있는 종류(선택, 기본 false — 0.14.4
  응답이 그대로 읽힌다).
"""

from agent_console_contracts import CONTRACT_VERSIONS, CONTRACTS_VERSION, CopyKindInfo
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_5() -> None:
    """0.14.5에서 정한 버전 이상이다(정확한 지금 값은 0.14.8 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 5)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0145 = {
        "common": "1.12.0",
        "resources": "1.1.0",
        "logs": "1.2.0",
        "definitions": "1.7.0",
        "runs": "1.8.0",
        "usage": "1.1.0",
        "projects": "3.5.0",
        "chat": "1.3.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.1.0",
        "sdd": "1.2.0",
        "wiki": "1.2.0",
        "modules": "1.6.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0145)
    for sub, version in v0145.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_old_kind_info_still_reads() -> None:
    info = CopyKindInfo.model_validate({"kind": "agent", "library": True, "portable": True})
    assert info.deletable is False


def test_deletable_round_trip() -> None:
    info = CopyKindInfo(kind="wiki", library=False, portable=True, deletable=True)
    assert CopyKindInfo.model_validate(info.model_dump(mode="json")).deletable is True
