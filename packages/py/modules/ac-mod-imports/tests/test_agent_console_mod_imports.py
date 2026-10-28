"""mod-imports: 출처·미리보기·가져오기·설정 경로·비밀 규칙 포트·끄기(design §3R.1.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_imports import (
    DEFINITIONS_STORE,
    HOME_REMOVED_REASON,
    SECRET_RULES,
    module,
)
from agent_console_mod_imports.settings import SETTINGS_COMPAT
from agent_console_mod_imports.testing import local_definitions_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ModulesConfig,
    Paths,
    assemble,
    removed_settings,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_secret_rules import default_rules

TOKEN = "t" * 32


def _home(tmp_path: Path) -> Path:
    """빈 HOME 픽스처: ~/.claude/agents·settings.json(전역 구성 — 읽으면 안 된다)."""
    home = tmp_path / "home"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "global.md").write_text(
        "---\nname: global\ndescription: 전역\n---\n전역 에이전트.\n", encoding="utf-8"
    )
    (home / ".claude" / "settings.json").write_text(
        '{"permissions": {"allow": ["Read"]}}', encoding="utf-8"
    )
    return home


def _project(tmp_path: Path) -> Path:
    """등록 프로젝트 폴더의 .claude/agents."""
    project = tmp_path / "proj"
    (project / ".claude" / "agents").mkdir(parents=True)
    (project / ".claude" / "agents" / "pl.md").write_text(
        "---\nname: pl\ndescription: 설계\n---\n당신은 PL입니다.\n", encoding="utf-8"
    )
    return project


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


def test_preview_and_import_from_project(tmp_path: Path) -> None:
    home = _home(tmp_path)
    project = _project(tmp_path)
    assembly = _assembly(tmp_path, environ={"HOME": str(home)}, project_dir="proj")
    original = (project / ".claude" / "agents" / "pl.md").read_bytes()
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
    assert (project / ".claude" / "agents" / "pl.md").read_bytes() == original


def test_user_global_claude_is_not_read(tmp_path: Path) -> None:
    """5.7R.30b: HOME에 ~/.claude/agents가 있어도 출처는 프로젝트 .claude/뿐이고 읽지 않는다."""
    home = _home(tmp_path)
    _project(tmp_path)
    assembly = _assembly(
        tmp_path, environ={"HOME": str(home), "USERPROFILE": str(home)}, project_dir="proj"
    )
    with _client(assembly) as client:
        sources = client.get("/api/v1/resources/import/sources").json()
        assert [s["id"] for s in sources] == ["project-claude"]
        assert all(str(home) not in str(s) for s in sources)
        preview = client.post(
            "/api/v1/resources/import/preview", json={"source": "project-claude"}
        ).json()
        names = {c["name"] for c in preview["candidates"]}
        assert "global" not in names
        assert names == {"pl"}
        gone = client.post("/api/v1/resources/import/preview", json={"source": "user-claude"})
        assert gone.status_code == 404


def test_old_home_setting_is_removed_key(tmp_path: Path) -> None:
    """옛 ``home``은 settings.removed_key 방식으로 이유를 알린다(설정 원문 검사)."""
    data = {"modules": {"options": {"mod-imports": {"home": "~"}}}}
    [found] = removed_settings(data, {"mod-imports": SETTINGS_COMPAT})
    assert found.path == "modules.options.mod-imports.home"
    assert found.message().startswith(HOME_REMOVED_REASON)
    assert (
        removed_settings(
            {"modules": {"options": {"mod-imports": {}}}}, {"mod-imports": SETTINGS_COMPAT}
        )
        == []
    )


def test_project_dir_resolves_against_base(tmp_path: Path) -> None:
    (tmp_path / "proj" / ".claude").mkdir(parents=True)
    assembly = _assembly(tmp_path, environ={}, project_dir="proj")
    with _client(assembly) as client:
        roots = {
            s["id"]: s["available"] for s in client.get("/api/v1/resources/import/sources").json()
        }
    assert roots == {"project-claude": True}


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
    _project(tmp_path)
    assembly = _assembly(tmp_path, environ={}, project_dir="proj")
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
