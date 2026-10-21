"""mod-chat의 공개 포트·토픽(이름 = 포트, design §3R.1.2·§3R.1.3·§3R.1.5).

다른 모듈은 이 파일을 import하지 않고 같은 이름을 자기 ``ports``에 선언해 연결한다. 포트 타입은
소비자 쪽 라이브러리(``agent_console_chat``)의 프로토콜이다.

제공:

- ``chat.conversations``: 대화 서비스(``agent_console_chat.ChatService`` — 대화·대기열·턴 조립,
  ``notify``·``resume_turn``·``apply_restart_policy``·``stop_dispatch``).
- ``server.warnings``(여러 제공자): 대화 기록 저장소가 메모리일 때 ``chat.storage_memory``.
- 토픽 ``conversations.updated``(``ConversationSummary``): 대화 요약이 바뀔 때마다.

받음(모두 선택 — 없으면 그 부분만 꺼진다):

- ``chat.turn_launcher``: 턴 시작·취소(``TurnLauncher``). 없으면 메시지 전송·이어 가기가 409
  ``feature_unavailable``이고 대기열은 꺼내지 않고 남긴다.
- ``chat.runs``: 턴 Run 조회(``RunReader``). 없으면 턴 목록이 비고 마지막 상태는 null.
- ``chat.run_events``: 턴 이벤트 조회(``EventReader``). 없으면 답변·세션을 읽지 않는다.
- ``chat.interactions``: 턴 상호작용 조회(``InteractionReader``). 없으면 대기 수 0.
- ``chat.turn_sessions``: 턴 세션 수집·정리 규칙(``TurnSessions``). 없으면 기본 규칙(턴 Run 자기
  노드만, 키 = 노드 id) — 중첩 팀 자식 노드 세션은 이어 쓰지 않는다.
- ``definitions.lookup``: 팀 구성 읽기(``get(kind, id).document``). 없으면 대화 만들기·팀 구성
  바꾸기가 409 ``feature_unavailable``(목록·기록은 동작).
- ``workspace.settings``: 공통 설정(``chat.*``). 없으면 스키마 기본값.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from agent_console_chat import (
    ChatService,
    EventReader,
    InteractionReader,
    RunReader,
    TurnLauncher,
    TurnSessions,
)
from agent_console_contracts import ConversationSummary, Issue, WorkspaceSettings
from agent_console_modkit import PortKey, Topic


class StoredLike(Protocol):
    """정의 원문 하나(``agent_console_store.StoredDefinition``이 만족)."""

    @property
    def document(self) -> Mapping[str, Any]: ...


class DefinitionLookup(Protocol):
    """정의 읽기(``definitions.lookup``). 없으면 저장소 예외를 낸다."""

    def get(self, kind: str, id: str) -> StoredLike: ...


type WorkspaceSettingsReader = Callable[[], WorkspaceSettings]
"""``workspace.settings`` 포트 모양."""

type WarningSource = Callable[[], Sequence[Issue]]
"""``server.warnings`` 포트 모양."""

CHAT_CONVERSATIONS: PortKey[ChatService] = PortKey("chat.conversations", "대화 서비스")
SERVER_WARNINGS: PortKey[WarningSource] = PortKey("server.warnings", "서버 정보 경고", multi=True)
CHAT_TURN_LAUNCHER: PortKey[TurnLauncher] = PortKey("chat.turn_launcher", "턴 시작·취소")
CHAT_RUNS: PortKey[RunReader] = PortKey("chat.runs", "턴 Run 조회")
CHAT_RUN_EVENTS: PortKey[EventReader] = PortKey("chat.run_events", "턴 이벤트 조회")
CHAT_INTERACTIONS: PortKey[InteractionReader] = PortKey("chat.interactions", "턴 상호작용 조회")
CHAT_TURN_SESSIONS: PortKey[TurnSessions] = PortKey("chat.turn_sessions", "턴 세션 수집·정리 규칙")
DEFINITIONS_LOOKUP: PortKey[DefinitionLookup] = PortKey("definitions.lookup", "정의 읽기")
WORKSPACE_SETTINGS: PortKey[WorkspaceSettingsReader] = PortKey(
    "workspace.settings", "지금 워크스페이스 설정"
)

CONVERSATIONS_UPDATED: Topic[ConversationSummary] = Topic("conversations.updated")
"""대화 요약이 바뀔 때(새 턴·제목·상태·대기열·대기 상호작용 수)."""

__all__ = [
    "CHAT_CONVERSATIONS",
    "CHAT_INTERACTIONS",
    "CHAT_RUNS",
    "CHAT_RUN_EVENTS",
    "CHAT_TURN_LAUNCHER",
    "CHAT_TURN_SESSIONS",
    "CONVERSATIONS_UPDATED",
    "DEFINITIONS_LOOKUP",
    "SERVER_WARNINGS",
    "WORKSPACE_SETTINGS",
    "DefinitionLookup",
    "StoredLike",
    "WarningSource",
    "WorkspaceSettingsReader",
]
