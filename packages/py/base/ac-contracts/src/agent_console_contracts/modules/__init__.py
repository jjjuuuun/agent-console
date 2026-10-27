"""계약 하위 모듈 `modules`: 호스트·모듈 조립 계약과 WebSocket 메시지.

`ModuleInfo`(GET /modules), 준비 신호·서버 정보, `feature_unavailable` 상세, `/ws` 메시지.
맨 위 층이라 다른 하위 모듈을 모두 쓸 수 있다. 설계: design §3R.1.8, §5.3.
"""

from ._host import (
    BootstrapResponse,
    FeatureUnavailableDetails,
    HealthResponse,
    ModuleInfo,
    ModuleOptionsView,
    ModuleStatus,
    PluginInfo,
    ServerInfo,
)
from ._ws import (
    ConversationUpdatedMessage,
    ConversationUpdatedPayload,
    ErrorMessage,
    InteractionUpdatedMessage,
    InteractionUpdatedPayload,
    LogsIngestedMessage,
    LogsIngestedPayload,
    MemoryChangedMessage,
    RunEventMessage,
    SubscribeMessage,
    SubscribePayload,
    UnsubscribeMessage,
    UnsubscribePayload,
    WsClientMessage,
    WsServerMessage,
)

__all__ = [
    "BootstrapResponse",
    "ConversationUpdatedMessage",
    "ConversationUpdatedPayload",
    "ErrorMessage",
    "FeatureUnavailableDetails",
    "HealthResponse",
    "InteractionUpdatedMessage",
    "InteractionUpdatedPayload",
    "LogsIngestedMessage",
    "LogsIngestedPayload",
    "MemoryChangedMessage",
    "ModuleInfo",
    "ModuleOptionsView",
    "ModuleStatus",
    "PluginInfo",
    "RunEventMessage",
    "ServerInfo",
    "SubscribeMessage",
    "SubscribePayload",
    "UnsubscribeMessage",
    "UnsubscribePayload",
    "WsClientMessage",
    "WsServerMessage",
]
