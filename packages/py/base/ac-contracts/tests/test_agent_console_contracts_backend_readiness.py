"""백엔드 준비 상태·연결 테스트 계약(5.2R.67, ux-overhaul §15.8 수용 기준 6·7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    BackendCapabilities,
    BackendDescriptor,
    BackendProbeRequest,
    BackendProbeResult,
    BackendReadiness,
    ErrorCodes,
    ReadinessCheck,
    build_schema,
)


def test_capabilities_and_descriptor_defaults_are_off() -> None:
    caps = BackendCapabilities()
    assert (caps.status, caps.probe) == (False, False)
    assert BackendDescriptor(id="b", title="B").probe_cost_note == ""


def test_readiness_tone_is_closed_but_state_is_open() -> None:
    r = BackendReadiness(backend_id="b", state="my_custom_state", tone="warn", checked_at=1.0)
    assert (r.summary, r.short_summary, r.detail, r.fixes, r.checks) == ("", "", "", [], [])
    with pytest.raises(ValidationError):
        BackendReadiness(backend_id="b", state="x", tone="purple", checked_at=1.0)  # type: ignore[arg-type]
    schema = build_schema()["$defs"]["BackendReadiness"]["properties"]
    assert "enum" not in schema["state"]
    assert ReadinessCheck(id="k", title="키", ok=False).note is None


def test_probe_request_and_result() -> None:
    assert BackendProbeRequest().timeout_s is None
    with pytest.raises(ValidationError):
        BackendProbeRequest(timeout_s=0)
    r = BackendProbeResult(backend_id="b", ok=True, finished_at=2.0)
    assert (r.latency_ms, r.reason, r.message, r.details, r.fixes) == (None, None, "", {}, [])
    with pytest.raises(ValidationError):
        BackendProbeResult(backend_id="b", ok=True, latency_ms=-1, finished_at=2.0)


def test_no_secret_value_fields_in_schemas() -> None:
    """응답 모델에 비밀 값을 담을 필드가 없다(값 필드 자체가 없게 설계)."""
    defs = build_schema()["$defs"]
    banned = ("key", "token", "secret", "password", "credential", "value")
    for name in ("BackendReadiness", "ReadinessCheck", "BackendProbeResult", "BackendProbeRequest"):
        for field in defs[name]["properties"]:
            assert not any(word in field.lower() for word in banned), (name, field)


def test_probe_unsupported_error_code_is_409() -> None:
    assert ErrorCodes.BACKEND_PROBE_UNSUPPORTED == "backend.probe_unsupported"
    assert HTTP_STATUS_BY_ERROR_CODE[ErrorCodes.BACKEND_PROBE_UNSUPPORTED] == 409
