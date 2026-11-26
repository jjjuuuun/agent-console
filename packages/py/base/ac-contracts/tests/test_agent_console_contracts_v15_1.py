"""계약 0.15.1(P1.5, 더하기만): `projects` 4.1.0, `sdd` 1.4.0.

- `CopyKindInfo.reserved_ids` — 종류별 id 예약어(정의 종류 데이터 `DefinitionKind.reserved_ids`).
- `SddInfo.reserved_template_ids` — 문서 틀 id 예약어(서버 경로 어휘).

둘 다 생략 = 빈 목록이라 옛 응답(필드 없음)이 그대로 읽힌다.
"""

from __future__ import annotations

from agent_console_contracts import CONTRACT_VERSIONS, CONTRACTS_VERSION
from agent_console_contracts.projects import CopyKindInfo
from agent_console_contracts.schema import build_schema
from agent_console_contracts.sdd import SddInfo


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contract_versions_are_at_least_0_15_1() -> None:
    """0.15.1(릴리스하지 않음, 0.16.0에 합침)에서 정한 하위 버전 이상이다.

    정확한 지금 값은 0.16.0 테스트가 고정한다.
    """
    assert _ver(CONTRACTS_VERSION) >= (0, 15, 1)
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0151 = {
        "common": "2.0.0",
        "resources": "1.1.0",
        "logs": "2.0.0",
        "definitions": "2.0.0",
        "runs": "1.9.0",
        "usage": "1.1.0",
        "projects": "4.1.0",
        "chat": "1.4.0",
        "exports": "1.0.0",
        "imports": "1.1.0",
        "architecture": "1.0.0",
        "memory": "1.3.0",
        "sdd": "1.4.0",
        "wiki": "1.3.0",
        "modules": "1.7.0",
    }
    assert set(v0151) <= set(CONTRACT_VERSIONS)
    for sub, version in v0151.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS


def test_copy_kind_info_reserved_ids_is_optional() -> None:
    old = CopyKindInfo.model_validate({"kind": "made-up-kind", "library": True, "portable": True})
    assert old.reserved_ids == []
    new = CopyKindInfo.model_validate(
        {"kind": "made-up-kind", "library": True, "portable": True, "reserved_ids": ["Zeta-Word"]}
    )
    assert new.reserved_ids == ["Zeta-Word"]
    assert new.model_dump(mode="json")["reserved_ids"] == ["Zeta-Word"]
    schema = build_schema()["$defs"]["CopyKindInfo"]
    assert schema["properties"]["reserved_ids"]["type"] == "array"
    assert "reserved_ids" not in schema.get("required", [])


def test_sdd_info_reserved_template_ids_is_optional() -> None:
    old = SddInfo.model_validate({"limits": {"max_bulk_start": 1, "max_tasks": 1}})
    assert old.reserved_template_ids == []
    new = SddInfo.model_validate(
        {"limits": {"max_bulk_start": 1, "max_tasks": 1}, "reserved_template_ids": ["omega"]}
    )
    assert new.reserved_template_ids == ["omega"]
    schema = build_schema()["$defs"]["SddInfo"]
    assert schema["properties"]["reserved_template_ids"]["type"] == "array"
    assert "reserved_template_ids" not in schema.get("required", [])
