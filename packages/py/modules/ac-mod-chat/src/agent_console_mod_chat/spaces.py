"""프로젝트 대화를 그 프로젝트 기록 DB에(design §PI.4.6.3·.5, 5.7R.33y2).

선택 포트 ``records.spaces``가 있으면 ``project_id``가 있는 대화·대기열은 그 프로젝트 폴더의 기록
DB(``records.sqlite3``)의 ``conversations``·``chat_queue``에만 둔다. 이 모듈은 프로젝트를 모른다 -
``project_id``는 불투명 문자열이고 공간 이름은 접두 + id다.

- ``SpaceConversations``·``SpaceQueue``: 공간 하나의 대화·대기열 저장소. 부를 때마다 기록 DB 핸들의
  엔진을 받는다(읽기는 파일이 없으면 빈 결과, 쓰기는 ``writable_engine()`` - 못 쓰면 409
  ``project.records_unavailable``). 대기열 행에는 이 앱의 ``host_id``를 적고, 다른 앱 항목은
  멈춘 것(``other_host``)으로 보이며 꺼내지 않는다.
- ``SpacedChatService``: 호스트 대화 서비스(``chat.conversations`` 포트 그대로) +
  ``for_project(id)``(그 공간의 대화 서비스, 처음이면 만들고 연결·재시작 대기열 정책을 적용).
  요청 경로는 ``for_project_ready(id)``를 쓴다 - 재시작 정책 적용이 끝난 뒤에 서비스를 돌려줘서,
  재시작 직후 첫 읽기도 정책이 적용된 대기열(예: ``ask`` = ``held``)을 본다.
  연결(``connect``)·꺼내기 멈춤·정리는 공간 서비스에도 같이 간다.
- 공간 대화의 ``conversation_busy``는 그 기록 DB의 끝나지 않은 턴 Run도 본다(다른 앱이 돌리는 턴,
  ``busy_elsewhere``).
- 대화 위치 찾기(``locate``, 요청 11/07 후속): 대화 id → 그 대화가 있는 공간(등록 id, None = 호스트
  DB). 이 프로세스에서 연 공간과 ``project_ids``(보통 ``projects.lookup``의 등록 id)의 기록 DB를
  상한(``locate_limit``)까지 읽기만 한다(파일을 만들지 않고, 공간 서비스도 열지 않는다). 찾은 자리는
  기억해 두고(상한 있음) 다음에는 그 자리만 다시 확인한다. WS ``conversation:<id>`` 구독은
  ``service_of``가 이것으로 아직 열지 않은 공간의 대화도 찾는다.
"""

from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from agent_console_chat import ChatError, ChatService, ConversationNotFoundError
from agent_console_contracts import Conversation, ErrorCodes
from agent_console_store import (
    DEFAULT_LOCATE_LIMIT,
    RecordsStores,
    RecordsUnavailable,
    SpaceLocator,
    StoreError,
)

from .storage import QueueCounts, QueuedItem, SqliteChatStorage

UNFINISHED = ("queued", "running", "paused", "waiting")
"""끝나지 않은 Run 상태(다른 곳에서 도는 턴 판정)."""

_log = logging.getLogger("agent_console_mod_chat")


class ConversationAmbiguousError(ChatError):
    """같은 대화 id가 여러 기록 공간에 있다(409 ``conversation.ambiguous``).

    ``details.project_ids`` = 찾은 곳(None = 호스트 DB, 앱 기록).
    """

    code = ErrorCodes.CONVERSATION_AMBIGUOUS


def chat_records(spaces: Callable[[], Any], *, prefix: str) -> RecordsStores[SqliteChatStorage]:
    """``records.spaces`` 포트 위의 대화 저장소 고르기(엔진 → ``SqliteChatStorage``).

    대기열의 ``host_id``는 ``SpaceQueue``가 핸들에서 받아 넘긴다.
    """
    return RecordsStores(spaces, SqliteChatStorage, prefix=prefix)


class SpaceConversations:
    """공간 하나의 대화 저장소(``ConversationRepository``). 읽은 대화의 ``project_id`` = 등록 id."""

    def __init__(self, records: RecordsStores[SqliteChatStorage], project_id: str) -> None:
        self._records = records
        self.project_id = project_id

    def _view(self, item: Conversation) -> Conversation:
        if item.project_id == self.project_id:
            return item
        return item.model_copy(update={"project_id": self.project_id})

    def get(self, conversation_id: str) -> Conversation | None:
        store = self._records.reader(self.project_id)
        found = None if store is None else store.conversations.get(conversation_id)
        return None if found is None else self._view(found)

    def save(self, conversation: Conversation) -> None:
        self._records.writer(self.project_id).conversations.save(conversation)

    def delete(self, conversation_id: str) -> bool:
        return bool(self._records.writer(self.project_id).conversations.delete(conversation_id))

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
    ) -> builtins.list[Conversation]:
        """그 공간의 대화(공간이 곧 범위라 ``project_id``로 거르지 않는다)."""
        store = self._records.reader(self.project_id)
        if store is None:
            return []
        return [
            self._view(c) for c in store.conversations.list(graph_id=graph_id, archived=archived)
        ]


class SpaceQueue:
    """공간 하나의 대기열(``QueueStore``). 이 앱의 ``host_id``로 자기 항목을 가린다."""

    def __init__(self, records: RecordsStores[SqliteChatStorage], project_id: str) -> None:
        self._records = records
        self.project_id = project_id

    def _repo(self, *, write: bool) -> Any | None:
        store = (
            self._records.writer(self.project_id)
            if write
            else self._records.reader(self.project_id)
        )
        if store is None:
            return None
        queue = store.queue
        queue.host_id = self._records.host_id(self.project_id)
        return queue

    def enqueue(
        self,
        item_id: str,
        conversation_id: str,
        text: str,
        *,
        created_at: float,
        held: bool = False,
        held_reason: str | None = None,
    ) -> QueuedItem:
        repo = self._repo(write=True)
        assert repo is not None
        found: QueuedItem = repo.enqueue(
            item_id,
            conversation_id,
            text,
            created_at=created_at,
            held=held,
            held_reason=held_reason,
        )
        return found

    def get(self, item_id: str) -> QueuedItem | None:
        repo = self._repo(write=False)
        return None if repo is None else repo.get(item_id)

    def list(
        self, conversation_id: str | None = None, *, held: bool | None = None
    ) -> builtins.list[QueuedItem]:
        repo = self._repo(write=False)
        return [] if repo is None else list(repo.list(conversation_id, held=held))

    def remove(self, item_id: str) -> bool:
        return bool(self._writer().remove(item_id))

    def hold_all(self, reason: str | None = None, *, conversation_id: str | None = None) -> int:
        return int(self._writer().hold_all(reason, conversation_id=conversation_id))

    def release(self, item_id: str) -> QueuedItem:
        found: QueuedItem = self._writer().release(item_id)
        return found

    def pop_next(self, conversation_id: str) -> QueuedItem | None:
        found: QueuedItem | None = self._writer().pop_next(conversation_id)
        return found

    def counts(self, conversation_ids: Iterable[str] | None = None) -> dict[str, QueueCounts]:
        repo = self._repo(write=False)
        return {} if repo is None else dict(repo.counts(conversation_ids))

    def clear(self, conversation_id: str) -> int:
        if self._repo(write=False) is None:  # 파일이 없으면 지울 것도 없다(만들지 않는다)
            return 0
        return int(self._writer().clear(conversation_id))

    def _writer(self) -> Any:
        repo = self._repo(write=True)
        assert repo is not None
        return repo


def _scoped(port: Any, project_id: str) -> Any:
    """읽기 포트의 선택 메서드 ``for_project``가 있으면 그 공간에 묶은 것, 없으면 그대로."""
    method = getattr(port, "for_project", None)
    return method(project_id) if callable(method) else port


class SpacedChatService(ChatService):
    """호스트 대화 서비스 + 프로젝트 공간별 대화 서비스(``for_project``).

    Args:
        records: 대화 저장소 고르기(``chat_records``). None이면 공간 없음(``for_project``는 자신).
        make: 공간 저장소 → 공간 대화 서비스(같은 팀 구성 조회·설정·알림을 쓴다).
        project_ids: 대화 위치 찾기(``locate``)가 볼 공간 id 목록(부를 때마다, 보통 등록
            프로젝트 id). None이면 이 프로세스에서 연 공간만 본다.
        locate_limit: ``locate``가 ``project_ids``에서 읽는 최대 개수(0 = 연 공간만).
        args, kwargs: ``ChatService`` 인자(호스트 저장소).
    """

    def __init__(
        self,
        *args: Any,
        records: RecordsStores[SqliteChatStorage] | None = None,
        make: Callable[[SpaceConversations, SpaceQueue, Callable[[str], str | None]], ChatService]
        | None = None,
        project_ids: Callable[[], Iterable[str]] | None = None,
        locate_limit: int = DEFAULT_LOCATE_LIMIT,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._records = records
        self._make = make
        self._locator = SpaceLocator(
            self._has,
            opened=lambda: builtins.list(self._spaces),
            project_ids=project_ids,
            limit=locate_limit,
            spaced=lambda: self.spaced,
            label="대화",
        )
        self._spaces: dict[str, ChatService] = {}
        self._links: dict[str, Any] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._restart_tasks: set[asyncio.Task[None]] = set()
        self._restart_pending: dict[
            str, asyncio.Future[None] | concurrent.futures.Future[None]
        ] = {}

    @property
    def spaced(self) -> bool:
        """기록 공간 포트가 있나(있으면 프로젝트 대화는 그 공간에)."""
        return self._records is not None and self._records.available and self._make is not None

    def connect(self, **links: Any) -> None:
        """연결을 정한다(공간 서비스에도 그 공간에 묶어 같이 정한다)."""
        super().connect(**links)
        self._links = dict(links)
        for project_id, service in self._spaces.items():
            service.connect(**self._space_links(project_id))
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def _space_links(self, project_id: str) -> dict[str, Any]:
        out = dict(self._links)
        for name in ("runs", "events", "interactions"):
            if out.get(name) is not None:
                out[name] = _scoped(out[name], project_id)
        return out

    def for_project(self, project_id: str | None) -> ChatService:
        """그 프로젝트의 대화 서비스(공간이 없거나 ``project_id``가 없으면 자신 - 호스트 DB).

        처음 만들 때 연결을 붙이고, 턴 실행기가 있으면 그 공간의 남은 대기열에 재시작 정책을
        적용한다(자기 앱 항목만).
        """
        if not project_id or not self.spaced:
            return self
        found = self._spaces.get(project_id)
        if found is not None:
            return found
        assert self._records is not None
        assert self._make is not None
        records = self._records
        service = self._make(
            SpaceConversations(records, project_id),
            SpaceQueue(records, project_id),
            self._busy_reader(project_id),
        )
        service.connect(**self._space_links(project_id))
        self._spaces[project_id] = service
        if service.can_send:
            self._schedule_restart(project_id, service)
        return service

    async def for_project_ready(self, project_id: str | None) -> ChatService:
        """``for_project``와 같되, 그 공간의 재시작 정책 적용이 끝날 때까지 기다린다.

        공간 서비스는 처음 요청될 때 만들어지고 재시작 정책은 비동기로 적용되므로, 요청 경로는 이
        메서드로 서비스를 받아야 재시작 직후 첫 응답도 정책이 적용된 상태를 본다. 정책 적용의
        실패는 ``_schedule_restart``가 기록하고 삼킨다(여기서는 다시 던지지 않는다). 기다리던
        요청이 취소돼도 정책 적용은 계속된다.
        """
        service = self.for_project(project_id)
        if not project_id:
            return service
        pending = self._restart_pending.get(project_id)
        if pending is None or pending.done():
            return service
        if isinstance(pending, concurrent.futures.Future):
            await asyncio.shield(asyncio.wrap_future(pending))
        elif pending.get_loop() is asyncio.get_running_loop():
            await asyncio.shield(pending)
        return service

    def _busy_reader(self, project_id: str) -> Callable[[str], str | None]:
        def busy(conversation_id: str) -> str | None:
            runs = self._links.get("runs")
            if runs is None:
                return None
            scoped = _scoped(runs, project_id)
            try:
                found = scoped.list(conversation_id=conversation_id, status=list(UNFINISHED))
            except (RecordsUnavailable, LookupError, TypeError):
                return None
            for run in found:
                return str(run.id)
            return None

        return busy

    def _schedule_restart(self, project_id: str, service: ChatService) -> None:
        async def apply() -> None:
            try:
                applied = await service.apply_restart_policy()
            except (RecordsUnavailable, LookupError):
                return
            except Exception:
                _log.exception("프로젝트 대기열 재시작 정책 실패: %s", project_id)
                return
            if applied:
                _log.info("프로젝트 %s의 대기열 %d개 대화를 처리했습니다", project_id, len(applied))

        def forget(done: object) -> None:
            if self._restart_pending.get(project_id) is done:
                del self._restart_pending[project_id]

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            task = running.create_task(apply())
            self._restart_tasks.add(task)
            task.add_done_callback(self._restart_tasks.discard)
            self._restart_pending[project_id] = task
            task.add_done_callback(forget)
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        # 루프 밖(워커 스레드)에서 처음 열렸으면 루프에 넘긴다(create_task는 스레드 안전 아님).
        future = asyncio.run_coroutine_threadsafe(apply(), loop)
        self._restart_pending[project_id] = future
        future.add_done_callback(forget)

    def service_of(self, conversation_id: str) -> ChatService:
        """그 대화를 가진 서비스(호스트 → 이 프로세스에서 연 공간 → ``locate`` 순, 없으면 호스트).

        여러 곳에 있으면(``locate``가 모호) 호스트를 돌려준다(호출자가 ``get``으로 없음을 본다).
        """
        if self._conversations.get(conversation_id) is not None:
            return self
        for service in self._spaces.values():
            try:
                service.get(conversation_id)
            except Exception:
                continue
            return service
        try:
            project_id = self.locate(conversation_id)
        except ChatError:
            return self
        return self.for_project(project_id)

    def locate(self, conversation_id: str) -> str | None:
        """그 대화가 있는 기록 공간(등록 id, None = 호스트 DB).

        기억한 자리가 있으면 그 자리만 다시 확인한다. 없으면 이 프로세스에서 연 공간과
        ``project_ids``(앞에서 ``locate_limit``개)의 기록 DB, 호스트 DB를 모두 읽어 하나로 정한다.
        기록 DB 파일이 없거나 읽을 수 없는 공간은 건너뛴다(파일을 만들지 않는다).

        Raises:
            ConversationNotFoundError: 어디에도 없다.
            ConversationAmbiguousError: 여러 곳에 있다(``details.project_ids``).
        """
        found = self._locator.find(conversation_id)
        if not found:
            raise ConversationNotFoundError(
                f"대화 {conversation_id!r}가 없습니다", details={"id": conversation_id}
            )
        if len(found) > 1:
            raise ConversationAmbiguousError(
                f"대화 {conversation_id!r}가 여러 기록 공간에 있습니다",
                details={"id": conversation_id, "project_ids": found},
            )
        return found[0]

    def _has(self, place: str | None, conversation_id: str) -> bool:
        """그 자리(None = 호스트)에 대화가 있나. 읽을 수 없으면 거짓."""
        if place is None:
            return self._conversations.get(conversation_id) is not None
        if self._records is None:
            return False
        try:
            store = self._records.reader(place)
            return store is not None and store.conversations.get(conversation_id) is not None
        except (RecordsUnavailable, StoreError, LookupError):
            return False

    def stop_dispatch(self) -> None:
        super().stop_dispatch()
        for service in self._spaces.values():
            service.stop_dispatch()

    async def aclose(self) -> None:
        for task in list(self._restart_tasks):
            task.cancel()
        for pending in list(self._restart_pending.values()):
            pending.cancel()
        for service in self._spaces.values():
            await service.aclose()
        await super().aclose()

    def spaces(self) -> Mapping[str, ChatService]:
        """이 프로세스에서 연 공간 서비스(점검용)."""
        return dict(self._spaces)


__all__ = [
    "DEFAULT_LOCATE_LIMIT",
    "UNFINISHED",
    "ConversationAmbiguousError",
    "SpaceConversations",
    "SpaceQueue",
    "SpacedChatService",
    "chat_records",
]
