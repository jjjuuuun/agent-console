"""mod-runs 백엔드 준비 상태·연결 테스트 경로(5.2R.67, ux-overhaul §15.8 수용 기준 3·5~9 서버 몫).

- fake(설치된 entry point)는 준비됨·즉시 성공, 능력 없는 플러그인은 unknown·409.
- 누르기 전에는 probe 호출이 없고(상태 조회는 probe를 부르지 않는다), 동시 요청은 한 번만 부른다.
- 시간 상한은 모듈 설정으로 잘린다.
- 키 값이 든 환경에서 응답·서버 로그 어디에도 값(과 앞 5자 이상 조각)이 없다. 응답 스키마에 값
  필드가 없다.
- 모듈이 꺼지면 세 경로가 404.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    BackendCapabilities,
    BackendDescriptor,
    BackendProbeResult,
    BackendReadiness,
    ModelInfo,
    ReadinessCheck,
    build_schema,
)
from agent_console_mod_runs import module
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import BackendCheckContext, Registries, load_registries

API = "/api/v1"
TOKEN = "t" * 32
SECRET = "sk-test-SECRET-123"
KEY_NAME = "ANTHROPIC_API_KEY"


class _Plain:
    """능력 없는 외부 백엔드 플러그인 흉내."""

    def __init__(self, backend_id: str, *, status: bool = False, probe: bool = False) -> None:
        self.descriptor = BackendDescriptor(
            id=backend_id,
            title=backend_id,
            capabilities=BackendCapabilities(status=status, probe=probe),
        )

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(self, req: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class FakeSdkBackend(_Plain):
    """가짜 SDK 백엔드: 환경에서 키를 직접 읽고(SDK처럼) 오류 문장에 값을 흘린다. 실제 호출 없음."""

    def __init__(self, environ: Mapping[str, str], *, delay: float = 0.0) -> None:
        super().__init__("fake-sdk", status=True, probe=True)
        self._environ = environ
        self.delay = delay
        self.sdk_calls = 0
        self._lock = threading.Lock()

    async def status(self, ctx: BackendCheckContext) -> BackendReadiness:
        present = KEY_NAME in self._environ
        return BackendReadiness(
            backend_id=ctx.backend_id,
            state="auth_ready" if present else "auth_missing",
            tone="ok" if present else "error",
            summary="인증 설정됨 (API 키)" if present else "키 없음",
            short_summary="준비됨" if present else "키 없음",
            detail=f"디버그: {self._environ.get(KEY_NAME, '')}",  # 일부러 흘림(가림 검사)
            checked_at=ctx.clock(),
            checks=[
                ReadinessCheck(
                    id="api_key",
                    title="API 키 환경변수",
                    ok=present,
                    note=f"{KEY_NAME}={self._environ.get(KEY_NAME, '')}",
                )
            ],
        )

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        with self._lock:
            self.sdk_calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        key = self._environ.get(KEY_NAME, "")
        return BackendProbeResult(
            backend_id=ctx.backend_id,
            ok=False,
            reason="auth_failed",
            message=f"401 invalid x-api-key: {key}",
            details={"model": "m-1", "header": f"x-api-key: {key}", "timeout_s": timeout_s},
            finished_at=ctx.clock(),
        )


def _registries(environ: Mapping[str, str], *, delay: float = 0.0) -> Registries:
    registries = Registries()
    load_registries(registries)  # fake(설치된 entry point)
    registries.backends.register("fake-sdk", FakeSdkBackend(environ, delay=delay), source="test")
    registries.backends.register("plain", _Plain("plain"), source="test")
    return registries


@contextmanager
def _client(
    tmp_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    delay: float = 0.0,
    config: ModulesConfig | None = None,
) -> Iterator[tuple[TestClient, Registries]]:
    env = dict(environ if environ is not None else {KEY_NAME: SECRET})
    registries = _registries(env, delay=delay)
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
        environ=env,
    )
    assembly = assemble([module, local_definitions_module()], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, registries


def _sdk(registries: Registries) -> FakeSdkBackend:
    found = registries.backends.get("fake-sdk")
    assert isinstance(found, FakeSdkBackend)
    return found


def _pieces(secret: str, size: int = 5) -> set[str]:
    return {secret[i : i + size] for i in range(len(secret) - size + 1)}


def test_status_all_and_one(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, registries):
        res = client.get(f"{API}/backends/status")
        assert res.status_code == 200
        assert res.headers["cache-control"] == "no-store"
        by_id = {r["backend_id"]: r for r in res.json()}
        assert by_id["fake-agent"]["tone"] == "ok"
        assert by_id["fake-agent"]["state"] == "always_ready"
        assert by_id["fake-sdk"]["tone"] == "ok"
        assert (by_id["plain"]["state"], by_id["plain"]["tone"]) == ("unknown", "unknown")
        one = client.get(f"{API}/backends/plain/status")
        assert one.status_code == 200  # 능력 없음은 404가 아니다
        assert one.json()["tone"] == "unknown"
        assert one.headers["cache-control"] == "no-store"
        assert client.get(f"{API}/backends/nope/status").status_code == 404
        # 정적 점검은 실제 호출을 하지 않는다
        assert _sdk(registries).sdk_calls == 0


def test_status_reports_missing_key(tmp_path: Path) -> None:
    with _client(tmp_path, environ={}) as (client, _):
        body = client.get(f"{API}/backends/fake-sdk/status").json()
        assert (body["state"], body["tone"]) == ("auth_missing", "error")


def test_probe_fake_succeeds_and_unsupported_is_409(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        ok = client.post(f"{API}/backends/fake-agent/probe")
        assert ok.status_code == 200
        assert ok.headers["cache-control"] == "no-store"
        assert ok.json()["ok"] is True
        res = client.post(f"{API}/backends/plain/probe", json={})
        assert res.status_code == 409
        error = res.json()["error"]
        assert error["code"] == "backend.probe_unsupported"
        assert error["details"] == {"backend": "plain"}
        assert client.post(f"{API}/backends/nope/probe").status_code == 404
        bad = client.post(f"{API}/backends/fake-agent/probe", json={"timeout_s": -1})
        assert bad.status_code == 422


def test_probe_timeout_is_clamped_by_module_setting(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-runs": {"backend_probe_timeout_max_s": 0.05}})
    with _client(tmp_path, delay=1.0, config=config) as (client, registries):
        body = client.post(f"{API}/backends/fake-sdk/probe", json={"timeout_s": 300}).json()
        assert (body["ok"], body["reason"]) == (False, "timeout")
        assert body["details"] == {"timeout_s": 0.05}
        assert _sdk(registries).sdk_calls == 1


def test_concurrent_probes_call_sdk_once(tmp_path: Path) -> None:
    with _client(tmp_path, delay=0.3) as (client, registries):

        def post() -> dict[str, Any]:
            res = client.post(f"{API}/backends/fake-sdk/probe")
            assert res.status_code == 200
            body: dict[str, Any] = res.json()
            return body

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: post(), range(2)))
        assert _sdk(registries).sdk_calls == 1
        assert first == second


def test_secret_never_in_responses_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """수용 기준 6(서버 몫): 응답 JSON·서버 로그·오류 본문에 키 값과 그 조각이 없다."""
    with caplog.at_level(logging.DEBUG), _client(tmp_path) as (client, registries):
        texts = [
            client.get(f"{API}/backends/status").text,
            client.get(f"{API}/backends/fake-sdk/status").text,
            client.post(f"{API}/backends/fake-sdk/probe").text,
            client.post(f"{API}/backends/plain/probe").text,
        ]
        assert _sdk(registries).sdk_calls == 1
    texts.append(caplog.text)
    for text in texts:
        assert SECRET not in text
        for piece in _pieces(SECRET):
            assert piece not in text, piece
    # 가림 표시는 남는다(값이 흘렀던 자리)
    assert "[REDACTED]" in texts[2]
    # 서버 로그: 백엔드 id·ok·reason·소요 시간만(결과 문장 원문 없음)
    probe_logs = [r.getMessage() for r in caplog.records if "연결 테스트" in r.getMessage()]
    assert probe_logs
    assert all("invalid x-api-key" not in line for line in probe_logs)


def test_response_schemas_have_no_value_fields() -> None:
    """응답 모델에 비밀 값을 담을 필드가 없다(계약 스키마 검사)."""
    defs = build_schema()["$defs"]
    banned = ("key", "token", "secret", "password", "credential", "value")
    for name in ("BackendReadiness", "ReadinessCheck", "BackendProbeResult"):
        for field in defs[name]["properties"]:
            assert not any(word in field.lower() for word in banned), (name, field)


def test_openapi_documents_routes_and_409(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        spec = client.app.openapi()  # type: ignore[attr-defined]
    paths = spec["paths"]
    assert "get" in paths[f"{API}/backends/status"]
    assert "get" in paths[f"{API}/backends/{{backend_id}}/status"]
    probe = paths[f"{API}/backends/{{backend_id}}/probe"]["post"]
    assert "409" in probe["responses"]
    assert "backend.probe_unsupported" in probe["description"]


def test_routes_absent_when_module_disabled(tmp_path: Path) -> None:
    config = ModulesConfig(disabled=["mod-runs"])
    with _client(tmp_path, config=config) as (client, _):
        assert client.get(f"{API}/backends/status").status_code == 404
        assert client.get(f"{API}/backends/fake-agent/status").status_code == 404
        assert client.post(f"{API}/backends/fake-agent/probe").status_code == 404
