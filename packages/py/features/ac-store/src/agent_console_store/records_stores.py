"""프로젝트 기록 DB 위의 저장소 고르기(`RecordsStores`, design §PI.4.6.3, 5.7R.33y2).

실행·대화 모듈은 프로젝트를 모른다. 요청의 프로젝트 id(불투명 문자열)를 받아
`records.spaces` 포트(`RecordsSpaces`)로 그 공간의 기록 DB 핸들을 열고, 핸들의 엔진 위에 자기
저장소 묶음(예: `SqliteStorage`)을 만든다.

- 읽기는 `reader(project_id)` - 파일이 없으면 None(빈 목록, 파일을 만들지 않는다).
- 쓰기는 `writer(project_id)` - **부를 때마다** `writable_engine()`(쓰기 전 리비전 재확인). 못 쓰면
  `RecordsUnavailable`(409, `project_id`를 채운다).
- 같은 엔진이면 저장소 묶음을 다시 쓴다(저장소가 만들 때 열 유무를 한 번 보므로 매번 만들지 않는다).
- 그 공간을 이 프로세스에서 처음 열면 `on_open(project_id)`를 한 번 부른다(재시작 복구 자리,
  §PI.4.6.5). 거짓을 돌려주거나 예외가 나면 다음 열기 때 다시 부른다.

포트가 없으면 `available`이 거짓이다. 소비 모듈은 그때 호스트 DB(기능 단독)를 쓴다.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable

from sqlalchemy import Engine

from agent_console_contracts import KnownRecordsUnavailableReasons

from .records import RecordsHandle, RecordsSpaces, RecordsUnavailable
from .spaces import UnknownSpace

_log = logging.getLogger(__name__)
_MADE_CAP = 64
"""엔진별 저장소 묶음을 들고 있는 최대 개수(공간 캐시 상한보다 넉넉히)."""


class RecordsStores[S]:
    """프로젝트 id → 그 기록 DB 위의 저장소 묶음.

    Args:
        spaces: 지금 `records.spaces` 포트(부를 때마다, 없으면 None).
        make: 엔진 → 저장소 묶음(예: `SqliteStorage`).
        prefix: 공간 이름 접두(공간 이름 = 접두 + 프로젝트 id).
        on_open: 그 공간을 이 프로세스에서 처음 열 때 부르는 함수(참 = 끝남).

    >>> import tempfile
    >>> from pathlib import Path
    >>> from agent_console_store import SqliteStorage, open_records_db
    >>> tmp = Path(tempfile.mkdtemp())
    >>> db = open_records_db(tmp / "records.sqlite3", backup_dir=tmp / "backups")
    >>> class Spaces:
    ...     def open(self, space):
    ...         return db
    ...     def state(self, space):
    ...         return db.state
    ...     def close(self, space):
    ...         pass
    >>> stores = RecordsStores(lambda: Spaces(), SqliteStorage)
    >>> stores.reader("p1") is None  # 파일이 아직 없다(만들지 않는다)
    True
    >>> stores.writer("p1").runs.list()
    []
    >>> db.close()
    """

    def __init__(
        self,
        spaces: Callable[[], RecordsSpaces | None],
        make: Callable[[Engine], S],
        *,
        prefix: str = "project:",
        on_open: Callable[[str], bool] | None = None,
    ) -> None:
        self._spaces = spaces
        self._make = make
        self.prefix = prefix
        self._on_open = on_open
        self._made: OrderedDict[int, tuple[Engine, S]] = OrderedDict()
        self._opened: set[str] = set()
        self._opening: set[str] = set()
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        """기록 공간 포트가 있나(없으면 소비 모듈은 호스트 DB를 쓴다)."""
        return self._spaces() is not None

    def space_name(self, project_id: str) -> str:
        """공간 이름(`접두 + 프로젝트 id`)."""
        return self.prefix + project_id

    def handle(self, project_id: str) -> RecordsHandle:
        """그 프로젝트의 기록 DB 핸들(처음 열면 `on_open`).

        Raises:
            RecordsUnavailable: 포트가 없다(`link_disabled`).
            UnknownSpace: 모르는 프로젝트(404 `project.not_found`).
        """
        port = self._spaces()
        if port is None:
            raise RecordsUnavailable(
                KnownRecordsUnavailableReasons.LINK_DISABLED, project_id=project_id
            )
        name = self.space_name(project_id)
        try:
            found = port.open(name)
        except LookupError:
            raise UnknownSpace(project_id) from None
        self._first_open(project_id)
        return found

    def host_id(self, project_id: str) -> str:
        """그 공간 핸들의 앱 id(`RecordsHandle.host_id`)."""
        return self.handle(project_id).host_id

    def reader(self, project_id: str) -> S | None:
        """읽기용 저장소 묶음. 기록 DB 파일이 없으면 None(빈 목록).

        Raises:
            RecordsUnavailable: 읽을 수 없다(폴더 없음·깨짐 등, `project_id`를 채운다).
            UnknownSpace: 모르는 프로젝트.
        """
        try:
            engine = self.handle(project_id).read_engine()
        except RecordsUnavailable as exc:
            raise _with_project(exc, project_id) from None
        return None if engine is None else self._of(engine)

    def writer(self, project_id: str) -> S:
        """쓰기용 저장소 묶음(부를 때마다 리비전을 다시 확인한다, 없으면 파일을 만든다).

        Raises:
            RecordsUnavailable: 쓸 수 없다(readonly·newer·busy·corrupt·folder_missing 등).
            UnknownSpace: 모르는 프로젝트.
        """
        try:
            engine = self.handle(project_id).writable_engine()
        except RecordsUnavailable as exc:
            raise _with_project(exc, project_id) from None
        return self._of(engine)

    def ensure_writable(self, project_id: str) -> None:
        """쓸 수 있는지 확인한다(없으면 만들고 계보를 올린다). 못 쓰면 `RecordsUnavailable`."""
        self.writer(project_id)

    def _of(self, engine: Engine) -> S:
        key = id(engine)
        with self._lock:
            entry = self._made.get(key)
            if entry is not None and entry[0] is engine:
                self._made.move_to_end(key)
                return entry[1]
            made = self._make(engine)
            self._made[key] = (engine, made)
            while len(self._made) > _MADE_CAP:  # 닫힌 엔진의 묶음을 오래 들지 않는다
                self._made.popitem(last=False)
            return made

    def _first_open(self, project_id: str) -> None:
        if self._on_open is None:
            return
        with self._lock:
            if project_id in self._opened or project_id in self._opening:
                return
            self._opening.add(project_id)
        done = False
        try:
            done = bool(self._on_open(project_id))
        except Exception:
            _log.exception("records space open hook failed: %s", project_id)
        finally:
            with self._lock:
                self._opening.discard(project_id)
                if done:
                    self._opened.add(project_id)


def _with_project(exc: RecordsUnavailable, project_id: str) -> RecordsUnavailable:
    if exc.project_id is not None:
        return exc
    return RecordsUnavailable(
        exc.reason, str(exc), backup_path=exc.backup_path, project_id=project_id
    )


__all__ = ["RecordsStores"]
