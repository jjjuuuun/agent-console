"""계약 0.14.1(7R.13·7R.17 계약 후속): `common` 1.11.0, `wiki` 1.1.0.

- `WikiSettings.secret_scan` 기본값에 `system: reject`(보안 강화 — 위키 고치기 노드가 에이전트
  출력을 옮겨 쓸 때 에이전트 직접 쓰기보다 느슨하지 않다). 스키마 기본값도 같다.
- 문서 상수 `KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE`(스키마 `x-constants`에도 나온다).
- `WikiInfo.writable`은 선택(null 기본)이고 0.14.0 응답이 그대로 읽힌다.
- 루트 공개 별칭 `Slug`가 계약 id 모양 그대로 검증한다.
"""

import pytest
from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    KnownIssueCodes,
    Slug,
    wiki,
)
from agent_console_contracts.schema import build_schema

LIMITS = {"max_page_bytes": 1, "max_pages": 1, "graph_max_nodes": 1}


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_contracts_version_is_at_least_0_14_1() -> None:
    """0.14.1에서 정한 버전 이상이다(정확한 지금 값은 0.14.8 테스트가 고정한다)."""
    assert _ver(CONTRACTS_VERSION) >= (0, 14, 1)
    assert build_schema()["x-constants"]["CONTRACTS_VERSION"] == CONTRACTS_VERSION
    v0141 = {
        "common": "1.11.0",
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
        "wiki": "1.1.0",
        "modules": "1.5.0",
    }
    assert set(CONTRACT_VERSIONS) == set(v0141)
    for sub, version in v0141.items():
        assert _ver(CONTRACT_VERSIONS[sub]) >= _ver(version), sub


def test_secret_scan_default_rejects_system_writes() -> None:
    expected = {"user": "warn", "agent": "reject", "system": "reject"}
    assert wiki.WikiSettings().secret_scan == expected
    assert wiki.WikiSettings.model_validate({}).secret_scan == expected
    prop = build_schema()["$defs"]["WikiSettings"]["properties"]["secret_scan"]
    assert prop["default"] == expected
    assert all(ex.get("system") == "reject" for ex in prop["examples"])
    # 사용자가 적은 값은 그대로(기본값과 합치지 않는다 — 없는 쪽은 user 값을 따른다)
    assert wiki.WikiSettings.model_validate({"secret_scan": {"user": "off"}}).secret_scan == {
        "user": "off"
    }
    # 기본값은 인스턴스마다 새 dict다
    a, b = wiki.WikiSettings(), wiki.WikiSettings()
    a.secret_scan["system"] = "off"
    assert b.secret_scan["system"] == "reject"


def test_wiki_update_unavailable_issue_code() -> None:
    assert KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE == "wiki.update_unavailable"
    known = build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]
    assert known["WIKI_UPDATE_UNAVAILABLE"] == "wiki.update_unavailable"


def test_wiki_info_writable_is_optional() -> None:
    old = wiki.WikiInfo.model_validate({"limits": LIMITS})
    assert old.writable is None
    ro = wiki.WikiInfo.model_validate({"limits": LIMITS, "writable": False})
    assert ro.writable is False
    assert ro.model_dump(mode="json")["writable"] is False
    prop = build_schema()["$defs"]["WikiInfo"]["properties"]["writable"]
    assert prop.get("default") is None
    assert "writable" not in build_schema()["$defs"]["WikiInfo"].get("required", [])


class _UsesSlug(BaseModel):
    id: Slug


@pytest.mark.parametrize("value", ["a", "A-1_b", "x" * 128])
def test_slug_alias_accepts_ids(value: str) -> None:
    assert _UsesSlug(id=value).id == value


@pytest.mark.parametrize("value", ["", "-a", "_a", "a b", "a/b", "x" * 129, "가"])
def test_slug_alias_rejects_other_shapes(value: str) -> None:
    with pytest.raises(ValidationError):
        _UsesSlug(id=value)


def test_slug_schema_pattern() -> None:
    schema = _UsesSlug.model_json_schema()["properties"]["id"]
    assert schema["pattern"] == r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
