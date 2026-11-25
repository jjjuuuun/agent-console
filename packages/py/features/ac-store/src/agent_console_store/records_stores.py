"""프로젝트 기록 DB 위의 저장소 고르기(`RecordsStores`, design §PI.4.6.3, 5.7R.33y2).

실행·대화 모듈은 프로젝트를 모른다. 요청의 프로젝트 id(불투명 문자열)를 받아
`records.spaces` 포트(`RecordsSpaces`)로 그 공간의 기록 DB 핸들을 열고, 핸들의 엔진 위에 자기
저장소 묶음(예: `SqliteStorage`)을 만든다.

- 읽기는 `reader(project_id)` - 파일이 없으면 None(빈 목록, 파일을 만들지 않는다).
- 쓰기는 `writer(project_id)` - **부를 때마다** `writable_engine()`(쓰기 전 리비전 재확인). 못 쓰면
  `RecordsUnavailable`(409, `project_id`를 채운다).
- 같은 엔진이면 저장소 묶음을 다시 쓴다(저장소가 만들 때 열 유무를 한 번 보므로 매번 만들지 않는다).
- 그 공간을 이 프로세스에서 처음 열면 `on_open(project_id)`를 한 번 부른다(재시작 복구 자리,
  §PI.4.6.5). 거짓을 돌려주거나 예외가 나면 다음 열기 때 다시 부른다. 훅이 도는 동안 같은 공간을
  여는 **다른 스레드는 훅이 끝날 때까지 기다린다**(예: 시작 직후 로그 수집이 먼저 열었을 때 첫
  요청이 복구 전 상태를 읽지 않게). 훅 안에서 같은 스레드가 다시 열면 기다리지 않는다.

- 여러 프로젝트를 차례로 읽는 순회(예: 사용량 집계)는 `with stores.batch():`로 감싼다. 포트가
  `BatchRecordsSpaces`면 순회 동안 연 공간을 열린 핸들 상한으로 밀어내지 않는다(상한보다
  프로젝트가 많을 때 연결을 쫓아내고 다시 여는 것을 막는다).

포트가 없으면 `available`이 거짓이다. 소비 모듈은 그때 호스트 DB(기능 단독)를 쓴다.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from sqlalchemy import Engine

from agent_console_contracts import KnownRecordsUnavailableReasons

from .records import BatchRecordsSpaces, RecordsHandle, RecordsSpaces, RecordsUnavailable
from .spaces import UnknownSpace

_log = logging.getLogger(__name__)
_MADE_CAP = 64
"""엔진별 저장소 묶음을 들고 있는 최대 개수(공간 캐시 상한보다 넉넉히)."""
DEFAULT_OPEN_WAIT = 30.0
"""다른 스레드의 `on_open`이 끝나기를 기다리는 최대 초(넘으면 경고 후 그냥 연다)."""


class RecordsStores[S]:
    """프로젝트 id → 그 기록 DB 위의 저장소 묶음.

    Args:
        spaces: 지금 `records.spaces` 포트(부를 때마다, 없으면 None).
        make: 엔진 → 저장소 묶음(예: `SqliteStorage`).
        prefix: 공간 이름 접두(공간 이름 = 접두 + 프로젝트 id).
        on_open: 그 공간을 이 프로세스에서 처음 열 때 부르는 함수(참 = 끝남).
        open_wait: 다른 스레드의 `on_open`을 기다리는 최대 초(넘으면 경고를 남기고 기다리지 않고
            연다 - 훅이 멈춰도 읽기가 영원히 막히지 않게).

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
        open_wait: float = DEFAULT_OPEN_WAIT,
    ) -> None:
        self._spaces = spaces
        self._make = make
        self.prefix = prefix
        self._on_open = on_open
        self._open_wait = open_wait
        self._made: OrderedDict[int, tuple[Engine, S]] = OrderedDict()
        self._opened: set[str] = set()
        self._opening: dict[str, int] = {}
        """훅이 도는 공간 → 그 훅을 부른 스레드 id."""
        self._lock = threading.RLock()
        self._opened_cond = threading.Condition(self._lock)

    @property
    def available(self) -> bool:
        """기록 공간 포트가 있나(없으면 소비 모듈은 호스트 DB를 쓴다)."""
        return self._spaces() is not None

    def batch(self) -> contextlib.AbstractContextManager[object]:
        """여러 프로젝트를 차례로 읽는 순회를 한 묶음으로(`with stores.batch(): ...`).

        포트가 `BatchRecordsSpaces`면 그 블록이다(블록 안에서 연 공간을 상한으로 밀어내지 않고
        끝날 때 맞춘다). 포트가 없거나 그 능력이 없으면 아무 일도 하지 않는 블록이다.
        """
        port: object = self._spaces()  # 선택 능력이라 포트 모양과 따로 본다
        if isinstance(port, BatchRecordsSpaces):
            return port.batch()
        return contextlib.nullcontext()

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
        me = threading.get_ident()
        with self._opened_cond:
            deadline: float | None = None
            while True:
                if project_id in self._opened:
                    return
                owner = self._opening.get(project_id)
                if owner is None:
                    break
                if owner == me:  # 훅 안에서 같은 공간을 다시 연다
                    return
                if deadline is None:
                    deadline = time.monotonic() + self._open_wait
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _log.warning("records space open hook still running: %s", project_id)
                    return
                self._opened_cond.wait(remaining)
            self._opening[project_id] = me
        done = False
        try:
            done = bool(self._on_open(project_id))
        except Exception:
            _log.exception("records space open hook failed: %s", project_id)
        finally:
            with self._opened_cond:
                self._opening.pop(project_id, None)
                if done:
                    self._opened.add(project_id)
                self._opened_cond.notify_all()


def _with_project(exc: RecordsUnavailable, project_id: str) -> RecordsUnavailable:
    if exc.project_id is not None:
        return exc
    return RecordsUnavailable(
        exc.reason, str(exc), backup_path=exc.backup_path, project_id=project_id
    )


__all__ = ["RecordsStores"]
