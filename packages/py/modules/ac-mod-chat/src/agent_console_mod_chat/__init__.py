"""agent-console-mod-chat: 채팅 기능 모듈(design §3R.1.3, R5.1·R10.7).

대화 서비스(``ac-chat``)를 서버에 꽂는다. 대화·턴·메시지·대기열 경로와 WS ``conversation:<id>``를
맡고, 턴 실행·Run 조회·상호작용은 선택 포트로 받는다(없으면 대화·대기열은 동작하고 전송만 409
``feature_unavailable``).

공개 API:
    - ``module``(``ChatModule``): entry point ``agent_console.server_modules``의 ``mod-chat``.
    - 포트·토픽(``ports``): 제공 ``CHAT_CONVERSATIONS``·``SERVER_WARNINGS``, 토픽
      ``CONVERSATIONS_UPDATED``. 받음(선택) ``CHAT_TURN_LAUNCHER``·``CHAT_RUNS``·
      ``CHAT_RUN_EVENTS``·``CHAT_INTERACTIONS``·``CHAT_TURN_SESSIONS``·``DEFINITIONS_LOOKUP``·
      ``WORKSPACE_SETTINGS``.
    - HTTP 없이 쓰는 부품: ``PortGraphLookup``(정의 읽기 → 팀 구성 조회), ``open_chat_storage``.
    - ``build_router``·``topic_handlers``·``error_map``.
"""

from __future__ import annotations

from .errors import DEPENDENCY_PORTS, error_map
from .graphs import PortGraphLookup
from .module import MODULE_ID, WEB_ROLES, ChatModule, module
from .ports import (
    CHAT_CONVERSATIONS,
    CHAT_INTERACTIONS,
    CHAT_RUN_EVENTS,
    CHAT_RUNS,
    CHAT_TURN_LAUNCHER,
    CHAT_TURN_SESSIONS,
    CONVERSATIONS_UPDATED,
    DEFINITIONS_LOOKUP,
    SERVER_WARNINGS,
    WORKSPACE_SETTINGS,
    DefinitionLookup,
)
from .routes import build_router
from .storage import STORAGE_MEMORY, ChatStorage, open_chat_storage
from .ws import CONVERSATION_TOPIC, topic_handlers

__all__ = [
    "CHAT_CONVERSATIONS",
    "CHAT_INTERACTIONS",
    "CHAT_RUNS",
    "CHAT_RUN_EVENTS",
    "CHAT_TURN_LAUNCHER",
    "CHAT_TURN_SESSIONS",
    "CONVERSATIONS_UPDATED",
    "CONVERSATION_TOPIC",
    "DEFINITIONS_LOOKUP",
    "DEPENDENCY_PORTS",
    "MODULE_ID",
    "SERVER_WARNINGS",
    "STORAGE_MEMORY",
    "WEB_ROLES",
    "WORKSPACE_SETTINGS",
    "ChatModule",
    "ChatStorage",
    "DefinitionLookup",
    "PortGraphLookup",
    "build_router",
    "error_map",
    "module",
    "open_chat_storage",
    "topic_handlers",
]
