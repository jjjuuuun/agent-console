"""MD.4: fake-agent 계정 모델 조회 흉내(X54) — 성공·실패·지연·능력 없음.

모델 id는 이 테스트가 정한 임의 값이다(모델 이름 표를 두지 않는다).
"""

from __future__ import annotations

import pytest

from agent_console_backend_fake_agent import (
    FAKE_DISCOVERY_UNSUPPORTED,
    FakeBackend,
    FakeInstallOptions,
)
from agent_console_runtime import (
    BackendCheckContext,
    BackendModelCatalogService,
    SecretResolver,
    supports_model_discovery,
)

CTX = BackendCheckContext("fake-agent")


def _make(options: dict[str, object]) -> FakeBackend:
    return FakeBackend.from_options(options, secrets=SecretResolver(), environ={})


def test_no_discovery_settings_means_no_capability() -> None:
    backend = _make({})
    assert backend.descriptor.capabilities.model_discovery is False
    assert not supports_model_discovery(backend)
    assert FakeInstallOptions().discovered_models is None


async def test_success_lists_configured_discovery() -> None:
    backend = _make({"discovered_models": [{"id": "zz-d1", "title": "D1"}, {"id": "zz-d2"}]})
    assert supports_model_discovery(backend)
    result = await backend.discover_models(CTX, 5.0)
    assert result.ok
    assert [m.id for m in result.models] == ["zz-d1", "zz-d2"]  # type: ignore[union-attr]
    assert backend.discovery_calls == 1


async def test_failure_reason() -> None:
    backend = _make({"discovery_failure": "zz-reason"})
    assert backend.descriptor.capabilities.model_discovery is True
    result = await backend.discover_models(CTX, 5.0)
    assert not result.ok
    assert result.reason == "zz-reason"
    assert not result.unsupported


async def test_unsupported_failure() -> None:
    backend = _make({"discovery_failure": FAKE_DISCOVERY_UNSUPPORTED})
    service = BackendModelCatalogService(lambda: {"fake-agent": backend})
    catalog = await service.catalog("fake-agent")
    assert catalog.discovery.state == "unsupported"


async def test_delay_hits_service_timeout() -> None:
    backend = _make({"discovered_models": [{"id": "zz-d1"}], "discovery_delay_s": 1.0})
    service = BackendModelCatalogService(lambda: {"fake-agent": backend}, timeout_s=0.01)
    catalog = await service.catalog("fake-agent")
    assert catalog.discovery.state == "failed"
    assert catalog.discovery.issues[0].details["reason"] == "timeout"


async def test_catalog_merges_with_configured_models() -> None:
    backend = _make(
        {
            "models": [{"id": "zz-c1"}, {"id": "zz-both", "title": "Mine"}],
            "discovered_models": [{"id": "zz-both", "title": "Theirs"}, {"id": "zz-d1"}],
        }
    )
    service = BackendModelCatalogService(lambda: {"fake-agent": backend})
    catalog = await service.catalog("fake-agent")
    assert [(m.id, m.title, m.sources) for m in catalog.models] == [
        ("zz-c1", None, ["config"]),
        ("zz-both", "Mine", ["config", "discovered"]),
        ("zz-d1", None, ["discovered"]),
    ]


def test_invalid_settings_rejected() -> None:
    with pytest.raises(ValueError, match="discovery_delay_s"):
        _make({"discovery_delay_s": -1})
