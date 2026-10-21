"""mod-imports: 출처·미리보기·가져오기·설정 경로·비밀 규칙 포트·끄기(design §3R.1.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_imports import (
    DEFINITIONS_STORE,
    SECRET_RULES,
    module,
    resolve_home,
)
from agent_console_mod_imports.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_secret_rules import default_rules

TOKEN = "t" * 32


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "pl.md").write_text(
        "---\nname: pl\ndescription: 설계\n---\n당신은 PL입니다.\n", encoding="utf-8"
    )
    return home


def _assembly(tmp_path: Path, *extra: Any, environ: dict[str, str], **options: Any) -> Assembly:
    base = BaseServices(
        environ=environ,
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    config = ModulesConfig(options={"mod-imports": options}) if options else None
    return assemble([module, local_definitions_module(), *extra], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def test_preview_and_import_from_home_env(tmp_path: Path) -> None:
    home = _home(tmp_path)
    assembly = _assembly(tmp_path, environ={"HOME": str(home)})
    original = (home / ".claude" / "agents" / "pl.md").read_bytes()
    with _client(assembly) as client:
        sources = client.get("/api/v1/resources/import/sources").json()
        user = next(s for s in sources if s["available"])
        preview = client.post("/api/v1/resources/import/preview", json={"source": user["id"]})
        assert preview.status_code == 200
        [agent] = [c for c in preview.json()["candidates"] if c["kind"] == "agent"]
        result = client.post(
            "/api/v1/resources/import",
            json={"source": user["id"], "items": [{"candidate_id": agent["id"]}]},
        ).json()
        assert [i["action"] for i in result["items"]] == ["created"]
        missing = client.post("/api/v1/resources/import/preview", json={"source": "ghost"})
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    assert store.list_ids("agent") == [agent["suggested_id"]]
    assert (home / ".claude" / "agents" / "pl.md").read_bytes() == original


def test_configured_home_and_project_dir_resolve_against_base(tmp_path: Path) -> None:
    _home(tmp_path)
    (tmp_path / "proj" / ".claude").mkdir(parents=True)
    assembly = _assembly(tmp_path, environ={}, home="home", project_dir="proj")
    with _client(assembly) as client:
        roots = {
            s["id"]: s["available"] for s in client.get("/api/v1/resources/import/sources").json()
        }
    assert roots
    assert all(roots.values())
    assert resolve_home(None, {"USERPROFILE": "C:/u"}, None) == Path("C:/u")
    assert resolve_home(None, {}, tmp_path) is None


def test_secret_rules_port_is_passed_to_sources(tmp_path: Path) -> None:
    calls: list[int] = []

    def rules() -> Any:
        calls.append(1)
        return default_rules()

    provider = fake_module(
        "rules", provides=[SECRET_RULES], on_build=lambda ctx: ctx.provide(SECRET_RULES, rules)
    )
    (tmp_path / ".mcp.json").write_text(
        '{"mcpServers": {"x": {"command": "run", "args": ["--header=Bearer abc123456789"]}}}',
        encoding="utf-8",
    )
    assembly = _assembly(tmp_path, provider, environ={})
    with _client(assembly) as client:
        for source in client.get("/api/v1/resources/import/sources").json():
            client.post("/api/v1/resources/import/preview", json={"source": source["id"]})
    assert calls


def test_requires_store_and_disabled_is_404(tmp_path: Path) -> None:
    assert assemble([module]).report[0].missing == ("definitions.store",)
    config = ModulesConfig(disabled=["mod-imports"])
    off = assemble([module, local_definitions_module(workspace=tmp_path)], config)
    with _client(off) as client:
        assert client.get("/api/v1/resources/import/sources").status_code == 404


def test_import_request_project_stamps_scope(tmp_path: Path) -> None:
    """요청 ``project``(계약 0.8.0) → 가져온 정의에 범위를 찍는다. 생략 = 공용(5.2R.31)."""
    home = _home(tmp_path)
    assembly = _assembly(tmp_path, environ={"HOME": str(home)})
    with _client(assembly) as client:
        sources = client.get("/api/v1/resources/import/sources").json()
        user = next(s for s in sources if s["available"])
        preview = client.post("/api/v1/resources/import/preview", json={"source": user["id"]})
        [agent] = [c for c in preview.json()["candidates"] if c["kind"] == "agent"]
        pick = {"candidate_id": agent["id"], "on_conflict": "rename"}
        body = {"source": user["id"], "items": [pick], "project": "app"}
        scoped = client.post("/api/v1/resources/import", json=body).json()
        shared = client.post("/api/v1/resources/import", json={**body, "project": None}).json()
        [first], [second] = scoped["items"], shared["items"]
    from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    assert store.get("agent", first["target_id"]).document["project"] == "app"
    assert "project" not in store.get("agent", second["target_id"]).document
