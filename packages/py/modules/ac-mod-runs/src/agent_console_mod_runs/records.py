"""Run 기록을 어디에 쓰고 읽나: 호스트 DB 또는 그 프로젝트의 기록 DB(design §PI.4.6.3·.5·.6).

선택 포트 ``records.spaces``가 있으면(앱 조립) ``project_id``가 있는 Run·NodeRun·이벤트·상호작용은
그 프로젝트 폴더의 기록 DB(``records.sqlite3``)에만 쓴다. 없으면(기능 단독) 지금처럼 호스트 DB다.
이 모듈은 프로젝트를 모른다 - ``project_id``는 불투명 문자열이고 공간 이름은 접두 + id다.

- ``SpaceRecorder``: 엔진(``GraphRuntime``)에 넘기는 ``RunRecorder``. Run을 처음 저장할 때 그 Run의
  ``project_id``로 자리를 정해 기억하고(자식 Run은 부모 값을 물려받으므로 같은 자리), 뒤따르는
  NodeRun·이벤트·상호작용을 ``run_id``로 같은 자리에 보낸다. 공간에 쓰는 Run에는 ``host_id``
  (``RecordsHandle.host_id``)를 적는다.
- 쓰는 중에 기록 DB를 못 쓰게 되면(폴더가 사라짐 등) 그 Run의 남은 쓰기를 모두 앱 대기 파일
  (``RecordsHandle.spool``)에 두고 ``on_lost``로 알린다(모듈이 Run을 취소한다). 마지막 Run의
  ``error.code``는 ``project.records_unavailable``이다. 다음에 그 공간을 쓸 수 있게 열면 대기 파일이
  기록 DB에 들어간다(이벤트 ``seq`` 중복 무시).
- 읽기 쪽(``runs.reader``·``runs.events``·상호작용)도 같은 객체다: 이 프로세스가 아는 ``run_id``
  (쓴 적이 있거나 ``?project=`` 조회로 본 Run)는 그 자리에서, 모르면 호스트 DB에서 읽는다.
  ``list(project_id=...)``는 그 공간에서 읽는다. 공간에 묶인 읽기는 ``for_project(id)``.
- 재시작 복구(``recover_space``): 공간을 이 프로세스에서 처음 열 때 **자기 host_id**의 끝나지 않은
  Run 중 지금 돌고 있지 않은 것만 ``interrupted``로 바꾼다(다른 앱의 Run은 건드리지 않는다).
"""

from __future__ import annotations

import builtins
import contextlib
import logging
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Collection, Iterable, Sequence
from typing import Any

from agent_console_contracts import (
    ErrorCodes,
    ErrorInfo,
    Interaction,
    InteractionStatus,
    NodeRun,
    Run,
    RunEvent,
    RunEventBase,
    RunStatus,
)
from agent_console_runtime import recover_unfinished_runs
from agent_console_store import RecordsStores, RecordsUnavailable, SqliteStorage

UNFINISHED: tuple[RunStatus, ...] = ("queued", "running", "paused", "waiting")
"""끝나지 않은 Run 상태(재시작 복구·다른 앱 표시 대상)."""

SPOOL_RUN = "run"
SPOOL_NODE_RUN = "node_run"
SPOOL_EVENT = "event"
SPOOL_INTERACTION = "interaction"
"""대기 파일 줄 종류(``link-projects-records``의 기본 적용 함수 키와 같다)."""

LOST_MESSAGE = "프로젝트 기록을 쓸 수 없어 실행을 멈췄습니다(남은 기록은 앱에 보관했다가 넣습니다)"
"""기록 DB를 잃어 멈춘 Run의 ``error.message``."""

_log = logging.getLogger("agent_console_mod_runs")


def space_records(
    spaces: Callable[[], Any], *, prefix: str, on_open: Callable[[str], bool] | None = None
) -> RecordsStores[SqliteStorage]:
    """``records.spaces`` 포트 위의 실행 기록 저장소 고르기(엔진 → ``SqliteStorage``)."""
    return RecordsStores(spaces, SqliteStorage, prefix=prefix, on_open=on_open)


class _Places:
    """``run_id``·상호작용 id → 프로젝트 id(이 프로세스가 아는 것만, 오래된 것부터 잊는다)."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._runs: OrderedDict[str, str] = OrderedDict()
        self._interactions: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def _put(self, table: OrderedDict[str, str], key: str, project_id: str) -> None:
        with self._lock:
            table[key] = project_id
            table.move_to_end(key)
            while len(table) > self._limit:
                table.popitem(last=False)

    def put_run(self, run_id: str, project_id: str) -> None:
        self._put(self._runs, run_id, project_id)

    def put_interaction(self, interaction_id: str, project_id: str) -> None:
        self._put(self._interactions, interaction_id, project_id)

    def run(self, run_id: str) -> str | None:
        with self._lock:
            return self._runs.get(run_id)

    def interaction(self, interaction_id: str) -> str | None:
        with self._lock:
            return self._interactions.get(interaction_id)


class SpaceRecorder:
    """엔진 저장 묶음 + 실행 기록 읽기(호스트 DB 또는 프로젝트 기록 DB로 나눈다).

    Args:
        host: 호스트 저장 묶음(``SqliteStorage``·``InMemoryStorage``).
        records: 기록 공간 저장소 고르기(``space_records``). None이면 늘 호스트(기능 단독).
        on_lost: 그 Run의 기록 DB를 잃었을 때 한 번(``run_id``, 이유). 워커 스레드에서 불린다.
        remember: 기억할 ``run_id`` 최대 개수.
    """

    def __init__(
        self,
        host: Any,
        records: RecordsStores[SqliteStorage] | None = None,
        *,
        on_lost: Callable[[str, str], None] = lambda _run, _reason: None,
        remember: int = 20_000,
    ) -> None:
        self.host = host
        self.records = records
        self._on_lost = on_lost
        self._places = _Places(remember)
        self._lost: dict[str, str] = {}
        self._lost_lock = threading.Lock()
        self._pending: dict[str, Interaction] = {}
        self.runs = _Runs(self)
        self.events = _Events(self)
        self.interactions = _Interactions(self)

    # ---- 자리 ---------------------------------------------------------------

    @property
    def spaced(self) -> bool:
        """기록 공간 포트가 있나(있으면 ``project_id``가 있는 Run은 그 공간에)."""
        return self.records is not None and self.records.available

    def project_of_run(self, run_id: str) -> str | None:
        """이 프로세스가 아는 그 Run의 프로젝트(공간에 쓴 Run). 모르면 None(호스트)."""
        return self._places.run(run_id)

    def remember(self, runs: Iterable[Run], project_id: str) -> None:
        """공간 조회로 본 Run의 자리를 기억한다(뒤따르는 ``run_id`` 조회가 그 공간을 본다)."""
        for run in runs:
            self._places.put_run(run.id, project_id)

    def reader(self, project_id: str | None) -> Any | None:
        """읽을 저장 묶음: 프로젝트 없음·포트 없음 = 호스트, 공간 파일 없음 = None(빈 결과).

        Raises:
            RecordsUnavailable: 그 공간을 읽을 수 없다. UnknownSpace: 모르는 프로젝트.
        """
        if project_id is None or not self.spaced or self.records is None:
            return self.host
        return self.records.reader(project_id)

    def for_project(self, project_id: str | None) -> SpaceReader:
        """그 프로젝트에 묶인 읽기(``get``·``list``·``list_node_runs``·이벤트·상호작용)."""
        return SpaceReader(self, project_id)

    def _read_at(self, run_id: str) -> Any | None:
        project_id = self._places.run(run_id)
        if project_id is None:
            return self.host
        try:
            return self.reader(project_id)
        except (RecordsUnavailable, LookupError):
            return None

    # ---- 쓰기 ---------------------------------------------------------------

    def _write(
        self, run_id: str, kind: str, spooled: Sequence[Any], write: Callable[[Any], Any]
    ) -> Any:
        """그 Run의 자리에 쓴다. 기록 DB를 잃으면 ``spooled``를 대기 파일에 두고 ``on_lost``를
        부른다(그 뒤 그 Run의 쓰기는 모두 대기 파일로 - 순서를 지킨다). 대기 파일로 갔으면 None."""
        project_id = self._places.run(run_id)
        if project_id is None or self.records is None:
            return write(self.host)
        if run_id not in self._lost:
            try:
                return write(self.records.writer(project_id))
            except RecordsUnavailable as exc:
                self._lose(run_id, exc.reason)
            except LookupError:
                self._lose(run_id, "not_found")
        for item in spooled:
            self._spool(project_id, run_id, kind, item)
        return None

    def _lose(self, run_id: str, reason: str) -> None:
        with self._lost_lock:
            first = run_id not in self._lost
            self._lost.setdefault(run_id, reason)
        if first:
            _log.warning("실행 기록 DB를 잃어 Run을 멈춥니다: %s (%s)", run_id, reason)
            try:
                self._on_lost(run_id, reason)
            except Exception:
                _log.exception("기록 DB 잃음 알림 실패: %s", run_id)

    def lost_reason(self, run_id: str) -> str | None:
        """그 Run이 기록 DB를 잃었으면 이유(아니면 None)."""
        return self._lost.get(run_id)

    def _spool(self, project_id: str, run_id: str, kind: str, data: Any) -> None:
        if self.records is None or data is None:
            return
        payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
        try:
            self.records.handle(project_id).spool(run_id, kind, payload)
        except Exception:  # 대기 파일까지 못 쓰면 기록을 잃는다 - 적어 둔다
            _log.exception("실행 기록 대기 파일 쓰기 실패: %s/%s", run_id, kind)

    def _stamp(self, run: Run, project_id: str) -> Run:
        """공간에 쓰는 Run: ``host_id``를 적고, 잃은 Run의 끝 상태는 오류 코드를 바꾼다."""
        update: dict[str, Any] = {}
        if run.host_id is None and self.records is not None:
            with contextlib.suppress(Exception):  # 핸들을 못 열면 쓰기에서 잃음으로 처리된다
                update["host_id"] = self.records.host_id(project_id)
        reason = self._lost.get(run.id)
        if reason is not None and run.status not in UNFINISHED:
            update["error"] = ErrorInfo(
                code=ErrorCodes.PROJECT_RECORDS_UNAVAILABLE,
                message=LOST_MESSAGE,
                details={"project_id": project_id, "reason": reason},
            )
        return run.model_copy(update=update) if update else run

    def save_run(self, run: Run) -> None:
        project_id = run.project_id if self.spaced else None
        if project_id is None:
            self.host.runs.save(run)
            return
        self._places.put_run(run.id, project_id)
        stamped = self._stamp(run, project_id)
        self._write(run.id, SPOOL_RUN, [stamped], lambda s: s.runs.save(stamped))


class _Runs:
    """``RunWriter`` + Run 읽기(``runs.reader``)."""

    def __init__(self, owner: SpaceRecorder) -> None:
        self._o = owner

    def save(self, run: Run) -> None:
        self._o.save_run(run)

    def save_node_run(self, node_run: NodeRun) -> None:
        self._o._write(
            node_run.run_id, SPOOL_NODE_RUN, [node_run], lambda s: s.runs.save_node_run(node_run)
        )

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        store = self._o._read_at(run_id)
        return [] if store is None else list(store.runs.list_node_runs(run_id))

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        """호스트 DB만(공간은 ``recover_space``가 열 때 자기 것만 한다)."""
        found: builtins.list[str] = self._o.host.runs.interrupt_unfinished(
            ended_at=ended_at, error=error
        )
        return found

    def get(self, run_id: str) -> Run | None:
        store = self._o._read_at(run_id)
        found: Run | None = None if store is None else store.runs.get(run_id)
        return found

    def list(self, **filters: Any) -> builtins.list[Run]:
        """조건에 맞는 Run. ``project_id``가 있고 포트가 있으면 그 공간에서 읽는다. 기준 Run
        (``root_run_id``·``parent_run_id``·``resumed_from``)의 자리를 알면 그 자리에서 읽는다."""
        project_id = filters.get("project_id")
        if project_id is None:
            for key in ("root_run_id", "parent_run_id", "resumed_from"):
                anchor = filters.get(key)
                if isinstance(anchor, str):
                    project_id = self._o.project_of_run(anchor)
                    if project_id is not None:
                        break
        if project_id is not None and self._o.spaced:
            return self._o.for_project(project_id).list(
                **{k: v for k, v in filters.items() if k != "project_id"}
            )
        found: builtins.list[Run] = self._o.host.runs.list(**filters)
        return found

    def page(self, **filters: Any) -> tuple[builtins.list[Run], str | None]:
        """커서 페이지(``RunRepository.page``, 6R.12). ``project_id``가 있고 포트가 있으면 그 공간
        기록 DB의 페이지, 아니면 호스트 DB."""
        project_id = filters.get("project_id")
        if project_id is not None and self._o.spaced:
            return self._o.for_project(project_id).page(
                **{k: v for k, v in filters.items() if k != "project_id"}
            )
        found: tuple[builtins.list[Run], str | None] = self._o.host.runs.page(**filters)
        return found

    def descendants(self, root_run_id: str) -> builtins.list[Run]:
        """그 루트 아래 모든 자손(생성 순, 색인 질의 한 번, 6R.12). 루트의 자리에서 읽는다."""
        store = self._o._read_at(root_run_id)
        return [] if store is None else list(store.runs.descendants(root_run_id))

    def for_project(self, project_id: str | None) -> SpaceReader:
        """그 프로젝트에 묶인 Run 읽기(``get``·``list``·``page``·``descendants``·
        ``list_node_runs``)."""
        return self._o.for_project(project_id)

    def __getattr__(self, name: str) -> Any:  # 호스트 저장소의 다른 메서드(넣기·개수 등)
        return getattr(self._o.host.runs, name)


class _Events:
    """``EventWriter`` + 이벤트 읽기(``runs.events``)."""

    def __init__(self, owner: SpaceRecorder) -> None:
        self._o = owner

    def append(self, event: RunEventBase) -> bool:
        result = self._o._write(
            event.run_id, SPOOL_EVENT, [event], lambda s: s.events.append(event)
        )
        return bool(result) if result is not None else True

    def append_many(self, events: Sequence[RunEventBase]) -> int:
        groups: dict[str, list[RunEventBase]] = {}
        for event in events:
            groups.setdefault(event.run_id, []).append(event)
        total = 0
        for run_id, batch in groups.items():
            result = self._o._write(run_id, SPOOL_EVENT, batch, _append_many(batch))
            total += int(result) if result is not None else len(batch)
        return total

    def last_seq(self, run_id: str) -> int:
        store = self._o._read_at(run_id)
        return 0 if store is None else int(store.events.last_seq(run_id))

    def list(self, run_id: str, **filters: Any) -> builtins.list[RunEvent]:
        store = self._o._read_at(run_id)
        return [] if store is None else list(store.events.list(run_id, **filters))

    def for_project(self, project_id: str | None) -> SpaceEvents:
        """그 프로젝트에 묶인 이벤트 읽기(``list``·``last_seq``)."""
        return SpaceEvents(self._o.for_project(project_id))

    def __getattr__(self, name: str) -> Any:  # list_by_actor·latest_by_type 등은 호스트
        return getattr(self._o.host.events, name)


def _append_many(batch: Sequence[RunEventBase]) -> Callable[[Any], Any]:
    def write(store: Any) -> Any:
        return store.events.append_many(batch)

    return write


class _Interactions:
    """``InteractionWriter`` + 상호작용 읽기."""

    def __init__(self, owner: SpaceRecorder) -> None:
        self._o = owner

    def save(self, interaction: Interaction) -> bool:
        project_id = self._o.project_of_run(interaction.run_id)
        if project_id is not None:
            self._o._places.put_interaction(interaction.id, project_id)
            if interaction.status == "pending":
                self._o._pending[interaction.id] = interaction
            else:
                self._o._pending.pop(interaction.id, None)
        result = self._o._write(
            interaction.run_id,
            SPOOL_INTERACTION,
            [interaction],
            lambda s: s.interactions.save(interaction),
        )
        return bool(result) if result is not None else True

    def _store_of(self, interaction_id: str) -> Any | None:
        project_id = self._o._places.interaction(interaction_id)
        if project_id is None:
            return self._o.host
        try:
            return self._o.reader(project_id)
        except (RecordsUnavailable, LookupError):
            return None

    def get(self, interaction_id: str) -> Interaction | None:
        store = self._store_of(interaction_id)
        found: Interaction | None = (
            None if store is None else store.interactions.get(interaction_id)
        )
        return found

    def close(
        self,
        interaction_id: str,
        *,
        status: InteractionStatus,
        closed_at: float,
        response: dict[str, Any] | None = None,
        answered_by: str | None = None,
        close_reason: str | None = None,
    ) -> Interaction:
        project_id = self._o._places.interaction(interaction_id)
        if project_id is None or self._o.records is None:
            closed: Interaction = self._o.host.interactions.close(
                interaction_id,
                status=status,
                closed_at=closed_at,
                response=response,
                answered_by=answered_by,
                close_reason=close_reason,
            )
            return closed
        current = self._o._pending.get(interaction_id)
        run_id = current.run_id if current is not None else ""
        if current is None or self._o.lost_reason(run_id) is None:
            try:
                closed = self._o.records.writer(project_id).interactions.close(
                    interaction_id,
                    status=status,
                    closed_at=closed_at,
                    response=response,
                    answered_by=answered_by,
                    close_reason=close_reason,
                )
                self._o._pending.pop(interaction_id, None)
                return closed
            except RecordsUnavailable as exc:
                if current is None:
                    raise
                self._o._lose(run_id, exc.reason)
        if current is None:
            raise LookupError(f"interaction/{interaction_id}")
        closed = current.model_copy(
            update={
                "status": status,
                "closed_at": closed_at,
                "response": response if response is not None else current.response,
                "answered_by": answered_by,
                "close_reason": close_reason,
            },
            deep=True,
        )
        self._o._pending.pop(interaction_id, None)
        self._o._spool(project_id, run_id, SPOOL_INTERACTION, closed)
        return closed

    def close_pending(
        self,
        *,
        status: InteractionStatus,
        closed_at: float,
        run_id: str | None = None,
        answered_by: str | None = "system",
        close_reason: str | None = None,
    ) -> builtins.list[Interaction]:
        if run_id is None or self._o.project_of_run(run_id) is None:
            found: builtins.list[Interaction] = self._o.host.interactions.close_pending(
                status=status,
                closed_at=closed_at,
                run_id=run_id,
                answered_by=answered_by,
                close_reason=close_reason,
            )
            return found
        result = self._o._write(
            run_id,
            SPOOL_INTERACTION,
            [],
            lambda s: s.interactions.close_pending(
                status=status,
                closed_at=closed_at,
                run_id=run_id,
                answered_by=answered_by,
                close_reason=close_reason,
            ),
        )
        return list(result) if result is not None else []

    def list(self, **filters: Any) -> builtins.list[Interaction]:
        run_id = filters.get("run_id") or filters.get("root_run_id")
        if isinstance(run_id, str) and self._o.project_of_run(run_id) is not None:
            store = self._o._read_at(run_id)
            return [] if store is None else list(store.interactions.list(**filters))
        found: builtins.list[Interaction] = self._o.host.interactions.list(**filters)
        return found

    def for_project(self, project_id: str | None) -> SpaceInteractions:
        """그 프로젝트에 묶인 상호작용 읽기(``get``·``list``)."""
        return SpaceInteractions(self._o.for_project(project_id))

    def __getattr__(self, name: str) -> Any:  # pending_counts 등은 호스트
        return getattr(self._o.host.interactions, name)


class SpaceReader:
    """한 프로젝트(또는 호스트)에 묶인 실행 기록 읽기. 공간 파일이 없으면 모두 빈 결과다.

    공간에서 읽은 Run의 ``project_id``는 그 앱의 등록 id(요청 값)로 채운다(K33-25). 읽은 Run의
    자리는 기억한다(뒤따르는 ``run_id`` 조회가 같은 공간을 본다).
    """

    def __init__(self, owner: SpaceRecorder, project_id: str | None) -> None:
        self._o = owner
        self.project_id = project_id
        self.spaced = project_id is not None and owner.spaced

    def _store(self) -> Any | None:
        return self._o.reader(self.project_id)

    def view(self, run: Run) -> Run:
        if self.spaced and run.project_id != self.project_id:
            return run.model_copy(update={"project_id": self.project_id})
        return run

    def _seen(self, runs: builtins.list[Run]) -> builtins.list[Run]:
        if self.spaced and self.project_id is not None:
            self._o.remember(runs, self.project_id)
        return [self.view(r) for r in runs]

    def get(self, run_id: str) -> Run | None:
        store = self._store()
        found = None if store is None else store.runs.get(run_id)
        return None if found is None else self._seen([found])[0]

    def list(self, **filters: Any) -> builtins.list[Run]:
        store = self._store()
        if store is None:
            return []
        if not self.spaced and self.project_id is not None:
            filters = {**filters, "project_id": self.project_id}
        return self._seen(list(store.runs.list(**filters)))

    def page(self, **filters: Any) -> tuple[builtins.list[Run], str | None]:
        """커서 페이지(``RunRepository.page`` 인자, 6R.12). 공간 파일이 없으면 빈 페이지."""
        store = self._store()
        if store is None:
            return [], None
        if not self.spaced and self.project_id is not None:
            filters = {**filters, "project_id": self.project_id}
        items, next_cursor = store.runs.page(**filters)
        return self._seen(list(items)), next_cursor

    def descendants(self, root_run_id: str) -> builtins.list[Run]:
        """그 루트 아래 모든 자손(``RunRepository.descendants``, 색인 질의 한 번)."""
        store = self._store()
        return [] if store is None else self._seen(list(store.runs.descendants(root_run_id)))

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        store = self._store()
        return [] if store is None else list(store.runs.list_node_runs(run_id))

    def last_seq(self, run_id: str) -> int:
        store = self._store()
        return 0 if store is None else int(store.events.last_seq(run_id))

    def events(self, run_id: str, **filters: Any) -> builtins.list[RunEvent]:
        store = self._store()
        return [] if store is None else list(store.events.list(run_id, **filters))

    def interactions(self, **filters: Any) -> builtins.list[Interaction]:
        store = self._store()
        return [] if store is None else list(store.interactions.list(**filters))

    @property
    def storage(self) -> Any | None:
        """그 자리의 저장 묶음(``runs``·``events``·``interactions``, 파일이 없으면 None)."""
        return self._store()


class SpaceEvents:
    """한 프로젝트에 묶인 이벤트 읽기(``EventReader`` 모양: ``list``·``last_seq``)."""

    def __init__(self, reader: SpaceReader) -> None:
        self._reader = reader

    def list(self, run_id: str, **filters: Any) -> builtins.list[RunEvent]:
        return self._reader.events(run_id, **filters)

    def last_seq(self, run_id: str) -> int:
        return self._reader.last_seq(run_id)


class SpaceInteractions:
    """한 프로젝트에 묶인 상호작용 읽기(``get``·``list``)."""

    def __init__(self, reader: SpaceReader) -> None:
        self._reader = reader

    def list(self, **filters: Any) -> builtins.list[Interaction]:
        return self._reader.interactions(**filters)

    def get(self, interaction_id: str) -> Interaction | None:
        store = self._reader.storage
        found: Interaction | None = (
            None if store is None else store.interactions.get(interaction_id)
        )
        return found


class _OwnRecorder:
    """재시작 복구용 저장 묶음: ``interrupt_unfinished``가 고른 Run만 바꾼다(자기 앱 것)."""

    def __init__(self, storage: Any, targets: Collection[str]) -> None:
        self._storage = storage
        self._targets = sorted(targets)
        self.events = storage.events
        self.runs = self
        self.interactions = self

    def interrupt_unfinished(
        self, *, ended_at: float, error: ErrorInfo | None = None
    ) -> builtins.list[str]:
        done: builtins.list[str] = []
        for run_id in self._targets:
            run = self._storage.runs.get(run_id)
            if run is None or run.status not in UNFINISHED:
                continue
            update: dict[str, Any] = {"status": "interrupted", "ended_at": ended_at}
            if error is not None:
                update["error"] = error
            self._storage.runs.save(run.model_copy(update=update))
            done.append(run_id)
        return done

    def close_pending(self, **kwargs: Any) -> builtins.list[Interaction]:
        out: builtins.list[Interaction] = []
        for run_id in self._targets:
            out.extend(self._storage.interactions.close_pending(**{**kwargs, "run_id": run_id}))
        return out

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]:
        return list(self._storage.runs.list_node_runs(run_id))

    def save_node_run(self, node_run: NodeRun) -> None:
        self._storage.runs.save_node_run(node_run)


def unfinished_of_host(storage: Any, host_id: str) -> builtins.list[Run]:
    """그 저장 묶음의 끝나지 않은 Run 중 ``host_id``가 같은 것(None = 알리지 않은 Run은 빠진다)."""
    return [r for r in storage.runs.list(status=list(UNFINISHED)) if r.host_id == host_id]


def recover_space(
    records: RecordsStores[SqliteStorage],
    project_id: str,
    *,
    active: Callable[[], Collection[str]],
    clock: Callable[[], float] = time.time,
    ids: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> bool:
    """공간을 처음 열 때의 재시작 복구(§PI.4.6.5): 자기 앱의 끝나지 않은 Run 중 지금 돌지 않는
    것만 ``interrupted``. 다른 앱(``host_id``가 다름)·``host_id`` 없는 Run은 건드리지 않는다.

    파일이 없으면 할 일이 없다(파일을 만들지 않는다). 쓸 수 없으면 거짓(다음 열기 때 다시).

    Returns:
        끝났으면 참.
    """
    try:
        store = records.reader(project_id)
    except (RecordsUnavailable, LookupError):
        return False
    if store is None:
        return True
    host_id = records.host_id(project_id)
    running = set(active())
    targets = [r.id for r in unfinished_of_host(store, host_id) if r.id not in running]
    if not targets:
        return True
    try:
        writer = records.writer(project_id)
    except (RecordsUnavailable, LookupError):
        return False
    own: Any = _OwnRecorder(writer, targets)
    done = recover_unfinished_runs(own, clock=clock, ids=ids)
    if done:
        _log.info("프로젝트 기록의 끝나지 않은 Run %d개를 끊김으로 정리했습니다", len(done))
    return True


def interrupt_run(
    storage: Any,
    run_id: str,
    *,
    message: str,
    clock: Callable[[], float] = time.time,
    ids: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> Run | None:
    """끝나지 않은 Run 하나를 ``interrupted``로 정리한다(대기 상호작용·노드·이벤트 포함).

    [끊긴 것으로 표시](``POST /runs/{id}/mark-interrupted``)가 쓴다. 이미 끝났으면 그대로.
    """
    own: Any = _OwnRecorder(storage, [run_id])
    recover_unfinished_runs(own, clock=clock, ids=ids, message=message)
    found: Run | None = storage.runs.get(run_id)
    return found


__all__ = [
    "LOST_MESSAGE",
    "SPOOL_EVENT",
    "SPOOL_INTERACTION",
    "SPOOL_NODE_RUN",
    "SPOOL_RUN",
    "UNFINISHED",
    "SpaceEvents",
    "SpaceInteractions",
    "SpaceReader",
    "SpaceRecorder",
    "interrupt_run",
    "recover_space",
    "space_records",
    "unfinished_of_host",
]
