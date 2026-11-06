# ruff: noqa: N818
"""프로젝트 기록 DB 열기: 폴더 안 SQLite 파일 하나를 앱 DB와 같은 계보 사슬로 맞춘다.

design §PI.4.6.2(K33-28). 서버·모듈 없이 파일 경로와 계보 목록만으로 동작한다.

- 파일이 없으면 **만들지 않는다**(`absent`, 보기 = 빈 목록).
  처음 쓸 때 `writable_engine()`이 만든다.
- 이 앱 head와 같으면 `ready`, 뒤처졌으면 **온라인 백업 후 계보별로 올린다**
  (쓰기 잠금 안에서 리비전을 다시 읽으므로 두 연결이 동시에 열어도 한쪽만 적용한다).
- 이 앱이 모르는 리비전이 있으면(더 새 앱이 올림) 올리지도 내리지도 않고
  `mode=ro`로만 연다(`newer`).
- 깨졌거나 올리다 실패했거나 쓸 수 없으면 `unavailable`(이유 `reason`). 앱 DB로 대신 쓰지 않는다.
- 자동으로 내리지 않는다. 내림은 사용자가 백업 파일로 되돌리는 것뿐이다.

계보 이름 목록은 코드에 없다. 호출자가 `branches`(= 켜진 모듈 중 프로젝트 범위를 선언한 계보,
modkit `MigrationBranch.scopes`)를 넘긴다. 계보 없이 `create_all`하는 경로는 없다.
"""

from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from agent_console_contracts import (
    ErrorCodes,
    KnownProjectRecordsStates,
    KnownRecordsUnavailableReasons,
)

from .database import LEGACY_BRANCH, MigrationBranchLike, _check_name
from .errors import StoreError
from .migrate import (
    LEGACY_VERSION_TABLE,
    branch_version_table,
    script_revisions,
    upgrade_on,
)
from .sqlite import create_sqlite_engine

RECORDS_SPACES_PORT = "records.spaces"
"""기록 공간 포트 이름. 소비 모듈은 같은 이름의 `PortKey`를 자기 `ports`에 선언한다."""

_STATES = KnownProjectRecordsStates
_REASONS = KnownRecordsUnavailableReasons
_JOURNALS = ("WAL", "DELETE")
_NETWORK_FS_TYPES = frozenset(
    {"nfs", "nfs4", "cifs", "smb", "smb2", "smb3", "smbfs", "afs", "ncpfs", "fuse.sshfs", "sshfs"}
)


class RecordsUnavailable(StoreError):
    """기록 DB를 쓸 수 없다 -> `project.records_unavailable`(409).

    Attributes:
        reason: `KnownRecordsUnavailableReasons`의 값(readonly·newer·busy·corrupt 등).
        backup_path: 올리다 실패했을 때 되돌릴 백업 파일.
        project_id: 어느 프로젝트의 기록인가(공간을 고른 쪽이 채운다, 5.7R.33y2). 없으면 None.
    """

    code = ErrorCodes.PROJECT_RECORDS_UNAVAILABLE

    def __init__(
        self,
        reason: str,
        message: str = "",
        *,
        backup_path: Path | None = None,
        project_id: str | None = None,
    ) -> None:
        super().__init__(message or f"records db unavailable: {reason}")
        self.reason = reason
        self.backup_path = backup_path
        self.project_id = project_id

    def details(self) -> dict[str, Any]:
        """409 본문 `details`(`ProjectRecordsUnavailableDetails` 모양, 없는 값은 뺀다)."""
        out: dict[str, Any] = {"reason": self.reason}
        if self.project_id is not None:
            out["project_id"] = self.project_id
        if self.backup_path is not None:
            out["backup_path"] = str(self.backup_path)
        return out


class RecordsAbsent(StoreError):
    """기록 DB 파일이 아직 없어 `engine`이 없다(`read_engine()`은 None) -> `not_found`."""

    code = "not_found"


@dataclass(frozen=True, slots=True)
class RecordsState:
    """기록 DB의 현재 상태.

    Attributes:
        state: `KnownProjectRecordsStates`의 값(absent·ready·newer·unavailable).
        reason: 쓸 수 없는 이유(`KnownRecordsUnavailableReasons`). 쓸 수 있으면 None.
        writable: 지금 쓸 수 있나(absent·ready이고 폴더에 쓸 수 있을 때만 참).
        backup_path: 이번에 올리면서 만든 백업(올림이 없었으면 None).
        journal_mode: 쓰는 저널(`WAL` 또는 `DELETE`).
        network_fs: 네트워크 파일 시스템으로 감지됐나(저널을 `DELETE`로 둔 이유).
    """

    state: str
    reason: str | None = None
    writable: bool = False
    backup_path: Path | None = None
    journal_mode: str = "WAL"
    network_fs: bool = False


@runtime_checkable
class RecordsHandle(Protocol):
    """소비 모듈(runs·chat·definitions)이 보는 기록 DB 모양. 구현은 `RecordsDb`(+ `host_id`).

    쓰기 전에는 늘 `writable_engine()`을 부른다(리비전 재확인). `engine`을 오래 들고 있지 않는다.
    """

    @property
    def state(self) -> RecordsState: ...

    @property
    def host_id(self) -> str:
        """이 앱의 id. Run·대기열에 남겨 두 앱의 복구 정책을 가른다."""
        ...

    @property
    def engine(self) -> Engine: ...

    def read_engine(self) -> Engine | None:
        """읽기용 엔진. 파일이 없으면 None(빈 목록), 읽을 수 없으면 `RecordsUnavailable`."""
        ...

    def writable_engine(self) -> Engine:
        """쓰기용 엔진(없으면 만들고 계보를 올린다). 못 쓰면 `RecordsUnavailable`."""
        ...

    def spool(self, run_id: str, kind: str, data: Mapping[str, Any]) -> None:
        """쓰지 못한 기록을 앱 대기 파일에 남긴다(폴더가 사라졌을 때). 다음에 열 때 다시 쓴다."""
        ...

    def close(self) -> None: ...


@runtime_checkable
class RecordsSpaces(Protocol):
    """`records.spaces` 포트 모양. 공간 이름은 불투명 문자열(예: `project:<등록 id>`)."""

    def open(self, space: str) -> RecordsHandle:
        """공간의 기록 DB 핸들(그 프로세스에서 처음이면 열고 계보를 맞춘다)."""
        ...

    def state(self, space: str) -> RecordsState:
        """상태만(파일을 만들지 않는다. 열려 있지 않으면 가볍게 살펴본다)."""
        ...

    def close(self, space: str) -> None:
        """공간의 핸들을 닫는다."""
        ...


def is_network_fs(path: str | Path, *, mountinfo: str | None = None) -> bool:
    """`path`가 네트워크 파일 시스템 위에 있는 것으로 보이나(감지할 수 있을 때만, 모르면 False).

    Windows UNC 경로(`\\\\서버\\공유`)와 Linux `/proc/self/mountinfo`의 파일 시스템 종류를 본다.

    Args:
        path: 확인할 경로(없어도 된다).
        mountinfo: 테스트용 `mountinfo` 텍스트. 생략하면 `/proc/self/mountinfo`.
    """
    text = str(path)
    if text.startswith("\\\\"):
        return True
    if mountinfo is None:
        try:
            mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        except OSError:
            return False
    target = Path(os.path.abspath(text)).as_posix()
    best_len = -1
    best_type = ""
    for line in mountinfo.splitlines():
        head, sep, tail = line.partition(" - ")
        fields = head.split()
        if not sep or len(fields) < 5 or not tail:
            continue
        mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
        within = target == mount or target.startswith(mount.rstrip("/") + "/")
        if within and len(mount) > best_len:
            best_len = len(mount)
            best_type = tail.split()[0]
    return best_type in _NETWORK_FS_TYPES


def can_write_path(path: str | Path) -> bool:
    """`path`(파일)를 만들거나 고칠 수 있나: 있으면 파일과 폴더, 없으면 가장 가까운 기존 폴더."""
    target = Path(path)
    if target.exists():
        return os.access(target, os.W_OK) and os.access(target.parent, os.W_OK)
    probe = target.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe.is_dir() and os.access(probe, os.W_OK)


type Rows = Callable[[str, tuple[Any, ...]], Sequence[Any]]


def _revisions(rows: Rows, tables: Mapping[str, str]) -> dict[str, str | None]:
    """계보 이름 → 적용된 리비전(버전 표가 없거나 비었으면 None)."""
    out: dict[str, str | None] = {}
    for name, table in tables.items():
        found = rows("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
        value: str | None = None
        if found:
            got = rows(f'SELECT version_num FROM "{table}"', ())
            value = str(got[0][0]) if got else None
        out[name] = value
    return out


type Verdict = Literal["same", "behind", "newer"]


def _verdict(
    revs: Mapping[str, str | None], scripts: Mapping[str, tuple[str | None, frozenset[str]]]
) -> Verdict:
    behind = False
    for name, rev in revs.items():
        head, known = scripts[name]
        if rev is None:
            behind = behind or head is not None
        elif rev not in known:
            return "newer"
        elif rev != head:
            behind = True
    return "behind" if behind else "same"


def _ro_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def _read_revisions_ro(
    path: Path, tables: Mapping[str, str], timeout: float
) -> dict[str, str | None]:
    """`mode=ro`로 버전 표를 읽는다(파일을 만들거나 고치지 않는다)."""
    conn = sqlite3.connect(_ro_uri(path), uri=True, timeout=timeout)
    try:
        return _revisions(lambda sql, p: conn.execute(sql, p).fetchall(), tables)
    finally:
        conn.close()


def _tables_and_scripts(
    branches: Iterable[MigrationBranchLike],
) -> tuple[dict[str, str], dict[str, tuple[str | None, frozenset[str]]]]:
    tables = {LEGACY_BRANCH: LEGACY_VERSION_TABLE}
    scripts = {LEGACY_BRANCH: script_revisions(None)}
    for b in branches:
        _check_name(b.name)
        tables[b.name] = branch_version_table(b.name)
        scripts[b.name] = script_revisions(b.versions)
    return tables, scripts


def inspect_records(
    path: str | Path,
    branches: Iterable[MigrationBranchLike] = (),
    *,
    busy_timeout: float = 5.0,
    can_write: Callable[[Path], bool] = can_write_path,
    network_fs: Callable[[Path], bool] = is_network_fs,
) -> RecordsState:
    """파일을 만들거나 올리지 않고 상태만 살펴본다(프로젝트 목록의 `records_state`용).

    뒤처진 DB는 `ready`로 본다(처음 쓸 때 `open_records_db`가 백업 후 올린다). 인자는
    `open_records_db`와 같다.
    """
    target = Path(path)
    tables, scripts = _tables_and_scripts(branches)
    net = network_fs(target)
    journal = "DELETE" if net else "WAL"
    writable = can_write(target)
    if not target.exists():
        return RecordsState(
            _STATES.ABSENT, None if writable else _REASONS.READONLY, writable, None, journal, net
        )
    try:
        revs = _read_revisions_ro(target, tables, busy_timeout)
    except sqlite3.OperationalError as exc:
        reason = _open_error_reason(exc, target, writable)
        return RecordsState(_STATES.UNAVAILABLE, reason, False, None, journal, net)
    except sqlite3.DatabaseError:
        return RecordsState(_STATES.UNAVAILABLE, _REASONS.CORRUPT, False, None, journal, net)
    if _verdict(revs, scripts) == "newer":
        return RecordsState(_STATES.NEWER, _REASONS.NEWER, False, None, journal, net)
    return RecordsState(
        _STATES.READY, None if writable else _REASONS.READONLY, writable, None, journal, net
    )


def _open_error_reason(exc: sqlite3.OperationalError, path: Path, writable: bool) -> str:
    text = str(exc).lower()
    if "locked" in text or "busy" in text:
        return _REASONS.BUSY
    if "unable to open" in text or "readonly" in text or "permission" in text:
        return (
            _REASONS.READONLY if not writable or not os.access(path, os.R_OK) else _REASONS.CORRUPT
        )
    return _REASONS.CORRUPT


class RecordsDb:
    """폴더 기록 DB 하나. `open_records_db`로 만든다.

    스레드 안전하다(상태 전이는 내부 잠금). 엔진은 상태에 따라 읽기·쓰기 용도가 정해진다.
    """

    def __init__(
        self,
        path: Path,
        branches: Sequence[MigrationBranchLike],
        *,
        backup_dir: Path,
        journal: str,
        busy_timeout: float,
        keep_backups: int,
        clock: Callable[[], float],
        can_write: Callable[[Path], bool],
        network_fs: Callable[[Path], bool],
    ) -> None:
        if journal not in (*_JOURNALS, "auto"):
            raise ValueError(f"journal must be one of WAL, DELETE, auto: {journal!r}")
        self.path = path
        self._backup_dir = backup_dir
        self._journal_arg = journal
        self._timeout = busy_timeout
        self._keep = max(1, keep_backups)
        self._clock = clock
        self._can_write = can_write
        self._network_fs = network_fs
        self._lock = threading.RLock()
        self._branches: dict[str, MigrationBranchLike] = {}
        self._scripts: dict[str, tuple[str | None, frozenset[str]]] = {}
        self._tables: dict[str, str] = {}
        self._engine: Engine | None = None
        self._engine_writable = False
        self._closed = False
        self._stale = False
        self._journal = "WAL"
        self._net = False
        self._state = RecordsState(_STATES.ABSENT)
        self._add_branches([_Legacy(), *branches])
        self.refresh()

    # ---- 읽기 ----------------------------------------------------------------

    @property
    def state(self) -> RecordsState:
        """현재 상태(쓰기 전 재확인은 `writable_engine()`이 한다)."""
        return self._state

    @property
    def exists(self) -> bool:
        """기록 DB 파일이 있나."""
        return self.path.exists()

    @property
    def engine(self) -> Engine:
        """상태에 맞는 엔진(`newer`·읽기 전용이면 `mode=ro`). 파일이 없으면 `RecordsAbsent`."""
        with self._lock:
            self._revive()
            engine = self._engine
            if engine is None:
                if self._state.state == _STATES.ABSENT:
                    raise RecordsAbsent(str(self.path.name))
                raise self._unavailable()
            return engine

    def read_engine(self) -> Engine | None:
        """읽기용 엔진. 파일이 없으면 None. 열 수 없으면 `RecordsUnavailable`."""
        try:
            return self.engine
        except RecordsAbsent:
            return None

    def revision(self, branch: str = LEGACY_BRANCH) -> str | None:
        """계보의 적용된 리비전(파일이 없으면 None)."""
        if not self.path.exists():
            return None
        table = self._tables.get(branch)
        if table is None:
            table = (
                LEGACY_VERSION_TABLE if branch == LEGACY_BRANCH else branch_version_table(branch)
            )
        return self._read_revisions({branch: table})[branch]

    # ---- 쓰기 ----------------------------------------------------------------

    def writable_engine(self) -> Engine:
        """쓰기용 엔진. 쓰기 전에 파일·리비전을 다시 확인한다(싸다).

        파일이 없으면 만들고 계보를 끝까지 올린다. 더 새 앱이 올렸으면 상태가 `newer`로 바뀌고
        예외를 던진다.

        Raises:
            RecordsUnavailable: 폴더에 쓸 수 없음(readonly)·newer·busy·corrupt·migration_failed.
        """
        with self._lock:
            self._check_open()
            self._revive()
            st = self._state
            if st.state == _STATES.UNAVAILABLE and st.reason == _REASONS.BUSY:
                self.refresh()
                st = self._state
            if st.state == _STATES.NEWER:
                self.refresh()  # 앱이 올라갔을 수 있다
                st = self._state
            if st.state == _STATES.UNAVAILABLE or st.state == _STATES.NEWER:
                raise self._unavailable()
            if not self._can_write(self.path):
                self._set(
                    _STATES.READY if self.path.exists() else _STATES.ABSENT,
                    False,
                    _REASONS.READONLY,
                )
                raise self._unavailable()
            if st.state == _STATES.ABSENT or not self.path.exists():
                self._migrate()
            else:
                self._recheck()
            st = self._state
            if st.state != _STATES.READY or not self._engine_writable or self._engine is None:
                raise self._unavailable()
            return self._engine

    def upgrade(self, branches: Iterable[MigrationBranchLike] = ()) -> None:
        """계보를 더 알리고(`DatabaseHandle` 모양) 쓰기 가능하게 만든다(파일이 없으면 만든다)."""
        with self._lock:
            self._add_branches(list(branches))
            self.writable_engine()

    def refresh(self) -> RecordsState:
        """파일을 처음부터 다시 살펴 상태를 정한다(뒤처졌으면 백업 후 올린다)."""
        with self._lock:
            self._check_open()
            self._stale = False
            self._drop_engine()
            path = self.path
            net = self._network_fs(path)
            journal = (
                ("DELETE" if net else "WAL") if self._journal_arg == "auto" else self._journal_arg
            )
            self._journal = journal
            self._net = net
            writable = self._can_write(path)
            if not path.exists():
                self._set(_STATES.ABSENT, writable, None if writable else _REASONS.READONLY)
                return self._state
            try:
                revs = self._read_revisions(self._tables)
            except sqlite3.OperationalError as exc:
                reason = _open_error_reason(exc, path, writable)
                self._set(_STATES.UNAVAILABLE, False, reason)
                return self._state
            except sqlite3.DatabaseError:
                self._set(_STATES.UNAVAILABLE, False, _REASONS.CORRUPT)
                return self._state
            verdict = _verdict(revs, self._scripts)
            if verdict == "newer":
                self._engine = self._ro_engine()
                self._engine_writable = False
                self._set(_STATES.NEWER, False, _REASONS.NEWER)
            elif verdict == "behind":
                if not writable:
                    self._set(_STATES.UNAVAILABLE, False, _REASONS.READONLY)
                else:
                    with contextlib.suppress(RecordsUnavailable):  # 상태는 _migrate가 정했다
                        self._migrate()
            elif writable:
                self._engine = self._rw_engine()
                self._engine_writable = True
                self._set(_STATES.READY, True, None)
            else:
                self._engine = self._ro_engine()
                self._engine_writable = False
                self._set(_STATES.READY, False, _REASONS.READONLY)
            return self._state

    def suspend(self) -> None:
        """연결을 모두 닫되 다시 쓸 수 있게 둔다(유휴 닫기). 다음 접근 때 상태를 다시 살핀다."""
        with self._lock:
            self._drop_engine()
            self._stale = True

    def close(self) -> None:
        """엔진의 연결을 모두 닫는다(여러 번 불러도 된다). 닫은 뒤에는 쓸 수 없다."""
        with self._lock:
            self._closed = True
            self._drop_engine()

    # ---- 내부 ----------------------------------------------------------------

    def _revive(self) -> None:
        if self._stale and not self._closed:
            self.refresh()

    def _check_open(self) -> None:
        if self._closed:
            raise RecordsUnavailable(_REASONS.FOLDER_MISSING, "records db is closed")

    def _add_branches(self, branches: Sequence[MigrationBranchLike]) -> None:
        for b in branches:
            if isinstance(b, _Legacy):
                self._tables[LEGACY_BRANCH] = LEGACY_VERSION_TABLE
                self._scripts[LEGACY_BRANCH] = script_revisions(None)
                continue
            _check_name(b.name)
            self._branches[b.name] = b
            self._tables[b.name] = branch_version_table(b.name)
            self._scripts[b.name] = script_revisions(b.versions)

    def _set(
        self, state: str, writable: bool, reason: str | None, backup: Path | None = None
    ) -> None:
        if backup is None and self._state.backup_path is not None and state == _STATES.READY:
            backup = self._state.backup_path
        self._state = RecordsState(
            state,
            reason,
            writable and state in (_STATES.ABSENT, _STATES.READY),
            backup,
            self._journal,
            self._net,
        )

    def _unavailable(self) -> RecordsUnavailable:
        st = self._state
        return RecordsUnavailable(st.reason or _REASONS.CORRUPT, backup_path=st.backup_path)

    def _drop_engine(self) -> None:
        engine, self._engine = self._engine, None
        self._engine_writable = False
        if engine is not None:
            engine.dispose()

    def _rw_engine(self) -> Engine:
        return create_sqlite_engine(self.path, journal_mode=self._journal, timeout=self._timeout)

    def _ro_engine(self) -> Engine:
        uri = _ro_uri(self.path)
        timeout = self._timeout

        def connect() -> sqlite3.Connection:
            return sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=timeout)

        return sa.create_engine("sqlite://", creator=connect, poolclass=sa.pool.QueuePool)

    def _read_revisions(self, tables: Mapping[str, str]) -> dict[str, str | None]:
        return _read_revisions_ro(self.path, tables, self._timeout)

    def _recheck(self) -> None:
        """쓰기 전 리비전 재확인. 앞섰으면 `newer`로 바꾸고, 뒤처졌으면 다시 올린다."""
        engine = self._engine
        if engine is None:
            self.refresh()
            return
        try:
            with engine.connect() as conn:
                revs = _revisions(
                    lambda sql, p: conn.exec_driver_sql(sql, p).fetchall(), self._tables
                )
        except sa.exc.DatabaseError:
            self.refresh()
            return
        verdict = _verdict(revs, self._scripts)
        if verdict == "newer":
            self._drop_engine()
            self._engine = self._ro_engine()
            self._set(_STATES.NEWER, False, _REASONS.NEWER)
        elif verdict == "behind":
            self._migrate()

    def _migrate(self) -> None:
        """쓰기 잠금 안에서 리비전을 다시 읽고, 뒤처졌으면 백업 후 계보별로 올린다.

        Raises:
            RecordsUnavailable: 잠금 시간 초과(busy)·읽기 전용·깨짐·올리기 실패(백업 경로 포함).
        """
        self._drop_engine()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        engine = self._rw_engine()
        backup: Path | None = None
        phase = "lock"
        newer = False
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    revs = _revisions(
                        lambda sql, p: conn.exec_driver_sql(sql, p).fetchall(), self._tables
                    )
                    verdict = _verdict(revs, self._scripts)
                    phase = "migrate"
                    if verdict == "newer":
                        newer = True
                    elif verdict == "behind":
                        if any(r is not None for r in revs.values()):
                            backup = self._backup(revs)
                        self._upgrade_all(conn)
                    if newer:
                        conn.rollback()
                    else:
                        conn.commit()
                except BaseException:
                    with contextlib.suppress(Exception):
                        conn.rollback()
                    raise
        except Exception as exc:
            engine.dispose()
            reason = _REASONS.MIGRATION_FAILED
            if phase == "lock" and isinstance(exc, sa.exc.OperationalError):
                text = str(exc).lower()
                reason = (
                    _REASONS.BUSY if ("locked" in text or "busy" in text) else _REASONS.READONLY
                )
            elif phase == "lock" and isinstance(exc, sa.exc.DatabaseError):
                reason = _REASONS.CORRUPT
            self._set(_STATES.UNAVAILABLE, False, reason, backup)
            raise self._unavailable() from exc
        if newer:
            engine.dispose()
            self._engine = self._ro_engine()
            self._set(_STATES.NEWER, False, _REASONS.NEWER)
            return
        self._engine = engine
        self._engine_writable = True
        self._set(_STATES.READY, True, None, backup)

    def _upgrade_all(self, conn: Connection) -> None:
        upgrade_on(conn, versions=None, version_table=LEGACY_VERSION_TABLE)
        for name, branch in self._branches.items():
            upgrade_on(conn, versions=branch.versions, version_table=branch_version_table(name))

    def _backup(self, revs: Mapping[str, str | None]) -> Path:
        """SQLite 온라인 백업 API로 올리기 전 상태를 `backup_dir`에 복사하고 오래된 것을 지운다."""
        stamp = datetime.fromtimestamp(self._clock(), UTC).strftime("%Y%m%dT%H%M%SZ")
        behind = [
            f"{name}@{rev}"
            for name, rev in revs.items()
            if rev is not None and rev != self._scripts[name][0]
        ]
        label = "-".join(behind) or "empty"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        dest = self._backup_dir / f"records-{stamp}-{label}.sqlite3"
        n = 1
        while dest.exists():
            n += 1
            dest = self._backup_dir / f"records-{stamp}-{label}-{n}.sqlite3"
        src = sqlite3.connect(_ro_uri(self.path), uri=True, timeout=self._timeout)
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        except BaseException:
            out.close()
            src.close()
            dest.unlink(missing_ok=True)
            raise
        out.close()
        src.close()
        olds = sorted(
            self._backup_dir.glob("records-*.sqlite3"), key=lambda p: (p.stat().st_mtime, p.name)
        )
        for old in olds[: max(0, len(olds) - self._keep)]:
            if old != dest:
                old.unlink(missing_ok=True)
        return dest


class _Legacy:
    """legacy 계보 표지(내부). `name`·`versions`는 쓰지 않는다."""

    name = LEGACY_BRANCH
    versions = Path()


def open_records_db(
    path: str | Path,
    branches: Iterable[MigrationBranchLike] = (),
    *,
    backup_dir: str | Path,
    journal: str = "auto",
    busy_timeout: float = 5.0,
    keep_backups: int = 3,
    clock: Callable[[], float] = time.time,
    can_write: Callable[[Path], bool] = can_write_path,
    network_fs: Callable[[Path], bool] = is_network_fs,
) -> RecordsDb:
    """프로젝트 기록 DB를 연다(파일이 없어도 만들지 않는다).

    legacy(0001~0003) + `branches`를 앱 DB와 같은 방식으로 맞춘다: 같으면 그대로, 뒤처졌으면 백업 후
    올림, 앞섰으면 읽기만, 깨졌거나 못 쓰면 `unavailable`. 상태는 `RecordsDb.state`.

    Args:
        path: `records.sqlite3` 경로.
        branches: 올릴 모듈 계보(`name`·`versions`가 있으면 된다). 프로젝트 범위를 선언한
            켜진 모듈의 것을 호출자가 모아 준다.
        backup_dir: 올리기 전 백업을 둘 폴더(보통 `<구성 폴더>/.state/backups`).
        journal: `WAL`·`DELETE`·`auto`(네트워크 파일 시스템이면 `DELETE`).
        busy_timeout: 다른 연결의 잠금을 기다리는 시간(초).
        keep_backups: 보관할 백업 개수.
        clock: 백업 파일 이름에 쓰는 시각(UTC 초).
        can_write: 경로에 쓸 수 있나(주입 — 테스트·원격 파일 시스템).
        network_fs: 경로가 네트워크 파일 시스템인가(주입).

    Raises:
        ValueError: `journal`이 허용 값이 아니거나 계보 이름을 쓸 수 없다.

    >>> import tempfile
    >>> tmp = Path(tempfile.mkdtemp())
    >>> db = open_records_db(tmp / "records.sqlite3", backup_dir=tmp / "backups")
    >>> db.state.state, db.exists
    ('absent', False)
    >>> _ = db.writable_engine()  # 처음 쓸 때 만들고 legacy를 올린다
    >>> db.state.state, db.exists, db.revision()
    ('ready', True, '0003')
    >>> db.close()
    """
    return RecordsDb(
        Path(path),
        list(branches),
        backup_dir=Path(backup_dir),
        journal=journal,
        busy_timeout=busy_timeout,
        keep_backups=keep_backups,
        clock=clock,
        can_write=can_write,
        network_fs=network_fs,
    )


__all__ = [
    "RECORDS_SPACES_PORT",
    "RecordsAbsent",
    "RecordsDb",
    "RecordsHandle",
    "RecordsSpaces",
    "RecordsState",
    "RecordsUnavailable",
    "can_write_path",
    "inspect_records",
    "is_network_fs",
    "open_records_db",
]
