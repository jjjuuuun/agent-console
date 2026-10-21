"""테스트·예제용 인메모리 구현(주입 프로토콜의 예제 구현이기도 하다).

실제 서버는 `agent_console_store` 저장소와 `GraphRuntime` 어댑터를 넘긴다.
"""

import asyncio
import builtins
from collections.abc import Iterable
from dataclasses import dataclass, field

from agent_console_contracts import (
    Conversation,
    Graph,
    Interaction,
    Run,
    RunEvent,
    RunStatus,
)

from ._ports import Clock, TurnStart

_TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled", "interrupted"})


class MemoryConversations:
    """`ConversationRepository` 인메모리 구현."""

    def __init__(self) -> None:
        self.items: dict[str, Conversation] = {}

    def get(self, conversation_id: str) -> Conversation | None:
        return self.items.get(conversation_id)

    def save(self, conversation: Conversation) -> None:
        self.items[conversation.id] = conversation

    def delete(self, conversation_id: str) -> bool:
        return self.items.pop(conversation_id, None) is not None

    def list(
        self,
        *,
        graph_id: str | None = None,
        archived: bool | None = None,
        project_id: str | None = None,
    ) -> builtins.list[Conversation]:
        return [
            c
            for c in self.items.values()
            if (graph_id is None or c.graph_id == graph_id)
            and (archived is None or c.archived == archived)
            and (project_id is None or c.project_id == project_id)
        ]


class MemoryRuns:
    """`RunReader` 인메모리 구현(최신 생성순). `root_run_id`로 자식 Run(손자 포함)도 거른다."""

    def __init__(self) -> None:
        self.items: dict[str, Run] = {}

    def save(self, run: Run) -> None:
        self.items[run.id] = run

    def get(self, run_id: str) -> Run | None:
        return self.items.get(run_id)

    def list(
        self,
        *,
        conversation_id: str | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]:
        runs = [
            r
            for r in self.items.values()
            if (conversation_id is None or r.conversation_id == conversation_id)
            and (root_run_id is None or r.root_run_id == root_run_id)
        ]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit] if limit is not None else runs


class MemoryEvents:
    """`EventReader` 인메모리 구현."""

    def __init__(self) -> None:
        self.items: dict[str, builtins.list[RunEvent]] = {}

    def add(self, events: Iterable[RunEvent]) -> None:
        for event in events:
            self.items.setdefault(event.run_id, []).append(event)

    def list(self, run_id: str, *, since_seq: int = 0, limit: int | None = None) -> list[RunEvent]:
        events = sorted(
            (e for e in self.items.get(run_id, []) if e.seq > since_seq), key=lambda e: e.seq
        )
        return events[:limit] if limit is not None else events


class MemoryInteractions:
    """`InteractionReader` 인메모리 구현."""

    def __init__(self) -> None:
        self.items: dict[str, Interaction] = {}

    def save(self, interaction: Interaction) -> None:
        self.items[interaction.id] = interaction

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: str | None = None,
    ) -> builtins.list[Interaction]:
        return [
            i
            for i in self.items.values()
            if (run_id is None or i.run_id == run_id)
            and (conversation_id is None or i.conversation_id == conversation_id)
            and (status is None or i.status == status)
        ]


class MemoryGraphs:
    """`GraphLookup` 인메모리 구현."""

    def __init__(self, graphs: Iterable[Graph] = ()) -> None:
        self.items: dict[str, Graph] = {g.id: g for g in graphs}

    def get_graph(self, graph_id: str) -> Graph | None:
        return self.items.get(graph_id)


@dataclass(eq=False)
class FakeTurnHandle:
    """`TurnHandle` 구현. 테스트가 `FakeLauncher.finish()`로 끝낸다."""

    current: Run
    done: asyncio.Future[Run] = field(
        default_factory=lambda: asyncio.get_running_loop().create_future()
    )

    @property
    def run_id(self) -> str:
        return self.current.id

    @property
    def run(self) -> Run:
        return self.current

    async def wait(self) -> Run:
        return await asyncio.shield(self.done)


class FakeLauncher:
    """`TurnLauncher` 가짜. 시작한 턴을 기록하고, 테스트가 상태를 바꾸거나 끝낸다.

    Args:
        runs: 시작한 Run을 저장할 곳(서비스와 같은 저장소).
        events: `finish(events=)`로 받은 이벤트를 넣을 곳.
        clock: 시각 함수.
        fail_with: 설정하면 `start_turn`이 이 예외를 낸다(검증 실패 흉내).
        run_prefix: Run id 접두(재시작 흉내로 가짜를 여럿 만들 때 id가 겹치지 않게).
    """

    def __init__(
        self,
        runs: MemoryRuns,
        events: MemoryEvents,
        *,
        clock: Clock | None = None,
        fail_with: Exception | None = None,
        run_prefix: str = "run-",
    ) -> None:
        self.runs = runs
        self.events = events
        self.clock = clock or (lambda: 0.0)
        self.fail_with = fail_with
        self.run_prefix = run_prefix
        self.started: builtins.list[TurnStart] = []
        self.handles: dict[str, FakeTurnHandle] = {}
        self.cancelled: builtins.list[tuple[str, str]] = []
        self._n = 0
        self._started_signal: asyncio.Event | None = None

    async def start_turn(self, turn: TurnStart) -> FakeTurnHandle:
        if self.fail_with is not None:
            raise self.fail_with
        self._n += 1
        now = self.clock()
        run = Run(
            id=f"{self.run_prefix}{self._n}",
            graph_id=turn.graph.id,
            graph_version="v",
            status="running",
            input=dict(turn.input),
            origin=turn.origin,
            conversation_id=turn.conversation_id,
            resumed_from=turn.resumed_from,
            project_id=turn.project_id,
            created_at=now + self._n * 1e-3,
            started_at=now,
        )
        self.runs.save(run)
        self.started.append(turn)
        handle = FakeTurnHandle(run)
        self.handles[run.id] = handle
        if self._started_signal is not None:
            self._started_signal.set()
            self._started_signal = None
        return handle

    async def wait_started(self, count: int, *, timeout: float | None = 5.0) -> FakeTurnHandle:
        """턴이 ``count``개 시작될 때까지 기다려 ``count``번째 손잡이를 돌려준다.

        대기열에서 자동으로 꺼내 시작하는 턴(``finish`` 뒤)을 잡을 때 쓴다.

        Args:
            count: 기다릴 누적 시작 수(1부터).
            timeout: 초. None이면 무제한.

        Raises:
            TimeoutError: 시간 안에 시작되지 않았을 때.
        """
        if count < 1:
            raise ValueError("count는 1 이상이어야 합니다")
        async with asyncio.timeout(timeout):
            while len(self.started) < count:
                if self._started_signal is None:
                    self._started_signal = asyncio.Event()
                await self._started_signal.wait()
        return builtins.list(self.handles.values())[count - 1]

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        handle = self.handles.get(run_id)
        if handle is None or handle.done.done():
            return False
        self.cancelled.append((run_id, reason))
        self.finish(run_id, "cancelled")
        return True

    def set_status(self, run_id: str, status: RunStatus) -> None:
        """실행 중 상태만 바꾼다(예: waiting)."""
        handle = self.handles[run_id]
        handle.current = handle.current.model_copy(update={"status": status})
        self.runs.save(handle.current)

    def finish(
        self,
        run_id: str,
        status: RunStatus = "completed",
        *,
        events: Iterable[RunEvent] = (),
    ) -> Run:
        """Run을 끝낸다(이벤트를 먼저 저장하고 손잡이를 완료)."""
        if status not in _TERMINAL:
            raise ValueError(f"끝 상태가 아닙니다: {status}")
        self.events.add(events)
        handle = self.handles[run_id]
        handle.current = handle.current.model_copy(
            update={"status": status, "ended_at": self.clock()}
        )
        self.runs.save(handle.current)
        if not handle.done.done():
            handle.done.set_result(handle.current)
        return handle.current


__all__ = [
    "FakeLauncher",
    "FakeTurnHandle",
    "MemoryConversations",
    "MemoryEvents",
    "MemoryGraphs",
    "MemoryInteractions",
    "MemoryRuns",
]
