"""link-projects-sdd 6R.14 완료 기준.

프로젝트 공간 → ``sdd.spaces``. 서버 조립(mod-projects + mod-sdd)에서 스펙이 각 폴더에만,
다른 workspace에서 같은 폴더 → 스펙·규칙 그대로, 쓰기 불가·폴더 없음·깨진 매니페스트 409,
폴더 밖 가져오기 거부, 연동 끔 → ``sdd.spaces_unavailable``(단독 루트로 새지 않음),
``spec_root`` = 구성 폴더 + ``spec_dir``, 모듈 단독 기동.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ErrorCodes, ProjectManifest
from agent_console_link_projects_sdd import (
    MODULE_ID,
    SDD_SPACES,
    ProjectSddSpaces,
    ProjectSpecFiles,
    UnsafeSpaceRoot,
    config_dir_of,
    module,
)
from agent_console_link_projects_sdd.testing import FolderSpaces, folder_spaces_module
from agent_console_mod_projects import ProjectsModule
from agent_console_mod_sdd import module as sdd_module
from agent_console_mod_sdd.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    Module,
    ModulesConfig,
    ModuleState,
    Paths,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_project_space import (
    FolderMissing,
    LocalFiles,
    ManifestInvalid,
    init_space,
)
from agent_console_sdd import definition_kinds
from agent_console_store import FileDefinitionStore, InMemoryVersionRepository

API = "/api/v1"
TOKEN = "s" * 32
CFG = ".agent-console"

TEMPLATE: dict[str, Any] = {
    "kind": "spec-template",
    "id": "flow",
    "name": "흐름",
    "documents": [
        {"id": "req", "title": "요구", "file": "req.md", "roles": ["requirements"]},
        {"id": "tasks", "title": "작업", "file": "tasks.md", "roles": ["tasks"]},
    ],
    "rules": {
        "document_states": [{"id": "draft"}, {"id": "ok", "label": "확인"}],
        "initial_document_state": "draft",
        "transitions": [{"from": "draft", "to": "ok", "by": ["human"]}],
    },
}
"""테스트 데이터(패키지 기본에 기대지 않음)."""
REQ = "# 요구\n\n**R1** 하나\n"
TASKS = "# 작업\n\n- [ ] 1 첫 작업 [req: R1]\n- [ ] 2 둘째 [depends: 1]\n"


def _write_template(config_root: Path) -> None:
    store = FileDefinitionStore(
        config_root,
        definition_kinds(
            spec_kind="spec",
            spec_directory="specs",
            template_kind="spec-template",
            template_directory="spec-templates",
        ),
    )
    created = store.create("spec-template", TEMPLATE)
    store.write_files(
        "spec-template",
        "flow",
        {"req.md": REQ.encode(), "tasks.md": TASKS.encode()},
        expected_version=created.version_hash,
    )


def _host(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


@contextmanager
def _app(
    root: Path,
    *,
    disabled: tuple[str, ...] = (),
    options: Mapping[str, Any] | None = None,
) -> Iterator[tuple[TestClient, Assembly]]:
    """앱 조립 하나(workspace = ``root/ws``): mod-projects + mod-sdd + 이 연동."""
    base = BaseServices(
        paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"),
    )
    mods: list[Module] = [
        ProjectsModule(versions=lambda _pid, _root: InMemoryVersionRepository()),
        sdd_module,
        static_settings_module({}),
        module,
    ]
    config = ModulesConfig(disabled=list(disabled), options=dict(options or {}))
    assembly = assemble(mods, config, base=base)
    with _host(assembly) as client:
        yield client, assembly


def _register(client: TestClient, folder: Path, project_id: str) -> None:
    created = client.post(f"{API}/projects", json={"folder": str(folder), "id": project_id})
    assert created.status_code == 201, created.text


def _state(assembly: Assembly) -> ModuleState:
    status = assembly.status(MODULE_ID)
    assert status is not None
    return status.state


def _code(res: Any) -> str:
    return str(res.json()["error"]["code"])


# ---- 부품(HTTP 없이) ------------------------------------------------------------------


def test_open_maps_project_space(tmp_path: Path) -> None:
    folder = tmp_path / "a"
    folder.mkdir()
    spaces = ProjectSddSpaces(lambda: FolderSpaces({"a": folder}, config_dir="cfg/app"))
    space = spaces.open("a")
    assert space.config_dir == "cfg/app"
    assert space.folder == folder
    assert space.config_writable is True
    assert isinstance(space.files, ProjectSpecFiles)
    assert space.files.reserved == ("cfg/app",)
    assert not (folder / "cfg").exists()  # 열기만으로 만들지 않는다


def test_open_errors(tmp_path: Path) -> None:
    with pytest.raises(LookupError):
        ProjectSddSpaces(lambda: None).open("a")
    with pytest.raises(LookupError):
        ProjectSddSpaces(lambda: FolderSpaces({})).open("a")
    with pytest.raises(FolderMissing) as missing:
        ProjectSddSpaces(lambda: FolderSpaces({"a": tmp_path / "none"})).open("a")
    assert missing.value.code == ErrorCodes.PROJECT_FOLDER_MISSING
    broken = tmp_path / "b"
    (broken / CFG).mkdir(parents=True)
    (broken / CFG / "project.yaml").write_text("id: [\n", encoding="utf-8")
    with pytest.raises(ManifestInvalid) as bad:
        ProjectSddSpaces(lambda: FolderSpaces({"b": broken})).open("b")
    assert bad.value.code == ErrorCodes.PROJECT_MANIFEST_INVALID
    assert HTTP_STATUS_BY_ERROR_CODE[bad.value.code] == 409


def test_extra_reserved_dirs_and_readonly(tmp_path: Path) -> None:
    class ReadonlyFiles(LocalFiles):
        def is_writable(self, path: Path) -> bool:
            return False

    spaces = ProjectSddSpaces(
        lambda: FolderSpaces({"a": tmp_path}, files=ReadonlyFiles()), reserved=[".git"]
    )
    space = spaces.open("a")
    assert space.config_writable is False
    assert isinstance(space.files, ProjectSpecFiles)
    assert space.files.reserved == (CFG, ".git")
    assert space.files.writable is False


def test_config_dir_of_refuses_root_outside() -> None:
    class Odd:
        folder = Path("/w/app")
        root = Path("/w/other")

    with pytest.raises(UnsafeSpaceRoot):
        config_dir_of(Odd())  # type: ignore[arg-type]

    class Same:
        folder = Path("/w/app")
        root = Path("/w/app")

    with pytest.raises(UnsafeSpaceRoot):
        config_dir_of(Same())  # type: ignore[arg-type]


# ---- 서버 조립 ------------------------------------------------------------------------


def test_specs_stay_in_each_project_folder(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with _app(tmp_path / "app1") as (client, assembly):
        assert _state(assembly) is ModuleState.ACTIVE
        assert assembly.port(SDD_SPACES) is not None
        _register(client, a, "pa")
        _register(client, b, "pb")
        assert client.post(f"{API}/sdd/specs?project=pa", json={"name": "Alpha"}).status_code == 201
        assert client.post(f"{API}/sdd/specs?project=pb", json={"name": "Beta"}).status_code == 201
        assert [s["id"] for s in client.get(f"{API}/sdd/specs?project=pa").json()] == ["alpha"]
        assert [s["id"] for s in client.get(f"{API}/sdd/specs?project=pb").json()] == ["beta"]
        assert client.get(f"{API}/sdd/specs").json() == []  # 단독 루트와 섞이지 않는다
        info = client.get(f"{API}/sdd/info?project=pa").json()
        assert info["spec_root"] == f"{CFG}/specs"
        assert info["writable"] is True
        assert info["capabilities"]["import_export"] is True
    assert (a / CFG / "specs" / "alpha").is_dir()
    assert not (a / CFG / "specs" / "beta").exists()
    assert (b / CFG / "specs" / "beta").is_dir()
    assert not (tmp_path / "app1" / "ws" / "sdd").exists()


def test_same_folder_in_another_workspace_keeps_specs_and_rules(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with _app(tmp_path / "app1") as (client, _):
        _register(client, folder, "p1")
        _write_template(folder / CFG)
        made = client.post(f"{API}/sdd/specs?project=p1", json={"name": "Pay", "template": "flow"})
        assert made.status_code == 201, made.text
        first = client.get(f"{API}/sdd/specs/pay?project=p1").json()
    with _app(tmp_path / "app2") as (client, _):
        _register(client, folder, "other-id")
        second = client.get(f"{API}/sdd/specs/pay?project=other-id")
        assert second.status_code == 200, second.text
        view = second.json()
        assert view["spec"]["rules"] == first["spec"]["rules"]
        assert [t["key"] for t in view["index"]["tasks"]] == ["1", "2"]
        assert {s["id"]: s["label"] for s in view["document_states"]} == {
            "draft": "draft",
            "ok": "확인",
        }
        doc = client.get(f"{API}/sdd/specs/pay/documents/tasks?project=other-id").json()
        assert doc["content"] == TASKS
        templates = client.get(f"{API}/sdd/templates?project=other-id").json()
        assert [t["id"] for t in templates] == ["flow"]


def test_folder_missing_and_broken_manifest_are_409(tmp_path: Path) -> None:
    gone, broken = tmp_path / "gone", tmp_path / "broken"
    gone.mkdir()
    broken.mkdir()
    with _app(tmp_path / "app") as (client, _):
        _register(client, gone, "g")
        _register(client, broken, "b")
        assert client.get(f"{API}/sdd/specs?project=b").status_code == 200
        shutil.rmtree(gone)
        res = client.get(f"{API}/sdd/specs?project=g")
        assert res.status_code == 409
        assert _code(res) == ErrorCodes.PROJECT_FOLDER_MISSING
        (broken / CFG / "project.yaml").write_text("id: [\n", encoding="utf-8")
        res = client.get(f"{API}/sdd/info?project=b")
        assert res.status_code == 409
        assert _code(res) == ErrorCodes.PROJECT_MANIFEST_INVALID
        made = client.post(f"{API}/sdd/specs?project=b", json={"name": "X"})
        assert made.status_code == 409
        unknown = client.get(f"{API}/sdd/specs?project=nope")
        assert unknown.status_code == 404
        assert _code(unknown) == ErrorCodes.PROJECT_NOT_FOUND
    assert not (broken / CFG / "specs").exists()


def test_readonly_folder_is_409_and_not_written(tmp_path: Path) -> None:
    class ReadonlyFiles(LocalFiles):
        def is_writable(self, path: Path) -> bool:
            return False

    folder = tmp_path / "ro"
    folder.mkdir()
    (folder / "plan.md").write_text("# 계획\n", encoding="utf-8")
    init_space(folder, manifest=ProjectManifest(id="ro", name="ro"))
    _write_template(folder / CFG)
    base = BaseServices(paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path))
    mods: list[Module] = [
        sdd_module,
        static_settings_module({}),
        folder_spaces_module({"ro": folder}, files=ReadonlyFiles()),
        module,
    ]
    before = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
    with _host(assemble(mods, None, base=base)) as client:
        info = client.get(f"{API}/sdd/info?project=ro").json()
        assert info["writable"] is False
        made = client.post(f"{API}/sdd/specs?project=ro", json={"name": "X", "template": "flow"})
        assert made.status_code == 409, made.text
        assert _code(made) == ErrorCodes.PROJECT_CONFIG_READONLY
        imported = client.post(
            f"{API}/sdd/specs/import?project=ro", json={"name": "I", "files": ["plan.md"]}
        )
        assert imported.status_code == 409
        assert _code(imported) == ErrorCodes.PROJECT_CONFIG_READONLY
        listing = client.get(f"{API}/sdd/import/files?project=ro")
        assert listing.status_code == 200  # 보기는 된다
        assert [f["name"] for f in listing.json()["files"]] == ["plan.md"]
    after = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
    assert after == before


def test_import_outside_folder_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    (folder / "docs").mkdir(parents=True)
    (folder / "docs" / "plan.md").write_text("# 계획\n- [ ] 1 하나\n", encoding="utf-8")
    (tmp_path / "outside.md").write_text("# 밖\n", encoding="utf-8")
    links = os.name != "nt"
    if links:
        (folder / "docs" / "link.md").symlink_to(tmp_path / "outside.md")
    with _app(tmp_path / "app") as (client, _):
        _register(client, folder, "p")
        for bad in ["../outside.md", str(tmp_path / "outside.md"), f"{CFG}/project.yaml"]:
            res = client.post(
                f"{API}/sdd/specs/import?project=p", json={"name": "Bad", "files": [bad]}
            )
            assert res.status_code == 422, (bad, res.text)
            assert _code(res) == ErrorCodes.FOLDERS_INVALID_PATH
        if links:
            res = client.post(
                f"{API}/sdd/specs/import?project=p",
                json={"name": "Bad", "files": ["docs/link.md"]},
            )
            assert res.status_code == 422
            assert res.json()["error"]["details"]["reason"] == "link"
        listing = client.get(f"{API}/sdd/import/files?project=p&path=docs").json()
        assert [f["name"] for f in listing["files"]] == ["plan.md"]  # 링크는 목록에도 없다
        assert client.get(f"{API}/sdd/import/files?project=p&path={CFG}").status_code == 422
        assert client.get(f"{API}/sdd/import/files?project=p&path=..").status_code == 422
        ok = client.post(
            f"{API}/sdd/specs/import?project=p", json={"name": "Plan", "files": ["docs/plan.md"]}
        )
        assert ok.status_code == 201, ok.text
        out = client.post(
            f"{API}/sdd/specs/plan/export?project=p", json={"to_dir": "out", "overwrite": False}
        )
        assert out.status_code == 200, out.text
        assert (folder / "out" / "plan.md").is_file()
        for to_dir in (CFG, f"{CFG}/x", "../x"):
            refused = client.post(
                f"{API}/sdd/specs/plan/export?project=p",
                json={"to_dir": to_dir, "overwrite": True},
            )
            assert refused.status_code == 422, (to_dir, refused.text)
    assert not (tmp_path / "x").exists()
    assert not (folder / CFG / "x").exists()


def test_link_disabled_gives_spaces_unavailable(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with _app(tmp_path / "app", disabled=(MODULE_ID,)) as (client, assembly):
        assert _state(assembly) is ModuleState.DISABLED
        _register(client, folder, "p")
        for res in (
            client.get(f"{API}/sdd/info?project=p"),
            client.get(f"{API}/sdd/specs?project=p"),
            client.post(f"{API}/sdd/specs?project=p", json={"name": "X"}),
        ):
            assert res.status_code == 409
            assert _code(res) == ErrorCodes.SDD_SPACES_UNAVAILABLE
        assert client.get(f"{API}/sdd/specs").json() == []
    assert not (tmp_path / "app" / "ws" / "sdd").exists()  # 단독 루트로 새지 않는다
    assert not (folder / CFG / "specs").exists()


def test_link_off_without_projects_module(tmp_path: Path) -> None:
    with _app(tmp_path / "app", disabled=("mod-projects",)) as (client, assembly):
        assert _state(assembly) is ModuleState.UNSATISFIED
        res = client.get(f"{API}/sdd/specs?project=p")
        assert _code(res) == ErrorCodes.SDD_SPACES_UNAVAILABLE


def test_spec_root_follows_config_dir_and_spec_dir(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    options = {"mod-projects": {"config_dir": ".ac2"}, "mod-sdd": {"spec_dir": "design-specs"}}
    with _app(tmp_path / "app", options=options) as (client, _):
        _register(client, folder, "p")
        info = client.get(f"{API}/sdd/info?project=p").json()
        assert info["spec_root"] == ".ac2/design-specs"
        made = client.post(f"{API}/sdd/specs?project=p", json={"name": "S"})
        assert made.status_code == 201, made.text
        assert made.json()["directory"] == ".ac2/design-specs/s"
        refused = client.post(
            f"{API}/sdd/specs/s/export?project=p", json={"to_dir": ".ac2/x", "overwrite": True}
        )
        assert refused.status_code == 422
    assert (folder / ".ac2" / "design-specs" / "s").is_dir()
    assert not (folder / CFG).exists()


def test_standalone_check() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_projects_sdd", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
