"""백엔드 모델 계정 조회(X54)와 합치기·캐시 서비스(MD.2, design §1.1-MB MD-3·MD-6·MD-7·MD-9).

합치기 표, 캐시(가짜 시계: ttl 안 재조회 0, 실패 캐시, refresh, 동시 2요청 → 조회 1번, 낡은 목록
stale, invalidate), 능력 없음 = unsupported, 꺼짐 = disabled, 예외·시간 초과 = failed + 이슈,
길이 자르기, 비밀 가림, 로그 규칙. 모델 id는 테스트가 정한 임의 값이다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from agent_console_contracts import (
    BackendCapabilities,
    BackendDescriptor,
    KnownIssueCodes,
    ModelInfo,
)
from agent_console_runtime import (
    REDACTED,
    BackendCheckContext,
    BackendLoginService,
    BackendModelCatalogService,
    ExecutionBackend,
    ModelDiscoveryCapableBackend,
    ModelDiscoveryReasons,
    ModelDiscoveryResult,
    ModelListLimits,
    UnknownBackendError,
    merge_models,
    supports_model_discovery,
)

NOW = 1_700_000_000.0
SECRET = "zz-SECRET-value-123"


class Mono:
    """손으로 움직이는 monotonic 시계."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _descriptor(backend_id: str, *, discovery: bool) -> BackendDescriptor:
    return BackendDescriptor(
        id=backend_id,
        title=backend_id,
        capabilities=BackendCapabilities(model_discovery=discovery),
    )


class PlainBackend:
    """조회 능력 없는 백엔드(설정 목록만)."""

    def __init__(self, backend_id: str = "zz-plain", models: Sequence[ModelInfo] = ()) -> None:
        self.descriptor = _descriptor(backend_id, discovery=False)
        self.models = list(models)

    async def list_models(self) -> list[ModelInfo]:
        return list(self.models)

    async def run(self, req: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class DiscoveringBackend(PlainBackend):
    """조회 능력이 있는 가짜 백엔드(호출 수를 센다)."""

    def __init__(
        self,
        backend_id: str = "zz-disc",
        models: Sequence[ModelInfo] = (),
        *,
        found: Sequence[ModelInfo | Mapping[str, Any]] = (),
        declare: bool = True,
    ) -> None:
        super().__init__(backend_id, models)
        self.descriptor = _descriptor(backend_id, discovery=declare)
        self.found = list(found)
        self.calls = 0
        self.result: ModelDiscoveryResult | None = None
        self.fail: Exception | None = None
        self.gate: asyncio.Event | None = None
        self.delay = 0.0
        self.contexts: list[BackendCheckContext] = []

    async def discover_models(
        self, ctx: BackendCheckContext, timeout_s: float
    ) -> ModelDiscoveryResult:
        self.calls += 1
        self.contexts.append(ctx)
        if self.gate is not None:
            await self.gate.wait()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        if self.result is not None:
            return self.result
        return ModelDiscoveryResult(ok=True, models=list(self.found), method="zz-method")


def _service(*backends: ExecutionBackend, **kwargs: Any) -> tuple[BackendModelCatalogService, Mono]:
    mono = Mono()
    table = {b.descriptor.id: b for b in backends}
    service = BackendModelCatalogService(
        lambda: table, clock=lambda: NOW + mono.now, monotonic=mono, **kwargs
    )
    return service, mono


def _ids(models: Sequence[ModelInfo]) -> list[str]:
    return [m.id for m in models]


# ---------------------------------------------------------------- 합치기(MD-3)


def test_merge_config_only() -> None:
    merged = merge_models([ModelInfo(id="c-1"), ModelInfo(id="c-2")], [])
    assert _ids(merged) == ["c-1", "c-2"]
    assert all(m.sources == ["config"] for m in merged)


def test_merge_discovered_only() -> None:
    merged = merge_models([], [ModelInfo(id="d-2"), ModelInfo(id="d-1")])
    assert _ids(merged) == ["d-2", "d-1"]  # 백엔드가 준 순서
    assert all(m.sources == ["discovered"] for m in merged)


def test_merge_both_keeps_config_first_and_order() -> None:
    merged = merge_models(
        [ModelInfo(id="c-1"), ModelInfo(id="both")],
        [ModelInfo(id="d-1"), ModelInfo(id="both"), ModelInfo(id="d-2")],
    )
    assert _ids(merged) == ["c-1", "both", "d-1", "d-2"]
    assert [m.sources for m in merged] == [
        ["config"],
        ["config", "discovered"],
        ["discovered"],
        ["discovered"],
    ]


def test_merge_same_id_config_wins_when_filled() -> None:
    configured = [
        ModelInfo(id="x", title="Mine", description="", context_window=None, attributes={"a": 1})
    ]
    discovered = [
        ModelInfo(
            id="x", title="Theirs", description="from api", context_window=7, attributes={"a": 2}
        )
    ]
    (one,) = merge_models(configured, discovered)
    assert one.title == "Mine"
    assert one.description == "from api"  # 설정 쪽이 빈 문자열이면 조회 값
    assert one.context_window == 7
    assert one.attributes == {"a": 1}


def test_merge_attributes_merge_by_key() -> None:
    (one,) = merge_models(
        [ModelInfo(id="x", attributes={"mine": True, "shared": "config"})],
        [ModelInfo(id="x", attributes={"theirs": 1, "shared": "api"})],
    )
    assert one.attributes == {"theirs": 1, "shared": "config", "mine": True}


def test_merge_is_exact_and_pure() -> None:
    configured = [ModelInfo(id="alias", attributes={"k": [1]})]
    discovered = [ModelInfo(id="alias-full-id"), ModelInfo(id="alias-full-id")]
    merged = merge_models(configured, discovered)
    assert _ids(merged) == ["alias", "alias-full-id"]  # 별칭과 전체 id는 다른 모델, 중복은 하나
    merged[0].attributes["k"].append(2)
    assert configured[0].attributes == {"k": [1]}  # 입력을 바꾸지 않는다
    assert configured[0].sources == []


def test_merge_duplicate_config_ids_keep_first() -> None:
    merged = merge_models([ModelInfo(id="c", title="first"), ModelInfo(id="c", title="second")], [])
    assert [(m.id, m.title) for m in merged] == [("c", "first")]


# ---------------------------------------------------------------- 능력 판정


def test_supports_model_discovery_needs_declaration_and_method() -> None:
    assert supports_model_discovery(DiscoveringBackend())
    assert not supports_model_discovery(DiscoveringBackend(declare=False))
    assert not supports_model_discovery(PlainBackend())
    plain = PlainBackend()
    plain.descriptor = _descriptor("zz-plain", discovery=True)  # 선언만 하고 메서드 없음
    assert not supports_model_discovery(plain)
    assert isinstance(DiscoveringBackend(), ModelDiscoveryCapableBackend)


# ---------------------------------------------------------------- 상태


async def test_unsupported_backend_returns_config_list() -> None:
    service, _ = _service(PlainBackend(models=[ModelInfo(id="c-1")]))
    catalog = await service.catalog("zz-plain")
    assert catalog.discovery.state == "unsupported"
    assert _ids(catalog.models) == ["c-1"]
    assert catalog.models[0].sources == ["config"]
    assert catalog.discovery.issues == []


async def test_disabled_globally_and_per_backend() -> None:
    backend = DiscoveringBackend(models=[ModelInfo(id="c-1")], found=[ModelInfo(id="d-1")])
    for kwargs in ({"enabled": False}, {"disabled_backends": ["zz-disc"]}):
        service, _ = _service(backend, **kwargs)
        catalog = await service.catalog("zz-disc")
        assert catalog.discovery.state == "disabled"
        assert _ids(catalog.models) == ["c-1"]
    assert backend.calls == 0


async def test_unknown_backend_raises() -> None:
    service, _ = _service(PlainBackend())
    with pytest.raises(UnknownBackendError):
        await service.catalog("zz-missing")


async def test_ok_merges_with_config_even_when_config_is_empty() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1"), {"id": "d-2", "title": "Two"}])
    service, mono = _service(backend)
    catalog = await service.catalog("zz-disc")
    assert catalog.discovery.state == "ok"
    assert _ids(catalog.models) == ["d-1", "d-2"]
    assert catalog.discovery.fetched_at == NOW + mono.now
    assert catalog.discovery.expires_at == NOW + mono.now + 3600
    assert backend.contexts[0].backend_id == "zz-disc"
    assert await service.models("zz-disc") == catalog.models


async def test_backend_failure_is_failed_with_warning_issue() -> None:
    backend = DiscoveringBackend(models=[ModelInfo(id="c-1")])
    backend.result = ModelDiscoveryResult(ok=False, reason="zz-reason")
    service, _ = _service(backend)
    catalog = await service.catalog("zz-disc")
    assert catalog.discovery.state == "failed"
    assert _ids(catalog.models) == ["c-1"]
    (issue,) = catalog.discovery.issues
    assert issue.severity == "warning"
    assert issue.code == KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED
    assert issue.details == {"backend_id": "zz-disc", "reason": "zz-reason"}
    assert "zz-disc" in issue.message


async def test_backend_unsupported_result_is_unsupported_without_issue() -> None:
    backend = DiscoveringBackend()
    backend.result = ModelDiscoveryResult(
        ok=False, unsupported=True, reason=ModelDiscoveryReasons.CLI_NO_MODELS
    )
    service, _ = _service(backend)
    catalog = await service.catalog("zz-disc")
    assert catalog.discovery.state == "unsupported"
    assert catalog.discovery.issues == []


async def test_exception_and_timeout_become_failed(caplog: pytest.LogCaptureFixture) -> None:
    raising = DiscoveringBackend("zz-raise")
    raising.fail = RuntimeError(f"boom {SECRET}")
    slow = DiscoveringBackend("zz-slow")
    slow.delay = 1.0
    service, _ = _service(raising, slow, timeout_s=0.01)
    with caplog.at_level(logging.INFO, logger="agent_console_runtime.models"):
        failed = await service.catalog("zz-raise")
        timed = await service.catalog("zz-slow")
    assert failed.discovery.state == "failed"
    assert failed.discovery.issues[0].details["reason"] == ModelDiscoveryReasons.ERROR
    assert timed.discovery.issues[0].details["reason"] == ModelDiscoveryReasons.TIMEOUT
    assert SECRET not in caplog.text  # 예외 문장은 로그에 남지 않는다
    assert "RuntimeError" in caplog.text
    assert "state=failed" in caplog.text


async def test_invalid_return_type_is_invalid_response() -> None:
    backend = DiscoveringBackend()

    async def wrong(ctx: BackendCheckContext, timeout_s: float) -> Any:
        return ["not", "a", "result"]

    backend.discover_models = wrong  # type: ignore[method-assign]
    service, _ = _service(backend)
    catalog = await service.catalog("zz-disc")
    assert catalog.discovery.issues[0].details["reason"] == ModelDiscoveryReasons.INVALID_RESPONSE


# ---------------------------------------------------------------- 캐시(MD-6)


async def test_no_refetch_within_ttl_then_refetch_after() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1")])
    service, mono = _service(backend, ttl_s=10)
    await service.catalog("zz-disc")
    mono.now += 9
    again = await service.catalog("zz-disc")
    assert backend.calls == 1
    assert again.discovery.state == "ok"
    mono.now += 2  # ttl 지남 → 직전 목록을 stale로 주고 뒤에서 다시 조회
    stale = await service.catalog("zz-disc")
    assert stale.discovery.state == "stale"
    assert _ids(stale.models) == ["d-1"]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert backend.calls == 2
    fresh = await service.catalog("zz-disc")
    assert fresh.discovery.state == "ok"
    assert backend.calls == 2


async def test_zero_ttl_asks_every_request_and_waits() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1")])
    service, _ = _service(backend, ttl_s=0)
    first = await service.catalog("zz-disc")
    second = await service.catalog("zz-disc")
    assert (first.discovery.state, second.discovery.state) == ("ok", "ok")
    assert backend.calls == 2


async def test_failure_is_cached_for_failure_ttl() -> None:
    backend = DiscoveringBackend()
    backend.result = ModelDiscoveryResult(ok=False, reason="network")
    service, mono = _service(backend, failure_ttl_s=5)
    await service.catalog("zz-disc")
    mono.now += 4
    cached = await service.catalog("zz-disc")
    assert cached.discovery.state == "failed"
    assert backend.calls == 1
    mono.now += 2
    await service.catalog("zz-disc")
    assert backend.calls == 2


async def test_refresh_skips_cache() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1")])
    service, _ = _service(backend)
    await service.catalog("zz-disc")
    backend.found = [ModelInfo(id="d-2")]
    refreshed = await service.catalog("zz-disc", refresh=True)
    assert backend.calls == 2
    assert _ids(refreshed.models) == ["d-2"]


async def test_concurrent_requests_share_one_lookup() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1")])
    backend.gate = asyncio.Event()
    service, _ = _service(backend)
    first = asyncio.ensure_future(service.catalog("zz-disc"))
    second = asyncio.ensure_future(service.catalog("zz-disc", refresh=True))
    await asyncio.sleep(0)
    backend.gate.set()
    a, b = await asyncio.gather(first, second)
    assert backend.calls == 1
    assert a == b


async def test_failed_refetch_keeps_last_success_as_stale() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="d-1")])
    service, mono = _service(backend, ttl_s=10, failure_ttl_s=5)
    await service.catalog("zz-disc")
    backend.result = ModelDiscoveryResult(ok=False, reason="network")
    stale = await service.catalog("zz-disc", refresh=True)
    assert stale.discovery.state == "stale"
    assert _ids(stale.models) == ["d-1"]
    assert stale.discovery.issues[0].details["reason"] == "network"
    assert stale.discovery.fetched_at is not None
    mono.now += 1  # 실패 캐시 안: 다시 부르지 않고 stale
    again = await service.catalog("zz-disc")
    assert again.discovery.state == "stale"
    assert backend.calls == 2


async def test_invalidate_drops_cache_and_inflight_result() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="old")])
    service, _ = _service(backend)
    await service.catalog("zz-disc")
    service.invalidate("zz-disc")
    backend.found = [ModelInfo(id="new")]
    after = await service.catalog("zz-disc")
    assert _ids(after.models) == ["new"]
    assert backend.calls == 2
    # 진행 중인 조회 결과는 비운 뒤 캐시에 남지 않는다
    backend.gate = asyncio.Event()
    running = asyncio.ensure_future(service.catalog("zz-disc", refresh=True))
    await asyncio.sleep(0)
    service.invalidate()
    backend.gate.set()
    await running
    backend.gate = None
    await service.catalog("zz-disc")
    assert backend.calls == 4


async def test_aclose_cancels_inflight() -> None:
    backend = DiscoveringBackend()
    backend.gate = asyncio.Event()
    service, _ = _service(backend)
    running = asyncio.ensure_future(service.catalog("zz-disc"))
    await asyncio.sleep(0)
    await service.aclose()
    with pytest.raises(asyncio.CancelledError):
        await running


# ---------------------------------------------------------------- 자르기·가림(MD-9)


async def test_limits_trim_and_skip() -> None:
    found: list[ModelInfo | Mapping[str, Any]] = [
        ModelInfo(id="x" * 11),
        ModelInfo(id="ok-1", title="T" * 30, description="D" * 30),
        {"id": "", "title": "bad"},
        {"title": "no id"},
        ModelInfo(id="ok-2"),
        ModelInfo(id="ok-3"),
    ]
    backend = DiscoveringBackend(found=found)
    limits = ModelListLimits(id_chars=10, title_chars=5, description_chars=7, max_items=2)
    service, _ = _service(backend, limits=limits)
    catalog = await service.catalog("zz-disc")
    assert _ids(catalog.models) == ["ok-1", "ok-2"]
    assert catalog.models[0].title == "TTTTT"
    assert catalog.models[0].description == "DDDDDDD"


async def test_redact_applies_to_models_and_issues() -> None:
    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(SECRET, REDACTED)
        if isinstance(value, dict):
            return {k: redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return value

    leaking = DiscoveringBackend(
        "zz-leak", found=[ModelInfo(id="m", description=f"key {SECRET}", attributes={"k": SECRET})]
    )
    failing = DiscoveringBackend(f"zz-{SECRET}")
    failing.result = ModelDiscoveryResult(ok=False, reason="auth_failed")
    service, _ = _service(leaking, failing, redact=redact)
    ok = await service.catalog("zz-leak")
    assert SECRET not in ok.model_dump_json()
    bad = await service.catalog(f"zz-{SECRET}")
    assert SECRET not in bad.discovery.issues[0].model_dump_json()


async def test_has_secret_is_passed_to_backend() -> None:
    backend = DiscoveringBackend()
    service, _ = _service(backend, has_secret=lambda name: name == "zz-key")
    await service.catalog("zz-disc")
    ctx = backend.contexts[0]
    assert ctx.has_secret("zz-key")
    assert not ctx.has_secret("other")


def test_invalid_times_rejected() -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        BackendModelCatalogService(dict, timeout_s=0)
    with pytest.raises(ValueError, match="ttl_s"):
        BackendModelCatalogService(dict, ttl_s=-1)


# ---------------------------------------------------------------- 로그인 끝 알림


async def test_login_service_reports_account_change() -> None:
    from agent_console_runtime.testing_login import LoginBackendStub

    seen: list[str] = []

    def listener(backend_id: str) -> None:
        seen.append(backend_id)
        raise RuntimeError("listener failure is ignored")

    backend = LoginBackendStub("zz-login")
    login = BackendLoginService(
        lambda: {"zz-login": backend}, on_account_change=listener, tick_s=10
    )
    result = await login.logout("zz-login")
    assert result.ok
    assert seen == ["zz-login"]
    session = await login.start("zz-login")
    backend.drivers[0].update(phase="succeeded", message="ok")
    finished = await login.cancel(session.session_id)  # 이미 성공 → 성공으로 끝남
    assert finished.phase == "succeeded"
    assert seen == ["zz-login", "zz-login"]
    login.get(session.session_id)  # 끝난 세션을 다시 봐도 다시 알리지 않는다
    assert seen == ["zz-login", "zz-login"]
    await login.aclose()


async def test_catalog_invalidated_by_login_listener() -> None:
    backend = DiscoveringBackend(found=[ModelInfo(id="before")])
    service, _ = _service(backend)
    await service.catalog("zz-disc")
    backend.found = [ModelInfo(id="after")]
    service.invalidate("zz-disc")  # 앱이 on_account_change로 부르는 것과 같다
    assert _ids((await service.catalog("zz-disc")).models) == ["after"]
