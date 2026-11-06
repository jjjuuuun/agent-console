"""공간 이름 → 프로젝트 기록 DB 핸들. 열린 핸들 캐시(상한·유휴 닫기)와 대기 파일 다시 쓰기.

``records.spaces`` 포트의 구현(``RecordsSpaces``). 프로젝트를 모르는 소비 모듈은
공간 이름 문자열만 넘긴다.
공간은 그 프로세스에서 **처음 쓸 때** 열고 계보를 맞춘다(서버 시작 때 열지 않는다).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from agent_console_project_space import FolderMissing, SpaceError
from agent_console_store import (
    MigrationBranchLike,
    RecordsDb,
    RecordsHandle,
    RecordsState,
    RecordsUnavailable,
    can_write_path,
    inspect_records,
    is_network_fs,
    open_records_db,
)

from .ports import ProjectSpaces, SpaceLike
from .replay import Applier, default_appliers, storage_apply
from .spool import RecordsSpool

_log = logging.getLogger(__name__)
_UNAVAILABLE = "unavailable"


class UnknownSpace(LookupError):  # noqa: N818 - 조회 실패 계열(LookupError)로 둔다
    """모르는 공간 이름(접두가 다르거나 등록되지 않은 프로젝트)."""


@dataclass(frozen=True)
class PoolOptions:
    """기록 공간 풀 설정(``ProjectsRecordsSettings``에서 온다)."""

    prefix: str = "project:"
    max_open: int = 8
    idle_close_seconds: float = 300.0
    busy_timeout: float = 5.0
    keep_backups: int = 3
    journal: str = "auto"


class SpaceRecords:
    """공간 하나의 기록 DB 핸들(``RecordsHandle``). 풀이 만든다.

    ``db``가 None이면 폴더를 열 수 없는 공간이다(``failure``가 이유). 읽기·쓰기는 폴더가 지금도
    있는지 먼저 확인한다(없으면 ``folder_missing`` - 사라진 폴더를 다시 만들지 않는다).
    """

    def __init__(
        self,
        pool: RecordsSpacePool,
        space: str,
        project_id: str,
        *,
        db: RecordsDb | None,
        folder: Path | None,
        failure: RecordsState | None,
        host_id: str,
    ) -> None:
        self._pool = pool
        self.space = space
        self.project_id = project_id
        self._db = db
        self._folder = folder
        self._failure = failure
        self._host_id = host_id

    @property
    def host_id(self) -> str:
        return self._host_id

    @property
    def state(self) -> RecordsState:
        if self._failure is not None:
            return self._failure
        if self._folder is not None and not self._pool.folder_exists(self._folder):
            return RecordsState(_UNAVAILABLE, "folder_missing", False)
        assert self._db is not None
        return self._db.state

    def _guard(self) -> RecordsDb:
        st = self.state
        if self._db is None or st.reason == "folder_missing":
            raise RecordsUnavailable(st.reason or "folder_missing", backup_path=st.backup_path)
        return self._db

    @property
    def engine(self) -> Engine:
        return self._guard().engine

    def read_engine(self) -> Engine | None:
        return self._guard().read_engine()

    def writable_engine(self) -> Engine:
        return self._guard().writable_engine()

    def spool(self, run_id: str, kind: str, data: Mapping[str, Any]) -> None:
        self._pool.spool.append(self.project_id, run_id, kind, data)

    def upgrade(self, branches: Any = ()) -> None:
        self._guard().upgrade(branches)

    def close(self) -> None:
        self._pool.close(self.space)


@dataclass
class _Entry:
    handle: SpaceRecords
    db: RecordsDb
    path: Path
    last_used: float


class RecordsSpacePool:
    """``RecordsSpaces`` 구현.

    Args:
        spaces: ``projects.spaces``(프로젝트 등록 id → 공간).
        branches: 열 때마다 부르는 함수 - 올릴 계보(켜진 모듈 중 ``project`` 범위를 선언한 것,
            ``ModuleContext.active_migrations("project")``).
        host_id: 이 앱의 id(``load_host_id``).
        spool: 쓰기 실패 대기 파일 저장소.
        options: 접두·상한·유휴·잠금 대기·백업 개수·저널.
        appliers: 대기 줄 종류 → 적용 함수. 생략하면 ``default_appliers()``.
        clock: 단조 시계(초).
        wall_clock: 백업 이름용 시각(UTC 초).
        folder_exists: 폴더가 있나(주입).
        network_fs: 경로가 네트워크 파일 시스템인가(주입).
    """

    def __init__(
        self,
        spaces: Callable[[], ProjectSpaces | None],
        branches: Callable[[], Sequence[MigrationBranchLike]],
        *,
        host_id: str,
        spool: RecordsSpool,
        options: PoolOptions = PoolOptions(),  # noqa: B008 - 불변 값
        appliers: Mapping[str, Applier] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        folder_exists: Callable[[Path], bool] = Path.is_dir,
        network_fs: Callable[[Path], bool] = is_network_fs,
    ) -> None:
        self._spaces = spaces
        self._branches = branches
        self._host_id = host_id
        self.spool = spool
        self._options = options
        self._appliers = dict(appliers) if appliers is not None else default_appliers()
        self._clock = clock
        self._wall_clock = wall_clock
        self.folder_exists = folder_exists
        self._network_fs = network_fs
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.RLock()

    # ---- RecordsSpaces -------------------------------------------------------

    def open(self, space: str) -> RecordsHandle:
        """공간의 기록 DB 핸들. 열려 있으면 그대로, 아니면 열고 계보를 맞춘 뒤 대기 파일을 쓴다.

        열 수 없는 공간(폴더 없음 등)도 핸들을 돌려준다. 읽기·쓰기에서 ``RecordsUnavailable``이
        나고 ``state``에 이유가 있다.

        Raises:
            UnknownSpace: 모르는 공간 이름이거나 등록되지 않은 프로젝트.
        """
        project_id = self._project_id(space)
        with self._lock:
            self._sweep()
            found = self._resolve(project_id)
            if isinstance(found, RecordsState):
                self._drop(space)
                return self._failed(space, project_id, found)
            path = found.records_db_path
            entry = self._entries.get(space)
            if entry is not None and entry.path != path:
                self._drop(space)  # 경로를 다시 지정했다
                entry = None
            if entry is None:
                entry = self._make(space, project_id, found)
                self._entries[space] = entry
                self._replay(project_id, entry.db)
            entry.last_used = self._clock()
            self._entries.move_to_end(space)
            self._enforce_cap()
            return entry.handle

    def state(self, space: str) -> RecordsState:
        """상태만. 열려 있지 않으면 파일을 만들거나 올리지 않고 살펴본다.

        Raises:
            UnknownSpace: 모르는 공간 이름이거나 등록되지 않은 프로젝트.
        """
        project_id = self._project_id(space)
        with self._lock:
            found = self._resolve(project_id)
            if isinstance(found, RecordsState):
                return found
            entry = self._entries.get(space)
            if entry is not None and entry.path == found.records_db_path:
                return entry.handle.state
            return inspect_records(
                found.records_db_path,
                self._branches(),
                busy_timeout=self._options.busy_timeout,
                can_write=self._can_write(found),
                network_fs=self._network_fs,
            )

    def close(self, space: str) -> None:
        """공간의 핸들을 닫는다(없으면 아무 일도 없다)."""
        with self._lock:
            self._drop(space)

    def close_all(self) -> None:
        """열린 핸들을 모두 닫는다(서버 종료)."""
        with self._lock:
            for space in list(self._entries):
                self._drop(space)

    def open_spaces(self) -> list[str]:
        """지금 열려 있는 공간 이름(최근에 쓴 순서의 반대, 점검용)."""
        with self._lock:
            return list(self._entries)

    # ---- 내부 ----------------------------------------------------------------

    def _project_id(self, space: str) -> str:
        prefix = self._options.prefix
        if not space.startswith(prefix) or len(space) == len(prefix):
            raise UnknownSpace(f"unknown records space: {space!r}")
        return space[len(prefix) :]

    def _resolve(self, project_id: str) -> SpaceLike | RecordsState:
        spaces = self._spaces()
        if spaces is None:
            return RecordsState(_UNAVAILABLE, "link_disabled", False)
        try:
            found = spaces.open(project_id)
        except FolderMissing:
            return RecordsState(_UNAVAILABLE, "folder_missing", False)
        except SpaceError:
            return RecordsState(_UNAVAILABLE, "readonly", False)
        except LookupError as exc:
            raise UnknownSpace(f"unknown project: {project_id!r}") from exc
        if found is None:
            raise UnknownSpace(f"unknown project: {project_id!r}")
        return found

    def _can_write(self, space: SpaceLike) -> Callable[[Path], bool]:
        def can_write(path: Path) -> bool:
            return (
                space.config_writable and self.folder_exists(space.folder) and can_write_path(path)
            )

        return can_write

    def _make(self, space: str, project_id: str, found: SpaceLike) -> _Entry:
        opts = self._options
        db = open_records_db(
            found.records_db_path,
            self._branches(),
            backup_dir=found.state_dir / "backups",
            journal=opts.journal,
            busy_timeout=opts.busy_timeout,
            keep_backups=opts.keep_backups,
            clock=self._wall_clock,
            can_write=self._can_write(found),
            network_fs=self._network_fs,
        )
        handle = SpaceRecords(
            self,
            space,
            project_id,
            db=db,
            folder=found.folder,
            failure=None,
            host_id=self._host_id,
        )
        return _Entry(handle, db, found.records_db_path, self._clock())

    def _failed(self, space: str, project_id: str, state: RecordsState) -> SpaceRecords:
        return SpaceRecords(
            self, space, project_id, db=None, folder=None, failure=state, host_id=self._host_id
        )

    def _replay(self, project_id: str, db: RecordsDb) -> None:
        """이 공간의 대기 파일을 기록 DB에 다시 쓴다(쓸 수 있을 때만, 실패는 남겨 둔다)."""
        if not self.spool.pending(project_id) or not db.state.writable:
            return
        try:
            engine = db.writable_engine()
            result = self.spool.drain(project_id, storage_apply(engine, self._appliers))
        except RecordsUnavailable as exc:
            _log.warning("records spool replay skipped (%s): %s", project_id, exc.reason)
            return
        for error in result.errors:
            _log.warning("records spool replay failed (%s): %s", project_id, type(error).__name__)

    def _drop(self, space: str) -> None:
        entry = self._entries.pop(space, None)
        if entry is not None:
            entry.db.close()

    def _sweep(self) -> None:
        idle = self._options.idle_close_seconds
        if idle <= 0:
            return
        now = self._clock()
        for entry in self._entries.values():
            if now - entry.last_used >= idle:
                entry.db.suspend()

    def _enforce_cap(self) -> None:
        while len(self._entries) > self._options.max_open:
            _, entry = self._entries.popitem(last=False)
            entry.db.suspend()  # 들고 있는 쪽이 다시 쓰면 살아난다(닫지 않는다)


__all__ = ["PoolOptions", "RecordsSpacePool", "SpaceRecords", "UnknownSpace"]
