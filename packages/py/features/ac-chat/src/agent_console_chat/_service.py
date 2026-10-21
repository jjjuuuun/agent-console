"""`ChatService`: 대화 CRUD, 메시지 → 턴, 실행 중 메시지 정책, 세션 이어 쓰기, 턴 조립."""

import asyncio
import builtins
import contextlib
import logging
import time
import uuid
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from typing import Any

from agent_console_contracts import (
    ChatSettings,
    ChatTurn,
    Conversation,
    ConversationSummary,
    CreateConversationRequest,
    Graph,
    PostMessageRequest,
    QueueAfterRestart,
    QueuedMessage,
    Run,
    RunStatus,
    UpdateConversationRequest,
)

from ._errors import (
    ChatFeatureUnavailableError,
    ConversationBusyError,
    ConversationNotFoundError,
    GraphNotFoundError,
    InvalidMessageError,
    QueuedMessageNotFoundError,
    TurnNotFoundError,
    TurnNotResumableError,
)
from ._ports import (
    ChatSettingsResolver,
    Clock,
    ConversationListener,
    ConversationRepository,
    EventReader,
    GraphLookup,
    IdFactory,
    InteractionReader,
    RunReader,
    TurnHandle,
    TurnLauncher,
    TurnSessions,
    TurnStart,
)
from ._queue import RESTART_HOLD_REASON, MemoryQueue, QueueEntry, QueueSize, QueueStore
from ._settings import layered_chat_settings
from ._turns import (
    RootRunSessions,
    assemble_turn,
    first_message_title,
    message_text,
)

_log = logging.getLogger(__name__)

PENDING_STATUS = "pending"
"""열린 상호작용 상태(계약 `InteractionStatus`)."""

LAUNCHER_DEPENDENCY = "launcher"
"""`ChatFeatureUnavailableError.dependency`: 턴 실행기(`launcher`)가 없다."""
RUNS_DEPENDENCY = "runs"
"""`ChatFeatureUnavailableError.dependency`: Run 조회(`runs`)가 없다."""

CLOSED_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "interrupted"})
"""턴이 끝난 Run 상태. 대화가 턴 마무리(세션 기록)를 마치기 전에는 바깥에 `CLOSING_STATUS`로
보인다(5.2R.39 순서: 답변·세션 기록 → 상태 공개 → 알림)."""
CLOSING_STATUS: RunStatus = "running"
"""턴 마무리 중(Run은 끝났고 대화가 아직 세션을 기록하지 않음)에 보이는 상태."""


def _default_ids() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class ChatOptions:
    """환경 값(설정 데이터가 아닌 조립 옵션).

    Attributes:
        message_input_key: 메시지 본문을 넣을 Run 입력 키. 입구 연결(`message`)이 `input_key`를
            생략하면 읽는 키와 맞춰야 한다.
        origin: 턴 Run의 `origin`.
        resume_origin: 끊긴 턴을 이어 간 Run의 `origin`(design §2R.10).
        title_chars: `chat.title = first_message`일 때 제목 길이(글자).
        default_turn_limit: `turns()`의 기본 개수.
    """

    message_input_key: str = "text"
    origin: str = "chat"
    resume_origin: str = "resume"
    title_chars: int = 40
    default_turn_limit: int = 50


def _open_view(run: Run) -> Run:
    """대화가 아직 마무리하지 않은 턴 Run의 바깥 모습.

    끝난 상태면 `CLOSING_STATUS`(종료 시각 없음), 아니면 그대로.
    """
    if run.status not in CLOSED_RUN_STATUSES:
        return run
    return run.model_copy(update={"status": CLOSING_STATUS, "ended_at": None})


def _queued_message(item: QueueEntry, *, position: int | None = None) -> QueuedMessage:
    return QueuedMessage(
        id=item.id,
        position=position if position is not None else item.position,
        text=item.text,
        held=item.held,
    )


class ChatService:
    """대화 서비스. 전송 계층(HTTP·WS·CLI)과 저장소·실행 엔진을 모른다(모두 주입).

    - 대화 한 턴 = Run 하나. 메시지 목록은 따로 저장하지 않고 Run 입력·`run.reply`·상호작용에서
      만든다(`turns`).
    - 실행 중(대기 `waiting` 포함)인 대화에 새 메시지가 오면 유효 설정 `chat.busy_policy`를 따른다:
      `queue`면 대기열에 넣고 앞 턴이 끝나면 실행, `reject`면 `ConversationBusyError`.
    - 턴이 끝나면 노드별 백엔드 세션을 대화 `sessions`에 저장하고 다음 턴에 넘긴다(R4.6). 키 모양과
      수집 범위는 주입한 `TurnSessions` 규칙이 정한다(기본: 턴 Run 자기 노드).
    - 대기열은 주입한 `QueueStore`에 있다(기본 메모리, 서버는 SQLite 저장소를 넘겨 재시작 뒤에도
      남긴다). 재시작 뒤 처리는 `apply_restart_policy()`가 설정 `chat.queue_after_restart`대로 한다.
      실행 중 표시는 이 프로세스 메모리에 있다.
    - 끊긴 턴은 `resume_turn`으로 같은 대화에서 이어 간다(새 Run, `resumed_from`).
    - 실행 연결(`launcher`·`runs`·`events`·`interactions`)은 모두 선택이다. 없으면 대화·대기열
      관리는 그대로 동작하고, 전송·이어 가기는 `ChatFeatureUnavailableError`, 턴 목록은 비고, 대기
      상호작용 수는 0이다. 대기열은 실행기가 생길 때까지 꺼내지 않는다(`connect`).

    Args:
        conversations: 대화 저장소.
        graphs: 팀 구성 정의 조회.
        launcher: 턴(Run) 시작·취소(없으면 전송 불가).
        runs: Run 조회(없으면 턴 목록이 비고 마지막 상태를 모른다).
        events: RunEvent 조회(없으면 답변·세션을 읽지 않는다).
        interactions: 상호작용 조회(없으면 턴의 상호작용이 비고 대기 수는 0).
        sessions: 턴 세션 수집·정리 규칙(없으면 `RootRunSessions(events)` — 턴 Run 자기 이벤트,
            키 = 노드 id. 중첩 실행(자식 Run)의 세션까지 이으려면 조립이 규칙을 넘긴다).
        settings: 유효 채팅 설정 해석기(공통 → 팀 구성). 기본은 스키마 기본값 + 팀 구성 층.
        listener: 대화 요약이 바뀔 때 부를 콜백(예외는 기록하고 삼킨다).
        clock: 시각 함수.
        ids: id 생성기(대화·대기열 항목).
        options: 조립 옵션.
        queue: 대기열 저장소(기본 `MemoryQueue`).
    """

    def __init__(
        self,
        conversations: ConversationRepository,
        graphs: GraphLookup,
        *,
        launcher: TurnLauncher | None = None,
        runs: RunReader | None = None,
        events: EventReader | None = None,
        interactions: InteractionReader | None = None,
        sessions: TurnSessions | None = None,
        settings: ChatSettingsResolver | None = None,
        listener: ConversationListener | None = None,
        clock: Clock = time.time,
        ids: IdFactory = _default_ids,
        options: ChatOptions | None = None,
        queue: QueueStore | None = None,
    ) -> None:
        self._launcher = launcher
        self._conversations = conversations
        self._runs = runs
        self._events = events
        self._interactions = interactions
        self._sessions = sessions
        self._graphs = graphs
        self._settings = settings or layered_chat_settings()
        self._listener = listener
        self._clock = clock
        self._ids = ids
        self.options = options or ChatOptions()
        self._active: dict[str, TurnHandle] = {}
        self._queue: QueueStore = queue if queue is not None else MemoryQueue()
        self._dispatching = True
        self._locks: dict[str, asyncio.Lock] = {}
        self._watchers: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------ 실행 연결

    def connect(
        self,
        *,
        launcher: TurnLauncher | None = None,
        runs: RunReader | None = None,
        events: EventReader | None = None,
        interactions: InteractionReader | None = None,
        sessions: TurnSessions | None = None,
    ) -> None:
        """실행 연결을 (다시) 정한다(모두 바꾼다, None = 없음 — `sessions`는 기본 규칙). 조립
        순서상 서비스를 먼저 만들고 연결을 나중에 아는 조립기(예: 서버 모듈의 시작 훅)가 턴을
        시작하기 전에 한 번 부른다."""
        self._launcher = launcher
        self._runs = runs
        self._events = events
        self._interactions = interactions
        self._sessions = sessions

    @property
    def can_send(self) -> bool:
        """메시지 전송(턴 시작)이 가능한지(턴 실행기가 있는지)."""
        return self._launcher is not None

    # ------------------------------------------------------------ 대화 CRUD

    def create(self, request: CreateConversationRequest) -> Conversation:
        """대화를 만든다.

        Raises:
            GraphNotFoundError: 팀 구성이 없을 때.
        """
        self._require_graph(request.graph_id)
        now = self._clock()
        conversation = Conversation(
            id=self._ids(),
            graph_id=request.graph_id,
            title=(request.title or "").strip(),
            created_at=now,
            updated_at=now,
            project_id=request.project_id,
        )
        self._conversations.save(conversation)
        self._notify(conversation)
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        """대화 하나.

        Raises:
            ConversationNotFoundError: 없을 때.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(
                f"대화 {conversation_id!r}가 없습니다", details={"id": conversation_id}
            )
        return conversation

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
    ) -> builtins.list[ConversationSummary]:
        """대화 요약 목록(최근 갱신순). `project_id` = 그 프로젝트의 대화만(불투명 문자열)."""
        # project_id는 거를 때만 넘긴다(옛 ConversationRepository 구현도 그대로 동작).
        extra = {"project_id": project_id} if project_id is not None else {}
        items = self._conversations.list(graph_id=graph_id, archived=archived, **extra)
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        sizes = self._queue.counts([c.id for c in items]) if items else {}
        return [self._summarize(c, sizes) for c in items]

    def summary(self, conversation_id: str) -> ConversationSummary:
        """대화 요약(마지막 턴 상태·대기열 수·대기 중 상호작용 수).

        Raises:
            ConversationNotFoundError: 없을 때.
        """
        return self._summarize(self.get(conversation_id))

    def update(self, conversation_id: str, request: UpdateConversationRequest) -> Conversation:
        """제목·보관·팀 구성을 바꾼다(생략한 필드는 그대로).

        팀 구성을 바꾸면 새 팀 구성에 없는 노드의 세션을 버린다. 실행 중인 턴은 원래 팀 구성으로
        끝까지 돌고, 다음 턴부터 새 팀 구성을 쓴다.

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
            GraphNotFoundError: 새 팀 구성이 없을 때.
        """
        conversation = self.get(conversation_id)
        changes: dict[str, object] = {}
        if request.title is not None:
            changes["title"] = request.title.strip()
        if request.archived is not None:
            changes["archived"] = request.archived
        if request.graph_id is not None and request.graph_id != conversation.graph_id:
            graph = self._require_graph(request.graph_id)
            changes["graph_id"] = graph.id
            changes["sessions"] = self._session_rules().prune(
                conversation.sessions, [n.id for n in graph.nodes]
            )
        if not changes:
            return conversation
        changes["updated_at"] = self._clock()
        updated = conversation.model_copy(update=changes)
        self._conversations.save(updated)
        self._notify(updated)
        return updated

    def delete(self, conversation_id: str) -> None:
        """대화를 지운다. 실행 중인 턴은 취소하고 대기열은 버린다. Run 기록은 남는다.

        Raises:
            ConversationNotFoundError: 없을 때.
        """
        self.get(conversation_id)
        self._queue.clear(conversation_id)
        handle = self._active.get(conversation_id)
        if handle is not None and self._launcher is not None:
            self._launcher.cancel(handle.run_id, "conversation_deleted")
        self._conversations.delete(conversation_id)

    # ------------------------------------------------------------ 메시지

    def is_busy(self, conversation_id: str) -> bool:
        """실행 중인 턴이 있는지(응답 대기 `waiting`도 실행 중이다)."""
        return conversation_id in self._active

    def active_run_id(self, conversation_id: str) -> str | None:
        """실행 중인 턴의 Run id(없으면 None)."""
        handle = self._active.get(conversation_id)
        return handle.run_id if handle is not None else None

    async def post_message(
        self, conversation_id: str, request: PostMessageRequest
    ) -> Run | QueuedMessage:
        """메시지를 보낸다. 쉬고 있으면 턴(Run)을 시작하고, 실행 중이면 `chat.busy_policy`를 따른다.

        실행 중이 아니어도 대기열에 항목(예: 재시작으로 멈춘 항목)이 남아 있고 정책이 `queue`면
        순서를 지키려고 그 뒤에 줄을 세운다(맨 앞이 멈춰 있으면 풀릴 때까지 기다린다).

        Returns:
            시작한 Run, 또는 대기열에 넣었으면 `QueuedMessage`.

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
            GraphNotFoundError: 대화의 팀 구성이 없을 때(바로 시작하는 경우).
            ConversationBusyError: 실행 중이고 정책이 `reject`일 때.
            InvalidMessageError: 본문이 비었을 때.
            ChatFeatureUnavailableError: 턴 실행기(`launcher`)가 없을 때(대기열에도 넣지 않는다).
            Exception: 실행 엔진이 시작을 거부한 오류(예: 그래프 검증 실패)는 그대로 올린다.
        """
        text = request.text
        if not text.strip():
            raise InvalidMessageError("빈 메시지는 보낼 수 없습니다")
        async with self._lock(conversation_id):
            conversation = self.get(conversation_id)
            if self._launcher is None:
                raise ChatFeatureUnavailableError(
                    LAUNCHER_DEPENDENCY, "턴 실행기가 연결되지 않아 메시지를 보낼 수 없습니다"
                )
            busy = self.is_busy(conversation_id)
            waiting = conversation_id in self._queue.counts([conversation_id])
            if busy or waiting:
                graph = self._graphs.get_graph(conversation.graph_id)
                policy = self._chat_settings(graph).busy_policy
                if busy and policy == "reject":
                    raise ConversationBusyError(
                        "실행 중인 턴이 있습니다",
                        details={
                            "conversation_id": conversation_id,
                            "run_id": self.active_run_id(conversation_id),
                        },
                    )
                if policy != "reject":
                    item = self._queue.enqueue(
                        self._ids(), conversation_id, text, created_at=self._clock()
                    )
                    conversation = self._maybe_title(conversation, text, graph)
                    if not busy:
                        await self._start_next(conversation)
                        handle = self._active.get(conversation_id)
                        if handle is not None and self._queue.get(item.id) is None:
                            return handle.run  # 앞 항목이 모두 빠져 이 메시지가 바로 시작됨
                    else:
                        self._notify(conversation)
                    current = self._queue.get(item.id)
                    return _queued_message(current if current is not None else item)
            handle = await self._start(conversation, text)
            return handle.run

    def queue(self, conversation_id: str) -> builtins.list[QueuedMessage]:
        """대기열(1 = 다음 차례).

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
        """
        self.get(conversation_id)
        return [_queued_message(item) for item in self._queue.list(conversation_id)]

    def cancel_queued(self, conversation_id: str, queued_id: str) -> QueuedMessage:
        """대기열 항목 하나를 취소한다(`DELETE /conversations/{id}/queue/{queued_id}`).

        Returns:
            취소한 항목(취소 직전 순번).

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
            QueuedMessageNotFoundError: 항목이 없을 때(이미 실행됐거나 취소됨).
        """
        conversation = self.get(conversation_id)
        item = self._require_queued(conversation_id, queued_id)
        if not self._queue.remove(queued_id):
            raise self._queued_not_found(conversation_id, queued_id)
        self._notify(conversation)
        # 멈춘 맨 앞 항목을 지웠으면 뒤의 항목이 흐를 수 있다(쉬고 있을 때).
        if item.position == 1 and not self.is_busy(conversation_id):
            self._spawn(conversation_id, self._kick(conversation_id))
        return _queued_message(item)

    async def release_queued(self, conversation_id: str, queued_id: str) -> QueuedMessage:
        """멈춘(held) 대기열 항목을 풀어 실행 순서에 넣는다(재시작 뒤 [실행], design §2R.10).

        쉬고 있고 이 항목이 맨 앞이면 곧바로 턴을 시작한다. 앞에 멈춘 항목이 남아 있으면 그것이
        풀리거나 지워질 때까지 기다린다(순서 보존). 이미 풀린 항목도 오류가 아니다.

        Returns:
            푼 항목(시작했으면 시작 직전 순번, `held=false`).

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
            QueuedMessageNotFoundError: 항목이 없을 때(이미 실행됐거나 취소됨).
        """
        async with self._lock(conversation_id):
            conversation = self.get(conversation_id)
            self._require_queued(conversation_id, queued_id)
            released = self._queue.release(queued_id)
            if self.is_busy(conversation_id):
                self._notify(conversation)
            else:
                await self._start_next(conversation)
            return _queued_message(released)

    async def apply_restart_policy(self) -> dict[str, QueueAfterRestart]:
        """서버 시작 시 한 번: 남아 있는 대기열을 설정 `chat.queue_after_restart`대로 처리한다.

        - `ask`: 대화의 모든 항목을 멈춘다(`held`, 사유 `restart`). 사용자가 풀거나 지운다.
        - `run`: 순서대로 실행한다(앞 턴이 끊겼어도). 이미 멈춘 항목은 그대로 둔다.
        - `drop`: 지운다.
        대화가 없어진 항목은 지운다. 설정은 대화의 팀 구성 층까지 해석한다.

        Returns:
            처리한 대화 id → 적용한 모드.
        """
        applied: dict[str, QueueAfterRestart] = {}
        for conversation_id in builtins.list(self._queue.counts()):
            async with self._lock(conversation_id):
                conversation = self._conversations.get(conversation_id)
                if conversation is None:
                    self._queue.clear(conversation_id)
                    continue
                graph = self._graphs.get_graph(conversation.graph_id)
                mode = self._chat_settings(graph).queue_after_restart
                applied[conversation_id] = mode
                if mode == "drop":
                    self._queue.clear(conversation_id)
                elif mode == "ask":
                    self._queue.hold_all(RESTART_HOLD_REASON, conversation_id=conversation_id)
                elif not self.is_busy(conversation_id):
                    await self._start_next(conversation)
                    continue  # _start_next·_start가 알린다
                self._notify(conversation)
        return applied

    async def resume_turn(
        self,
        run_id: str,
        *,
        graph: Graph,
        seed: Mapping[str, Mapping[str, Any]],
    ) -> Run:
        """끊긴 턴을 같은 대화에서 이어 간다: 고른 노드를 저장된 입력으로 다시 실행하는 새 Run.

        새 Run은 `origin = ChatOptions.resume_origin`, `resumed_from = run_id`이고 입력은 원래 턴과
        같다(같은 사용자 메시지). 어떤 노드를 다시 실행해도 되는지는 호출자가 검사한다.

        Args:
            run_id: 끊긴 턴의 Run id.
            graph: 실행할 팀 구성(보통 원래 Run 당시 버전).
            seed: 노드 id → 저장된 입력.

        Raises:
            TurnNotFoundError: Run이 없거나 대화 턴이 아닐 때.
            ConversationNotFoundError: 대화가 지워졌을 때.
            ConversationBusyError: 대화에 실행 중인 턴이 있을 때.
            TurnNotResumableError: 대화의 마지막 턴이 아닐 때(뒤에 새 턴이 있음).
            ChatFeatureUnavailableError: 턴 실행기·Run 조회가 없을 때.
            Exception: 실행 엔진이 시작을 거부한 오류는 그대로.
        """
        if self._launcher is None:
            raise ChatFeatureUnavailableError(LAUNCHER_DEPENDENCY)
        if self._runs is None:
            raise ChatFeatureUnavailableError(RUNS_DEPENDENCY)
        run = self._runs.get(run_id)
        if run is None or run.conversation_id is None:
            raise TurnNotFoundError(f"턴 {run_id!r}가 없습니다", details={"run_id": run_id})
        conversation_id = run.conversation_id
        async with self._lock(conversation_id):
            conversation = self.get(conversation_id)
            if self.is_busy(conversation_id):
                raise ConversationBusyError(
                    "실행 중인 턴이 있습니다",
                    details={
                        "conversation_id": conversation_id,
                        "run_id": self.active_run_id(conversation_id),
                    },
                )
            if conversation.last_run_id != run_id:
                raise TurnNotResumableError(
                    "대화의 마지막 턴만 이어 갈 수 있습니다",
                    details={
                        "conversation_id": conversation_id,
                        "run_id": run_id,
                        "last_run_id": conversation.last_run_id,
                    },
                )
            handle = await self._start(
                conversation,
                message_text(run, self.options.message_input_key),
                graph=graph,
                input=dict(run.input),
                seed={k: dict(v) for k, v in seed.items()},
                resumed_from=run_id,
                origin=self.options.resume_origin,
            )
            return handle.run

    # ------------------------------------------------------------ 턴

    def turns(
        self, conversation_id: str, *, before: str | None = None, limit: int | None = None
    ) -> builtins.list[ChatTurn]:
        """대화의 턴 목록. `before`(Run id)보다 앞선 턴 중 최근 `limit`개를 **오래된 순**으로.
        Run 조회(`runs`)가 없으면 빈 목록.

        Raises:
            ConversationNotFoundError: 대화가 없을 때.
            TurnNotFoundError: `before`가 이 대화의 턴이 아닐 때.
        """
        self.get(conversation_id)
        if self._runs is None:
            return []
        count = max(1, limit if limit is not None else self.options.default_turn_limit)
        runs = self._runs.list(conversation_id=conversation_id, limit=None)
        if before is not None:
            index = next((i for i, r in enumerate(runs) if r.id == before), None)
            if index is None:
                raise TurnNotFoundError(
                    f"이 대화에 턴 {before!r}가 없습니다",
                    details={"conversation_id": conversation_id, "run_id": before},
                )
            runs = runs[index + 1 :]
        page = builtins.list(reversed(runs[:count]))
        return [self._turn(run) for run in page]

    def turn(self, run_id: str) -> ChatTurn:
        """턴 하나(Run id로).

        Raises:
            TurnNotFoundError: Run이 없거나 대화 턴이 아닐 때(Run 조회가 없을 때 포함).
        """
        run = self._runs.get(run_id) if self._runs is not None else None
        if run is None or run.conversation_id is None:
            raise TurnNotFoundError(f"턴 {run_id!r}가 없습니다", details={"run_id": run_id})
        return self._turn(run)

    def notify(self, conversation_id: str) -> None:
        """대화 요약을 다시 알린다(예: 상호작용 상태가 바뀌어 대기 수가 달라졌을 때).

        대화가 없으면 아무것도 하지 않는다.
        """
        conversation = self._conversations.get(conversation_id)
        if conversation is not None:
            self._notify(conversation)

    async def wait_idle(self, conversation_id: str | None = None) -> None:
        """실행 중인 턴과 대기열이 모두 끝날 때까지 기다린다(테스트·종료용)."""
        while True:
            pending = [
                t
                for t in self._watchers
                if conversation_id is None or t.get_name() == f"chat:{conversation_id}"
            ]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)

    def stop_dispatch(self) -> None:
        """대기열에서 새 턴을 꺼내지 않게 한다(종료 직전, 엔진을 멈추기 전에 부른다).

        대기열 항목은 저장소에 남아 다음 시작 때 `apply_restart_policy`가 처리한다.
        """
        self._dispatching = False

    async def aclose(self) -> None:
        """감시 태스크를 정리한다. 대기열(저장소)과 실행 중인 Run(엔진 몫)은 건드리지 않는다."""
        self._dispatching = False
        watchers = builtins.list(self._watchers)
        for task in watchers:
            task.cancel()
        for task in watchers:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # ------------------------------------------------------------ 내부

    def _lock(self, conversation_id: str) -> asyncio.Lock:
        return self._locks.setdefault(conversation_id, asyncio.Lock())

    def _require_graph(self, graph_id: str) -> Graph:
        graph = self._graphs.get_graph(graph_id)
        if graph is None:
            raise GraphNotFoundError(f"팀 구성 {graph_id!r}가 없습니다", details={"id": graph_id})
        return graph

    def _chat_settings(self, graph: Graph | None) -> ChatSettings:
        return self._settings(graph)

    def _maybe_title(
        self, conversation: Conversation, text: str, graph: Graph | None
    ) -> Conversation:
        if conversation.title or self._chat_settings(graph).title != "first_message":
            return conversation
        title = first_message_title(text, self.options.title_chars)
        if not title:
            return conversation
        updated = conversation.model_copy(update={"title": title, "updated_at": self._clock()})
        self._conversations.save(updated)
        return updated

    async def _start(
        self,
        conversation: Conversation,
        text: str,
        *,
        graph: Graph | None = None,
        input: dict[str, Any] | None = None,
        seed: dict[str, dict[str, Any]] | None = None,
        resumed_from: str | None = None,
        origin: str | None = None,
    ) -> TurnHandle:
        """락 안에서 부른다. Run을 시작하고 대화를 갱신한 뒤 끝을 감시한다."""
        launcher = self._launcher
        if launcher is None:
            raise ChatFeatureUnavailableError(LAUNCHER_DEPENDENCY)
        if graph is None:
            graph = self._require_graph(conversation.graph_id)
            sessions = dict(conversation.sessions)
        else:
            sessions = self._session_rules().prune(
                conversation.sessions, [n.id for n in graph.nodes]
            )
        handle = await launcher.start_turn(
            TurnStart(
                conversation_id=conversation.id,
                graph=graph,
                input=input if input is not None else {self.options.message_input_key: text},
                text=text,
                sessions=sessions,
                origin=origin or self.options.origin,
                seed=seed,
                resumed_from=resumed_from,
                project_id=conversation.project_id,
            )
        )
        self._active[conversation.id] = handle
        # start_turn을 기다리는 동안 update(graph_id=…)·제목 변경이 들어왔을 수 있다.
        # 옛 스냅샷으로 덮어쓰지 않도록 저장소에서 다시 읽고 바꿀 필드만 갱신한다.
        latest = self._conversations.get(conversation.id)
        if latest is None:  # 시작하는 동안 대화가 지워짐: 시작한 턴을 취소한다
            launcher.cancel(handle.run_id, "conversation_deleted")
            self._active.pop(conversation.id, None)
            return handle
        conversation = self._maybe_title(latest, text, graph)
        conversation = conversation.model_copy(
            update={"last_run_id": handle.run_id, "updated_at": self._clock()}
        )
        self._conversations.save(conversation)
        self._spawn(conversation.id, self._watch(conversation.id, handle))
        self._notify(conversation)
        return handle

    def _spawn(self, conversation_id: str, coro: Coroutine[Any, Any, None]) -> None:
        """대화 이름표를 단 감시 태스크(`wait_idle`·`aclose`가 기다리고 정리한다)."""
        task = asyncio.create_task(coro, name=f"chat:{conversation_id}")
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    async def _kick(self, conversation_id: str) -> None:
        """쉬고 있으면 대기열 맨 앞을 실행한다(멈춘 항목을 지운 뒤 등)."""
        async with self._lock(conversation_id):
            if self.is_busy(conversation_id):
                return
            conversation = self._conversations.get(conversation_id)
            if conversation is not None:
                await self._start_next(conversation)

    def _require_queued(self, conversation_id: str, queued_id: str) -> QueueEntry:
        item = self._queue.get(queued_id)
        if item is None or item.conversation_id != conversation_id:
            raise self._queued_not_found(conversation_id, queued_id)
        return item

    @staticmethod
    def _queued_not_found(conversation_id: str, queued_id: str) -> QueuedMessageNotFoundError:
        return QueuedMessageNotFoundError(
            f"대기열 항목 {queued_id!r}가 없습니다",
            details={"conversation_id": conversation_id, "queued_id": queued_id},
        )

    async def _watch(self, conversation_id: str, handle: TurnHandle) -> None:
        try:
            run = await handle.wait()
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # 이 감시 태스크가 취소됨(aclose)
            run = handle.run  # Run 태스크 쪽이 취소됨: 끝난 것으로 처리
        except Exception:
            _log.exception("턴 %s 대기 실패", handle.run_id)
            run = handle.run
        # 턴 마무리 순서(5.2R.39): 세션 기록 → 손잡이 내림(그때부터 끝난 상태가 보인다) → 알림.
        # 손잡이가 `_active`에 있는 동안 `_turn`·`_status`는 끝난 Run을 `CLOSING_STATUS`로 보인다.
        # 세션 저장이 실패해도 손잡이는 반드시 내린다(턴이 running으로 굳거나 대기열이 멈추지 않게).
        async with self._lock(conversation_id):
            try:
                conversation = self._conversations.get(conversation_id)
                if conversation is not None:
                    try:
                        conversation = self._record_sessions(conversation, run)
                    except Exception:  # 저장 실패: 기록하고 이전 대화 상태로 이어 간다
                        _log.exception("턴 %s 세션 기록 실패", run.id)
            finally:
                if self._active.get(conversation_id) is handle:
                    del self._active[conversation_id]
            if conversation is None:  # 실행 중에 대화가 지워짐
                self._queue.clear(conversation_id)
                return
            await self._start_next(conversation)

    def _session_rules(self) -> TurnSessions:
        return self._sessions if self._sessions is not None else RootRunSessions(self._events)

    def _record_sessions(self, conversation: Conversation, run: Run) -> Conversation:
        rules = self._session_rules()
        try:
            found = rules.collect(run)
        except Exception:  # 세션 기록 실패가 대화 진행(대기열)을 막지 않게 한다
            _log.exception("턴 %s 세션 수집 실패", run.id)
            found = {}
        graph = self._graphs.get_graph(conversation.graph_id)
        if graph is not None:  # 실행 중에 팀 구성이 바뀌었으면 새 팀 구성 기준으로 거른다
            found = rules.prune(found, [n.id for n in graph.nodes])
        sessions = {**conversation.sessions, **found}
        updated = conversation.model_copy(
            update={"sessions": sessions, "updated_at": self._clock()}
        )
        self._conversations.save(updated)
        return updated

    async def _start_next(self, conversation: Conversation) -> None:
        """락 안에서 부른다. 맨 앞이 멈추지 않았으면 꺼내 시작한다(실패한 항목은 버리고 다음).
        턴 실행기가 없으면 꺼내지 않는다(항목은 실행기가 연결될 때까지 남는다)."""
        while self._dispatching and self._launcher is not None:
            item = self._queue.pop_next(conversation.id)
            if item is None:
                break
            try:
                await self._start(conversation, item.text)
                return
            except Exception:
                # 대기 중에 팀 구성이 지워졌거나 검증에 실패한 메시지는 버리고 다음 것을 시도한다.
                _log.exception("대기열 메시지 %s 시작 실패(버림)", item.id)
        self._notify(conversation)

    def _status(self, conversation: Conversation) -> RunStatus | None:
        handle = self._active.get(conversation.id)
        if handle is not None:
            return _open_view(handle.run).status
        if conversation.last_run_id is None or self._runs is None:
            return None
        run = self._runs.get(conversation.last_run_id)
        return run.status if run is not None else None

    def _summarize(
        self, conversation: Conversation, sizes: Mapping[str, QueueSize] | None = None
    ) -> ConversationSummary:
        """`sizes`가 없으면 이 대화의 대기열 규모를 조회한다(목록은 한 번에 조회해 넘긴다)."""
        if sizes is None:
            sizes = self._queue.counts([conversation.id])
        size = sizes.get(conversation.id)
        pending = (
            self._interactions.list(conversation_id=conversation.id, status=PENDING_STATUS)
            if self._interactions is not None
            else []
        )
        return ConversationSummary(
            id=conversation.id,
            graph_id=conversation.graph_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_run_id=conversation.last_run_id,
            last_status=self._status(conversation),
            archived=conversation.archived,
            queued=size.queued if size is not None else 0,
            held=size.held if size is not None else 0,
            pending_interactions=sum(1 for i in pending if i.status == PENDING_STATUS),
            project_id=conversation.project_id,
        )

    def _turn(self, run: Run) -> ChatTurn:
        handle = self._active.get(run.conversation_id or "")
        if handle is not None and handle.run_id == run.id:
            run = _open_view(handle.run)
        return assemble_turn(
            run,
            self._events.list(run.id) if self._events is not None else [],
            self._interactions.list(run_id=run.id) if self._interactions is not None else [],
            input_key=self.options.message_input_key,
        )

    def _notify(self, conversation: Conversation) -> None:
        if self._listener is None:
            return
        try:
            self._listener(self._summarize(conversation))
        except Exception:
            _log.exception("대화 %s 변경 알림 실패", conversation.id)
