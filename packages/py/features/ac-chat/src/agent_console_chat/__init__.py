"""agent-console-chat: 대화 서비스(design §R1.4, §R5.1, §R14.4·§R14.7).

대화 한 턴 = Run 하나. 메시지는 따로 저장하지 않고 Run 입력·`run.reply` 이벤트·상호작용에서
턴을 조립한다. 저장소·실행 엔진·상호작용 조회는 모두 프로토콜로 주입받으며(실행 연결은 선택 —
없으면 대화·대기열만 동작하고 전송은 `ChatFeatureUnavailableError`) 이 패키지는
`agent_console_contracts` 외의 Agent Console 패키지를 import하지 않는다.

세션 이어 가기(5.7R.33y3, design §PI.4.6.4): 선택 연결 `SessionContinuity`(`state`·`prepare`)를
주면 `ChatService.session_states`가 노드별 상태를 보이고, 보내기 전에 기록이 없는 노드를
`SessionUnavailableError`(409 `chat.session_unavailable`) 또는 `on_missing_session: "fresh"`로
처리하며, 보관 사본에서 복원한 노드는 `TurnStart.session_notes`(`FRESH_SESSION_NOTE` 등)로 알린다.
"""

from ._errors import (
    ChatError,
    ChatFeatureUnavailableError,
    ConversationBusyError,
    ConversationNotFoundError,
    GraphNotFoundError,
    InvalidMessageError,
    QueuedMessageNotFoundError,
    SessionUnavailableError,
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
    ProjectGraphLookup,
    RunReader,
    SessionContinuity,
    TurnHandle,
    TurnLauncher,
    TurnSessions,
    TurnStart,
)
from ._queue import (
    RESTART_HOLD_REASON,
    MemoryQueue,
    MemoryQueueItem,
    MemoryQueueSize,
    QueueEntry,
    QueueSize,
    QueueStore,
)
from ._service import (
    FRESH_SESSION_NOTE,
    LAUNCHER_DEPENDENCY,
    RESTORED_STATES,
    RUNS_DEPENDENCY,
    ChatOptions,
    ChatService,
)
from ._settings import layered_chat_settings, overlay_chat_settings
from ._turns import (
    REPLY_EVENT,
    SESSION_EVENT,
    RootRunSessions,
    assemble_turn,
    first_message_title,
    message_text,
    prune_sessions,
    replies_from_events,
    sessions_from_events,
)

__all__ = [
    "FRESH_SESSION_NOTE",
    "LAUNCHER_DEPENDENCY",
    "REPLY_EVENT",
    "RESTART_HOLD_REASON",
    "RESTORED_STATES",
    "RUNS_DEPENDENCY",
    "SESSION_EVENT",
    "ChatError",
    "ChatFeatureUnavailableError",
    "ChatOptions",
    "ChatService",
    "ChatSettingsResolver",
    "Clock",
    "ConversationBusyError",
    "ConversationListener",
    "ConversationNotFoundError",
    "ConversationRepository",
    "EventReader",
    "GraphLookup",
    "GraphNotFoundError",
    "IdFactory",
    "InteractionReader",
    "InvalidMessageError",
    "MemoryQueue",
    "MemoryQueueItem",
    "MemoryQueueSize",
    "ProjectGraphLookup",
    "QueueEntry",
    "QueueSize",
    "QueueStore",
    "QueuedMessageNotFoundError",
    "RootRunSessions",
    "RunReader",
    "SessionContinuity",
    "SessionUnavailableError",
    "TurnHandle",
    "TurnLauncher",
    "TurnNotFoundError",
    "TurnNotResumableError",
    "TurnSessions",
    "TurnStart",
    "assemble_turn",
    "first_message_title",
    "layered_chat_settings",
    "message_text",
    "overlay_chat_settings",
    "prune_sessions",
    "replies_from_events",
    "sessions_from_events",
]
