"""서버 자동 정리를 등록 프로젝트 메모리에도(5.7R.46, design ``[pl 결정 11/20, 5.7R.46·5.7R.47]``).

대상 = 사용자 설정 ``memory.retention.auto``, 프로젝트 = ``memory.spaces``의 ``existing()``(메모리
파일이 이미 있는 켜진 등록만, 파일을 만들지 않음). 범위 종류·규칙 이름은 테스트 데이터다.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agent_console_contracts import ProjectManifest
from agent_console_contracts.constants import KnownIssueCodes
from agent_console_contracts.memory import MemoryScopeRef, MemoryWriteRequest
from agent_console_link_projects_memory import MEMORY_SPACES, ProjectMemoryPool, module
from agent_console_link_projects_memory.testing import FolderSpaces, folder_spaces_module
from agent_console_mod_memory import (
    MEMORY_SERVICE,
    SERVER_WARNINGS,
    MemoryService,
    run_retention_cycle,
)
from agent_console_mod_memory import module as memory_module
from agent_console_mod_memory.storage import BRANCH as MEMORY_BRANCH
from agent_console_mod_memory.testing import static_settings_module
from agent_console_modkit import Assembly, BaseServices, ExtensionRegistries, Module, ModulesConfig
from agent_console_modkit import assemble as assemble_modules
from agent_console_project_space import init_space
from agent_console_store import SqliteDatabase

NOTES = MemoryScopeRef(kind="notes", id="")
RULE = {
    "id": "temp-cleanup",
    "when": {"all": [{"path": "/tags", "op": "contains", "value": "임시"}]},
    "action": "delete",
}


def _settings(rules: list[Any] | None = None, auto: dict[str, Any] | None = None) -> dict[str, Any]:
    retention: dict[str, Any] = {"rules": [RULE] if rules is None else rules}
    if auto is not None:
        retention["auto"] = auto
    return {
        "memory": {
            "include_default_scope_kinds": False,
            "scope_kinds": {"notes": {"label": "노트", "id": ""}},
            "retention": retention,
        }
    }


def _project(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    init_space(folder, manifest=ProjectManifest(id=f"folder-{name}", name=name))
    return folder


def _db(folder: Path) -> Path:
    return folder / ".agent-console" / "memory.sqlite3"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    db = SqliteDatabase.open(tmp_path / "console.sqlite3")
    yield db
    db.close()


def _assemble(
    database: SqliteDatabase,
    folders: dict[str, Path],
    settings: dict[str, Any],
    *,
    with_link: bool = True,
    archived: tuple[str, ...] = (),
    listing: bool = True,
    options: dict[str, Any] | None = None,
) -> Assembly:
    modules: list[Module] = [
        memory_module,
        static_settings_module(lambda: settings),
        folder_spaces_module(folders, archived=archived, listing=listing),
    ]
    if with_link:
        modules.append(module)
    return assemble_modules(
        modules,
        ModulesConfig(options={"mod-memory": options} if options else {}),
        base=BaseServices(database=database, registries=ExtensionRegistries()),
    )


def _service(assembly: Assembly) -> MemoryService:
    service = assembly.port(MEMORY_SERVICE)
    assert isinstance(service, MemoryService)
    return service


def _temp(service: MemoryService, key: str = "t") -> str:
    request = MemoryWriteRequest(scope=NOTES, key=key, content="x", tags=["임시"])
    return service.create(request).id


def _deleted(service: MemoryService, entry_id: str) -> bool:
    found = service.store.get(entry_id, include_deleted=True)
    assert found is not None
    return found.deleted_at is not None


def _seed(service: MemoryService, *names: str | None) -> dict[str | None, str]:
    return {name: _temp(service.space(name)) for name in names}


def _close(assembly: Assembly) -> None:
    pool = assembly.port(MEMORY_SPACES)
    if isinstance(pool, ProjectMemoryPool):
        pool.close_all()


def test_cycle_cleans_projects_with_db_and_creates_no_file(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    """규칙 저장 + 등록 2개(하나만 memory.sqlite3) → 있는 쪽만 정리, 없는 쪽 파일 없음."""
    a, b = _project(tmp_path, "a"), _project(tmp_path, "b")
    assembly = _assemble(database, {"a": a, "b": b}, _settings())
    try:
        service = _service(assembly)
        seeded = _seed(service, None, "a")
        assert _db(a).is_file()
        assert not _db(b).exists()
        result = run_retention_cycle(service)
        assert list(result.results) == [None, "a"]
        assert result.failed == {}
        assert all(_deleted(service.space(n), i) for n, i in seeded.items())
        assert not _db(b).exists()
        version = service.space("a").versions(seeded["a"])[-1]
        assert version.author.kind == "system"
        assert version.author.label == "temp-cleanup"
    finally:
        _close(assembly)


def test_background_task_cleans_project(tmp_path: Path, database: SqliteDatabase) -> None:
    """서버 배경 작업 한 주기(간격 옵션) 뒤 프로젝트 저장소가 정리된다."""
    a = _project(tmp_path, "a")
    assembly = _assemble(
        database, {"a": a}, _settings(), options={"retention_interval_seconds": 0.01}
    )
    try:
        service = _service(assembly)
        entry = _temp(service.space("a"))
        (job,) = assembly.parts["mod-memory"].background

        async def run_job() -> None:
            await job()

        async def scenario() -> None:
            task = asyncio.create_task(run_job())
            for _ in range(300):
                await asyncio.sleep(0.01)
                if service.space("a").store.get(entry) is None:
                    break
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert _deleted(service.space("a"), entry)
    finally:
        _close(assembly)


@pytest.mark.parametrize(
    ("auto", "cleaned", "kept"),
    [
        ({"projects": False}, [None], ["a", "c"]),
        ({"exclude_projects": ["a"]}, [None, "c"], ["a"]),
        ({"library": False}, ["a", "c"], [None]),
        ({"library": False, "projects": False}, [], [None, "a", "c"]),
    ],
)
def test_auto_targets(
    tmp_path: Path,
    database: SqliteDatabase,
    auto: dict[str, Any],
    cleaned: list[str | None],
    kept: list[str | None],
) -> None:
    folders = {"a": _project(tmp_path, "a"), "c": _project(tmp_path, "c")}
    assembly = _assemble(database, folders, _settings(auto=auto))
    try:
        service = _service(assembly)
        seeded = _seed(service, None, "a", "c")
        result = run_retention_cycle(service)
        assert list(result.results) == cleaned
        assert [n for n in seeded if _deleted(service.space(n), seeded[n])] == cleaned
        assert [n for n in seeded if not _deleted(service.space(n), seeded[n])] == kept
    finally:
        _close(assembly)


def test_default_rules_empty_change_nothing_and_open_nothing(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    """정리 규칙 기본값(빈 목록): 켜도 지우는 것이 없고 공간을 열지 않는다."""
    a, b = _project(tmp_path, "a"), _project(tmp_path, "b")
    settings: dict[str, Any] = {"memory": {"scope_kinds": {"notes": {"label": "노트", "id": ""}}}}
    assembly = _assemble(database, {"a": a, "b": b}, settings)
    try:
        service = _service(assembly)
        seeded = _seed(service, None, "a")
        pool = assembly.port(MEMORY_SPACES)
        assert isinstance(pool, ProjectMemoryPool)
        pool.close_all()
        result = run_retention_cycle(service)
        assert result.results == {}
        assert pool.open_spaces() == []
        assert not any(_deleted(service.space(n), i) for n, i in seeded.items())
        assert not _db(b).exists()
    finally:
        _close(assembly)


def test_missing_folder_is_skipped_and_others_continue(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    folders = {"a": _project(tmp_path, "a"), "c": _project(tmp_path, "c")}
    assembly = _assemble(database, folders, _settings())
    try:
        service = _service(assembly)
        seeded = _seed(service, None, "a", "c")
        _close(assembly)
        shutil.rmtree(folders["a"])
        result = run_retention_cycle(service)
        assert list(result.results) == [None, "c"]
        assert _deleted(service, seeded[None])
        assert _deleted(service.space("c"), seeded["c"])
        assert not folders["a"].exists()  # 다시 만들지 않는다
    finally:
        _close(assembly)


def test_archived_and_readonly_projects_are_not_targets(
    tmp_path: Path, database: SqliteDatabase
) -> None:
    folders = {"a": _project(tmp_path, "a"), "old": _project(tmp_path, "old")}
    assembly = _assemble(database, folders, _settings(), archived=("old",))
    try:
        service = _service(assembly)
        _seed(service, "a", "old")
        pool = assembly.port(MEMORY_SPACES)
        assert isinstance(pool, ProjectMemoryPool)
        assert pool.existing() == ["a"]
    finally:
        _close(assembly)

    class _Space:
        def __init__(self, folder: Path, writable: bool) -> None:
            self.folder = folder
            self.memory_db_path = _db(folder)
            self.config_writable = writable

    class _Spaces(FolderSpaces):
        def open(self, project_id: str) -> Any:
            return _Space(self.folders[project_id], project_id != "ro")

    spaces = _Spaces({"a": folders["a"], "ro": folders["old"]})
    pool = ProjectMemoryPool(lambda: spaces, lambda: [MEMORY_BRANCH], listing=lambda: spaces)
    assert pool.existing() == ["a"]  # 쓸 수 없는 구성 폴더는 뺀다
    assert ProjectMemoryPool(lambda: spaces, lambda: [MEMORY_BRANCH]).existing() == []


def test_link_off_cleans_library_only(tmp_path: Path, database: SqliteDatabase) -> None:
    a = _project(tmp_path, "a")
    assembly = _assemble(database, {"a": a}, _settings(), with_link=False)
    service = _service(assembly)
    entry = _temp(service)
    result = run_retention_cycle(service)
    assert list(result.results) == [None]
    assert result.failed == {}
    assert _deleted(service, entry)
    assert not _db(a).exists()


def test_no_project_listing_cleans_library_only(tmp_path: Path, database: SqliteDatabase) -> None:
    a = _project(tmp_path, "a")
    assembly = _assemble(database, {"a": a}, _settings(), listing=False)
    try:
        service = _service(assembly)
        seeded = _seed(service, None, "a")
        assert list(run_retention_cycle(service).results) == [None]
        assert not _deleted(service.space("a"), seeded["a"])
    finally:
        _close(assembly)


def test_interval_zero_turns_everything_off(tmp_path: Path, database: SqliteDatabase) -> None:
    a = _project(tmp_path, "a")
    assembly = _assemble(database, {"a": a}, _settings(), options={"retention_interval_seconds": 0})
    assert assembly.parts["mod-memory"].background == []


def test_broken_auto_warns_and_uses_defaults(tmp_path: Path, database: SqliteDatabase) -> None:
    a = _project(tmp_path, "a")
    settings = _settings(auto={"library": "아니오", "exclude_projects": "a"})
    assembly = _assemble(database, {"a": a}, settings)
    try:
        service = _service(assembly)
        auto = service.settings().retention.auto
        assert (auto.library, auto.projects, auto.exclude_projects) == (True, True, [])
        assert service.settings().retention.rules  # 규칙은 그대로
        issues = [i for source in assembly.ports(SERVER_WARNINGS) for i in source()]
        paths = {i.path for i in issues if i.code == KnownIssueCodes.MEMORY_SETTINGS_INVALID}
        assert paths == {
            "/memory/retention/auto/library",
            "/memory/retention/auto/exclude_projects",
        }
        _seed(service, "a")
        assert list(run_retention_cycle(service).results) == [None, "a"]
    finally:
        _close(assembly)
