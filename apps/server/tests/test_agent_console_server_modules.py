"""3R.9 서버 호스트화: modkit 조립, `modules` 설정·명령행, `GET /modules`, `feature_unavailable`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.testclient import TestClient

from agent_console_contracts import (
    CONTRACT_VERSIONS,
    ErrorCodes,
    ErrorResponse,
    FeatureUnavailableDetails,
    ModuleInfo,
)
from agent_console_modkit import (
    ModuleContext,
    ModuleDescriptor,
    ModuleParts,
    ModuleReport,
    ModuleState,
    PortKey,
)
from agent_console_server import (
    apply_module_flags,
    create_app,
    installed_modules,
    load_settings,
    module_info,
)
from agent_console_server.testing import API, TEST_TOKEN, make_settings, server

LAUNCHER: PortKey[Any] = PortKey("example.launcher")


class _OptionalPortModule:
    """선택 포트가 없으면 `/example/launch`가 409 `feature_unavailable`인 예제 모듈."""

    descriptor = ModuleDescriptor(
        id="mod-example",
        version="0.0.1",
        kind="feature",
        title="Example",
        optional=(LAUNCHER,),
        contracts={"modules": "1.0.0"},
        web_roles=("example",),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        launcher = ctx.port(LAUNCHER)
        router = APIRouter()

        @router.get("/example/launch")
        async def launch() -> dict[str, str]:
            if launcher is None:
                raise ctx.unavailable(LAUNCHER)
            return {"launched": str(launcher)}

        return ModuleParts(routers=[router])


def _modules(client: TestClient) -> list[ModuleInfo]:
    res = client.get(f"{API}/modules")
    assert res.status_code == 200
    return [ModuleInfo.model_validate(m) for m in res.json()]


def test_modules_lists_installed_modules_active(tmp_path: Path) -> None:
    with server(make_settings(tmp_path)) as client:
        infos = _modules(client)
        # entry point로 설치된 모듈(mod-*·link-*)만, 모두 active
        ids = {m.id for m in infos}
        assert ids == {m.descriptor.id for m in installed_modules()}
        assert all(m.status == "active" for m in infos), [(m.id, m.status) for m in infos]
        assert all(m.reason is None for m in infos)
        for info in infos:
            assert set(info.contracts) <= set(CONTRACT_VERSIONS)
        # 동작 불변: 기능 경로가 그대로 있다
        assert client.get(f"{API}/agents").status_code == 200
        assert client.get(f"{API}/runs").status_code == 200


def test_modules_readable_without_token(tmp_path: Path) -> None:
    with server(make_settings(tmp_path), with_token=False) as client:
        assert client.get(f"{API}/modules").status_code == 200


def test_disable_modules_by_config_keeps_host_routes(tmp_path: Path) -> None:
    # DB를 쓰는 모듈(계보를 선언한 모듈 전부 + mod-definitions, 실행은 정의 필수라 꺼짐)을 모두 끄면
    # DB 파일은 만들어지지 않는다(켜진 모듈의 계보만 올림). 정의 모듈을 끄면 그것을 필수로 쓰는
    # 모듈은 unsatisfied다. 계보 모듈 목록은 설치된 모듈에서 읽는다(4R.10: mod-logs가 늘었다).
    with_lineage = [m.descriptor.id for m in installed_modules() if m.descriptor.migrations]
    disabled = sorted({"mod-usage", "mod-definitions", "mod-chat", *with_lineage})
    settings = make_settings(tmp_path, modules={"disabled": disabled})
    with server(settings) as client:
        infos = {m.id: m for m in _modules(client)}
        assert infos["mod-chat"].status == "disabled"
        assert infos["mod-chat"].reason == "modules.disabled"
        assert client.get(f"{API}/health").status_code == 200
        assert client.get(f"{API}/bootstrap").json()["token"] == TEST_TOKEN
        # 꺼진 모듈의 경로는 등록되지 않는다(404)
        res = client.get(f"{API}/agents")
        assert res.status_code == 404
        ErrorResponse.model_validate(res.json())
        assert not hasattr(client.app.state, "ctx")  # type: ignore[attr-defined]
    assert not (tmp_path / "ws" / ".state" / "console.sqlite3").exists()  # 저장소를 열지 않았다


def test_enabled_list_disables_the_rest(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"enabled": ["mod-example"]})
    app = create_app(
        settings,
        environ={},
        token=TEST_TOKEN,
        modules=[*installed_modules(), _OptionalPortModule()],
    )
    with TestClient(app) as client:
        states = {m.id: m.status for m in _modules(client)}
    assert states.pop("mod-example") == "active"
    assert set(states.values()) == {"disabled"}


def test_feature_unavailable_maps_to_contract_409(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path),
        environ={},
        token=TEST_TOKEN,
        modules=[*installed_modules(), _OptionalPortModule()],
    )
    with TestClient(app) as client:
        states = {m.id: m.status for m in _modules(client)}
        assert set(states.values()) == {"active"}
        res = client.get(f"{API}/example/launch")
    assert res.status_code == 409
    error = ErrorResponse.model_validate(res.json()).error
    assert error.code == ErrorCodes.FEATURE_UNAVAILABLE
    details = FeatureUnavailableDetails.model_validate(error.details)
    assert (details.module, details.port) == ("mod-example", LAUNCHER.name)


def test_feature_available_when_port_provided(tmp_path: Path) -> None:
    class _Provider:
        descriptor = ModuleDescriptor(
            id="mod-provider", version="0", kind="link", title="P", provides=(LAUNCHER,)
        )

        def build(self, ctx: ModuleContext) -> ModuleParts:
            ctx.provide(LAUNCHER, "go")
            return ModuleParts()

    app = create_app(
        make_settings(tmp_path),
        environ={},
        token=TEST_TOKEN,
        modules=[_OptionalPortModule(), _Provider()],
    )
    with TestClient(app) as client:
        res = client.get(f"{API}/example/launch")
    assert res.status_code == 200
    assert res.json() == {"launched": "go"}


def test_modules_config_from_yaml(tmp_path: Path) -> None:
    (tmp_path / "agent-console.yaml").write_text(
        "modules:\n  disabled: [mod-y]\n  options:\n    mod-x: {a: 1}\n",
        encoding="utf-8",
    )
    settings = load_settings(cwd=tmp_path, environ={})
    assert settings.modules.disabled == ["mod-y"]
    assert settings.modules.options == {"mod-x": {"a": 1}}


def test_apply_module_flags_overrides_config(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, modules={"disabled": ["mod-y", "mod-a"]})
    out = apply_module_flags(settings, enable=["mod-y"], disable=["mod-b"])
    assert out.modules.disabled == ["mod-a", "mod-b"]
    assert out.modules.enabled is None
    assert settings.modules.disabled == ["mod-y", "mod-a"]  # 원본 그대로
    assert apply_module_flags(settings) is settings


def test_module_info_from_report() -> None:
    report = ModuleReport(
        id="mod-chat",
        version="1.0.0",
        kind="feature",
        title="Chat",
        state=ModuleState.UNSATISFIED,
        reason="필수 포트 없음: definitions.store",
        missing=("definitions.store",),
        provides=("chat.conversations",),
        requires=("definitions.store",),
        optional=("chat.turn_launcher", "definitions.store"),
        web_roles=("conversations",),
        contracts={"chat": "1.0.0"},
    )
    info = module_info(report)
    assert info.status == "unsatisfied"
    assert info.requires == ["definitions.store", "chat.turn_launcher"]
    assert info.provides == ["chat.conversations"]
    assert info.contracts == {"chat": "1.0.0"}
    assert info.web_roles == ["conversations"]


def test_openapi_documents_modules(tmp_path: Path) -> None:
    schema: dict[str, Any] = create_app(make_settings(tmp_path), environ={}).openapi()
    body = schema["paths"]["/api/v1/modules"]["get"]["responses"]["200"]["content"]
    assert body["application/json"]["schema"]["items"]["$ref"].endswith("/ModuleInfo")
    assert "/api/v1/bootstrap" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]


def test_project_run_link_is_a_server_dependency(tmp_path: Path) -> None:
    """B-12: 서버만 설치해도(휠·`uv tool install`) 프로젝트·실행 연동이 켜진다.

    워크스페이스에서는 모든 패키지가 깔려 있어 드러나지 않으므로 설치 메타데이터도 확인한다.
    """
    import re
    from importlib.metadata import requires

    names = {
        re.split(r"[\s<>=!~;\[(]", r, maxsplit=1)[0] for r in requires("agent-console-server") or []
    }
    assert "agent-console-link-projects-runs" in names
    with server(make_settings(tmp_path)) as client:
        infos = {m.id: m for m in _modules(client)}
        assert infos["link-projects-runs"].status == "active"
