"""agent-console-link-chat-runs: 채팅·실행 연동 모듈(design §3R.1.4 L1~L3, R5.1·R4.4·R10.7).

공개 API:
    - ``module``(``ChatRunsLink``): entry point ``agent_console.server_modules``의
      ``link-chat-runs``.
    - 포트(``ports``): 받음 ``CHAT_CONVERSATIONS``·``RUNS_STARTER``·``RUNS_READER``·``RUNS_EVENTS``
      (필수)·``INTERACTIONS_PORT``(선택), 구독 ``RUNS_EVENT``, 제공 ``CHAT_TURN_LAUNCHER``·
      ``CHAT_RUNS``·``CHAT_RUN_EVENTS``·``CHAT_INTERACTIONS``·``CHAT_TURN_SESSIONS``·
      ``RESUME_HANDLERS``.
    - HTTP 없이 쓰는 부품(``adapters``): ``RuntimeTurnLauncher``(대화 턴 = 실행 시작),
      ``ConversationResume``(대화 턴 이어 가기), ``ConversationNotifier``(실행 이벤트 → 대화 알림,
      자식 Run은 루트 대화로), ``RootInteractions``(턴 상호작용을 루트 기준으로),
      ``LineageSessions``(턴 세션 — 자식 Run 노드는 경로 키로).
"""

from __future__ import annotations

from .adapters import (
    INTERACTION_EVENT_PREFIX,
    RUN_STATE_EVENTS,
    ConversationNotifier,
    ConversationResume,
    LineageSessions,
    RootInteractions,
    RuntimeTurnLauncher,
)
from .module import MODULE_ID, WEB_ROLES, ChatRunsLink, module
from .ports import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    CHAT_TURN_SESSIONS,
    INTERACTIONS_PORT,
    RESUME_HANDLERS,
    RUNS_EVENT,
    RUNS_EVENTS,
    RUNS_READER,
    RUNS_STARTER,
    ChatLike,
    LineageRunReader,
    ResumeHandlerLike,
    RootInteractionReader,
    RunStarter,
)

__all__ = [
    "CHAT_CONVERSATIONS",
    "CHAT_INTERACTIONS",
    "CHAT_RUNS",
    "CHAT_RUN_EVENTS",
    "CHAT_TURN_LAUNCHER",
    "CHAT_TURN_SESSIONS",
    "INTERACTIONS_PORT",
    "INTERACTION_EVENT_PREFIX",
    "MODULE_ID",
    "RESUME_HANDLERS",
    "RUNS_EVENT",
    "RUNS_EVENTS",
    "RUNS_READER",
    "RUNS_STARTER",
    "RUN_STATE_EVENTS",
    "WEB_ROLES",
    "ChatLike",
    "ChatRunsLink",
    "ConversationNotifier",
    "ConversationResume",
    "LineageRunReader",
    "LineageSessions",
    "ResumeHandlerLike",
    "RootInteractionReader",
    "RootInteractions",
    "RunStarter",
    "RuntimeTurnLauncher",
    "module",
]
