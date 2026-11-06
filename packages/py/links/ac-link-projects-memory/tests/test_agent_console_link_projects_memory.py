"""link-projects-memory: 프로젝트 폴더 memory.sqlite3 열기·계보·맥락(폴더 id)·캐시·읽기 전용·
메모리 모듈과 조립(REST ?project=·복사·실행 도구 쓰기가 폴더 DB에만)·단독 기동
(5.7R.33z, §PI.4.3)."""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_console_contracts import HTTP_STATUS_BY_ERROR_CODE, ErrorCodes, ProjectManifest
from agent_console_contracts.memory import (
    MemoryAccessConfig,
    MemoryAccessContext,
    MemoryScopeRef,
)
from agent_console_link_projects_memory import (
    MEMORY_SPACES,
    MODULE_ID,
    MemoryDbUnavailable,
    PoolOptions,
    ProjectMemoryPool,
    folder_id,
    module,
)
from agent_console_link_projects_memory.testing import FolderSpaces, folder_spaces_module
from agent_console_memory.testing import user_author
from agent_console_mod_memory import MEMORY_SERVICE, MemoryService
from agent_console_mod_memory import module as memory_module
from agent_console_mod_memory.storage import BRANCH as MEMORY_BRANCH
from agent_console_mod_memory.testing import static_settings_module
from agent_console_modkit import (
    Assembly,
    BaseServices,
    ExtensionRegistries,
    Module,
    ModulesConfig,
    ModuleState,
    assemble,
)
from agent_console_modkit.host import SecurityPolicy, create_host_app
from agent_console_project_space import ConfigReadonly, init_space, open_space
from agent_console_store import SqliteDatabase

API = "/api/v1"
TOKEN = "p" * 32
SETTINGS = {
    "memory": {
        "include_default_scope_kinds": False,
        "scope_kinds": {
            "proj": {"label": "프로젝트", "id": "{/project_id}"},
            "notes": {"label": "노트", "id": ""},
        },
    }
}
"""범위 종류는 테스트 데이터다(패키지 기본에 기대지 않음)."""


def _project(tmp_path: Path, name: str, folder_project_id: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    init_space(folder, manifest=ProjectManifest(id=folder_project_id, name=name))
    return folder


def _pool(spaces: FolderSpaces, **options: Any) -> ProjectMemoryPool:
    return ProjectMemoryPool(
        lambda: spaces, lambda: [MEMORY_BRANCH], options=PoolOptions(**options)
    )


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


# ---- 묶음 단위 --------------------------------------------------------------------------


def test_open_creates_db_in_folder_and_context_is_folder_id(tmp_path: Path) -> None:
    folder = _project(tmp_path, "a", "folder-a")
    pool = _pool(FolderSpaces({"reg-1": folder}))
    space = pool.open("reg-1")
    try:
        assert space.path == folder / ".agent-console" / "memory.sqlite3"
        assert space.path.is_file()
        # 등록 id ≠ 폴더 id: 맥락은 폴더 id
        assert space.context == {"project_id": "folder-a"}
        assert pool.open("reg-1") is space  # 캐시
        written = space.store.write(
            MemoryScopeRef(kind="notes", id=""), "k", "본문", author=user_author()
        )
        assert written.entry.version == 1
    finally:
        pool.close_all()
    assert pool.open_spaces() == []


def test_context_field_is_setting_and_falls_back_to_registered_id(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()  # 매니페스트 없음
    pool = _pool(FolderSpaces({"reg-2": folder}), context_field="graph_id")
    try:
        assert pool.open("reg-2").context == {"graph_id": "reg-2"}
    finally:
        pool.close_all()
    assert folder_id(open_space(folder)) is None


def test_unknown_project_and_missing_branches(tmp_path: Path) -> None:
    folder = _project(tmp_path, "a", "folder-a")
    pool = _pool(FolderSpaces({}))
    with pytest.raises(LookupError):
        pool.open("nope")
    empty = ProjectMemoryPool(lambda: FolderSpaces({"a": folder}), lambda: [])
    with pytest.raises(MemoryDbUnavailable) as caught:
        empty.open("a")
    assert caught.value.code == ErrorCodes.FEATURE_UNAVAILABLE
    no_provider = ProjectMemoryPool(lambda: None, lambda: [MEMORY_BRANCH])
    with pytest.raises(LookupError):
        no_provider.open("a")


@dataclass
class _ReadonlySpace:
    folder: Path
    memory_db_path: Path
    config_writable: bool = False


class _ReadonlySpaces:
    def __init__(self, root: Path) -> None:
        self.root = root

    def open(self, project_id: str) -> _ReadonlySpace:
        return _ReadonlySpace(self.root, self.root / ".agent-console" / "memory.sqlite3")


def test_readonly_folder_without_db_is_not_created(tmp_path: Path) -> None:
    pool = ProjectMemoryPool(lambda: _ReadonlySpaces(tmp_path), lambda: [MEMORY_BRANCH])
    with pytest.raises(ConfigReadonly) as caught:
        pool.open("ro")
    assert caught.value.code == ErrorCodes.PROJECT_CONFIG_READONLY
    assert not (tmp_path / ".agent-console").exists()


def test_cap_idle_and_moved_folder(tmp_path: Path) -> None:
    a = _project(tmp_path, "a", "fa")
    b = _project(tmp_path, "b", "fb")
    spaces = FolderSpaces({"a": a, "b": b})
    clock = _Clock()
    pool = ProjectMemoryPool(
        lambda: spaces,
        lambda: [MEMORY_BRANCH],
        options=PoolOptions(max_open=1, idle_close_seconds=10),
        clock=clock,
    )
    try:
        pool.open("a")
        pool.open("b")
        assert pool.open_spaces() == ["b"]  # 상한 1: 오래된 a를 닫음
        clock.now = 11
        first = pool.open("b")  # 유휴로 닫힌 뒤 다시 엶
        assert pool.open("b") is first
        moved = _project(tmp_path, "b2", "fb")
        spaces.folders["b"] = moved
        assert pool.open("b").path.parent.parent == moved  # 경로가 바뀌면 새로 엶
    finally:
        pool.close_all()


def test_network_fs_uses_delete_journal(tmp_path: Path) -> None:
    folder = _project(tmp_path, "net", "fn")
    pool = ProjectMemoryPool(
        lambda: FolderSpaces({"n": folder}),
        lambda: [MEMORY_BRANCH],
        network_fs=lambda _path: True,
    )
    space = pool.open("n")
    space.store.write(MemoryScopeRef(kind="notes", id=""), "k", "x", author=user_author())
    pool.close_all()
    with sqlite3.connect(space.path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"


# ---- 메모리 모듈과 조립 ------------------------------------------------------------------


def _assemble(
    database: SqliteDatabase, folders: dict[str, Path], *, with_link: bool = True
) -> Assembly:
    modules: list[Module] = [
        memory_module,
        static_settings_module(SETTINGS),
        folder_spaces_module(folders),
    ]
    if with_link:
        modules.append(module)
    return assemble(
        modules,
        ModulesConfig(),
        base=BaseServices(database=database, registries=ExtensionRegistries()),
    )


def _client(assembly: Assembly) -> TestClient:
    policy = SecurityPolicy.for_bind("127.0.0.1", 0, token=TOKEN, allowed_hosts=["testserver"])
    app = create_host_app(assembly, policy=policy, error_status=HTTP_STATUS_BY_ERROR_CODE)
    client = TestClient(app)
    client.headers["X-Console-Token"] = TOKEN
    return client


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "console.sqlite3")
    yield db
    db.close()


def _app_rows(database: SqliteDatabase) -> int:
    path = Path(str(database.engine.url.database))
    with sqlite3.connect(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0])


def _file_rows(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0])


def test_rest_project_query_uses_folder_db_only(tmp_path: Path, database: SqliteDatabase) -> None:
    folder = _project(tmp_path, "a", "folder-a")
    assembly = _assemble(database, {"reg-1": folder})
    db_file = folder / ".agent-console" / "memory.sqlite3"
    with _client(assembly) as client:
        body = {"scope": {"kind": "notes", "id": ""}, "key": "k", "content": "프로젝트 본문"}
        created = client.post(f"{API}/memory/entries?project=reg-1", json=body)
        assert created.status_code == 201, created.text
        assert _file_rows(db_file) == 1
        assert _app_rows(database) == 0
        # 라이브러리에는 안 보인다
        assert client.get(f"{API}/memory/entries").json()["items"] == []
        listed = client.get(f"{API}/memory/entries?project=reg-1").json()["items"]
        assert [e["key"] for e in listed] == ["k"]
        entry_id = created.json()["id"]
        assert client.get(f"{API}/memory/entries/{entry_id}").status_code == 404
        assert client.get(f"{API}/memory/entries/{entry_id}?project=reg-1").status_code == 200
        # 모르는 프로젝트 404
        unknown = client.get(f"{API}/memory/entries?project=nope")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == ErrorCodes.PROJECT_NOT_FOUND


def test_scope_kinds_context_fields_same_in_project_space(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    """remap 판별(§PI.16 ⑤): 공간에서도 범위 종류 목록·context_fields가 같다."""
    folder = _project(tmp_path, "a", "folder-a")
    with _client(_assemble(database, {"reg-1": folder})) as client:
        library = client.get(f"{API}/memory/scope-kinds").json()
        project = client.get(f"{API}/memory/scope-kinds?project=reg-1").json()
    assert library == project
    fields = {k["kind"]: k["context_fields"] for k in project["kinds"]}
    assert fields == {"proj": ["project_id"], "notes": []}


def test_copy_library_to_project_is_independent(tmp_path: Path, database: SqliteDatabase) -> None:
    folder = _project(tmp_path, "a", "folder-a")
    with _client(_assemble(database, {"reg-1": folder})) as client:
        lib = client.post(
            f"{API}/memory/entries",
            json={"scope": {"kind": "proj", "id": "lib-proj"}, "key": "k", "content": "원본"},
        ).json()
        client.post(
            f"{API}/memory/entries",
            json={"scope": {"kind": "notes", "id": ""}, "key": "other", "content": "안 고름"},
        )
        request = {
            "source": {"project_id": None},
            "target": {"project_id": "reg-1"},
            "filter": {"scope_kinds": ["proj"]},
            "on_conflict": "skip",
            "remap": [{"from": "lib-proj", "to": "folder-a", "kind": "proj"}],
        }
        result = client.post(f"{API}/memory/copy", json=request)
        assert result.status_code == 200, result.text
        assert result.json()["copied"] == 1
        # 공용 고치기 → 사본 불변
        changed = client.put(
            f"{API}/memory/entries/{lib['id']}",
            json={"content": "고친 원본"},
            headers={"If-Match": str(lib["version"])},
        )
        assert changed.status_code == 200
        copied = client.get(f"{API}/memory/entries?project=reg-1").json()["items"]
        assert [(e["scope"], e["key"]) for e in copied] == [
            ({"kind": "proj", "id": "folder-a"}, "k")
        ]
        full = client.get(f"{API}/memory/entries/{copied[0]['id']}?project=reg-1").json()
        assert full["content"] == "원본"
        # 다시 복사: 충돌 skip
        again = client.post(f"{API}/memory/copy", json=request).json()
        assert again["copied"] == 0
        assert again["conflicts"][0]["resolution"] == "skip"
        # 같은 공간끼리는 400
        same = client.post(
            f"{API}/memory/copy",
            json={"source": {"project_id": "reg-1"}, "target": {"project_id": "reg-1"}},
        )
        assert same.status_code == 400


def test_agent_tool_write_lands_in_folder_db_with_folder_id(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    """프로젝트 실행의 도구 쓰기는 폴더 DB에만, 범위 id = 폴더 id(등록 id와 다름)."""
    folder = _project(tmp_path, "a", "folder-a")
    assembly = _assemble(database, {"reg-1": folder})
    service = assembly.port(MEMORY_SERVICE)
    assert isinstance(service, MemoryService)
    space = service.space("reg-1")
    access = MemoryAccessConfig.model_validate(
        {"scopes": [{"kind": "proj", "access": ["read", "write"]}]}
    )
    toolkit = space.toolkit(access, MemoryAccessContext(project_id="reg-1", run_id="r1"))
    outcome = asyncio.run(toolkit.call("write", {"key": "k", "content": "x", "scope": "proj"}))
    assert not outcome.is_error, outcome.text
    found = space.store.find(MemoryScopeRef(kind="proj", id="folder-a"), "k")
    assert found is not None
    assert _app_rows(database) == 0
    assert _file_rows(folder / ".agent-console" / "memory.sqlite3") == 1


def test_link_off_project_query_is_feature_unavailable(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    folder = _project(tmp_path, "a", "folder-a")
    with _client(_assemble(database, {"reg-1": folder}, with_link=False)) as client:
        res = client.get(f"{API}/memory/entries?project=reg-1")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == ErrorCodes.FEATURE_UNAVAILABLE
        assert client.get(f"{API}/memory/entries").status_code == 200
    assert not (folder / ".agent-console" / "memory.sqlite3").exists()


def test_link_disabled_without_projects_spaces() -> None:
    assembly = assemble([module], ModulesConfig(), base=BaseServices())
    status = assembly.status(MODULE_ID)
    assert status is not None
    assert status.state is ModuleState.UNSATISFIED
    assert assembly.port(MEMORY_SPACES) is None


def test_standalone_check() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "agent_console_link_projects_memory", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
