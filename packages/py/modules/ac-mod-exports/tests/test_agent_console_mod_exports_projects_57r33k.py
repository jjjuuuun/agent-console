"""5.7R.33k: 내보내기 쓰기 대상 = 등록 프로젝트 폴더, 원본 기본 = 그 프로젝트 공간.

- 포트 ``projects.folders``가 있는 조립: 루트 = 등록 폴더(id = 등록 id), 설치자 ``roots``는 쓰지
  않는다. 등록 안 된 루트·프로젝트는 404, 루트 밖 ``subdir``는 422. 원본은 ``?project=`` 공간(기본)
  또는 ``source=library``.
- 포트가 없는 조립(모듈 단독): 설치자 ``roots``와 라이브러리 그대로.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_mod_exports import DEFINITIONS_SPACES, PROJECT_FOLDERS, module
from agent_console_mod_exports.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModuleParts, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

TOKEN = "t" * 32
API = "/api/v1/exports"
LIB_AGENT = {"id": "rev", "name": "공용 리뷰어", "backend": "fake-agent", "system_prompt": "공용"}
PRJ_AGENT = {"id": "rev", "name": "사본 리뷰어", "backend": "fake-agent", "system_prompt": "사본"}
REQUEST = {"exporter": "claude-dir", "items": [{"kind": "agent", "id": "rev"}]}


@dataclass(frozen=True)
class _Folder:
    id: str
    folder: Path


@dataclass(frozen=True)
class _Folders:
    entries: tuple[_Folder, ...]


class _Spaces:
    def __init__(self, folders: dict[str, Path]) -> None:
        self.stores = {
            k: FileDefinitionStore(v / ".agent-console", DEFAULT_KINDS) for k, v in folders.items()
        }

    def open(self, project_id: str) -> FileDefinitionStore:
        if project_id not in self.stores:
            raise LookupError(project_id)
        return self.stores[project_id]


def _projects_module(folders: dict[str, Path], spaces: _Spaces) -> Any:
    value = _Folders(tuple(_Folder(k, v) for k, v in folders.items()))

    def build(ctx: Any) -> ModuleParts:
        ctx.provide(PROJECT_FOLDERS, lambda: value)
        ctx.provide(DEFINITIONS_SPACES, spaces)
        return ModuleParts()

    return fake_module(
        "fake-projects",
        kind="testing",
        provides=[PROJECT_FOLDERS, DEFINITIONS_SPACES],
        on_build=build,
    )


def _assembly(tmp_path: Path, *extra: Any, **options: Any) -> Assembly:
    base = BaseServices(
        environ={"HOME": str(tmp_path / "home")},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    config = ModulesConfig(options={"mod-exports": options}) if options else None
    return assemble([module, local_definitions_module(), *extra], config, base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


def _setup(tmp_path: Path) -> tuple[Path, Path, _Spaces]:
    FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS).create("agent", LIB_AGENT)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    spaces = _Spaces({"a": a, "b": b})
    spaces.open("a").create("agent", PRJ_AGENT)
    return a, b, spaces


def _zip_text(content: bytes, name: str) -> str:
    return zipfile.ZipFile(io.BytesIO(content)).read(name).decode("utf-8")


def test_roots_are_registered_project_folders(tmp_path: Path) -> None:
    a, b, spaces = _setup(tmp_path)
    installer = tmp_path / "installer-root"
    installer.mkdir()
    assembly = _assembly(
        tmp_path,
        _projects_module({"a": a, "b": b}, spaces),
        roots=[{"id": "out", "path": str(installer)}],
    )
    with _client(assembly) as client:
        roots = client.get(f"{API}/roots").json()
        assert [(r["id"], r["path"]) for r in roots] == [("a", str(a)), ("b", str(b))]

        # 원본 기본 = 그 프로젝트 사본, 쓰기 대상 = 등록 폴더
        body = {**REQUEST, "root": "a", "subdir": ""}
        written = client.post(f"{API}/write", params={"project": "a"}, json=body)
        assert written.status_code == 200, written.text
        text = (a / ".claude" / "agents" / "rev.md").read_text(encoding="utf-8")
        assert "사본" in text
        assert "공용" not in text

        # source=library → 공용 원본을 다른 등록 폴더에
        body_b = {**REQUEST, "root": "b"}
        lib = client.post(f"{API}/write", params={"project": "a", "source": "library"}, json=body_b)
        assert lib.status_code == 200, lib.text
        assert "공용" in (b / ".claude" / "agents" / "rev.md").read_text(encoding="utf-8")

        # zip 내려받기: 원본 선택이 그대로 적용
        archive = client.post(f"{API}/archive", params={"project": "a"}, json=REQUEST)
        assert "사본" in _zip_text(archive.content, ".claude/agents/rev.md")
        shared = client.post(f"{API}/archive", json=REQUEST)  # project 없음 = 공용
        assert "공용" in _zip_text(shared.content, ".claude/agents/rev.md")

        # 설치자 roots·등록 안 된 루트·프로젝트는 쓰지 않는다
        outside = client.post(f"{API}/write", json={**REQUEST, "root": "out"})
        assert outside.status_code == 404
        assert list(installer.iterdir()) == []
        unknown = client.post(f"{API}/plan", params={"project": "zz"}, json=REQUEST)
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
        escape = client.post(f"{API}/write", json={**REQUEST, "root": "a", "subdir": "../x"})
        assert escape.status_code == 422
        assert not (tmp_path / "x").exists()
        need = client.post(f"{API}/plan", params={"source": "project"}, json=REQUEST)
        assert need.status_code == 422
        assert need.json()["error"]["code"] == "project.required"


def test_without_projects_installer_roots_and_library(tmp_path: Path) -> None:
    FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS).create("agent", LIB_AGENT)
    out = tmp_path / "out"
    out.mkdir()
    assembly = _assembly(tmp_path, roots=[{"id": "out", "path": str(out)}])
    with _client(assembly) as client:
        assert [r["id"] for r in client.get(f"{API}/roots").json()] == ["out"]
        ok = client.post(f"{API}/write", json={**REQUEST, "root": "out"})
        assert ok.status_code == 200, ok.text
        assert "공용" in (out / ".claude" / "agents" / "rev.md").read_text(encoding="utf-8")
        refused = client.post(f"{API}/plan", params={"project": "a"}, json=REQUEST)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"


def test_module_starts_alone_with_optional_ports_missing() -> None:
    assembly = assemble([module, local_definitions_module()])
    [report] = [r for r in assembly.report if r.id == "mod-exports"]
    assert report.state.value == "active"
    assert set(module.descriptor.optional) >= {PROJECT_FOLDERS, DEFINITIONS_SPACES}
