"""mod-exports: 형식·미리보기·보관 파일·폴더 쓰기·토큰·의존 포트·끄기(design §3R.1.3)."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_exports import (
    EXPORT_DEPENDENCIES,
    DefinitionLookup,
    ExportDependencies,
    LookupExportCatalog,
    module,
    protected_paths,
)
from agent_console_mod_exports.settings import ExportModuleSettings
from agent_console_mod_exports.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

TOKEN = "t" * 32
AGENT = {"id": "rev", "name": "리뷰어", "backend": "fake-agent", "system_prompt": "너는 리뷰어다."}
REQUEST = {"exporter": "claude-dir", "items": [{"kind": "agent", "id": "rev"}]}


def _workspace(tmp_path: Path) -> FileDefinitionStore:
    store = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
    store.create("agent", AGENT)
    return store


def _assembly(tmp_path: Path, *extra: Any, **options: Any) -> Assembly:
    base = BaseServices(
        environ={"HOME": str(tmp_path / "home")},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    config = ModulesConfig(options={"mod-exports": options}) if options else None
    return assemble([module, local_definitions_module(), *extra], config, base=base)


def _client(assembly: Assembly, *, token: bool = True) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    if token:
        client.headers["X-Console-Token"] = TOKEN
    return client


def test_plan_and_archive_without_writing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    with _client(_assembly(tmp_path)) as client:
        assert "claude-dir" in [e["id"] for e in client.get("/api/v1/exporters").json()]
        plan = client.post("/api/v1/exports/plan", json=REQUEST)
        assert plan.status_code == 200, plan.text
        assert ".claude/agents/rev.md" in [f["path"] for f in plan.json()["files"]]
        archive = client.post("/api/v1/exports/archive", json=REQUEST)
        assert archive.headers["content-type"] == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
        assert ".claude/agents/rev.md" in names
        invalid = client.post(
            "/api/v1/exports/plan", json={**REQUEST, "options": {"secret_style": "loud"}}
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["details"]["issues"][0]["path"] == "/options/secret_style"
        assert client.post("/api/v1/exports/plan", json={"exporter": "nope"}).status_code == 404


def test_roots_need_token_and_write_conflicts_report_paths(tmp_path: Path) -> None:
    _workspace(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    assembly = _assembly(tmp_path, roots=[{"id": "o", "path": "out"}], expose_paths=False)
    with _client(assembly, token=False) as anonymous:
        assert anonymous.get("/api/v1/exports/roots").status_code == 401
    with _client(assembly) as client:
        [root] = client.get("/api/v1/exports/roots").json()
        assert root["id"] == "o"
        assert not root.get("path")  # expose_paths: false
        write = {**REQUEST, "root": "o", "subdir": "x"}
        assert client.post("/api/v1/exports/write", json=write).status_code == 200
        (out / "x" / ".claude" / "agents" / "rev.md").write_text("바꿈", encoding="utf-8")
        refused = client.post("/api/v1/exports/write", json=write)
        assert refused.status_code == 409
        assert refused.json()["error"]["details"]["paths"] == [".claude/agents/rev.md"]


@dataclass(frozen=True)
class _Dep:
    kind: str
    id: str
    node_id: str | None = None
    shared: bool = False
    mode: str | None = None
    config_override: dict[str, Any] | None = None


class _Deps:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def dependencies(self, kind: str, id: str) -> Sequence[Any]:
        self.calls.append((kind, id))
        if id == "boom":
            raise RuntimeError("해석 실패")
        return [_Dep("resource", "r1")]


def test_dependencies_port_feeds_the_catalog(tmp_path: Path) -> None:
    store = _workspace(tmp_path)
    deps = _Deps()
    provider = fake_module(
        "deps",
        provides=[EXPORT_DEPENDENCIES],
        on_build=lambda ctx: ctx.provide(EXPORT_DEPENDENCIES, deps),
    )
    with _client(_assembly(tmp_path, provider)) as client:
        assert client.post("/api/v1/exports/plan", json=REQUEST).status_code == 200
    assert ("agent", "rev") in deps.calls
    catalog = LookupExportCatalog(store, deps)
    assert [d.id for d in catalog.dependencies("agent", "rev")] == ["r1"]
    assert catalog.dependencies("agent", "boom") == []
    assert catalog.document("agent", "ghost") is None
    assert catalog.files("agent", "ghost") == {}
    assert LookupExportCatalog(store).dependencies("agent", "rev") == []
    assert isinstance(store, DefinitionLookup)
    assert isinstance(deps, ExportDependencies)


def test_protected_paths_use_home_option_or_environ(tmp_path: Path) -> None:
    cfg = ExportModuleSettings(home=Path("h"), protected=[Path("p")])
    assert protected_paths(cfg, base=tmp_path, environ={}) == [
        tmp_path / "p",
        tmp_path / "h" / ".claude",
    ]
    env = protected_paths(ExportModuleSettings(), base=None, environ={"USERPROFILE": "C:/u"})
    assert env == [Path("C:/u") / ".claude"]


def test_requires_lookup_and_disabled_is_404(tmp_path: Path) -> None:
    assert assemble([module]).report[0].missing == ("definitions.lookup",)
    off = assemble(
        [module, local_definitions_module(workspace=tmp_path)],
        ModulesConfig(disabled=["mod-exports"]),
    )
    with _client(off) as client:
        assert client.get("/api/v1/exporters").status_code == 404
