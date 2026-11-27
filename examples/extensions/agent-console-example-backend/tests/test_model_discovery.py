"""계정 모델 조회(X54) 예제: ``models_file``이 있을 때만 능력을 선언하고, 파일 목록을 준다.

서버와 같은 공용 서비스(``BackendModelCatalogService``)로 설정 목록과 합치는 것까지 본다.
모델 id는 이 테스트가 정한 임의 값이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_console_example_backend import MODELS_FILE_MISSING, ScriptedBackend
from agent_console_runtime import (
    BackendCheckContext,
    BackendHostContext,
    BackendModelCatalogService,
    ModelDiscoveryReasons,
    SecretResolver,
    supports_model_discovery,
)

CTX = BackendCheckContext("example.scripted")


def configured(options: dict[str, object], workspace: Path | None = None) -> ScriptedBackend:
    host = BackendHostContext(workspace_dir=workspace) if workspace is not None else None
    return ScriptedBackend.from_options(options, secrets=SecretResolver([]), environ={}, host=host)


def test_capability_only_with_models_file(tmp_path: Path) -> None:
    assert not supports_model_discovery(configured({}))
    backend = configured({"models_file": "models.json"}, workspace=tmp_path)
    assert backend.descriptor.capabilities.model_discovery is True
    assert supports_model_discovery(backend)
    with pytest.raises(ValueError, match="models_file"):
        configured({"models_file": "models.json"})  # 상대 경로인데 workspace 없음


async def test_success_and_merge_with_configured(tmp_path: Path) -> None:
    (tmp_path / "models.json").write_text(
        json.dumps([{"id": "zz-both", "title": "Gateway"}, {"id": "zz-file"}, {"title": "no id"}]),
        encoding="utf-8",
    )
    backend = configured(
        {"models": [{"id": "zz-both", "title": "Mine"}], "models_file": "models.json"},
        workspace=tmp_path,
    )
    result = await backend.discover_models(CTX, 5.0)
    assert result.ok
    service = BackendModelCatalogService(lambda: {"example.scripted": backend})
    catalog = await service.catalog("example.scripted")
    assert catalog.discovery.state == "ok"
    assert [(m.id, m.title, m.sources) for m in catalog.models] == [
        ("zz-both", "Mine", ["config", "discovered"]),
        ("zz-file", None, ["discovered"]),
    ]


async def test_missing_and_invalid_file(tmp_path: Path) -> None:
    backend = configured({"models_file": str(tmp_path / "absent.json")})
    missing = await backend.discover_models(CTX, 5.0)
    assert (missing.ok, missing.reason) == (False, MODELS_FILE_MISSING)
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    bad = configured({"models_file": str(tmp_path / "bad.json")})
    invalid = await bad.discover_models(CTX, 5.0)
    assert invalid.reason == ModelDiscoveryReasons.INVALID_RESPONSE
    service = BackendModelCatalogService(lambda: {"example.scripted": backend})
    catalog = await service.catalog("example.scripted")
    assert catalog.discovery.state == "failed"
    assert catalog.discovery.issues[0].details == {
        "backend_id": "example.scripted",
        "reason": MODELS_FILE_MISSING,
    }
