"""mod-runs 백엔드 계정 로그인 경로(5.2R.80, ux-overhaul §15.9 F14 서버 몫).

가짜 드라이버(``agent_console_runtime.testing_login``)로 시작·폴링·코드 입력·성공/실패·취소·busy·
로그아웃, 입력 한도(4KB·422), 코드 문자열 비노출(응답·서버 로그·오류), 설정(꺼짐·시간 상한),
모듈 꺼짐, 종료 훅 취소, 인증 토큰, OpenAPI 문서를 확인한다. 실제 CLI·PTY는 쓰지 않는다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    BackendCapabilities,
    BackendDescriptor,
    ModelInfo,
    build_schema,
)
from agent_console_mod_runs import module
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import BackendLoginContext, LoginProgress, Registries, load_registries
from agent_console_runtime.testing_login import LoginBackendStub, ManualLoginDriver

API = "/api/v1"
TOKEN = "t" * 32
CODE = "CODE-SECRET-12345"
ENV_SECRET = "sk-ant-ENVSECRET-999"


class _Plain:
    """능력 없는 외부 백엔드 흉내."""

    def __init__(self, backend_id: str) -> None:
        self.descriptor = BackendDescriptor(
            id=backend_id, title=backend_id, capabilities=BackendCapabilities()
        )

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def run(self, req: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


def _script(ctx: BackendLoginContext, method: str) -> ManualLoginDriver:
    """코드 ``ok``면 성공, 그 밖은 verify_failed. 화면은 PTY 에코처럼 입력을 다시 보인다."""

    def on_text(d: ManualLoginDriver, text: str) -> None:
        screen = ["Paste code here if prompted > " + text]
        if text == "ok":
            d.update(phase="succeeded", message="로그인됨", screen=screen, needs_code=False)
        else:
            d.update(
                phase="failed",
                message=f"인증 실패: {text}",
                reason="verify_failed",
                details={"exit_code": 1, "echo": text},
                screen=[*screen, f"key {ENV_SECRET}"],
                needs_code=False,
            )

    return ManualLoginDriver(
        LoginProgress(
            phase="waiting_user",
            message="브라우저에서 로그인하세요",
            open_url="https://login.example/oauth/authorize?x=1",
            needs_code=True,
            code_label="브라우저에 나온 코드",
            accepts_keys=["enter"],
        ),
        on_text=on_text,
    )


@contextmanager
def _client(
    tmp_path: Path, *, config: ModulesConfig | None = None
) -> Iterator[tuple[TestClient, LoginBackendStub]]:
    env = {"ANTHROPIC_API_KEY": ENV_SECRET, "HOME": str(tmp_path)}
    registries = Registries()
    load_registries(registries)
    stub = LoginBackendStub("stub-login", make_driver=_script)
    registries.backends.register("stub-login", stub, source="test")
    registries.backends.register("plain", _Plain("plain"), source="test")
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
        yield client, stub


def _wait_phase(client: TestClient, sid: str, phase: str, timeout: float = 5.0) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = client.get(f"{API}/backends/login/{sid}").json()
        if body["phase"] == phase:
            return body
        if time.monotonic() > end:
            raise AssertionError(body)
        time.sleep(0.02)


def _pieces(secret: str, size: int = 5) -> list[str]:
    return [secret[i : i + size] for i in range(len(secret) - size + 1)]


def test_login_flow_success(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, stub):
        assert client.get(f"{API}/backends/login/current").status_code == 204
        res = client.post(f"{API}/backends/stub-login/login", json={})
        assert res.status_code == 201, res.text
        assert res.headers["cache-control"] == "no-store"
        session = res.json()
        assert session["phase"] == "waiting_user"
        assert session["method_id"] == "m1"
        assert session["needs_code"] is True
        assert session["accepts_keys"] == ["enter"]
        assert session["open_url"] == "https://login.example/oauth/authorize?x=1"
        sid = session["session_id"]

        current = client.get(f"{API}/backends/login/current")
        assert current.status_code == 200
        assert current.json()["session_id"] == sid

        sent = client.post(f"{API}/backends/login/{sid}/input", json={"text": " ok "})
        assert sent.status_code == 202
        assert sent.content == b""
        done = _wait_phase(client, sid, "succeeded")
        assert done["finished_at"] is not None
        assert done["screen"] == ["Paste code here if prompted > [REDACTED]"]
        assert stub.drivers[0].texts == ["ok"]
        assert client.get(f"{API}/backends/login/current").status_code == 204
        # 끝난 세션은 보관 시간 안에 다시 보인다
        assert client.get(f"{API}/backends/login/{sid}").json()["phase"] == "succeeded"


def test_wrong_code_fails_and_nothing_leaks(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """수용 기준 5(서버 몫): 코드 값과 그 조각이 응답·서버 로그·오류 본문에 없다."""
    with caplog.at_level(logging.DEBUG), _client(tmp_path) as (client, _):
        sid = client.post(f"{API}/backends/stub-login/login").json()["session_id"]
        texts = [client.post(f"{API}/backends/login/{sid}/input", json={"text": CODE}).text]
        failed = _wait_phase(client, sid, "failed")
        texts.append(client.get(f"{API}/backends/login/{sid}").text)
        texts.append(client.delete(f"{API}/backends/login/{sid}").text)
        # 끝난 세션에 다시 보내기·받지 않는 키 → 오류 본문에도 값이 없다
        texts.append(client.post(f"{API}/backends/login/{sid}/input", json={"text": CODE}).text)
        texts.append(client.post(f"{API}/backends/login/{sid}/input", json={"key": CODE}).text)
    texts.append(caplog.text)
    assert failed["reason"] == "verify_failed"
    assert failed["details"]["exit_code"] == 1
    assert "[REDACTED]" in failed["screen"][0]
    for text in texts:
        for secret in (CODE, ENV_SECRET):
            assert secret not in text
            for piece in _pieces(secret):
                assert piece not in text, (piece, text[:200])
    assert "login.example" not in caplog.text  # URL은 로그에 없다
    login_logs = [r.getMessage() for r in caplog.records if "백엔드 로그인" in r.getMessage()]
    assert any("phase=failed" in line and "reason=verify_failed" in line for line in login_logs)


def test_busy_and_cancel(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, stub):
        first = client.post(f"{API}/backends/stub-login/login").json()
        busy = client.post(f"{API}/backends/stub-login/login")
        assert busy.status_code == 409
        error = busy.json()["error"]
        assert error["code"] == "backend.login_busy"
        assert error["details"]["session_id"] == first["session_id"]
        # [여기서 이어 보기]: 같은 세션 폴링
        same = client.get(f"{API}/backends/login/{error['details']['session_id']}")
        assert same.json()["phase"] == "waiting_user"
        # 진행 중에는 같은 백엔드 로그아웃도 막는다
        assert client.post(f"{API}/backends/stub-login/logout").status_code == 409
        cancelled = client.delete(f"{API}/backends/login/{first['session_id']}")
        assert cancelled.status_code == 200
        assert cancelled.json()["phase"] == "cancelled"
        assert stub.drivers[0].cancelled
        again = client.post(f"{API}/backends/stub-login/login")
        assert again.status_code == 201
        client.delete(f"{API}/backends/login/{again.json()['session_id']}")


def test_input_rules(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, stub):
        sid = client.post(f"{API}/backends/stub-login/login").json()["session_id"]
        url = f"{API}/backends/login/{sid}/input"
        res = client.post(url, json={"key": "up"})
        assert res.status_code == 422
        assert res.json()["error"]["details"] == {"reason": "key_not_accepted"}
        assert client.post(url, json={"key": "enter"}).status_code == 202
        assert stub.drivers[0].keys == ["enter"]
        assert client.post(url, json={"text": "a", "key": "enter"}).status_code == 422
        assert client.post(url, json={}).status_code == 422
        too_long = client.post(url, json={"text": "x" * 3000})
        assert too_long.status_code == 422
        assert "x" * 20 not in too_long.text
        big = client.post(
            url,
            content=b'{"key": "enter", "pad": "' + b"y" * 5000 + b'"}',
            headers={"Content-Type": "application/json"},
        )
        assert big.status_code == 413
        sized = client.post(
            url,
            content=('{"text": "' + "가" * 1500 + '"}').encode(),
            headers={"Content-Type": "application/json"},
        )
        assert sized.status_code == 413  # 1500자지만 4KB 넘음
        assert stub.drivers[0].texts == []
        nope = client.post(f"{API}/backends/login/nope/input", json={"key": "enter"})
        assert nope.status_code == 404
        missing = client.get(f"{API}/backends/login/nope")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "backend.login_session_not_found"
        client.delete(f"{API}/backends/login/{sid}")


def test_unsupported_unknown_and_logout(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, stub):
        res = client.post(f"{API}/backends/plain/login")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "backend.login_unsupported"
        assert res.json()["error"]["details"] == {"backend": "plain"}
        res = client.post(f"{API}/backends/stub-login/login", json={"method_id": "nope"})
        assert res.status_code == 409
        res = client.post(f"{API}/backends/plain/logout")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "backend.logout_unsupported"
        assert client.post(f"{API}/backends/missing/login").status_code == 404
        out = client.post(f"{API}/backends/stub-login/logout")
        assert out.status_code == 200
        assert out.headers["cache-control"] == "no-store"
        assert out.json()["ok"] is True
        assert stub.logout_calls == 1


def test_timeout_clamped_by_settings(tmp_path: Path) -> None:
    config = ModulesConfig(
        options={"mod-runs": {"backend_login": {"timeout_s": 600, "timeout_max_s": 120}}}
    )
    with _client(tmp_path, config=config) as (client, _):
        body = client.post(f"{API}/backends/stub-login/login", json={"timeout_s": 5000}).json()
        assert body["expires_at"] - body["started_at"] == pytest.approx(120)
        client.delete(f"{API}/backends/login/{body['session_id']}")


def test_disabled_by_setting(tmp_path: Path) -> None:
    config = ModulesConfig(options={"mod-runs": {"backend_login": {"enabled": False}}})
    with _client(tmp_path, config=config) as (client, _):
        assert client.post(f"{API}/backends/stub-login/login").status_code == 404
        assert client.get(f"{API}/backends/login/current").status_code == 404
        assert client.post(f"{API}/backends/stub-login/logout").status_code == 404
        assert client.get(f"{API}/backends/status").status_code == 200  # 나머지는 그대로


def test_routes_absent_when_module_disabled(tmp_path: Path) -> None:
    config = ModulesConfig(disabled=["mod-runs"])
    with _client(tmp_path, config=config) as (client, _):
        assert client.post(f"{API}/backends/stub-login/login").status_code == 404
        assert client.get(f"{API}/backends/login/current").status_code == 404


def test_shutdown_cancels_active_session(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, stub):
        assert client.post(f"{API}/backends/stub-login/login").status_code == 201
        driver = stub.drivers[0]
        assert not driver.cancelled
    assert driver.cancelled  # 종료 훅


def test_token_required(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        res = client.post(
            f"{API}/backends/stub-login/login", headers={"X-Console-Token": "wrong" * 7}
        )
        assert res.status_code == 401


def test_openapi_documents_login_routes(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        spec = client.app.openapi()  # type: ignore[attr-defined]
    paths = spec["paths"]
    start = paths[f"{API}/backends/{{backend_id}}/login"]["post"]
    assert "409" in start["responses"]
    assert "backend.login_busy" in start["description"]
    assert "get" in paths[f"{API}/backends/login/current"]
    assert {"get", "delete"} <= set(paths[f"{API}/backends/login/{{session_id}}"])
    assert "post" in paths[f"{API}/backends/login/{{session_id}}/input"]
    assert "post" in paths[f"{API}/backends/{{backend_id}}/logout"]


def test_schemas_have_no_token_fields() -> None:
    defs = build_schema()["$defs"]
    banned = ("token", "secret", "password", "credential")
    for name in ("BackendLoginSession", "BackendLogoutResult", "LoginMethodInfo"):
        for field in defs[name]["properties"]:
            assert not any(word in field.lower() for word in banned), (name, field)
    text = defs["BackendLoginInput"]["properties"]["text"]
    assert text.get("writeOnly") is True
    assert text.get("x-secret") is True
