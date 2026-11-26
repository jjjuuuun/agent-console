"""계약 0.14.10(FU.13, 더하기만): `projects` 3.7.0.

- `CopyItemReferences` — 종류 공통 거꾸로 참조 `GET /projects/copy/items/{kind}/{id}/references`
  응답(같은 공간에서 이 항목을 쓰는 정의, 검사 여부 `checked`, 이슈 `warnings`).
"""

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    CopyItem,
    CopyItemReferences,
    KnownIssueCodes,
)
from agent_console_contracts.projects import CopyItemReferences as SubpathCopyItemReferences
from agent_console_contracts.schema import build_schema


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_10() -> None:
    """0.14.10에서 정한 버전 이상이다(정확한 지금 값은 0.15.0 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 10)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v01410 = {
        "common": "1.15.0",
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
    assert set(v01410) <= set(CONTRACT_VERSIONS)  # 0.16.0: 하위 모듈 i18n이 늘었다
    for sub, version in v01410.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_model_is_exported_from_subpath_and_schema() -> None:
    assert SubpathCopyItemReferences is CopyItemReferences
    defs = build_schema()["$defs"]
    assert "CopyItemReferences" in defs
    assert defs["CopyItemReferences"].get("required", []) == []


def test_empty_body_means_checked_and_nobody_uses_it() -> None:
    body = CopyItemReferences.model_validate({})
    assert body.items == []
    assert body.checked is True
    assert body.warnings == []


def test_round_trip_keeps_open_kind_names() -> None:
    body = CopyItemReferences(
        items=[CopyItem(kind="any-plugin-kind", id="t", name="T", version="v1")],
        checked=False,
        warnings=[],
    )
    again = CopyItemReferences.model_validate_json(body.model_dump_json())
    assert again == body
    assert again.items[0].kind == "any-plugin-kind"


def test_unavailable_issue_code_is_documented() -> None:
    assert KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE == "project.references_unavailable"
