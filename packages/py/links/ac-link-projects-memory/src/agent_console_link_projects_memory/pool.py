# ruff: noqa: N818
"""프로젝트 메모리 DB 묶음: 등록 id → 그 폴더의 ``memory.sqlite3`` 저장소(``memory.spaces`` 모양).

- 처음 열 때 파일에 메모리 계보(켜진 모듈 중 ``migration_scope`` 범위를 선언한 것)를 올리고
  ``ac-memory`` SQLite 저장소로 붙는다. 앱 DB와 같은 구현·같은 표이고 경로만 다르다(§PI.4.3).
- 열린 저장소 캐시: 상한 ``max_open``(오래 안 쓴 것부터 닫음), 유휴 ``idle_close_seconds``(다음
  접근 때 판정), 폴더를 다시 지정해 경로가 바뀌면 새로 연다.
- 맥락 바꾸기: ``{context_field: 폴더 id}``(매니페스트 ``id``, 없거나 읽지 못하면 등록 id).
- 파일이 없고 구성 폴더에 쓸 수 없으면 만들지 않고 ``ConfigReadonly``(409
  ``project.config_readonly``). 계보를 올리지 못하면(더 새 앱이 올린 DB 등)
  ``MemoryDbUnavailable``(409 ``feature_unavailable``). 앱 DB로 대신 쓰지 않는다.
- 네트워크 파일 시스템이면(저널 ``auto``) ``DELETE`` 저널을 쓴다. 사용자 안내 이슈
  ``project.network_fs``는 프로젝트 목록(``mod-projects``)이 낸다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_console_contracts import ErrorCodes
from agent_console_memory import MemoryStore
from agent_console_memory.sqlite import SqliteMemoryStore, open_sqlite_memory_store
from agent_console_project_space import (
    ConfigReadonly,
    ManifestInvalid,
    ProjectSpace,
    SpaceError,
    read_manifest,
)
from agent_console_store import (
    MigrationBranchLike,
    branch_version_table,
    create_sqlite_engine,
    is_network_fs,
    upgrade,
)

from .ports import ProjectSpaces, SpaceLike

_log = logging.getLogger(__name__)


class MemoryDbUnavailable(SpaceError):
    """프로젝트 메모리 DB를 열 수 없다(계보 없음·올리기 실패) -> ``feature_unavailable``(409)."""

    code = ErrorCodes.FEATURE_UNAVAILABLE


@dataclass(frozen=True)
class ProjectMemorySpace:
    """열린 프로젝트 메모리 공간(``mod-memory`` ``MemorySpaceLike`` 모양).

    Attributes:
        store: 메모리 저장소.
        context: 실행 도구 접근 맥락에 덮어쓸 값.
        path: DB 파일 경로.
    """

    store: MemoryStore
    context: Mapping[str, str]
    path: Path


@dataclass(frozen=True)
class PoolOptions:
    """캐시·열기 옵션(``ProjectsMemorySettings``에서 옮긴다)."""

    max_open: int = 8
    idle_close_seconds: float = 300.0
    busy_timeout: float = 10.0
    use_fts: bool = True
    journal: str = "auto"
    context_field: str = "project_id"


@dataclass
class _Entry:
    space: ProjectMemorySpace
    last_used: float
    stores: list[SqliteMemoryStore] = field(default_factory=list)


def folder_id(space: Any) -> str | None:
    """공간의 폴더 id(매니페스트 ``id``). 매니페스트가 없거나 읽지 못하면 None."""
    if not isinstance(space, ProjectSpace):
        value = getattr(space, "folder_id", None)
        return value if isinstance(value, str) and value else None
    try:
        record = read_manifest(space)
    except (ManifestInvalid, OSError):
        return None
    return record.manifest.id if record is not None else None


def migrate_memory_db(path: Path, branches: Sequence[MigrationBranchLike]) -> None:
    """``path``에 계보들을 올린다(폴더·파일이 없으면 만든다).

    Raises:
        MemoryDbUnavailable: 계보가 없거나 올리지 못했다.
    """
    if not branches:
        raise MemoryDbUnavailable("메모리 DB 계보가 없습니다(메모리 모듈이 꺼졌나요?)")
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_sqlite_engine(path)
    try:
        for branch in branches:
            upgrade(
                engine, versions=branch.versions, version_table=branch_version_table(branch.name)
            )
    except Exception as exc:
        raise MemoryDbUnavailable("프로젝트 메모리 DB를 이 앱 버전으로 맞추지 못했습니다") from exc
    finally:
        engine.dispose()


class ProjectMemoryPool:
    """``memory.spaces`` 구현.

    Args:
        spaces: 지금 ``projects.spaces``(없으면 None).
        branches: 열 때마다 부르는 함수 - 올릴 계보(``ModuleContext.active_migrations(scope)``).
        options: 상한·유휴·잠금 대기·전문 검색·저널·맥락 필드.
        clock: 단조 시계(초).
        network_fs: 경로가 네트워크 파일 시스템인가(주입).
        folder_id_of: 공간 → 폴더 id(주입, 기본 매니페스트 읽기).
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        branches: Callable[[], Sequence[MigrationBranchLike]],
        *,
        options: PoolOptions = PoolOptions(),  # noqa: B008 - 불변 값
        clock: Callable[[], float] = time.monotonic,
        network_fs: Callable[[Path], bool] = is_network_fs,
        folder_id_of: Callable[[Any], str | None] = folder_id,
    ) -> None:
        self._spaces = spaces
        self._branches = branches
        self._options = options
        self._clock = clock
        self._network_fs = network_fs
        self._folder_id_of = folder_id_of
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.RLock()

    def open(self, space: str) -> ProjectMemorySpace:
        """등록 id의 메모리 공간(열려 있으면 그대로).

        Raises:
            LookupError: 모르는 프로젝트(또는 ``projects.spaces`` 없음).
            agent_console_project_space.FolderMissing: 폴더가 없다.
            agent_console_project_space.ConfigReadonly: 파일이 없고 쓸 수 없다.
            MemoryDbUnavailable: 계보를 올리지 못했다.
        """
        provider = self._spaces()
        if provider is None:
            raise LookupError(space)
        found = provider.open(space)
        with self._lock:
            self._sweep()
            path = Path(found.memory_db_path)
            entry = self._entries.get(space)
            if entry is not None and entry.space.path != path:
                self._drop(space)
                entry = None
            if entry is None:
                entry = self._make(space, found, path)
                self._entries[space] = entry
            entry.last_used = self._clock()
            self._entries.move_to_end(space)
            self._enforce_cap()
            return entry.space

    def close(self, space: str) -> None:
        """그 공간의 저장소를 닫는다(없으면 아무 일도 없다)."""
        with self._lock:
            self._drop(space)

    def close_all(self) -> None:
        """열린 저장소를 모두 닫는다(서버 종료)."""
        with self._lock:
            for space in list(self._entries):
                self._drop(space)

    def open_spaces(self) -> list[str]:
        """지금 열린 공간 이름(오래 안 쓴 것부터)."""
        with self._lock:
            return list(self._entries)

    # ---- 내부 ------------------------------------------------------------------

    def _journal(self, path: Path) -> str:
        if self._options.journal in ("WAL", "DELETE"):
            return self._options.journal
        try:
            return "DELETE" if self._network_fs(path) else "WAL"
        except OSError:
            return "WAL"

    def _make(self, space: str, found: SpaceLike, path: Path) -> _Entry:
        if not path.exists() and not found.config_writable:
            raise ConfigReadonly("프로젝트 구성 폴더에 쓸 수 없어 메모리 DB를 만들 수 없습니다")
        migrate_memory_db(path, list(self._branches()))
        store = open_sqlite_memory_store(
            path,
            use_fts=None if self._options.use_fts else False,
            busy_timeout_seconds=self._options.busy_timeout,
            journal=self._journal(path),
        )
        context_id = self._folder_id_of(found) or space
        context = {self._options.context_field: context_id}
        return _Entry(ProjectMemorySpace(store, context, path), self._clock(), [store])

    def _drop(self, space: str) -> None:
        entry = self._entries.pop(space, None)
        if entry is None:
            return
        for store in entry.stores:
            try:
                store.close()
            except Exception:  # pragma: no cover - 닫기 실패는 기록만
                _log.exception("프로젝트 메모리 DB를 닫지 못함: %s", space)

    def _sweep(self) -> None:
        idle = self._options.idle_close_seconds
        if idle <= 0:
            return
        now = self._clock()
        for space, entry in list(self._entries.items()):
            if now - entry.last_used >= idle:
                self._drop(space)

    def _enforce_cap(self) -> None:
        while len(self._entries) > max(1, self._options.max_open):
            oldest = next(iter(self._entries))
            self._drop(oldest)


__all__ = [
    "MemoryDbUnavailable",
    "PoolOptions",
    "ProjectMemoryPool",
    "ProjectMemorySpace",
    "folder_id",
    "migrate_memory_db",
]
