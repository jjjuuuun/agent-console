"""agent-console-chat: 대화 서비스(design §R1.4, §R5.1, §R14.4·§R14.7).

대화 한 턴 = Run 하나. 메시지는 따로 저장하지 않고 Run 입력·`run.reply` 이벤트·상호작용에서
턴을 조립한다. 저장소·실행 엔진·상호작용 조회는 모두 프로토콜로 주입받으며(실행 연결은 선택 —
없으면 대화·대기열만 동작하고 전송은 `ChatFeatureUnavailableError`) 이 패키지는
`agent_console_contracts` 외의 Agent Console 패키지를 import하지 않는다.
"""

from ._errors import (
    ChatError,
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
from ._queue import (
    RESTART_HOLD_REASON,
    MemoryQueue,
    MemoryQueueItem,
    MemoryQueueSize,
    QueueEntry,
    QueueSize,
    QueueStore,
)
from ._service import LAUNCHER_DEPENDENCY, RUNS_DEPENDENCY, ChatOptions, ChatService
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
    "LAUNCHER_DEPENDENCY",
    "REPLY_EVENT",
    "RESTART_HOLD_REASON",
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
    "QueueEntry",
    "QueueSize",
    "QueueStore",
    "QueuedMessageNotFoundError",
    "RootRunSessions",
    "RunReader",
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
