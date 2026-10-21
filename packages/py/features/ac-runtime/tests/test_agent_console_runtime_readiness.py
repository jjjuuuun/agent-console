"""백엔드 준비 상태·연결 테스트 서비스(5.2R.67, ux-overhaul §15.8).

능력 없음 → unknown·409용 예외, 시간 상한·자르기, 같은 백엔드 동시 probe 합치기, 비밀 가림
(응답·로그·예외 문장), ``SecretResolver.has``(값을 기억하지 않음).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from agent_console_contracts import (
    BackendCapabilities,
    BackendDescriptor,
    BackendProbeResult,
    BackendReadiness,
    ModelInfo,
    ReadinessCheck,
)
from agent_console_runtime import (
    REDACTED,
    BackendCheckContext,
    BackendReadinessService,
    EnvSecretProvider,
    ExecutionBackend,
    ProbeCapableBackend,
    ProbeReasons,
    ProbeUnsupportedError,
    SecretResolver,
    StatusCapableBackend,
    UnknownBackendError,
    supports_probe,
    supports_status,
)

SECRET = "sk-test-SECRET-123"
NOW = 1_700_000_000.0


def _descriptor(backend_id: str, *, status: bool, probe: bool) -> BackendDescriptor:
    return BackendDescriptor(
        id=backend_id,
        title=backend_id,
        capabilities=BackendCapabilities(status=status, probe=probe),
    )


class PlainBackend:
    """능력 없는 백엔드(외부 플러그인 흉내)."""

    def __init__(self, backend_id: str = "plain") -> None:
        self.descriptor = _descriptor(backend_id, status=False, probe=False)

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(self, req: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class CheckingBackend(PlainBackend):
    """status·probe를 구현한 가짜 백엔드(호출 수를 센다, 실제 SDK 호출 없음)."""

    def __init__(
        self,
        backend_id: str = "checking",
        *,
        leak: str | None = None,
        delay: float = 0.0,
        fail: Exception | None = None,
        declare: bool = True,
    ) -> None:
        super().__init__(backend_id)
        self.descriptor = _descriptor(backend_id, status=declare, probe=declare)
        self.leak = leak
        self.delay = delay
        self.fail = fail
        self.status_calls = 0
        self.probe_calls = 0
        self.timeouts: list[float] = []
        self.contexts: list[BackendCheckContext] = []

    async def status(self, ctx: BackendCheckContext) -> BackendReadiness:
        self.status_calls += 1
        self.contexts.append(ctx)
        if self.fail is not None:
            raise self.fail
        if self.delay:
            await asyncio.sleep(self.delay)
        note = f"키 {self.leak}" if self.leak else "환경변수 MY_KEY"
        return BackendReadiness(
            backend_id="wrong-id",  # 서비스가 등록 id로 고친다
            state="auth_ready",
            tone="ok",
            summary="인증 설정됨",
            short_summary="준비됨",
            detail=self.leak or "",
            checked_at=ctx.clock(),
            checks=[
                ReadinessCheck(id="key", title="API 키", ok=ctx.has_secret("my_key"), note=note)
            ],
        )

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        self.probe_calls += 1
        self.timeouts.append(timeout_s)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return BackendProbeResult(
            backend_id=ctx.backend_id,
            ok=self.leak is None,
            reason=None if self.leak is None else "auth_failed",
            message="연결됨" if self.leak is None else f"인증 실패: {self.leak}",
            details={"model": "m-1", "echo": self.leak or ""},
            finished_at=ctx.clock(),
        )


def _redact_secret(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(SECRET, REDACTED)
    if isinstance(value, dict):
        return {k: _redact_secret(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_secret(v) for v in value]
    return value


def _service(*backends: Any, **kwargs: Any) -> BackendReadinessService:
    table: dict[str, ExecutionBackend] = {b.descriptor.id: b for b in backends}
    kwargs.setdefault("clock", lambda: NOW)
    return BackendReadinessService(lambda: table, **kwargs)


# ---------------------------------------------------------------- 능력 판정


def test_capability_needs_both_declaration_and_method() -> None:
    assert not supports_status(PlainBackend())
    assert not supports_probe(PlainBackend())
    assert supports_status(CheckingBackend())
    assert supports_probe(CheckingBackend())
    # 메서드는 있으나 선언하지 않음 → 지원하지 않음
    assert not supports_status(CheckingBackend(declare=False))
    assert isinstance(CheckingBackend(), StatusCapableBackend)
    assert isinstance(CheckingBackend(), ProbeCapableBackend)

    class DeclaresOnly(PlainBackend):
        def __init__(self) -> None:
            super().__init__("declares")
            self.descriptor = _descriptor("declares", status=True, probe=True)

    assert not supports_status(DeclaresOnly())
    assert not supports_probe(DeclaresOnly())


# ---------------------------------------------------------------- 정적 점검


async def test_status_without_capability_is_unknown_not_error() -> None:
    svc = _service(PlainBackend())
    r = await svc.status("plain")
    assert (r.backend_id, r.state, r.tone) == ("plain", "unknown", "unknown")
    assert r.summary
    assert r.short_summary
    assert r.checked_at == NOW


async def test_status_passes_backend_result_with_registered_id() -> None:
    backend = CheckingBackend()
    svc = _service(backend, has_secret=lambda name: name == "my_key")
    r = await svc.status("checking")
    assert (r.backend_id, r.state, r.tone, r.summary) == (
        "checking",
        "auth_ready",
        "ok",
        "인증 설정됨",
    )
    assert r.checks[0].ok is True
    assert backend.probe_calls == 0  # 정적 점검은 probe를 부르지 않는다
    assert backend.contexts[0].backend_id == "checking"


async def test_status_failure_and_timeout_become_unknown(caplog: pytest.LogCaptureFixture) -> None:
    failing = CheckingBackend("failing", fail=RuntimeError(f"boom {SECRET}"))
    slow = CheckingBackend("slow", delay=1.0)
    svc = _service(failing, slow, status_timeout_s=0.05)
    with caplog.at_level(logging.DEBUG):
        a = await svc.status("failing")
        b = await svc.status("slow")
    assert a.tone == b.tone == "unknown"
    assert SECRET not in caplog.text
    assert SECRET not in a.model_dump_json()


async def test_status_all_in_registration_order() -> None:
    svc = _service(CheckingBackend("b"), PlainBackend("a"))
    got = await svc.status_all()
    assert [(r.backend_id, r.tone) for r in got] == [("b", "ok"), ("a", "unknown")]


async def test_unknown_backend_raises() -> None:
    svc = _service(PlainBackend())
    with pytest.raises(UnknownBackendError):
        await svc.status("nope")
    with pytest.raises(UnknownBackendError):
        await svc.probe("nope")


# ---------------------------------------------------------------- 연결 테스트


async def test_probe_unsupported_raises() -> None:
    svc = _service(PlainBackend(), CheckingBackend(declare=False))
    for backend_id in ("plain", "checking"):
        assert svc.probe_supported(backend_id) is False
        with pytest.raises(ProbeUnsupportedError):
            await svc.probe(backend_id)


async def test_probe_success_fills_latency_and_id() -> None:
    ticks = iter([10.0, 10.25])
    backend = CheckingBackend()
    svc = _service(backend, monotonic=lambda: next(ticks))
    r = await svc.probe("checking")
    assert r.ok is True
    assert r.latency_ms == 250
    assert r.details == {"model": "m-1", "echo": ""}
    assert backend.status_calls == 0


async def test_concurrent_probes_are_merged() -> None:
    backend = CheckingBackend(delay=0.05)
    svc = _service(backend)
    first, second = await asyncio.gather(svc.probe("checking"), svc.probe("checking"))
    assert backend.probe_calls == 1
    assert first == second
    # 끝난 뒤의 새 요청은 다시 부른다
    await svc.probe("checking")
    assert backend.probe_calls == 2


async def test_probe_timeout_is_clamped_to_server_limit() -> None:
    backend = CheckingBackend()
    svc = _service(backend, probe_timeout_max_s=5.0)
    await svc.probe("checking", timeout_s=999)
    await svc.probe("checking", timeout_s=1.5)
    await svc.probe("checking")
    assert backend.timeouts == [5.0, 1.5, 5.0]
    assert svc.clamp_timeout(None) == 5.0
    svc_default = _service(backend, probe_timeout_max_s=5.0, probe_timeout_default_s=2.0)
    assert svc_default.clamp_timeout(None) == 2.0
    with pytest.raises(ValueError, match="0보다"):
        _service(backend, probe_timeout_max_s=0)


async def test_probe_timeout_result() -> None:
    backend = CheckingBackend(delay=1.0)
    svc = _service(backend, probe_timeout_max_s=0.05)
    r = await svc.probe("checking")
    assert (r.ok, r.reason) == (False, ProbeReasons.TIMEOUT)
    assert r.message
    assert r.details == {"timeout_s": 0.05}


async def test_probe_exception_drops_message(caplog: pytest.LogCaptureFixture) -> None:
    backend = CheckingBackend(fail=RuntimeError(f"auth header {SECRET}"))
    svc = _service(backend)
    with caplog.at_level(logging.DEBUG):
        r = await svc.probe("checking")
    assert (r.ok, r.reason) == (False, ProbeReasons.ERROR)
    assert r.details == {"error": "RuntimeError"}
    assert SECRET not in r.model_dump_json()
    assert SECRET not in caplog.text


async def test_secret_never_in_responses_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    """수용 기준 6(서비스 수준): 백엔드가 값을 흘려도 응답·로그에 없다(앞 5자 이상 조각 포함)."""
    backend = CheckingBackend(leak=SECRET)
    svc = _service(backend, redact=_redact_secret)
    with caplog.at_level(logging.DEBUG):
        status = await svc.status("checking")
        probe = await svc.probe("checking")
        everything = [status.model_dump_json(), probe.model_dump_json(), caplog.text]
    assert REDACTED in status.detail
    assert REDACTED in probe.message
    pieces = {SECRET[i : i + 5] for i in range(len(SECRET) - 4)} - {"sk-te", "k-tes", "-test"}
    for text in everything:
        assert SECRET not in text
        for piece in pieces:
            assert piece not in text, piece
    # 서버 로그는 백엔드 id·ok·reason·소요 시간만
    probe_logs = [r for r in caplog.records if "연결 테스트" in r.getMessage()]
    assert len(probe_logs) == 1
    assert "인증 실패" not in probe_logs[0].getMessage()


def test_secret_resolver_has_checks_existence_only() -> None:
    resolver = SecretResolver([EnvSecretProvider({"API_KEY": SECRET})])
    assert resolver.has("secret://api_key") is True
    assert resolver.has("API_KEY") is True
    assert resolver.has("missing") is False
    # 값을 꺼내지 않았으므로 가림 목록에도 없다
    assert resolver.has_secrets is False
