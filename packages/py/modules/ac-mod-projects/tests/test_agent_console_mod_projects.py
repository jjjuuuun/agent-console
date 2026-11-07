"""mod-projects 2(5.7R.33f): 등록·폴더·선택 창·복사·포트(design §PI.10).

실제 OS 폴더 선택 창은 띄우지 않는다(가짜 실행기·가짜 제공자). 참조 추출은 테스트 규칙(문서의
``uses: [[kind, id], ...]``)을 ``definitions.references``로 준다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import (
    HTTP_STATUS_BY_ERROR_CODE,
    FolderPickRequest,
    KnownIssueCodes,
    ProjectView,
)
from agent_console_local_folders import CancelSignal, CommandOutcome, LocalFileSystem
from agent_console_mod_projects import (
    DEFINITIONS_SPACES,
    DEFINITIONS_STORE,
    PROJECT_FOLDERS,
    PROJECTS_LOOKUP,
    PROJECTS_SPACES,
    FolderDialogSettings,
    FolderPicker,
    ProjectsModule,
)
from agent_console_mod_projects.testing import local_definitions_module, references_module
from agent_console_modkit import Assembly, BaseServices, ModulesConfig, Paths, assemble
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_modkit.testing import fake_module
from agent_console_project_space import FolderMissing, ProjectSpace
from agent_console_project_space.testing import snapshot_tree
from agent_console_store import RecordsState, load_yaml_text, to_plain

TOKEN = "t" * 32
API = "/api/v1"
CFG = ".agent-console"


def uses(kind: str, document: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    """테스트 참조 규칙: 문서 ``uses``의 ``[종류, id]`` 목록."""
    return [(k, i) for k, i in document.get("uses", [])]


class FakeRunner:
    """가짜 명령 실행기(창을 띄우지 않음). ``gate``가 있으면 그것이 켜질 때까지 기다린다."""

    def __init__(self, outcome: CommandOutcome, gate: threading.Event | None = None) -> None:
        self.outcome = outcome
        self.gate = gate
        self.started = threading.Event()
        self.calls: list[list[str]] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout: float,
        cancel: CancelSignal | None = None,
    ) -> CommandOutcome:
        self.calls.append(list(argv))
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        return self.outcome


FAKE_SPEC = {
    "id": "fake-dialog",
    "platforms": ["linux"],
    "requires": ["fakepick"],
    "argv": ["fakepick"],
    "cancel_exit_codes": [1],
}


def _which(name: str) -> str | None:
    return f"/usr/bin/{name}" if name == "fakepick" else None


def _module(runner: FakeRunner | None = None) -> ProjectsModule:
    return ProjectsModule(
        runner=runner or FakeRunner(CommandOutcome(1)),
        dialog_providers=[],
        platform="linux",
        which=_which,
    )


def _assembly(
    tmp_path: Path,
    *,
    options: Mapping[str, Any] | None = None,
    runner: FakeRunner | None = None,
    definitions: bool = True,
    extra: Sequence[Any] = (),
) -> Assembly:
    mods: list[Any] = [_module(runner), *extra]
    if definitions:
        mods.append(local_definitions_module(workspace=tmp_path / "ws"))
        mods.append(references_module(uses))
    opts = {
        "snapshot_ttl_seconds": 0,
        "folder_dialog": {"providers": [FAKE_SPEC], "include_default_providers": False},
        **(options or {}),
    }
    base = BaseServices(
        environ={"HOME": str(tmp_path)},
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state"),
    )
    return assemble(mods, ModulesConfig(options={"mod-projects": opts}), base=base)


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


@pytest.fixture
def work(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def _folder(work: Path, name: str) -> Path:
    path = work / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _register(client: TestClient, folder: Path, **extra: Any) -> dict[str, Any]:
    response = client.post(f"{API}/projects", json={"folder": str(folder), **extra})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert response.headers["ETag"] == f'"{body["version_hash"]}"'
    return body


def _yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = to_plain(load_yaml_text(path.read_text("utf-8"), path.name))
    return data


def _manifest(folder: Path, **values: Any) -> None:
    (folder / CFG).mkdir(parents=True, exist_ok=True)
    doc = {"format": 1, **values}
    (folder / CFG / "project.yaml").write_text(json.dumps(doc), encoding="utf-8")


# ---------------------------------------------------------------- 등록


def test_register_creates_manifest_and_gitignore(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "My App")
    with _client(_assembly(tmp_path)) as client:
        view = _register(client, app)
        ProjectView.model_validate(view)
        assert view["project"]["id"] == "my-app"
        assert view["project"]["name"] == "My App"
        assert view["project"]["folder"] == str(app)
        assert view["status"] == "ready"
        assert view["config_writable"] is True
        assert view["config_dir"] == CFG
        assert view["manifest_id"] == "my-app"
        assert {"graph", "agent", "resource"} <= set(view["kinds"])
        assert "settings" not in view["kinds"]
        # 기록 연동이 없으면 쓸 수 없음 + 이유
        assert view["records_state"] == "unavailable"
        assert view["records_writable"] is False
        assert view["records_issue"]["details"]["reason"] == "link_disabled"
        assert (app / CFG / "project.yaml").is_file()
        assert (app / CFG / ".gitignore").is_file()
        registry = _yaml(tmp_path / "ws/projects/my-app.yaml")
        assert set(registry) <= {"kind", "id", "folder", "labels"}
        assert [v["project"]["id"] for v in client.get(f"{API}/projects").json()] == ["my-app"]


def test_user_gitignore_is_kept_and_append_only_adds(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    (app / CFG).mkdir()
    (app / CFG / ".gitignore").write_text("mine.txt\n/.state/\n", encoding="utf-8")
    with _client(_assembly(tmp_path)) as client:
        view = _register(client, app)
        assert (app / CFG / ".gitignore").read_text("utf-8") == "mine.txt\n/.state/\n"
        outdated = [
            i for i in view["issues"] if i["code"] == KnownIssueCodes.PROJECT_GITIGNORE_OUTDATED
        ]
        assert outdated
        assert outdated[0]["details"]["lines"]
        after = client.post(f"{API}/projects/app/gitignore/append")
        assert after.status_code == 200, after.text
        text = (app / CFG / ".gitignore").read_text("utf-8")
        assert text.startswith("mine.txt\n/.state/\n")
        assert not [
            i
            for i in after.json()["issues"]
            if i["code"] == KnownIssueCodes.PROJECT_GITIGNORE_OUTDATED
        ]


def test_adopt_manifest_and_worktree_gets_suffix(tmp_path: Path, work: Path) -> None:
    one = _folder(work, "wt-1")
    two = _folder(work, "wt-2")
    for folder in (one, two):
        _manifest(folder, id="pay", name="결제")
        (folder / CFG / ".gitignore").write_text("x\n", encoding="utf-8")
    before = snapshot_tree(two)
    with _client(_assembly(tmp_path)) as client:
        first = _register(client, one)
        second = _register(client, two)
        assert first["project"]["id"] == "pay"
        assert second["project"]["id"] == "pay-2"
        assert second["project"]["name"] == "결제"
        assert second["manifest_id"] == "pay"
    assert snapshot_tree(two) == before


def test_conflicts_archive_and_reregister(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    inner = _folder(app, "inner")
    with _client(_assembly(tmp_path)) as client:
        _register(client, app)
        same = client.post(f"{API}/projects", json={"folder": str(app)})
        assert same.status_code == 409
        assert same.json()["error"]["code"] == "project.folder_taken"
        child = client.post(f"{API}/projects", json={"folder": str(inner)})
        assert child.status_code == 409
        err = child.json()["error"]
        assert err["code"] == "project.folder_overlaps"
        assert err["details"] == {
            "project_id": "app",
            "relation": "parent",
            "archived": False,
            "folder": str(app),
        }
        # 등록 해제 = 보관(폴더 내용 그대로)
        tree = snapshot_tree(app)
        assert client.delete(f"{API}/projects/app").status_code == 204
        assert snapshot_tree(app) == tree
        [view] = client.get(f"{API}/projects").json()
        assert view["project"]["archived"] is True
        assert view["project"]["archived_at"] is not None
        again = client.post(f"{API}/projects", json={"folder": str(app)})
        assert again.status_code == 409
        assert again.json()["error"]["details"]["archived"] is True
        # 보관 중이면 겹침 아님
        assert client.post(f"{API}/projects", json={"folder": str(inner)}).status_code == 201
        # 다시 등록은 겹치는 inner 때문에 막힘
        blocked = client.put(f"{API}/projects/app", json={"archived": False})
        assert blocked.status_code == 409
        assert client.delete(f"{API}/projects/inner").status_code == 204
        revived = client.put(f"{API}/projects/app", json={"archived": False})
        assert revived.status_code == 200, revived.text
        assert revived.json()["project"]["archived"] is False


def test_relative_or_invalid_path_is_rejected(tmp_path: Path) -> None:
    with _client(_assembly(tmp_path)) as client:
        response = client.post(f"{API}/projects", json={"folder": "relative/path"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "folders.relative"


def test_folder_missing_status(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "gone")
    with _client(_assembly(tmp_path)) as client:
        _register(client, app)
        for p in sorted(app.rglob("*"), reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        app.rmdir()
        view = client.get(f"{API}/projects/gone").json()
        assert view["status"] == "folder_missing"
        assert view["config_writable"] is False
        assert view["records_writable"] is False
        put = client.put(f"{API}/projects/gone", json={"name": "새 이름"})
        assert put.status_code == 409
        assert put.json()["error"]["code"] == "project.folder_missing"


def test_broken_manifest_registers_without_writing_and_reset(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "broken")
    (app / CFG).mkdir()
    (app / CFG / "project.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    before = snapshot_tree(app)
    with _client(_assembly(tmp_path)) as client:
        view = _register(client, app)
        assert snapshot_tree(app) == before
        assert view["status"] == "manifest_invalid"
        check = client.post(f"{API}/projects/folders/check", json={"path": str(app)}).json()
        assert check["existing"]["state"] == "invalid"
        edit = client.put(f"{API}/projects/broken", json={"name": "x"})
        assert edit.status_code == 409
        assert edit.json()["error"]["code"] == "project.manifest_invalid"
        reset = client.post(f"{API}/projects/broken/manifest/reset", json={"name": "고침"})
        assert reset.status_code == 200, reset.text
        body = reset.json()
        assert body["project"]["status"] == "ready"
        assert body["project"]["project"]["name"] == "고침"
        assert Path(body["backup_path"]).is_file()
        not_broken = client.post(f"{API}/projects/broken/manifest/reset", json={"name": "a"})
        assert not_broken.status_code == 409
        (app / CFG / "project.yaml").write_text("{{bad\n", encoding="utf-8")
        second = client.post(f"{API}/projects/broken/manifest/reset", json={"name": "다시"})
        assert second.status_code == 200, second.text
    backups = list((app / CFG / ".state" / "backups").iterdir())
    assert len(backups) == 2


def test_update_writes_manifest_and_if_match(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    with _client(_assembly(tmp_path)) as client:
        view = _register(client, app)
        stale = client.put(
            f"{API}/projects/app", json={"name": "x"}, headers={"If-Match": '"nope"'}
        )
        assert stale.status_code == 412
        ok = client.put(
            f"{API}/projects/app",
            json={"name": "새 이름", "description": "설명", "labels": ["a"]},
            headers={"If-Match": f'"{view["version_hash"]}"'},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["project"]["name"] == "새 이름"
        assert ok.json()["project"]["labels"] == ["a"]
        assert ok.json()["version_hash"] != view["version_hash"]
        manifest = _yaml(app / CFG / "project.yaml")
        assert manifest["name"] == "새 이름"
        assert manifest["description"] == "설명"
        registry = _yaml(tmp_path / "ws/projects/app.yaml")
        assert "name" not in registry


def test_legacy_registration_moves_to_manifest_on_first_save(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "old")
    (tmp_path / "ws/projects").mkdir(parents=True)
    (tmp_path / "ws/projects/old.yaml").write_text(
        json.dumps({"id": "old", "name": "옛 이름", "working_directory": str(app), "uses": []}),
        encoding="utf-8",
    )
    with _client(_assembly(tmp_path)) as client:
        view = client.get(f"{API}/projects/old").json()
        assert view["project"]["name"] == "옛 이름"
        assert view["project"]["folder"] == str(app)
        assert any(i["code"] == "settings.ignored_key" for i in view["issues"])
        assert not (app / CFG / "project.yaml").exists()  # 읽기만으로 쓰지 않음(K33-9)
        saved = client.put(f"{API}/projects/old", json={"description": "새 설명"})
        assert saved.status_code == 200, saved.text
        assert saved.json()["project"]["name"] == "옛 이름"
    manifest = _yaml(app / CFG / "project.yaml")
    assert manifest["name"] == "옛 이름"
    registry = _yaml(tmp_path / "ws/projects/old.yaml")
    assert {"name", "uses", "working_directory"}.isdisjoint(registry)
    assert registry["folder"] == str(app)


def test_secret_in_new_manifest_is_refused(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    with _client(_assembly(tmp_path)) as client:
        response = client.post(
            f"{API}/projects",
            json={"folder": str(app), "attributes": {"API_KEY": "abcd1234efgh5678"}},
        )
        assert response.status_code == 422
        assert "abcd1234efgh5678" not in response.text
        assert client.get(f"{API}/projects").json() == []


# ---------------------------------------------------------------- 폴더


def test_folder_check_reads_counts_only(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    _manifest(app, id="pay", name="결제", description="설명")
    (app / CFG / "agents").mkdir()
    (app / CFG / "agents" / "secret-agent-name.yaml").write_text("id: x\n", encoding="utf-8")
    (app / "private-file-name.txt").write_text("내용", encoding="utf-8")
    with _client(_assembly(tmp_path)) as client:
        response = client.post(f"{API}/projects/folders/check", json={"path": str(app)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ok"
        assert body["existing"] == {
            "state": "found",
            "id": "pay",
            "name": "결제",
            "description": "설명",
            "definitions": 1,
            "issue": None,
        }
        assert body["suggested_id"] == "pay"
        assert body["config_dir"] == CFG
        assert "secret-agent-name" not in response.text
        assert "private-file-name" not in response.text
        _register(client, app)
        taken = client.post(f"{API}/projects/folders/check", json={"path": str(app)}).json()
        assert taken["status"] == "taken"
        assert taken["conflict"]["project_id"] == "pay"
        own = client.post(
            f"{API}/projects/folders/check",
            json={"path": str(app), "exclude_project_id": "pay"},
        ).json()
        assert own["status"] == "same_path"


def test_folder_check_create_and_listing(tmp_path: Path, work: Path) -> None:
    _folder(work, "visible")
    _folder(work, ".hidden")
    (work / "file.txt").write_text("x", encoding="utf-8")
    with _client(_assembly(tmp_path)) as client:
        target = work / "new-one"
        missing = client.post(f"{API}/projects/folders/check", json={"path": str(target)})
        assert missing.json()["status"] == "missing"
        made = client.post(
            f"{API}/projects/folders/check", json={"path": str(target), "create": True}
        )
        assert made.status_code == 200, made.text
        assert target.is_dir()
        _register(client, work / "visible")
        listing = client.get(f"{API}/projects/folders", params={"path": str(work)})
        assert listing.status_code == 200, listing.text
        body = listing.json()
        names = {e["name"]: e for e in body["entries"]}
        assert set(names) == {"visible", "new-one"}
        assert names["visible"]["project_id"] == "visible"
        assert body["hidden_count"] == 1
        assert "file.txt" not in listing.text
        shown = client.get(
            f"{API}/projects/folders", params={"path": str(work), "hidden": True}
        ).json()
        assert ".hidden" in {e["name"] for e in shown["entries"]}
        assert body["roots"]


def test_remote_bind_blocks_folders(tmp_path: Path, work: Path) -> None:
    options: dict[str, Any] = {"server_host": "0.0.0.0"}
    with _client(_assembly(tmp_path, options=options)) as client:
        check = client.post(f"{API}/projects/folders/check", json={"path": str(work)})
        assert check.status_code == 403
        assert check.json()["error"]["code"] == "folders.remote_disabled"
        assert client.get(f"{API}/projects/folders").status_code == 403
        caps = client.get(f"{API}/projects/folders/capabilities").json()
        assert caps == {
            "browse": False,
            "native_dialog": False,
            "provider": None,
            "reason": "remote",
        }
        assert client.post(f"{API}/projects/folders/pick", json={}).status_code == 403
    options = {"server_host": "0.0.0.0", "allow_remote_browse": True}
    with _client(_assembly(tmp_path, options=options)) as client:
        check = client.post(f"{API}/projects/folders/check", json={"path": str(work)})
        assert check.status_code == 200
        caps = client.get(f"{API}/projects/folders/capabilities").json()
        assert caps["browse"] is True
        assert caps["native_dialog"] is False


# ---------------------------------------------------------------- 선택 창


def test_pick_states(tmp_path: Path, work: Path) -> None:
    picked = FakeRunner(CommandOutcome(0, f"{work}\n".encode()))
    with _client(_assembly(tmp_path, runner=picked)) as client:
        caps = client.get(f"{API}/projects/folders/capabilities").json()
        assert caps["native_dialog"] is True
        assert caps["provider"] == "fake-dialog"
        body = client.post(f"{API}/projects/folders/pick", json={"title": "고르기"}).json()
        assert body["status"] == "picked"
        assert body["path"] == str(work)
        assert body["check"]["status"] == "ok"
        assert picked.calls == [["fakepick"]]
    cancelled = FakeRunner(CommandOutcome(1))
    with _client(_assembly(tmp_path, runner=cancelled)) as client:
        body = client.post(f"{API}/projects/folders/pick", json={}).json()
        assert body["status"] == "cancelled"
    timeout = FakeRunner(CommandOutcome(None, timed_out=True))
    with _client(_assembly(tmp_path, runner=timeout)) as client:
        body = client.post(f"{API}/projects/folders/pick", json={}).json()
        assert body["status"] == "timeout"
    off = {"folder_dialog": {"mode": "off"}}
    with _client(_assembly(tmp_path, options=off)) as client:
        caps = client.get(f"{API}/projects/folders/capabilities").json()
        assert caps["native_dialog"] is False
        assert caps["reason"] == "off"
        assert client.post(f"{API}/projects/folders/pick", json={}).json() == {
            "status": "unavailable",
            "path": None,
            "check": None,
            "provider": None,
        }


def test_pick_busy_and_cancel(tmp_path: Path, work: Path) -> None:
    gate = threading.Event()
    runner = FakeRunner(CommandOutcome(None, cancelled=True), gate=gate)
    fs = LocalFileSystem()
    picker = FolderPicker(
        settings=FolderDialogSettings(
            providers=[FAKE_SPEC], include_default_providers=False, timeout_seconds=5
        ),
        runner=runner,
        providers=[],
        loopback=lambda: True,
        platform="linux",
        which=_which,
        environ={},
        fs=fs,
        check=lambda path: pytest.fail("고르지 않았다"),
    )
    cancel = threading.Event()
    results: list[str] = []
    first = threading.Thread(
        target=lambda: results.append(picker.pick(FolderPickRequest(), cancel).status)
    )
    first.start()
    assert runner.started.wait(5)
    assert picker.pick(FolderPickRequest(), threading.Event()).status == "busy"
    cancel.set()
    gate.set()
    first.join(5)
    assert results == ["cancelled"]


class FakeProvider:
    """코드 제공자 예(X35): 늘 정해진 폴더를 고른다."""

    id = "fake-code"

    def __init__(self, path: str) -> None:
        self.path = path

    def available(self, environ: Mapping[str, str]) -> bool:
        return True

    def pick(
        self, *, initial: str | None, title: str | None, timeout: float, cancel: CancelSignal
    ) -> str | None:
        return self.path


def test_code_provider_comes_first(tmp_path: Path, work: Path) -> None:
    mod = ProjectsModule(
        runner=FakeRunner(CommandOutcome(1)),
        dialog_providers=[FakeProvider(str(work))],
        platform="linux",
        which=_which,
    )
    base = BaseServices(
        paths=Paths(base_dir=tmp_path, workspace=tmp_path / "ws", state=tmp_path / "state")
    )
    assembly = assemble([mod], ModulesConfig(), base=base)
    with _client(assembly) as client:
        body = client.post(f"{API}/projects/folders/pick", json={}).json()
        assert body["status"] == "picked"
        assert body["provider"] == "fake-code"


# ---------------------------------------------------------------- 복사


def _library(assembly: Assembly) -> Any:
    store = assembly.port(DEFINITIONS_STORE)
    assert store is not None
    return store


def _seed_library(assembly: Assembly) -> None:
    lib = _library(assembly)
    lib.create("agent", {"id": "a", "name": "에이", "backend": "fake-agent"})
    lib.create("resource", {"id": "r", "name": "지침", "type": "instructions", "config": {}})
    stored = lib.get("resource", "r")
    lib.write_files("resource", "r", {"README.md": b"# hi\n"}, expected_version=stored.version_hash)
    lib.create(
        "graph",
        {
            "id": "team",
            "name": "팀",
            "nodes": [],
            "edges": [],
            "uses": [["agent", "a"], ["resource", "r"]],
        },
    )


def _plan(client: TestClient, target: str | None, items: list[dict[str, str]]) -> dict[str, Any]:
    response = client.post(
        f"{API}/projects/copy/plan",
        json={"source": {"project_id": None}, "target": {"project_id": target}, "items": items},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _apply_all(
    client: TestClient, plan: Mapping[str, Any], target: str | None, **extra: Any
) -> dict[str, Any]:
    items = [
        {
            "kind": i["kind"],
            "id": i["id"],
            "action": i["default_action"] or "overwrite",
            "source_version": i["source_version"],
            "target_version": i["target_version"],
        }
        for i in plan["items"]
    ]
    response = client.post(
        f"{API}/projects/copy/apply",
        json={
            "source": {"project_id": None},
            "target": {"project_id": target},
            "items": items,
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_copy_library_to_project(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    assembly = _assembly(tmp_path)
    _seed_library(assembly)
    with _client(assembly) as client:
        _register(client, app)
        plan = _plan(client, "app", [{"kind": "graph", "id": "team"}])
        assert [(i["kind"], i["id"], i["reason"], i["default_action"]) for i in plan["items"]] == [
            ("graph", "team", "requested", "copy"),
            ("agent", "a", "referenced", "copy"),
            ("resource", "r", "referenced", "copy"),
        ]
        result = _apply_all(client, plan, "app")
        assert [i["status"] for i in result["items"]] == ["copied"] * 3
        space = assembly.port(PROJECTS_SPACES)
        assert space is not None
        store = space.open("app").definitions
        assert store.read_file("resource", "r", "README.md") == b"# hi\n"
        lib = _library(assembly)
        for kind, def_id in (("graph", "team"), ("agent", "a"), ("resource", "r")):
            assert store.get(kind, def_id).version_hash == lib.get(kind, def_id).version_hash
            versions = store.list_versions(kind, def_id)
            assert versions[-1].message.startswith("가져옴: library ")
        # 사본 파일에 출처 메타 없음
        text = (app / CFG / "graphs" / "team.yaml").read_text("utf-8")
        assert "library" not in text
        assert "가져옴" not in text
        # 다시 계획하면 같은 내용 = reuse
        again = _plan(client, "app", [{"kind": "graph", "id": "team"}])
        assert {i["target_state"] for i in again["items"]} == {"identical"}
        # 라이브러리를 바꾸면 different + 충돌 항목만 conflict
        lib.save("agent", {"id": "a", "name": "바뀜", "backend": "fake-agent"})
        changed = _plan(client, "app", [{"kind": "agent", "id": "a"}])
        [item] = changed["items"]
        assert item["target_state"] == "different"
        assert item["default_action"] is None
        store.save(
            "agent",
            {"id": "a", "name": "프로젝트에서 고침", "backend": "fake-agent"},
        )
        stale = client.post(
            f"{API}/projects/copy/apply",
            json={
                "source": {"project_id": None},
                "target": {"project_id": "app"},
                "items": [
                    {
                        "kind": "agent",
                        "id": "a",
                        "action": "overwrite",
                        "source_version": item["source_version"],
                        "target_version": item["target_version"],
                    },
                    {
                        "kind": "graph",
                        "id": "team",
                        "action": "rename",
                        "new_id": "team-2",
                        "source_version": lib.get("graph", "team").version_hash,
                    },
                ],
            },
        ).json()
        assert [i["status"] for i in stale["items"]] == ["conflict", "renamed"]
        assert stale["items"][0]["issue"]["details"]["reason"] == "target_changed"
        assert store.get("graph", "team-2").document["id"] == "team-2"


def test_copy_refuses_plain_secret(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    assembly = _assembly(tmp_path)
    _library(assembly).create(
        "agent",
        {
            "id": "s",
            "name": "s",
            "backend": "fake-agent",
            "attributes": {"API_KEY": "abcd1234efgh5678"},
        },
    )
    with _client(assembly) as client:
        _register(client, app)
        plan = _plan(client, "app", [{"kind": "agent", "id": "s"}])
        response = client.post(
            f"{API}/projects/copy/apply",
            json={
                "source": {"project_id": None},
                "target": {"project_id": "app"},
                "items": [
                    {
                        "kind": "agent",
                        "id": "s",
                        "action": "copy",
                        "source_version": plan["items"][0]["source_version"],
                    }
                ],
            },
        )
        assert response.status_code == 422
        assert "abcd1234efgh5678" not in response.text
    assert not (app / CFG / "agents").exists()


def test_copy_plan_blocks_plain_secret_before_apply(tmp_path: Path, work: Path) -> None:
    """묶음 4b V1: 계획이 적용 422를 미리 알린다(값 없음), 막힌 항목을 빼면 적용 성공."""
    secret = "abcd1234efgh5678"
    app = _folder(work, "app")
    assembly = _assembly(tmp_path)
    lib = _library(assembly)
    lib.create(
        "agent",
        {"id": "s", "name": "s", "backend": "fake-agent", "attributes": {"API_KEY": secret}},
    )
    lib.create("agent", {"id": "ok", "name": "ok", "backend": "fake-agent"})
    lib.create(
        "graph",
        {
            "id": "team",
            "name": "팀",
            "nodes": [],
            "edges": [],
            "uses": [["agent", "s"], ["agent", "ok"]],
        },
    )
    with _client(assembly) as client:
        registered = _register(client, app)
        plan = _plan(client, "app", [{"kind": "graph", "id": "team"}])
        assert secret not in json.dumps(plan)
        rows = {i["id"]: i for i in plan["items"]}
        blocked = rows["s"]
        assert blocked["blocked"] is True
        assert blocked["default_action"] == "skip"
        [issue] = blocked["issues"]
        assert issue["severity"] == "error"
        assert issue["code"] == KnownIssueCodes.SECRET_PLAIN_FOUND
        assert issue["path"] == "/attributes/API_KEY"
        assert issue["details"]["kind"] == "agent"
        assert issue["details"]["id"] == "s"
        assert issue["details"]["path"] == "/attributes/API_KEY"
        assert issue["details"]["reason"]
        assert f"프로젝트 \u2018{registered['project']['name']}\u2019" in issue["message"]
        assert rows["team"]["blocked"] is False
        assert rows["team"]["issues"] == []
        assert rows["ok"]["blocked"] is False
        # 막힌 항목을 빼서 그것을 쓰는 팀이 실행 전에 막힌다는 경고
        assert "project.copy_skip_breaks_reference" in [w["code"] for w in plan["warnings"]]
        # 기본 동작 그대로 적용(막힌 항목 skip) = 성공
        result = _apply_all(client, plan, "app")
        assert {i["id"]: i["status"] for i in result["items"]} == {
            "team": "copied",
            "s": "skipped",
            "ok": "copied",
        }
        # 막힌 항목을 억지로 copy하면 적용 422(안전망)는 그대로
        forced = client.post(
            f"{API}/projects/copy/apply",
            json={
                "source": {"project_id": None},
                "target": {"project_id": "app"},
                "items": [
                    {
                        "kind": "agent",
                        "id": "s",
                        "action": "copy",
                        "source_version": blocked["source_version"],
                    }
                ],
            },
        )
        assert forced.status_code == 422
        assert secret not in forced.text
    assert not (app / CFG / "agents" / "s.yaml").exists()


def test_copy_errors(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    with _client(_assembly(tmp_path)) as client:
        _register(client, app)
        unknown = client.post(
            f"{API}/projects/copy/plan",
            json={"source": {"project_id": None}, "target": {"project_id": "ghost"}, "items": []},
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "project.not_found"
        same = client.post(
            f"{API}/projects/copy/plan",
            json={"source": {"project_id": "app"}, "target": {"project_id": "app"}, "items": []},
        )
        assert same.status_code == 400
    with _client(_assembly(tmp_path / "nodefs", definitions=False)) as client:
        _register(client, _folder(work, "b"))
        off = client.post(
            f"{API}/projects/copy/plan",
            json={"source": {"project_id": None}, "target": {"project_id": "b"}, "items": []},
        )
        assert off.status_code == 409
        assert off.json()["error"]["code"] == "feature_unavailable"


def test_legacy_plan_and_remove_source(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    assembly = _assembly(tmp_path)
    lib = _library(assembly)
    lib.create("agent", {"id": "old", "name": "옛", "backend": "fake-agent", "project": "app"})
    lib.create("agent", {"id": "keep", "name": "남김", "backend": "fake-agent"})
    with _client(assembly) as client:
        _register(client, app)
        plan = client.post(f"{API}/projects/app/legacy/plan")
        assert plan.status_code == 200, plan.text
        assert [(i["kind"], i["id"]) for i in plan.json()["items"]] == [("agent", "old")]
        result = _apply_all(client, plan.json(), "app", remove_source=True)
        assert [i["status"] for i in result["items"]] == ["copied"]
    assert lib.list_ids("agent") == ["keep"]
    copied = _yaml(app / CFG / "agents" / "old.yaml")
    assert "project" not in copied


# ---------------------------------------------------------------- 포트


def test_ports(tmp_path: Path, work: Path) -> None:
    app = _folder(work, "app")
    assembly = _assembly(tmp_path)
    with _client(assembly) as client:
        _register(client, app, name="앱")
        spaces = assembly.port(PROJECTS_SPACES)
        assert spaces is not None
        space = spaces.open("app")
        assert isinstance(space, ProjectSpace)
        assert space.folder == app
        assert space.records_db_path == app / CFG / "records.sqlite3"
        assert spaces.open("app") is space  # 캐시
        with pytest.raises(LookupError):
            spaces.open("ghost")
        defs = assembly.port(DEFINITIONS_SPACES)
        assert defs is not None
        assert defs.open("app") is space.definitions
        lookup = assembly.port(PROJECTS_LOOKUP)
        assert lookup is not None
        project = lookup.get_project("app")
        assert project is not None
        assert project.name == "앱"
        assert lookup.get_project("ghost") is None
        folders = assembly.port(PROJECT_FOLDERS)
        assert folders is not None
        assert [(e.id, e.folder) for e in folders().entries] == [("app", app)]
        assert folders().project_for(app / "src") == "app"
        for p in sorted(app.rglob("*"), reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        app.rmdir()
        with pytest.raises(FolderMissing):
            spaces.open("app")


class FakeRecords:
    """``records.spaces`` 가짜(상태만)."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def open(self, space: str) -> Any:  # pragma: no cover - 쓰지 않음
        raise NotImplementedError

    def state(self, space: str) -> RecordsState:
        self.asked.append(space)
        return RecordsState(state="absent", writable=True)

    def close(self, space: str) -> None:  # pragma: no cover - 쓰지 않음
        return None


def test_records_port_fills_view(tmp_path: Path, work: Path) -> None:
    from agent_console_mod_projects import RECORDS_SPACES

    records = FakeRecords()

    def build(ctx: Any) -> Any:
        from agent_console_modkit import ModuleParts

        ctx.provide(RECORDS_SPACES, records)
        return ModuleParts()

    extra = [fake_module("fake-records", provides=[RECORDS_SPACES], on_build=build)]
    with _client(_assembly(tmp_path, extra=extra)) as client:
        view = _register(client, _folder(work, "app"))
        assert view["records_state"] == "absent"
        assert view["records_writable"] is True
        assert view["records_issue"] is None
    assert "project:app" in records.asked


def test_module_runs_standalone() -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run(
        [sys.executable, "-m", "agent_console_mod_projects", "--check"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
