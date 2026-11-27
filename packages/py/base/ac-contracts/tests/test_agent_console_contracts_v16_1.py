"""계약 0.16.1(MD.1, design §1.1-MB MD-8): 모델 계정 조회 — 더하기만.

- `runs` 1.10.0: `ModelInfo.sources`, `BackendCapabilities.model_discovery`, `BackendModelCatalog`·
  `ModelDiscoveryInfo`(`GET /backends/{id}/model-catalog`).
- `common` 2.2.0: 이슈 코드 `KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED`(+ `locales` 문구).
- 옛 응답(`sources`·`model_discovery` 없음)도 그대로 읽힌다.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import pytest
from pydantic import ValidationError

import agent_console_contracts as contracts
from agent_console_contracts import (
    CONTRACT_VERSIONS,
    CONTRACTS_VERSION,
    BackendCapabilities,
    BackendDescriptor,
    BackendModelCatalog,
    Issue,
    KnownIssueCodes,
    ModelDiscoveryInfo,
    ModelInfo,
)
from agent_console_contracts.schema import build_schema


def test_contracts_version_is_0_16_1() -> None:
    assert CONTRACTS_VERSION == "0.16.1"
    constants = build_schema()["x-constants"]
    assert constants["CONTRACTS_VERSION"] == "0.16.1"
    assert CONTRACT_VERSIONS["runs"] == "1.10.0"
    assert CONTRACT_VERSIONS["common"] == "2.2.0"
    assert constants["CONTRACT_VERSIONS"] == CONTRACT_VERSIONS


# ---------------------------------------------------------------- 옛 응답


def test_old_model_info_without_sources_reads() -> None:
    old: dict[str, Any] = {"id": "zz-model-1", "title": "Zz", "attributes": {"k": 1}}
    info = ModelInfo.model_validate(old)
    assert info.sources == []
    assert "sources" not in ModelInfo.model_json_schema().get("required", [])


def test_old_backend_descriptor_without_model_discovery_reads() -> None:
    old = {"id": "zz-backend", "title": "Zz", "capabilities": {"streaming": True, "status": True}}
    descriptor = BackendDescriptor.model_validate(old)
    assert descriptor.capabilities.model_discovery is False
    assert BackendCapabilities().model_discovery is False


# ---------------------------------------------------------------- 새 필드


def test_model_info_sources_values() -> None:
    info = ModelInfo(id="zz-1", sources=["config", "discovered"])
    assert info.model_dump(mode="json")["sources"] == ["config", "discovered"]
    with pytest.raises(ValidationError):
        ModelInfo.model_validate({"id": "zz-1", "sources": ["somewhere"]})


def test_catalog_shape_and_states() -> None:
    issue = Issue(
        severity="warning",
        code=KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED,
        message="x",
        details={"backend_id": "zz-backend", "reason": "timeout"},
    )
    catalog = BackendModelCatalog(
        backend_id="zz-backend",
        models=[ModelInfo(id="zz-1", sources=["config"])],
        discovery=ModelDiscoveryInfo(state="failed", issues=[issue]),
    )
    dumped = catalog.model_dump(mode="json")
    assert dumped["discovery"]["state"] == "failed"
    assert dumped["discovery"]["fetched_at"] is None
    assert BackendModelCatalog.model_validate(dumped) == catalog
    for state in ("ok", "stale", "failed", "disabled", "unsupported"):
        assert ModelDiscoveryInfo.model_validate({"state": state}).state == state
    with pytest.raises(ValidationError):
        ModelDiscoveryInfo.model_validate({"state": "zz-unknown"})
    with pytest.raises(ValidationError):  # discovery는 필수
        BackendModelCatalog.model_validate({"backend_id": "zz-backend", "models": []})


def test_new_models_live_in_runs_submodule() -> None:
    schema = build_schema()
    runs = set(schema["x-modules"]["runs"])
    assert {"BackendModelCatalog", "ModelDiscoveryInfo"} <= runs
    assert "model_discovery" in schema["$defs"]["BackendCapabilities"]["properties"]
    assert "sources" in schema["$defs"]["ModelInfo"]["properties"]
    for name in ("BackendModelCatalog", "ModelDiscoveryInfo", "ModelSource", "ModelDiscoveryState"):
        assert name in contracts.__all__, name


def test_issue_code_constant_and_messages() -> None:
    code = "backend.model_discovery_failed"
    assert code == KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED
    assert build_schema()["x-constants"]["KNOWN_ISSUE_CODES"]["BACKEND_MODEL_DISCOVERY_FAILED"] == (
        code
    )
    folder = resources.files("agent_console_contracts") / "locales"
    for lang in ("ko", "en"):
        codes = json.loads((folder / f"{lang}.json").read_text(encoding="utf-8"))["codes"]
        message = codes[code]
        assert "{backend_id}" in message
        assert "{reason}" in message
