"""MD.5(design §1.1-MB MD-5~MD-8): mod-runs 모델 목록 조립 — 설정 + 계정 조회.

fake 백엔드(설치된 entry point, 설치자 설정 ``discovered_models``)와 테스트 대역으로:
빈 설정 목록 + 조회 → 칸 목록, 설정 + 조회 합치기·``sources``, 실패 → 200·``failed``·이슈,
``enabled: false`` → ``disabled``, ``disabled_backends``, 모르는 백엔드 404, ``refresh`` 재조회,
로그인·로그아웃 끝 → 다시 조회, OpenAPI 새 경로. 모델 id는 테스트가 정한 임의 값이다.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    BackendCapabilities,
    BackendDescriptor,
    KnownIssueCodes,
    LoginMethodInfo,
)
from agent_console_mod_runs import module
from agent_console_mod_runs.testing import local_definitions_module
from agent_console_modkit import BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_runtime import (
    BackendCheckContext,
    ModelDiscoveryResult,
    Registries,
    load_registries,
)
from agent_console_runtime.testing_login import LoginBackendStub

API = "/api/v1"
TOKEN = "t" * 32


class LoginAndListing(LoginBackendStub):
    """로그인·로그아웃 + 계정 모델 조회(호출 수를 센다). 실제 호출 없음."""

    def __init__(self) -> None:
        super().__init__("zz-account", methods=(LoginMethodInfo(id="m1", label="로그인"),))
        caps = self.descriptor.capabilities.model_copy(update={"model_discovery": True})
        self.descriptor = self.descriptor.model_copy(update={"capabilities": caps})
        self.calls = 0

    async def discover_models(
        self, ctx: BackendCheckContext, timeout_s: float
    ) -> ModelDiscoveryResult:
        self.calls += 1
        return ModelDiscoveryResult(ok=True, models=[{"id": f"zz-account-{self.calls}"}])


class Plain:
    def __init__(self) -> None:
        self.descriptor = BackendDescriptor(
            id="zz-plain", title="zz-plain", capabilities=BackendCapabilities()
        )

    async def list_models(self) -> list[Any]:
        return []

    async def run(self, req: Any, sink: Any, cancel: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


@contextmanager
def _client(
    tmp_path: Path, options: dict[str, Any] | None = None
) -> Iterator[tuple[TestClient, LoginAndListing]]:
    registries = Registries()
    load_registries(registries)  # fake-agent(설치된 entry point)
    account = LoginAndListing()
    registries.backends.register("zz-account", account, source="test")
    registries.backends.register("zz-plain", Plain(), source="test")
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
        registries=registries,
        environ={},
    )
    config = ModulesConfig(options={"mod-runs": options or {}})
    assembly = assemble([module, local_definitions_module()], config, base=base)
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    with TestClient(app) as client:
        client.headers["X-Console-Token"] = TOKEN
        yield client, account


def _fake(**install: Any) -> dict[str, Any]:
    return {"backends": {"fake-agent": install}}


def test_empty_config_list_gets_discovered_models(tmp_path: Path) -> None:
    with _client(tmp_path, _fake(discovered_models=[{"id": "zz-d1"}, {"id": "zz-d2"}])) as (
        client,
        _,
    ):
        res = client.get(f"{API}/backends/fake-agent/models")
        assert res.status_code == 200
        assert [(m["id"], m["sources"]) for m in res.json()] == [
            ("zz-d1", ["discovered"]),
            ("zz-d2", ["discovered"]),
        ]
        catalog = client.get(f"{API}/backends/fake-agent/model-catalog")
        assert catalog.status_code == 200
        assert catalog.headers["cache-control"] == "no-store"
        body = catalog.json()
        assert body["backend_id"] == "fake-agent"
        assert body["discovery"]["state"] == "ok"
        assert body["discovery"]["fetched_at"] is not None


def test_config_and_discovery_merge(tmp_path: Path) -> None:
    options = _fake(
        models=[{"id": "zz-both", "title": "Mine"}, {"id": "zz-c"}],
        discovered_models=[{"id": "zz-d"}, {"id": "zz-both", "title": "Theirs"}],
    )
    with _client(tmp_path, options) as (client, _):
        body = client.get(f"{API}/backends/fake-agent/models").json()
        assert [(m["id"], m["title"], m["sources"]) for m in body] == [
            ("zz-both", "Mine", ["config", "discovered"]),
            ("zz-c", None, ["config"]),
            ("zz-d", None, ["discovered"]),
        ]


def test_failure_is_200_with_issue(tmp_path: Path) -> None:
    options = _fake(models=[{"id": "zz-c"}], discovery_failure="zz-reason")
    with _client(tmp_path, options) as (client, _):
        res = client.get(f"{API}/backends/fake-agent/model-catalog")
        assert res.status_code == 200
        body = res.json()
        assert [m["id"] for m in body["models"]] == ["zz-c"]
        assert body["discovery"]["state"] == "failed"
        (issue,) = body["discovery"]["issues"]
        assert issue["code"] == KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED
        assert issue["severity"] == "warning"
        assert issue["details"] == {"backend_id": "fake-agent", "reason": "zz-reason"}
        assert client.get(f"{API}/backends/fake-agent/models").status_code == 200


def test_disabled_globally_and_per_backend(tmp_path: Path) -> None:
    found = {"discovered_models": [{"id": "zz-d"}], "models": [{"id": "zz-c"}]}
    for switch in ({"enabled": False}, {"disabled_backends": ["fake-agent"]}):
        options = {**_fake(**found), "model_discovery": switch}
        with _client(tmp_path, options) as (client, _):
            body = client.get(f"{API}/backends/fake-agent/model-catalog").json()
            assert body["discovery"]["state"] == "disabled"
            assert [m["id"] for m in body["models"]] == ["zz-c"]
            other = client.get(f"{API}/backends/zz-account/model-catalog").json()
            expected = "disabled" if "enabled" in switch else "ok"
            assert other["discovery"]["state"] == expected


def test_unsupported_and_unknown(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        body = client.get(f"{API}/backends/zz-plain/model-catalog").json()
        assert body["discovery"]["state"] == "unsupported"
        assert client.get(f"{API}/backends/zz-nope/model-catalog").status_code == 404
        assert client.get(f"{API}/backends/zz-nope/models").status_code == 404
        fake = client.get(f"{API}/backends/fake-agent/model-catalog").json()
        assert fake["discovery"]["state"] == "unsupported"  # 조회 설정 없는 fake = 능력 없음


def test_cache_and_refresh(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, account):
        first = client.get(f"{API}/backends/zz-account/models").json()
        again = client.get(f"{API}/backends/zz-account/model-catalog").json()
        assert [m["id"] for m in first] == ["zz-account-1"]
        assert [m["id"] for m in again["models"]] == ["zz-account-1"]
        assert account.calls == 1
        fresh = client.get(f"{API}/backends/zz-account/model-catalog?refresh=true").json()
        assert [m["id"] for m in fresh["models"]] == ["zz-account-2"]
        assert account.calls == 2


def test_logout_and_login_invalidate(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, account):
        client.get(f"{API}/backends/zz-account/models")
        assert client.post(f"{API}/backends/zz-account/logout").status_code == 200
        after_logout = client.get(f"{API}/backends/zz-account/models").json()
        assert [m["id"] for m in after_logout] == ["zz-account-2"]
        sid = client.post(f"{API}/backends/zz-account/login", json={}).json()["session_id"]
        account.drivers[0].update(phase="succeeded", message="ok")
        end = time.monotonic() + 5
        while client.get(f"{API}/backends/login/{sid}").json()["phase"] != "succeeded":
            assert time.monotonic() < end
            time.sleep(0.05)
        after_login = client.get(f"{API}/backends/zz-account/models").json()
        assert [m["id"] for m in after_login] == ["zz-account-3"]


def test_works_without_login_service(tmp_path: Path) -> None:
    options = {**_fake(discovered_models=[{"id": "zz-d"}]), "backend_login": {"enabled": False}}
    with _client(tmp_path, options) as (client, _):
        body = client.get(f"{API}/backends/fake-agent/model-catalog").json()
        assert body["discovery"]["state"] == "ok"


def test_openapi_has_new_route(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _):
        paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
        route = paths[f"{API}/backends/{{backend_id}}/model-catalog"]["get"]
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "BackendModelCatalog"
        )
        assert any(p["name"] == "refresh" for p in route["parameters"])
