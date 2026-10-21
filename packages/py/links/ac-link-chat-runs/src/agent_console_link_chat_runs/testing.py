"""단독 실행·테스트용 모듈(공개).

- ``LocalRunStarter``: ``runs.starter`` 가짜(엔진 없이 Run을 만들어 저장하고, 테스트가
  ``finish``로 끝낸다). ``runs.reader``·``runs.events``는 그 저장소(``agent_console_chat.testing``의
  ``MemoryRuns``·``MemoryEvents``)다.
- ``local_runs_module``: 위 가짜로 ``runs.starter``·``runs.reader``·``runs.events``를 주는 모듈.
- ``local_chat_module``: ``chat.conversations``를 메모리 대화 서비스로 주는 모듈(실행 연결은
  시작 때 이 연동의 포트에서 읽는다 — ``mod-chat``과 같은 순서).
- ``standalone_modules``: 단독 실행 ``python -m agent_console_link_chat_runs``가 ``--with`` 없이
  붙이는 모듈(위 둘). 통합 서버에서는 ``mod-chat``·``mod-runs``가 대신한다.
"""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_console_chat import (
    ChatService,
    ChatSettingsResolver,
    ConversationListener,
    QueueStore,
)
from agent_console_chat.testing import MemoryConversations, MemoryEvents, MemoryGraphs, MemoryRuns
from agent_console_contracts import Graph, Run, RunStatus
from agent_console_modkit import Module, ModuleContext, ModuleParts
from agent_console_modkit.testing import fake_module

from .ports import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    CHAT_TURN_SESSIONS,
    RUNS_EVENTS,
    RUNS_READER,
    RUNS_STARTER,
)

LOCAL_RUNS_ID = "local-runs"
LOCAL_CHAT_ID = "local-chat"
_TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled", "interrupted"})


@dataclass
class LocalRunHandle:
    """``start_run``의 손잡이(``run_id``·``run``·``wait``)."""

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


class LocalRunStarter:
    """``runs.starter`` 가짜. 시작 인자를 기록하고 Run을 저장한다(실행하지 않는다).

    Args:
        runs: Run 저장소(``chat.runs``로도 나간다).
        events: 이벤트 저장소.
    """

    def __init__(self, runs: MemoryRuns | None = None, events: MemoryEvents | None = None) -> None:
        self.runs = runs if runs is not None else MemoryRuns()
        self.events = events if events is not None else MemoryEvents()
        self.calls: builtins.list[dict[str, Any]] = []
        self.handles: dict[str, LocalRunHandle] = {}
        self.shutdowns = 0
        self._n = 0

    async def start_run(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = "api",
        conversation_id: str | None = None,
        extra_services: Mapping[Any, Any] | None = None,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        resumed_from: str | None = None,
        project_id: str | None = None,
    ) -> LocalRunHandle:
        self._n += 1
        self.calls.append(
            {
                "graph_id": graph.id,
                "input": dict(input or {}),
                "origin": origin,
                "conversation_id": conversation_id,
                "extra_services": dict(extra_services or {}),
                "seed": seed,
                "resumed_from": resumed_from,
                "project_id": project_id,
            }
        )
        run = Run(
            id=f"run-{self._n}",
            graph_id=graph.id,
            graph_version="v",
            status="running",
            input=dict(input or {}),
            origin=origin,
            conversation_id=conversation_id,
            resumed_from=resumed_from,
            project_id=project_id,
            created_at=float(self._n),
            started_at=float(self._n),
        )
        self.runs.save(run)
        handle = LocalRunHandle(run)
        self.handles[run.id] = handle
        return handle

    def finish(self, run_id: str, status: RunStatus = "completed") -> Run:
        """Run을 끝낸다."""
        if status not in _TERMINAL:
            raise ValueError(f"끝 상태가 아닙니다: {status}")
        handle = self.handles[run_id]
        handle.current = handle.current.model_copy(update={"status": status})
        self.runs.save(handle.current)
        if not handle.done.done():
            handle.done.set_result(handle.current)
        return handle.current

    def set_status(self, run_id: str, status: RunStatus) -> None:
        """실행 중 상태만 바꾼다(예: waiting)."""
        handle = self.handles[run_id]
        handle.current = handle.current.model_copy(update={"status": status})
        self.runs.save(handle.current)

    def cancel(self, run_id: str, reason: str = "cancelled") -> bool:
        handle = self.handles.get(run_id)
        if handle is None or handle.done.done():
            return False
        self.finish(run_id, "cancelled")
        return True

    def current_run(self, run_id: str) -> Run | None:
        handle = self.handles.get(run_id)
        return handle.run if handle is not None else self.runs.get(run_id)

    async def shutdown(self) -> None:
        """실행 중 Run을 "끊김"으로 정리한다."""
        self.shutdowns += 1
        for run_id, handle in self.handles.items():
            if not handle.done.done():
                self.finish(run_id, "interrupted")


def local_runs_module(
    module_id: str = LOCAL_RUNS_ID, *, starter: LocalRunStarter | None = None
) -> Module:
    """``runs.starter``·``runs.reader``·``runs.events`` 제공 모듈(``LocalRunStarter``)."""
    found = starter if starter is not None else LocalRunStarter()

    def build(ctx: ModuleContext) -> ModuleParts:
        ctx.provide(RUNS_STARTER, found)
        ctx.provide(RUNS_READER, found.runs)
        ctx.provide(RUNS_EVENTS, found.events)
        return ModuleParts()

    return fake_module(
        module_id, kind="testing", provides=[RUNS_STARTER, RUNS_READER, RUNS_EVENTS], on_build=build
    )


def local_chat_module(
    module_id: str = LOCAL_CHAT_ID,
    *,
    graphs: builtins.list[Graph] | None = None,
    conversations: MemoryConversations | None = None,
    queue: QueueStore | None = None,
    settings: ChatSettingsResolver | None = None,
    listener: ConversationListener | None = None,
) -> Module:
    """``chat.conversations`` 제공 모듈(메모리 대화 서비스, 시작 때 실행 연결을 붙인다).

    Args:
        graphs: 팀 구성 목록.
        conversations: 대화 저장소(재시작 흉내로 여러 조립이 나눠 쓸 수 있다).
        queue: 대기열 저장소(같은 이유, 없으면 서비스 기본 메모리 대기열).
        settings: 유효 채팅 설정 해석기.
        listener: 대화 요약이 바뀔 때 부를 콜백.
    """

    def build(ctx: ModuleContext) -> ModuleParts:
        service = ChatService(
            conversations if conversations is not None else MemoryConversations(),
            MemoryGraphs(graphs or []),
            queue=queue,
            settings=settings,
            listener=listener,
        )
        ctx.provide(CHAT_CONVERSATIONS, service)

        async def start() -> None:
            service.connect(
                launcher=ctx.port(CHAT_TURN_LAUNCHER),
                runs=ctx.port(CHAT_RUNS),
                events=ctx.port(CHAT_RUN_EVENTS),
                interactions=ctx.port(CHAT_INTERACTIONS),
                sessions=ctx.port(CHAT_TURN_SESSIONS),
            )

        async def stop() -> None:
            await service.aclose()

        return ModuleParts(startup=[start], shutdown=[stop])

    return fake_module(
        module_id,
        kind="testing",
        provides=[CHAT_CONVERSATIONS],
        optional=[
            CHAT_TURN_LAUNCHER,
            CHAT_RUNS,
            CHAT_RUN_EVENTS,
            CHAT_INTERACTIONS,
            CHAT_TURN_SESSIONS,
        ],
        on_build=build,
    )


def standalone_modules() -> builtins.list[Module]:
    """단독 실행 기본 동반 모듈."""
    return [local_chat_module(), local_runs_module()]


__all__ = [
    "LOCAL_CHAT_ID",
    "LOCAL_RUNS_ID",
    "LocalRunHandle",
    "LocalRunStarter",
    "local_chat_module",
    "local_runs_module",
    "standalone_modules",
]
