"""한 Run의 열린 상호작용을 관리한다(대기·응답·시간 제한·닫기, design §R14.5). 내부 모듈.

엔진(`_Execution`)이 `WaitHost`로 노드 상태 전이와 동시 실행 슬롯을 맡고, 이 모듈은 요청의
생명주기와 기록(저장 후 발행)만 다룬다. 종류 이름은 모른다(디스크립터만 본다).
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from agent_console_contracts import (
    Interaction,
    InteractionAnsweredPayload,
    InteractionClosedPayload,
    InteractionGrant,
    InteractionRequestedPayload,
    InteractionSettings,
    InteractionStatus,
    Issue,
    OnTimeout,
    Run,
    WaitInfo,
)
from agent_console_graph import SchemaChecker, compile_schema

from ._cancel import CancelToken
from ._interactions import (
    InteractionAnsweredBy,
    InteractionClosedError,
    InteractionCloseReasons,
    InteractionOutcome,
    InteractionRequest,
    ResponseValidationError,
    UnknownInteractionError,
    is_closed_error,
)
from ._interfaces import Clock, IdFactory, RunRecorder
from ._journal import RecorderError, RunJournal
from ._registries import Registries
from ._usage import preview

_log = logging.getLogger(__name__)

type Sleep = Callable[[float], Awaitable[object]]
"""`delay`초 기다리는 함수(기본 `asyncio.sleep`). 시간 제한 타이머가 쓴다(테스트에서 가짜로)."""

RUN_CANCEL_REASON = "interaction_timeout"
"""`on_timeout=cancel_run`으로 Run을 취소할 때의 취소 사유."""

RESPONSE_ISSUE_CODE = "invalid_response"
"""응답이 `response_schema`에 맞지 않을 때 `Issue.code`."""

type WaitKey = Hashable
"""기다리는 실행 하나를 가리키는 키. 스케줄된 노드는 노드 id, 위임자가 부른 노드 실행은 엔진이 정한
다른 키(같은 노드 id의 실행이 여럿일 수 있어서, design §5R.6)."""


class WaitHost(Protocol):
    """브로커가 엔진에 맡기는 것: 노드 상태 전이·슬롯·Run 상태(엔진 `_Execution`이 만족).

    `key`는 기다리는 실행 하나(`WaitKey`, 스케줄된 노드면 노드 id)다.
    """

    @property
    def run(self) -> Run: ...

    def node_open(self, key: WaitKey) -> bool:
        """노드 실행이 아직 진행 중이라 요청을 열 수 있는지."""
        ...

    def node_label(self, node_id: str) -> str:
        """노드 표시 이름(`NodeSpec.label`, 없으면 id). 요청의 `node_label`에 복사한다."""
        ...

    def node_waiting(self, key: WaitKey, wait: WaitInfo) -> None:
        """열린 요청이 생겼다(또는 늘었다): NodeRun waiting, 슬롯 반납, Run 상태 갱신."""
        ...

    async def node_resuming(self, key: WaitKey, waited_ms: int) -> None:
        """열린 요청이 모두 닫혔다: 슬롯 재획득 후 `node.resumed`, Run 상태 갱신."""
        ...


@dataclass(frozen=True)
class WaitPolicy:
    """시간 제한 기본값: 요청 값 > `grants[node_id]` > `settings` > 무기한·expire."""

    grants: Mapping[str, InteractionGrant] = field(default_factory=dict)
    settings: InteractionSettings | None = None

    def resolve(self, node_id: str, req: InteractionRequest) -> tuple[float | None, OnTimeout]:
        grant = self.grants.get(node_id)
        settings = self.settings
        timeout = req.timeout_seconds
        if timeout is None and grant is not None:
            timeout = grant.timeout_seconds
        if timeout is None and settings is not None:
            timeout = settings.timeout_seconds
        on_timeout = req.on_timeout
        if on_timeout is None and grant is not None:
            on_timeout = grant.on_timeout
        if on_timeout is None and settings is not None:
            on_timeout = settings.on_timeout
        return timeout, on_timeout or "expire"


@dataclass
class _Open:
    key: WaitKey
    stored: Interaction
    """비밀을 가린 저장본(pending)."""
    checker: SchemaChecker
    expire_response: dict[str, Any] | None
    on_timeout: OnTimeout
    future: asyncio.Future[InteractionOutcome]
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    closing: bool = False
    timer: asyncio.Task[None] | None = None


@dataclass
class _NodeWaits:
    open_ids: list[str] = field(default_factory=list)
    since: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InteractionBroker:
    """한 Run의 상호작용 요청·응답을 관리한다."""

    def __init__(
        self,
        host: WaitHost,
        *,
        journal: RunJournal,
        recorder: RunRecorder,
        registries: Registries,
        token: CancelToken,
        clock: Clock,
        ids: IdFactory,
        sleep: Sleep,
        policy: WaitPolicy,
        preview_chars: int,
        conversation_id: str | None = None,
    ) -> None:
        """`conversation_id`: 요청(`Interaction.conversation_id`)에 넣을 대화 id. 루트 Run이면
        그 Run의 값, 자식 Run이면 루트 Run의 값(자식 Run은 대화 턴이 아니다, design §5R.7)."""
        self._host = host
        self._conversation_id = conversation_id
        self._journal = journal
        self._recorder = recorder
        self._registries = registries
        self._token = token
        self._clock = clock
        self._ids = ids
        self._sleep = sleep
        self._policy = policy
        self._preview_chars = preview_chars
        self._open: dict[str, _Open] = {}
        self._closed: dict[str, Interaction] = {}
        self._nodes: dict[WaitKey, _NodeWaits] = {}
        self._tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------ 조회

    def pending(self) -> list[Interaction]:
        """열린 상호작용(저장본, `created_at` 순)."""
        return sorted((o.stored for o in self._open.values()), key=lambda i: (i.created_at, i.id))

    def knows(self, interaction_id: str) -> bool:
        """이 Run에서 연 상호작용인지(열림·닫힘 모두)."""
        return interaction_id in self._open or interaction_id in self._closed

    # ------------------------------------------------------------ 요청

    async def request(
        self,
        node_id: str,
        req: InteractionRequest,
        *,
        node_path: Sequence[str],
        actor: str | None,
        attempt: int,
        key: WaitKey | None = None,
    ) -> InteractionOutcome:
        """요청을 열고 닫힐 때까지 기다린다(`NodeContext.request_input`의 구현).

        `key`는 기다리는 실행(`WaitKey`, 생략하면 `node_id`). 시간 제한 기본값은 `node_id`로 찾는다.

        Raises:
            UnknownExtensionError: 등록되지 않은 종류.
            InvalidSchemaError: 응답 스키마가 잘못되었다.
            ValueError: `req.node_path`가 노드 경로로 시작하지 않는다.
        """
        descriptor = self._registries.interaction_kinds.get(req.kind).descriptor
        source = (
            req.response_schema if req.response_schema is not None else descriptor.response_schema
        )
        schema = copy.deepcopy(dict(source))
        checker = compile_schema(schema)
        own = list(node_path)
        path = own if req.node_path is None else list(req.node_path)
        if path[: len(own)] != own:
            raise ValueError(f"node_path {path!r}는 이 노드 경로 {own!r}로 시작해야 합니다")
        expire_response = (
            copy.deepcopy(dict(descriptor.expire_response))
            if descriptor.expire_response is not None
            else None
        )
        interaction_id = self._ids()
        wait_key: WaitKey = node_id if key is None else key
        if self._token.cancelled or not self._host.node_open(wait_key):
            reason = (
                InteractionCloseReasons.CANCELLED
                if self._token.cancelled
                else InteractionCloseReasons.NODE_FINISHED
            )
            return InteractionOutcome(
                interaction_id=interaction_id,
                status="cancelled",
                response=expire_response,
                reason=reason,
            )

        timeout, on_timeout = self._policy.resolve(node_id, req)
        now = self._clock()
        run = self._host.run
        interaction = Interaction(
            id=interaction_id,
            run_id=run.id,
            root_run_id=run.root_run_id,
            conversation_id=self._conversation_id,
            node_id=node_id,
            node_label=self._host.node_label(node_id),
            node_path=path,
            attempt=attempt,
            actor=req.actor if req.actor is not None else actor,
            kind=req.kind,
            status="pending",
            title=req.title,
            message=req.message,
            payload=dict(req.payload),
            response_schema=schema,
            created_at=now,
            expires_at=now + timeout if timeout is not None else None,
        )
        stored = self._journal.redact_model(interaction)
        entry = _Open(
            key=wait_key,
            stored=stored,
            checker=checker,
            expire_response=expire_response,
            on_timeout=on_timeout,
            future=asyncio.get_running_loop().create_future(),
        )
        waits = self._nodes.setdefault(wait_key, _NodeWaits())
        async with waits.lock:
            writer = self._recorder.interactions
            self._journal.save(writer.save, stored)
            self._journal.event(
                "interaction.requested",
                InteractionRequestedPayload(interaction=stored),
                node_path=path,
                attempt=attempt,
                actor=stored.actor,
            )
            self._open[interaction_id] = entry
            waits.open_ids.append(interaction_id)
            if len(waits.open_ids) == 1:
                waits.since = now
            self._host.node_waiting(
                wait_key,
                WaitInfo(
                    reason=req.kind,
                    message=stored.message or stored.title,
                    data={"interaction_ids": list(waits.open_ids)},
                ),
            )
            if timeout is not None:
                entry.timer = self._spawn(self._expire_later(entry, timeout))
        try:
            return await asyncio.shield(entry.future)
        except asyncio.CancelledError:
            # 요청한 쪽(노드 태스크)이 취소됐다: 요청도 취소로 닫는다.
            if not entry.closing:
                self._spawn(
                    self._close_quietly(entry, "cancelled", InteractionCloseReasons.CANCELLED)
                )
            raise
        finally:
            await self._leave(wait_key, waits, interaction_id)

    async def _leave(self, key: WaitKey, waits: _NodeWaits, interaction_id: str) -> None:
        """요청 하나가 끝났다. 열린 요청이 없으면 노드를 다시 running으로(슬롯 재획득)."""
        async with waits.lock:
            if interaction_id in waits.open_ids:
                waits.open_ids.remove(interaction_id)
            if waits.open_ids:
                return
            since, waits.since = waits.since, None
            if self._token.cancelled or not self._host.node_open(key):
                return
            waited_ms = round((self._clock() - since) * 1000) if since is not None else 0
            await self._host.node_resuming(key, max(waited_ms, 0))

    # ------------------------------------------------------------ 응답·닫기

    async def respond(
        self, interaction_id: str, response: Mapping[str, Any], *, by: str
    ) -> Interaction:
        """응답을 검증해 요청을 닫는다(먼저 도착한 하나만 성공).

        Raises:
            UnknownInteractionError: 이 Run에서 연 요청이 아니다.
            InteractionClosedError: 이미 닫혔다(또는 다른 응답이 먼저 닫는 중).
            ResponseValidationError: `response_schema`에 맞지 않는다.
            RecorderError: 저장소 기록 실패(요청은 메모리에서 닫히고 요청자는 응답을 받는다).
        """
        entry = self._open.get(interaction_id)
        if entry is None:
            if interaction_id in self._closed:
                raise InteractionClosedError(self._closed[interaction_id])
            raise UnknownInteractionError(self._host.run.id, interaction_id)
        if entry.closing:
            await entry.closed.wait()
            raise InteractionClosedError(self._closed.get(interaction_id, entry.stored))
        body = dict(response)
        violations = entry.checker(body)
        if violations:
            raise ResponseValidationError(
                [
                    Issue(
                        severity="error",
                        code=RESPONSE_ISSUE_CODE,
                        message=v.message,
                        path=v.pointer,
                        details={"validator": v.validator},
                    )
                    for v in violations
                ]
            )
        return await self._close(entry, "answered", answered_by=by, reason=None, response=body)

    async def close_node(self, key: WaitKey) -> None:
        """노드 실행이 끝났다: 그 실행(`key`)의 열린 요청을 `cancelled(node_finished)`로 닫는다."""
        for entry in [o for o in self._open.values() if o.key == key]:
            await self._close_quietly(entry, "cancelled", InteractionCloseReasons.NODE_FINISHED)

    async def close_all(
        self,
        reason: str = InteractionCloseReasons.CANCELLED,
        *,
        status: InteractionStatus = "cancelled",
    ) -> None:
        """열린 요청을 모두 닫는다(Run 취소 = `cancelled`, 실행 끊김 = `expired`/`interrupted`)."""
        for entry in list(self._open.values()):
            await self._close_quietly(entry, status, reason)

    async def drain(self) -> None:
        """남은 타이머를 멈추고 뒤에서 도는 닫기 작업이 끝날 때까지 기다린다."""
        for entry in self._open.values():
            if entry.timer is not None:
                entry.timer.cancel()
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _close_quietly(self, entry: _Open, status: InteractionStatus, reason: str) -> None:
        if entry.closing:
            return
        try:
            await self._close(
                entry,
                status,
                answered_by=InteractionAnsweredBy.SYSTEM,
                reason=reason,
                response=None,
            )
        except InteractionClosedError:
            pass
        except RecorderError:
            _log.warning("상호작용 %s 닫기 기록 실패", entry.stored.id)

    async def _expire_later(self, entry: _Open, timeout: float) -> None:
        await self._sleep(timeout)
        if entry.closing:
            return
        cancel_run = entry.on_timeout == "cancel_run"
        try:
            await self._close(
                entry,
                "cancelled" if cancel_run else "expired",
                answered_by=InteractionAnsweredBy.TIMEOUT,
                reason=InteractionCloseReasons.TIMEOUT,
                response=None,
            )
        except (InteractionClosedError, RecorderError):
            return
        if cancel_run:
            self._token.cancel(RUN_CANCEL_REASON)

    async def _close(
        self,
        entry: _Open,
        status: InteractionStatus,
        *,
        answered_by: str,
        reason: str | None,
        response: dict[str, Any] | None,
    ) -> Interaction:
        """요청 하나를 닫는다: 저장(조건부) → 이벤트 → 요청자에게 결과."""
        if entry.closing:
            raise InteractionClosedError(entry.stored)
        entry.closing = True
        if entry.timer is not None and entry.timer is not asyncio.current_task():
            entry.timer.cancel()
        stored_response = self._journal.redact(response) if response is not None else None
        interaction_id = entry.stored.id
        closed_at = self._clock()
        writer = self._recorder.interactions
        conflict = False
        failure: BaseException | None = None
        try:
            closed = await self._journal.call(
                lambda: writer.close(
                    interaction_id,
                    status=status,
                    closed_at=closed_at,
                    response=stored_response,
                    answered_by=answered_by,
                    close_reason=reason,
                )
            )
        except Exception as exc:
            if is_closed_error(exc):
                conflict = True
                closed = exc.interaction  # type: ignore[attr-defined]
            else:
                failure = exc
                closed = entry.stored.model_copy(
                    update={
                        "status": status,
                        "closed_at": closed_at,
                        "response": stored_response,
                        "answered_by": answered_by,
                        "close_reason": reason,
                    }
                )
        self._open.pop(interaction_id, None)
        self._closed[interaction_id] = closed
        if not conflict:
            self._emit_closed(closed)
        entry.closed.set()
        if not entry.future.done():
            entry.future.set_result(self._outcome(entry, closed, response))
        if conflict:
            raise InteractionClosedError(closed)
        if failure is not None:
            err = RecorderError(f"상호작용 {interaction_id} 닫기 기록 실패")
            raise err from failure
        return closed

    def _emit_closed(self, closed: Interaction) -> None:
        if closed.status == "answered":
            self._journal.event(
                "interaction.answered",
                InteractionAnsweredPayload(
                    interaction_id=closed.id,
                    kind=closed.kind,
                    answered_by=closed.answered_by,
                    response_preview=preview(closed.response, self._preview_chars),
                ),
                node_path=list(closed.node_path),
                attempt=closed.attempt,
                actor=closed.actor,
            )
        elif closed.status in ("expired", "cancelled"):
            self._journal.event(
                "interaction.closed",
                InteractionClosedPayload(
                    interaction_id=closed.id,
                    kind=closed.kind,
                    status="expired" if closed.status == "expired" else "cancelled",
                    reason=closed.close_reason,
                ),
                node_path=list(closed.node_path),
                attempt=closed.attempt,
                actor=closed.actor,
            )

    @staticmethod
    def _outcome(
        entry: _Open, closed: Interaction, response: dict[str, Any] | None
    ) -> InteractionOutcome:
        if closed.status == "answered":
            return InteractionOutcome(
                interaction_id=closed.id,
                status="answered",
                response=response if response is not None else closed.response,
            )
        return InteractionOutcome(
            interaction_id=closed.id,
            status="expired" if closed.status == "expired" else "cancelled",
            response=copy.deepcopy(entry.expire_response),
            reason=closed.close_reason,
        )

    def _spawn[T](self, coro: Awaitable[T]) -> asyncio.Task[T]:
        task: asyncio.Task[T] = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            _log.error("상호작용 작업 실패: %r", exc)
