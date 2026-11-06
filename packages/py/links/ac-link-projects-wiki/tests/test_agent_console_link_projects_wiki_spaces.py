"""link-projects-wiki 7R.13 완료 기준.

프로젝트 공간 → ``wiki.spaces``. 서버 조립(mod-projects + mod-wiki + link-projects-records)에서
위키가 각 폴더에만, 다른 workspace에서 같은 폴더 → 위키·페이지·규칙·기록 그대로,
쓰기 불가 폴더는 보기만, 폴더 없음·깨진 매니페스트 409, 페이지 폴더가 예약 폴더·
폴더 밖(링크)이면 422, 연동 끔 → ``wiki.spaces_unavailable``(단독 루트로 새지 않음),
``pages_root`` = 구성 폴더 + ``pages_dir``(``mod-wiki.pages_dir`` 이어받기), 모듈 단독 기동.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ErrorCodes, ProjectManifest
from agent_console_link_projects_records import module as records_module
from agent_console_link_projects_wiki import (
    MODULE_ID,
    SETTINGS_COMPAT,
    WIKI_SPACES,
    ProjectsWikiSettings,
    ProjectWikiSpaces,
    UnsafePagesRoot,
    UnsafeSpaceRoot,
    config_dir_of,
    module,
)
from agent_console_link_projects_wiki.testing import FolderSpaces, folder_spaces_module
from agent_console_mod_projects import ProjectsModule
from agent_console_mod_wiki import WikiSpace
from agent_console_mod_wiki import module as wiki_module
from agent_console_mod_wiki.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    Module,
    ModulesConfig,
    ModuleState,
    Paths,
    assemble,
    seed_settings,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_project_space import FolderMissing, ManifestInvalid, init_space
from agent_console_project_space.testing import ReadOnlyFiles, snapshot_tree
from agent_console_store import InMemoryVersionRepository

API = "/api/v1"
TOKEN = "w" * 32
CFG = ".agent-console"
PAGES = f"{CFG}/wiki-pages"
LINKS = os.name != "nt"

RULES: dict[str, Any] = {
    "id": "team-rules",
    "name": "규칙",
    "write_rules": [
        {"id": "no-temp", "deny_patterns": ["TEMPNOTE"], "action": "reject", "message": "금지"}
    ],
}
"""테스트 데이터(패키지 기본에 기대지 않음)."""


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
    """앱 조립 하나(workspace = ``root/ws``): mod-projects + mod-wiki + 기록 연동 + 이 연동."""
    base = BaseServices(paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"))
    mods: list[Module] = [
        ProjectsModule(versions=lambda _pid, _root: InMemoryVersionRepository()),
        wiki_module,
        static_settings_module({}),
        records_module,
        module,
    ]
    config = ModulesConfig(disabled=list(disabled), options=dict(options or {}))
    assembly = assemble(mods, config, base=base)
    with _host(assembly) as client:
        yield client, assembly


@contextmanager
def _folder_app(
    root: Path, folders: Mapping[str, Path], **open_options: Any
) -> Iterator[TestClient]:
    """mod-projects 없이 폴더 목록(``open_space`` 옵션 그대로)으로 조립."""
    base = BaseServices(paths=Paths(base_dir=root, workspace=root / "ws", state=root / "state"))
    mods: list[Module] = [
        wiki_module,
        static_settings_module({}),
        folder_spaces_module(folders, **open_options),
        module,
    ]
    with _host(assemble(mods, None, base=base)) as client:
        yield client


def _register(client: TestClient, folder: Path, project_id: str) -> None:
    created = client.post(f"{API}/projects", json={"folder": str(folder), "id": project_id})
    assert created.status_code == 201, created.text


def _state(assembly: Assembly) -> ModuleState:
    status = assembly.status(MODULE_ID)
    assert status is not None
    return status.state


def _code(res: Any) -> str:
    return str(res.json()["error"]["code"])


def _put(client: TestClient, wiki: str, path: str, content: str, project: str) -> Any:
    q = {"project": project}
    current = client.get(f"{API}/wiki/wikis/{wiki}/pages/{path}", params=q)
    headers = (
        {"If-Match": current.headers["etag"]}
        if current.status_code == 200
        else {"If-None-Match": "*"}
    )
    return client.put(
        f"{API}/wiki/wikis/{wiki}/pages/{path}",
        json={"content": content},
        headers=headers,
        params=q,
    )


def _make_wiki(client: TestClient, project: str, *, rules: bool = True) -> None:
    q = {"project": project}
    if rules:
        made = client.post(f"{API}/wiki/rules", json=RULES, params=q)
        assert made.status_code == 201, made.text
    body: dict[str, Any] = {"name": "notes", "rules": ["team-rules"] if rules else []}
    created = client.post(f"{API}/wiki/wikis", json=body, params=q)
    assert created.status_code == 201, created.text


# ---- 부품(HTTP 없이) ------------------------------------------------------------------


def test_open_maps_project_space(tmp_path: Path) -> None:
    folder = tmp_path / "a"
    folder.mkdir()
    space = ProjectWikiSpaces(lambda: FolderSpaces({"a": folder}, config_dir="cfg/app")).open("a")
    assert isinstance(space, WikiSpace)  # mod-wiki가 받는 모양
    assert space.config_dir == "cfg/app"
    assert space.pages_dir == "cfg/app/wiki-pages"
    assert space.pages_root == folder / "cfg" / "app" / "wiki-pages"
    assert space.index_dir == folder / "cfg" / "app" / ".state" / "wiki-index"
    assert space.folder == folder
    assert space.config_writable is True
    assert not (folder / "cfg").exists()  # 열기만으로 만들지 않는다


def test_options_rename_folders(tmp_path: Path) -> None:
    spaces = ProjectWikiSpaces(
        lambda: FolderSpaces({"a": tmp_path}), pages_dir="docs/pages", index_dir="idx"
    )
    space = spaces.open("a")
    assert space.pages_dir == f"{CFG}/docs/pages"
    assert space.index_dir == tmp_path / CFG / ".state" / "idx"


def test_open_errors(tmp_path: Path) -> None:
    with pytest.raises(LookupError):
        ProjectWikiSpaces(lambda: None).open("a")
    with pytest.raises(LookupError):
        ProjectWikiSpaces(lambda: FolderSpaces({})).open("a")
    with pytest.raises(FolderMissing) as missing:
        ProjectWikiSpaces(lambda: FolderSpaces({"a": tmp_path / "none"})).open("a")
    assert missing.value.code == ErrorCodes.PROJECT_FOLDER_MISSING
    broken = tmp_path / "b"
    (broken / CFG).mkdir(parents=True)
    (broken / CFG / "project.yaml").write_text("id: [\n", encoding="utf-8")
    with pytest.raises(ManifestInvalid) as bad:
        ProjectWikiSpaces(lambda: FolderSpaces({"b": broken})).open("b")
    assert HTTP_STATUS_BY_ERROR_CODE[bad.value.code] == 409


def test_readonly_space_has_no_index(tmp_path: Path) -> None:
    space = ProjectWikiSpaces(lambda: FolderSpaces({"a": tmp_path}, files=ReadOnlyFiles())).open(
        "a"
    )
    assert space.config_writable is False
    assert space.index_dir is None  # 색인은 메모리(쓰지 않는다)


def test_unwritable_pages_folder_is_readonly(tmp_path: Path) -> None:
    (tmp_path / PAGES).mkdir(parents=True)
    seen: list[Path] = []

    def writable(path: Path) -> bool:
        seen.append(path)
        return False

    space = ProjectWikiSpaces(lambda: FolderSpaces({"a": tmp_path}), writable=writable).open("a")
    assert space.config_writable is False
    assert seen == [tmp_path / PAGES]


@pytest.mark.parametrize("pages_dir", [".state", ".STATE/wiki", "sessions", "keep"])
def test_pages_dir_overlapping_reserved_is_refused(tmp_path: Path, pages_dir: str) -> None:
    spaces = ProjectWikiSpaces(
        lambda: FolderSpaces({"a": tmp_path}), pages_dir=pages_dir, reserved=[f"{CFG}/keep"]
    )
    with pytest.raises(UnsafePagesRoot) as err:
        spaces.open("a")
    assert err.value.reason == "reserved"
    assert err.value.code == ErrorCodes.FOLDERS_INVALID_PATH
    assert str(tmp_path) not in err.value.path  # 절대 경로를 싣지 않는다


def test_pages_dir_containing_reserved_is_refused(tmp_path: Path) -> None:
    spaces = ProjectWikiSpaces(
        lambda: FolderSpaces({"a": tmp_path}), pages_dir="p", reserved=[f"{CFG}/p/x"]
    )
    with pytest.raises(UnsafePagesRoot):
        spaces.open("a")


def test_kind_folder_is_reserved(tmp_path: Path) -> None:
    store_space = FolderSpaces({"a": tmp_path}).open("a")
    kinds = store_space.definitions.kinds()
    info = getattr(store_space.definitions, "kind_info")  # noqa: B009 - 구현 전용 능력
    dirs = [info(k).directory for k in kinds if info(k).directory]
    if not dirs:  # pragma: no cover - 기본 공간에 종류가 없는 환경
        pytest.skip("no kind folders")
    with pytest.raises(UnsafePagesRoot):
        ProjectWikiSpaces(lambda: FolderSpaces({"a": tmp_path}), pages_dir=dirs[0]).open("a")


@pytest.mark.skipif(not LINKS, reason="symlink")
def test_pages_root_link_outside_is_refused(tmp_path: Path) -> None:
    folder, outside = tmp_path / "proj", tmp_path / "outside"
    (folder / CFG).mkdir(parents=True)
    outside.mkdir()
    (folder / PAGES).symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePagesRoot) as err:
        ProjectWikiSpaces(lambda: FolderSpaces({"a": folder})).open("a")
    assert (err.value.reason, err.value.path) == ("link", PAGES)


@pytest.mark.skipif(not LINKS, reason="symlink")
def test_wiki_folder_link_outside_is_refused(tmp_path: Path) -> None:
    folder, outside = tmp_path / "proj", tmp_path / "outside"
    (folder / PAGES / "ok").mkdir(parents=True)
    outside.mkdir()
    (folder / PAGES / "bad").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePagesRoot) as err:
        ProjectWikiSpaces(lambda: FolderSpaces({"a": folder})).open("a")
    assert (err.value.reason, err.value.path) == ("link", f"{PAGES}/bad")
    # 폴더 안을 가리키는 링크는 괜찮다
    (folder / PAGES / "bad").unlink()
    (folder / "elsewhere").mkdir()
    (folder / PAGES / "inside").symlink_to(folder / "elsewhere", target_is_directory=True)
    ProjectWikiSpaces(lambda: FolderSpaces({"a": folder})).open("a")


def test_injected_realpath_outside(tmp_path: Path) -> None:
    def realpath(path: str) -> str:
        return str(tmp_path.parent / "x") if path.endswith("wiki-pages") else path

    with pytest.raises(UnsafePagesRoot) as err:
        ProjectWikiSpaces(lambda: FolderSpaces({"a": tmp_path}), realpath=realpath).open("a")
    assert err.value.reason == "link"


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


@pytest.mark.parametrize("bad", ["../x", "/abs", "a\\b", "a/../b", "C:x", "."])
def test_settings_refuse_unsafe_dirs(bad: str) -> None:
    with pytest.raises(ValidationError):
        ProjectsWikiSettings(pages_dir=bad)
    with pytest.raises(ValidationError):
        ProjectsWikiSettings(index_dir=bad)


def test_pages_dir_seeds_from_wiki_module() -> None:
    data = {"modules": {"options": {"mod-wiki": {"pages_dir": "notes-pages"}}}}
    seeded = seed_settings(data, {MODULE_ID: SETTINGS_COMPAT})
    assert seeded["modules"]["options"][MODULE_ID] == {"pages_dir": "notes-pages"}
    own = {"modules": {"options": {"mod-wiki": {"pages_dir": "x"}, MODULE_ID: {"pages_dir": "y"}}}}
    kept = seed_settings(own, {MODULE_ID: SETTINGS_COMPAT})
    assert kept["modules"]["options"][MODULE_ID]["pages_dir"] == "y"  # 적은 값이 이긴다
    assert ProjectsWikiSettings().pages_dir == "wiki-pages"


# ---- 서버 조립 ------------------------------------------------------------------------


def test_wikis_stay_in_each_project_folder(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with _app(tmp_path / "app1") as (client, assembly):
        assert _state(assembly) is ModuleState.ACTIVE
        assert assembly.port(WIKI_SPACES) is not None
        _register(client, a, "pa")
        _register(client, b, "pb")
        info = client.get(f"{API}/wiki/info", params={"project": "pa"}).json()
        assert info["pages_root"] == PAGES
        assert info["capabilities"]["history"] is True
        _make_wiki(client, "pa")
        assert _put(client, "notes", "home", "# 홈\n[[b]]\n", "pa").status_code == 201
        assert [
            w["id"] for w in client.get(f"{API}/wiki/wikis", params={"project": "pb"}).json()
        ] == []
        assert client.get(f"{API}/wiki/wikis").json() == []  # 단독 루트와 섞이지 않는다
        _make_wiki(client, "pb", rules=False)
        assert _put(client, "notes", "other", "# B\n", "pb").status_code == 201
    assert (a / PAGES / "notes" / "home.md").is_file()
    assert not (a / PAGES / "notes" / "other.md").exists()
    assert (b / PAGES / "notes" / "other.md").is_file()
    with sqlite3.connect(a / CFG / "records.sqlite3") as db:  # 계보 wiki(범위 project)가 올라갔다
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "alembic_version_wiki" in tables
    assert not (tmp_path / "app1" / "ws" / "wiki").exists()


def test_same_folder_in_another_workspace_keeps_wiki(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with _app(tmp_path / "app1") as (client, _):
        _register(client, folder, "p1")
        _make_wiki(client, "p1")
        assert _put(client, "notes", "home", "# 홈\n", "p1").status_code == 201
        assert _put(client, "notes", "home", "# 홈\n둘째\n", "p1").status_code == 200
        first = client.get(f"{API}/wiki/wikis/notes", params={"project": "p1"}).json()
    with _app(tmp_path / "app2") as (client, _):
        _register(client, folder, "other-id")
        q = {"project": "other-id"}
        wiki = client.get(f"{API}/wiki/wikis/notes", params=q)
        assert wiki.status_code == 200, wiki.text
        assert wiki.json()["wiki"]["rules"] == first["wiki"]["rules"] == ["team-rules"]
        assert wiki.json()["rules"]["write_rules"] == 1
        assert wiki.json()["directory"] == f"{PAGES}/notes"
        page = client.get(f"{API}/wiki/wikis/notes/pages/home", params=q)
        assert page.status_code == 200
        assert page.json()["content"] == "# 홈\n둘째\n"
        rules = client.get(f"{API}/wiki/rules", params=q).json()
        assert [r["id"] for r in rules] == ["team-rules"]
        history = client.get(f"{API}/wiki/wikis/notes/pages/home/history", params=q).json()
        assert [i["op"] for i in history["items"]] == ["update", "create"]
        # 규칙도 그대로 적용된다
        refused = _put(client, "notes", "x", "TEMPNOTE\n", "other-id")
        assert refused.status_code == 422, refused.text


def test_readonly_folder_is_view_only(tmp_path: Path) -> None:
    folder = tmp_path / "ro"
    folder.mkdir()
    init_space(folder, manifest=ProjectManifest(id="ro", name="ro"))
    with _folder_app(tmp_path / "w1", {"ro": folder}) as client:
        _make_wiki(client, "ro", rules=False)
        assert _put(client, "notes", "home", "# 홈\n", "ro").status_code == 201
    before = snapshot_tree(folder)
    with _folder_app(tmp_path / "w2", {"ro": folder}, files=ReadOnlyFiles()) as client:
        q = {"project": "ro"}
        assert client.get(f"{API}/wiki/wikis/notes/pages/home", params=q).status_code == 200
        assert (
            client.get(f"{API}/wiki/wikis/notes/search", params={**q, "q": "홈"}).status_code == 200
        )
        res = _put(client, "notes", "new", "x\n", "ro")
        assert res.status_code == 409, res.text
        assert _code(res) == ErrorCodes.PROJECT_CONFIG_READONLY
        made = client.post(f"{API}/wiki/wikis", json={"name": "more"}, params=q)
        assert made.status_code == 409
        assert _code(made) == ErrorCodes.PROJECT_CONFIG_READONLY
    after = snapshot_tree(folder)
    assert after == before


def test_folder_missing_and_broken_manifest_are_409(tmp_path: Path) -> None:
    gone, broken = tmp_path / "gone", tmp_path / "broken"
    gone.mkdir()
    broken.mkdir()
    with _app(tmp_path / "app") as (client, _):
        _register(client, gone, "g")
        _register(client, broken, "b")
        assert client.get(f"{API}/wiki/wikis", params={"project": "b"}).status_code == 200
        shutil.rmtree(gone)
        res = client.get(f"{API}/wiki/wikis", params={"project": "g"})
        assert res.status_code == 409
        assert _code(res) == ErrorCodes.PROJECT_FOLDER_MISSING
        (broken / CFG / "project.yaml").write_text("id: [\n", encoding="utf-8")
        res = client.get(f"{API}/wiki/info", params={"project": "b"})
        assert res.status_code == 409
        assert _code(res) == ErrorCodes.PROJECT_MANIFEST_INVALID
        made = client.post(f"{API}/wiki/wikis", json={"name": "X"}, params={"project": "b"})
        assert made.status_code == 409
        unknown = client.get(f"{API}/wiki/wikis", params={"project": "nope"})
        assert unknown.status_code == 404
        assert _code(unknown) == ErrorCodes.PROJECT_NOT_FOUND
    assert not (broken / PAGES).exists()


@pytest.mark.skipif(not LINKS, reason="symlink")
def test_pages_link_outside_is_422_and_nothing_written(tmp_path: Path) -> None:
    folder, outside = tmp_path / "proj", tmp_path / "outside"
    (folder / CFG).mkdir(parents=True)
    outside.mkdir()
    (folder / PAGES).symlink_to(outside, target_is_directory=True)
    with _folder_app(tmp_path / "w", {"p": folder}) as client:
        for res in (
            client.get(f"{API}/wiki/wikis", params={"project": "p"}),
            client.post(f"{API}/wiki/wikis", json={"name": "x"}, params={"project": "p"}),
        ):
            assert res.status_code == 422, res.text
            assert _code(res) == ErrorCodes.FOLDERS_INVALID_PATH
            assert str(tmp_path) not in res.text
    assert list(outside.iterdir()) == []


def test_link_disabled_gives_spaces_unavailable(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    with _app(tmp_path / "app", disabled=(MODULE_ID,)) as (client, assembly):
        assert _state(assembly) is ModuleState.DISABLED
        _register(client, folder, "p")
        for res in (
            client.get(f"{API}/wiki/info", params={"project": "p"}),
            client.get(f"{API}/wiki/wikis", params={"project": "p"}),
            client.post(f"{API}/wiki/wikis", json={"name": "X"}, params={"project": "p"}),
        ):
            assert res.status_code == 409
            assert _code(res) == ErrorCodes.WIKI_SPACES_UNAVAILABLE
        assert client.get(f"{API}/wiki/wikis").json() == []
    assert not (tmp_path / "app" / "ws" / "wiki").exists()  # 단독 루트로 새지 않는다
    assert not (folder / PAGES).exists()


def test_link_off_without_projects_module(tmp_path: Path) -> None:
    with _app(tmp_path / "app", disabled=("mod-projects",)) as (client, assembly):
        assert _state(assembly) is ModuleState.UNSATISFIED
        res = client.get(f"{API}/wiki/wikis", params={"project": "p"})
        assert _code(res) == ErrorCodes.WIKI_SPACES_UNAVAILABLE


def test_pages_root_follows_config_dir_and_pages_dir(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    data = {
        "modules": {
            "options": {
                "mod-projects": {"config_dir": ".ac2"},
                "mod-wiki": {"pages_dir": "notes-pages"},
            }
        }
    }
    options = seed_settings(data, {MODULE_ID: SETTINGS_COMPAT})["modules"]["options"]
    with _app(tmp_path / "app", options=options) as (client, _):
        _register(client, folder, "p")
        info = client.get(f"{API}/wiki/info", params={"project": "p"}).json()
        assert info["pages_root"] == ".ac2/notes-pages"
        _make_wiki(client, "p", rules=False)
        assert _put(client, "notes", "a", "# a\n", "p").status_code == 201
    assert (folder / ".ac2" / "notes-pages" / "notes" / "a.md").is_file()
    assert (folder / ".ac2" / ".state" / "wiki-index").is_dir()
    assert not (folder / CFG).exists()


def test_standalone_check() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_projects_wiki", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
