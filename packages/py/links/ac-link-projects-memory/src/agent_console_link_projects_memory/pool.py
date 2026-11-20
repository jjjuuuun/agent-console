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
- 자동 정리 대상(``existing()``, 5.7R.46): 켜진(보관 안 된) 등록 중 폴더가 있고 구성 폴더에 쓸 수
  있고 ``memory.sqlite3``가 **이미 있는** 것만. 파일·폴더를 만들지 않고 저장소도 열지 않는다.
- 서버 종료(``shutdown()``, 모듈 종료 훅) 뒤에는 새로 열지 않는다. 늦게 온 열기(예: 끝나지 않은
  배경 자동 정리 스레드)는 ``MemoryDbUnavailable``이고 파일을 열지 않는다. ``existing()``은 빈 목록.
- 네트워크 파일 시스템이면(저널 ``auto``) ``DELETE`` 저널을 쓴다. 사용자 안내 이슈
  ``project.network_fs``는 프로젝트 목록(``mod-projects``)이 낸다.
"""

from __future__ import annotations

import logging
import time
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
    OpenCache,
    branch_version_table,
    create_sqlite_engine,
    is_network_fs,
    upgrade,
)

from .ports import ProjectListing, ProjectSpaces, SpaceLike

_log = logging.getLogger(__name__)
_SHUT_MESSAGE = "서버를 닫는 중이라 프로젝트 메모리를 열 수 없습니다"


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


_DEFAULT_OPTIONS = PoolOptions()


@dataclass
class _Entry:
    space: ProjectMemorySpace
    stores: list[SqliteMemoryStore] = field(default_factory=list)


def _close_entry(entry: _Entry) -> None:
    for store in entry.stores:
        try:
            store.close()
        except Exception:  # pragma: no cover - 닫기 실패는 기록만
            _log.exception("프로젝트 메모리 DB를 닫지 못함: %s", entry.space.path.name)


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
        listing: 지금 ``projects.lookup``(등록 목록, 없으면 None — ``existing()``이 빈 목록).
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        branches: Callable[[], Sequence[MigrationBranchLike]],
        *,
        options: PoolOptions = _DEFAULT_OPTIONS,
        clock: Callable[[], float] = time.monotonic,
        network_fs: Callable[[Path], bool] = is_network_fs,
        folder_id_of: Callable[[Any], str | None] = folder_id,
        listing: Callable[[], ProjectListing | None] = lambda: None,
    ) -> None:
        self._listing = listing
        self._spaces = spaces
        self._branches = branches
        self._options = options
        self._network_fs = network_fs
        self._folder_id_of = folder_id_of
        self._entries: OpenCache[_Entry] = OpenCache(_close_entry, clock=clock)
        self._lock = self._entries.lock

    def open(self, space: str) -> ProjectMemorySpace:
        """등록 id의 메모리 공간(열려 있으면 그대로).

        Raises:
            LookupError: 모르는 프로젝트(또는 ``projects.spaces`` 없음).
            agent_console_project_space.FolderMissing: 폴더가 없다.
            agent_console_project_space.ConfigReadonly: 파일이 없고 쓸 수 없다.
            MemoryDbUnavailable: 계보를 올리지 못했다. 또는 서버 종료(``shutdown()``) 뒤다.
        """
        if self._entries.shut:
            raise MemoryDbUnavailable(_SHUT_MESSAGE)
        provider = self._spaces()
        if provider is None:
            raise LookupError(space)
        found = provider.open(space)
        with self._lock:
            if self._entries.shut:  # 공간을 찾는 사이에 닫혔다
                raise MemoryDbUnavailable(_SHUT_MESSAGE)
            self._sweep()
            path = Path(found.memory_db_path)
            entry = self._entries.get(space)
            if entry is not None and entry.space.path != path:
                self._drop(space)
                entry = None
            if entry is None:
                entry = self._make(space, found, path)
                self._entries.put(space, entry)
            self._enforce_cap()
            return entry.space

    def existing(self) -> list[str]:
        """메모리 DB가 이미 있는 등록 id(``memory.spaces``의 선택 메서드, 서버 자동 정리 대상).

        켜진(``archived``가 아닌) 등록 중 공간을 열 수 있고(폴더 있음) 구성 폴더에 쓸 수 있고
        ``memory.sqlite3`` 파일이 이미 있는 것만, 등록 목록 순서로. 아무것도 만들지 않고 저장소를
        열지 않는다. 열 수 없는 프로젝트는 건너뛴다(기록만). 등록 목록이나 공간 제공자가 없으면
        빈 목록.
        """
        provider = self._spaces()
        listing = self._listing()
        if provider is None or listing is None or self._entries.shut:
            return []
        out: list[str] = []
        for project in listing.list_projects():
            pid = getattr(project, "id", None)
            if not isinstance(pid, str) or not pid or getattr(project, "archived", False):
                continue
            try:
                found = provider.open(pid)
                if found.config_writable and Path(found.memory_db_path).is_file():
                    out.append(pid)
            except Exception as exc:
                _log.debug("자동 정리 대상에서 뺌(%s): %s", type(exc).__name__, pid)
        return out

    def close(self, space: str) -> None:
        """그 공간의 저장소를 닫는다(없으면 아무 일도 없다)."""
        with self._lock:
            self._drop(space)

    def close_all(self) -> None:
        """열린 저장소를 모두 닫는다(다음 ``open``은 다시 연다)."""
        self._entries.clear()

    def shutdown(self) -> None:
        """서버 종료: 열린 저장소를 모두 닫고, 그 뒤 ``open``은 ``MemoryDbUnavailable``(파일을
        열지 않는다), ``existing()``은 빈 목록. 여러 번 불러도 된다."""
        self._entries.shutdown()

    @property
    def is_shut(self) -> bool:
        """``shutdown()``을 불렀나."""
        return self._entries.shut

    def open_spaces(self) -> list[str]:
        """지금 열린 공간 이름(오래 안 쓴 것부터)."""
        return self._entries.names()

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
        return _Entry(ProjectMemorySpace(store, context, path), [store])

    def _drop(self, space: str) -> None:
        self._entries.drop(space)

    def _sweep(self) -> None:
        for space, _ in self._entries.idle(self._options.idle_close_seconds):
            self._drop(space)

    def _enforce_cap(self) -> None:
        for _, entry in self._entries.over(max(1, self._options.max_open)):
            _close_entry(entry)


__all__ = [
    "MemoryDbUnavailable",
    "PoolOptions",
    "ProjectMemoryPool",
    "ProjectMemorySpace",
    "folder_id",
    "migrate_memory_db",
]
