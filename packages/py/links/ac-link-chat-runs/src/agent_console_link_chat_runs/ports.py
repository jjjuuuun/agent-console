"""link-chat-runs의 포트(이름 = 포트, design §3R.1.2·§3R.1.4 L1~L3).

받음(소비자 쪽 프로토콜 — 제공 모듈을 import하지 않는다):

- 필수 ``chat.conversations``: 대화 서비스(``ChatLike`` — ``agent_console_chat.ChatService``가
  만족).
- 필수 ``runs.starter``: 실행 시작·취소·조회·종료(``RunStarter``).
- 필수 ``runs.reader``: Run 조회(``LineageRunReader`` — ``agent_console_chat.RunReader`` +
  ``root_run_id`` 조회, 턴의 자식 Run 세션을 모을 때 쓴다).
- 필수 ``runs.events``: 실행 이벤트 조회(``agent_console_chat.EventReader``).
- 선택 ``interactions.port``: 상호작용 조회(``RootInteractionReader`` — ``root_run_id`` 조회 포함).
  없으면 ``chat.interactions``를 주지 않는다(대화의 대기 수 0, 턴의 상호작용 없음).
- 토픽 ``runs.event``(구독): 상호작용·대기 상태가 바뀐 대화 턴이면 대화 요약을 다시 알린다.

제공:

- ``chat.turn_launcher``: 대화 턴 = ``runs.starter.start_run(conversation_id=...)``
  (``RuntimeTurnLauncher``).
- ``chat.runs``·``chat.run_events``: 받은 실행 포트 그대로. ``chat.interactions``: 루트 기준
  상호작용(``RootInteractions`` — 턴 = 루트 Run과 자식 Run의 요청). ``chat.turn_sessions``: 턴
  세션 규칙(``LineageSessions`` — 자식 Run 노드 세션을 경로 키로, design §5R.7).
- ``runs.resume_handlers``(여러 제공자): 대화 턴 이어 가기(``ConversationResume`` →
  ``resume_turn``).
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from agent_console_chat import (
    EventReader,
    InteractionReader,
    RunReader,
    TurnHandle,
    TurnLauncher,
    TurnSessions,
)
from agent_console_contracts import Graph, Interaction, Run, RunEvent
from agent_console_modkit import PortKey, Topic
from agent_console_runtime import ResumeStart


@runtime_checkable
class ChatLike(Protocol):
    """``chat.conversations``에서 이 연동이 쓰는 부분."""

    def notify(self, conversation_id: str) -> None: ...

    async def resume_turn(
        self, run_id: str, *, graph: Graph, seed: Mapping[str, Mapping[str, Any]]
    ) -> Run: ...

    async def apply_restart_policy(self) -> Mapping[str, str]: ...

    def stop_dispatch(self) -> None: ...


@runtime_checkable
class RunStarter(Protocol):
    """``runs.starter``에서 이 연동이 쓰는 부분(``mod-runs`` ``RunService``가 만족)."""

    async def start_run(
        self,
        graph: Graph,
        input: Mapping[str, Any] | None = None,
        *,
        origin: str = ...,
        conversation_id: str | None = None,
        extra_services: Mapping[Any, Any] | None = None,
        seed: Mapping[str, Mapping[str, Any]] | None = None,
        resumed_from: str | None = None,
        project_id: str | None = None,
    ) -> TurnHandle: ...

    def cancel(self, run_id: str, reason: str = ...) -> bool: ...

    def current_run(self, run_id: str) -> Run | None: ...

    async def shutdown(self) -> None: ...


class LineageRunReader(RunReader, Protocol):
    """``runs.reader``에서 이 연동이 쓰는 부분(저장소 Run 리포지토리가 만족).

    ``root_run_id`` = 그 루트 Run 아래 모든 자식 Run(손자 포함, 루트 자신은 빠짐).
    """

    def list(
        self,
        *,
        conversation_id: str | None = None,
        root_run_id: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Run]: ...


class RootInteractionReader(Protocol):
    """``interactions.port``에서 이 연동이 쓰는 부분(``mod-runs`` ``InteractionService``가 만족).

    ``root_run_id`` = 그 Run과 아래 모든 자식 Run의 상호작용(design §5R.10).
    """

    def list(
        self,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
        status: Any = None,
        root_run_id: str | None = None,
    ) -> builtins.list[Interaction]: ...


@runtime_checkable
class ResumeHandlerLike(Protocol):
    """``runs.resume_handlers`` 항목 모양(``mod-runs`` ``ResumeHandler``와 같다)."""

    def accepts(self, run: Run) -> bool: ...

    async def resume(self, request: ResumeStart) -> Run: ...


CHAT_CONVERSATIONS: PortKey[ChatLike] = PortKey("chat.conversations", "대화 서비스")
RUNS_STARTER: PortKey[RunStarter] = PortKey("runs.starter", "실행 시작·검증·취소")
RUNS_READER: PortKey[LineageRunReader] = PortKey("runs.reader", "Run·NodeRun 조회")
RUNS_EVENTS: PortKey[EventReader] = PortKey("runs.events", "실행 이벤트 조회")
INTERACTIONS_PORT: PortKey[RootInteractionReader] = PortKey(
    "interactions.port", "상호작용 조회·응답"
)

CHAT_TURN_LAUNCHER: PortKey[TurnLauncher] = PortKey("chat.turn_launcher", "턴 시작·취소")
CHAT_RUNS: PortKey[RunReader] = PortKey("chat.runs", "턴 Run 조회")
CHAT_RUN_EVENTS: PortKey[EventReader] = PortKey("chat.run_events", "턴 이벤트 조회")
CHAT_INTERACTIONS: PortKey[InteractionReader] = PortKey("chat.interactions", "턴 상호작용 조회")
CHAT_TURN_SESSIONS: PortKey[TurnSessions] = PortKey("chat.turn_sessions", "턴 세션 수집·정리 규칙")
RESUME_HANDLERS: PortKey[ResumeHandlerLike] = PortKey(
    "runs.resume_handlers", "이어 가기 처리기", multi=True
)

RUNS_EVENT: Topic[RunEvent] = Topic("runs.event")
"""저장이 끝난 실행 이벤트(전부)."""

__all__ = [
    "CHAT_CONVERSATIONS",
    "CHAT_INTERACTIONS",
    "CHAT_RUNS",
    "CHAT_RUN_EVENTS",
    "CHAT_TURN_LAUNCHER",
    "CHAT_TURN_SESSIONS",
    "INTERACTIONS_PORT",
    "RESUME_HANDLERS",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "RUNS_STARTER",
    "ChatLike",
    "LineageRunReader",
    "ResumeHandlerLike",
    "RootInteractionReader",
    "RunStarter",
]
