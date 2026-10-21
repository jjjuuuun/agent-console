"""fake 준비 상태·연결 테스트(5.2R.67, ux-overhaul §15.8): 늘 준비됨, 지연 없는 성공."""

from __future__ import annotations

from agent_console_backend_fake import FAKE_READY_STATE, FakeBackend
from agent_console_runtime import (
    BackendCheckContext,
    BackendReadinessService,
    supports_probe,
    supports_status,
)


async def test_fake_declares_and_implements_both_capabilities() -> None:
    backend = FakeBackend()
    assert backend.descriptor.capabilities.status is True
    assert backend.descriptor.capabilities.probe is True
    assert backend.descriptor.probe_cost_note
    assert supports_status(backend)
    assert supports_probe(backend)


async def test_fake_status_always_ready_and_probe_succeeds() -> None:
    backend = FakeBackend(backend_id="fake-2", models=[{"id": "m"}])
    ctx = BackendCheckContext("fake-2", clock=lambda: 5.0)
    status = await backend.status(ctx)
    assert (status.backend_id, status.state, status.tone) == ("fake-2", FAKE_READY_STATE, "ok")
    assert status.summary
    assert status.short_summary
    assert status.checked_at == 5.0
    probe = await backend.probe(ctx, 1.0)
    assert (probe.ok, probe.reason, probe.latency_ms) == (True, None, 0)
    assert probe.details == {"models": 1}


async def test_fake_through_service() -> None:
    backend = FakeBackend()
    svc = BackendReadinessService(lambda: {"fake": backend})
    assert (await svc.status("fake")).tone == "ok"
    assert (await svc.probe("fake")).ok is True
