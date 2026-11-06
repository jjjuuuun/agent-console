"""5.7R.33k: 가져오기 출처 = 등록 프로젝트 폴더, 저장 위치 = 그 프로젝트 공간(기본) 또는 공용.

- 포트 ``projects.folders``가 있는 조립: 출처는 ``?project=``의 등록 폴더 ``.claude``뿐이고 설정
  ``project_dir``는 쓰지 않는다. 등록 안 된 id는 404, ``project`` 없이 이 프로젝트에 가져오기는 422.
- 포트가 없는 조립(모듈 단독): 지금 설정(``project_dir``) 그대로.
- 두 조립 모두 사용자 전역 ``~/.claude`` 출처가 없다(빈 HOME 픽스처에 전역 구성을 둬도).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE
from agent_console_imports.claude import USER_SOURCE_ID
from agent_console_mod_imports import DEFINITIONS_SPACES, PROJECT_FOLDERS, module
from agent_console_mod_imports.testing import local_definitions_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_store import DEFAULT_KINDS, FileDefinitionStore

TOKEN = "t" * 32
API = "/api/v1/resources/import"


@dataclass(frozen=True)
class _Folder:
    id: str
    folder: Path


@dataclass(frozen=True)
class _Folders:
    entries: tuple[_Folder, ...]


class _Spaces:
    """``definitions.spaces`` 흉내: 등록 id → ``<folder>/.agent-console`` 파일 저장소."""

    def __init__(self, folders: dict[str, Path]) -> None:
        self.folders = folders
        self.stores: dict[str, FileDefinitionStore] = {}

    def open(self, project_id: str) -> FileDefinitionStore:
        if project_id not in self.folders:
            raise LookupError(project_id)
        if project_id not in self.stores:
            root = self.folders[project_id] / ".agent-console"
            self.stores[project_id] = FileDefinitionStore(root, DEFAULT_KINDS)
        return self.stores[project_id]


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "global.md").write_text(
        "---\nname: global\ndescription: 전역\n---\n전역 에이전트.\n", encoding="utf-8"
    )
    (home / ".claude" / "CLAUDE.md").write_text("전역 지침", encoding="utf-8")
    return home


def _project(tmp_path: Path, name: str, agent: str) -> Path:
    project = tmp_path / name
    (project / ".claude" / "agents").mkdir(parents=True)
    (project / ".claude" / "agents" / f"{agent}.md").write_text(
        f"---\nname: {agent}\ndescription: 설명\n---\n당신은 {agent}입니다.\n", encoding="utf-8"
    )
    return project


def _projects_module(folders: dict[str, Path], spaces: _Spaces | None) -> Any:
    value = _Folders(tuple(_Folder(k, v) for k, v in folders.items()))

    def build(ctx: Any) -> Any:
        from agent_console_modkit import ModuleParts

        ctx.provide(PROJECT_FOLDERS, lambda: value)
        if spaces is not None:
            ctx.provide(DEFINITIONS_SPACES, spaces)
        return ModuleParts()

    provides = [PROJECT_FOLDERS] + ([DEFINITIONS_SPACES] if spaces is not None else [])
    return fake_module("fake-projects", kind="testing", provides=provides, on_build=build)


def _assembly(tmp_path: Path, *extra: Any, home: Path, **options: Any) -> Assembly:
    base = BaseServices(
        environ={"HOME": str(home), "USERPROFILE": str(home)},
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


def _no_global(sources: list[dict[str, Any]], home: Path) -> None:
    assert all(s["id"] != USER_SOURCE_ID for s in sources)
    assert not any(str(s.get("path") or "").startswith(str(home)) for s in sources)


def _import_agent(client: TestClient, project: str, **params: str) -> dict[str, Any]:
    q = {"project": project, **params}
    [source] = [s for s in client.get(f"{API}/sources", params=q).json() if s["available"]]
    preview = client.post(f"{API}/preview", params=q, json={"source": source["id"]}).json()
    [agent] = [c for c in preview["candidates"] if c["kind"] == "agent"]
    body = {"source": source["id"], "items": [{"candidate_id": agent["id"]}], "project": "x"}
    result = client.post(API, params=q, json=body)
    assert result.status_code == 200, result.text
    [item] = result.json()["items"]
    assert item["action"] in ("created", "renamed"), item
    return dict(item)


def test_with_projects_sources_are_registered_folders_only(tmp_path: Path) -> None:
    home = _home(tmp_path)
    a = _project(tmp_path, "a", "alpha")
    b = _project(tmp_path, "b", "beta")
    _project(tmp_path, "unregistered", "gamma")
    spaces = _Spaces({"a": a, "b": b})
    assembly = _assembly(
        tmp_path, _projects_module({"a": a, "b": b}, spaces), home=home, project_dir="unregistered"
    )
    with _client(assembly) as client:
        sources = client.get(f"{API}/sources", params={"project": "a"}).json()
        _no_global(sources, home)
        assert sources
        assert all(str(s["path"]).startswith(str(a)) for s in sources)
        # project 없음 → 프로젝트 .claude 출처 없음(설정 project_dir 폴더를 대신 쓰지 않는다),
        # 이 프로젝트에 가져오기는 422, 등록 안 된 id → 404
        assert client.get(f"{API}/sources").json() == []
        nothing = client.post(f"{API}/preview", json={"source": "project-claude"})
        assert nothing.status_code == 404
        missing = client.post(
            API, params={"target": "project"}, json={"source": "project-claude", "items": []}
        )
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "project.required"
        unknown = client.get(f"{API}/sources", params={"project": "unregistered"})
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
        assert unknown.json()["error"]["details"] == {"project_id": "unregistered"}
        bad = client.post(API, params={"project": "nope"}, json={"source": "x", "items": []})
        assert bad.status_code == 404

        # 기본 저장 위치 = 그 프로젝트 공간(<folder>/.agent-console), 공용은 그대로
        item = _import_agent(client, "a")
        stored = spaces.open("a").get("agent", item["target_id"]).document
        assert stored["name"] == "alpha"
        assert "project" not in stored  # 프로젝트 공간에는 옛 범위 필드를 찍지 않는다
        library = FileDefinitionStore(tmp_path / "ws", DEFAULT_KINDS)
        assert library.list_ids("agent") == []
        assert (a / ".agent-console").is_dir()

        # target=library → 공용(라이브러리)
        shared = _import_agent(client, "b", target="library")
        assert library.get("agent", shared["target_id"]).document["name"] == "beta"
        assert spaces.open("b").list_ids("agent") == []
        bad_target = client.post(
            f"{API}/preview", params={"project": "a", "target": "zz"}, json={"source": "x"}
        )
        assert bad_target.status_code == 422


def test_projects_without_spaces_can_only_import_to_library(tmp_path: Path) -> None:
    home = _home(tmp_path)
    a = _project(tmp_path, "a", "alpha")
    assembly = _assembly(tmp_path, _projects_module({"a": a}, None), home=home)
    with _client(assembly) as client:
        q = {"project": "a"}
        [source] = client.get(f"{API}/sources", params=q).json()
        body = {"source": source["id"], "items": []}
        refused = client.post(API, params=q, json=body)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"
        ok = client.post(API, params={**q, "target": "library"}, json=body)
        assert ok.status_code == 200


@pytest.mark.parametrize("project_dir", [None, "proj"])
def test_without_projects_uses_settings_and_no_global_source(
    tmp_path: Path, project_dir: str | None
) -> None:
    home = _home(tmp_path)
    _project(tmp_path, "proj", "alpha")
    options = {"project_dir": project_dir} if project_dir else {}
    assembly = _assembly(tmp_path, home=home, **options)
    with _client(assembly) as client:
        sources = client.get(f"{API}/sources").json()
        _no_global(sources, home)
        expected = tmp_path / project_dir if project_dir else tmp_path
        assert all(str(s["path"]).startswith(str(expected)) for s in sources)
        # 프로젝트 기능이 없으면 project·target=project를 받지 않는다(조용히 공용에 쓰지 않음)
        refused = client.get(f"{API}/sources", params={"project": "a"})
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "feature_unavailable"


def test_module_starts_alone_with_optional_ports_missing(tmp_path: Path) -> None:
    assembly = assemble([module, local_definitions_module(workspace=tmp_path / "ws")])
    [report] = [r for r in assembly.report if r.id == "mod-imports"]
    assert report.state.value == "active"
    assert set(module.descriptor.optional) >= {PROJECT_FOLDERS, DEFINITIONS_SPACES}
