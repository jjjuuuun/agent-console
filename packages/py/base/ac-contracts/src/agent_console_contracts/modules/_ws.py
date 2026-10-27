"""WebSocket 메시지(design §5.3). 단일 소켓 `/ws`, 메시지 = `{type, id?, payload}`.

`id`는 클라이언트가 붙이는 요청 상관 id(선택)이며,
서버는 그 요청에 대한 `error`에 같은 `id`를 붙인다.
"""

from typing import Annotated, Literal

from pydantic import Field, RootModel

from agent_console_contracts._base import ContractModel, NonEmptyStr
from agent_console_contracts.chat import ConversationSummary
from agent_console_contracts.common import ErrorInfo
from agent_console_contracts.memory import MemoryChanged
from agent_console_contracts.runs import Interaction, RunEvent


class WsMessageBase(ContractModel):
    id: str | None = Field(default=None, description="요청 상관 id(선택).")


# ---------------------------------------------------------------- client → server


class SubscribePayload(ContractModel):
    topic: NonEmptyStr = Field(
        description=(
            "토픽 이름. 켜진 서버 모듈이 정한다(`ModuleParts.ws_topics`). 기본 모듈: "
            '"run:<id>" | "conversation:<id>" | "interactions" | "logs". 모르는 토픽은 `error`.'
        )
    )
    since_seq: int | None = Field(
        default=None, ge=0, description="이 seq 다음부터 저장소에서 재생한 뒤 실시간으로 전환."
    )


class SubscribeMessage(WsMessageBase):
    type: Literal["subscribe"]
    payload: SubscribePayload


class UnsubscribePayload(ContractModel):
    topic: NonEmptyStr


class UnsubscribeMessage(WsMessageBase):
    type: Literal["unsubscribe"]
    payload: UnsubscribePayload


class WsClientMessage(
    RootModel[
        Annotated[
            SubscribeMessage | UnsubscribeMessage,
            Field(discriminator="type"),
        ]
    ]
):
    """클라이언트 → 서버 메시지 유니온."""


# ---------------------------------------------------------------- server → client


class RunEventMessage(WsMessageBase):
    type: Literal["run.event"]
    payload: RunEvent


class ErrorMessage(WsMessageBase):
    type: Literal["error"]
    payload: ErrorInfo


class ConversationUpdatedPayload(ContractModel):
    """토픽 `conversation:<id>`: 새 턴·제목·상태·대기 중 상호작용 수가 바뀜."""

    conversation: ConversationSummary


class ConversationUpdatedMessage(WsMessageBase):
    type: Literal["conversation.updated"]
    payload: ConversationUpdatedPayload


class InteractionUpdatedPayload(ContractModel):
    """토픽 `interactions`: 구독 직후 현재 대기 목록을 하나씩 보낸 뒤, 상태가 바뀔 때마다 보낸다."""

    interaction: Interaction


class InteractionUpdatedMessage(WsMessageBase):
    type: Literal["interaction.updated"]
    payload: InteractionUpdatedPayload


class LogsIngestedPayload(ContractModel):
    """토픽 `logs`: 로그 수집으로 새 이벤트가 색인됨.

    목록 화면은 `max_seq`보다 큰 이벤트를 다시 불러온다.
    """

    source_ids: list[str] = Field(default_factory=list, description="새 이벤트가 생긴 출처 id.")
    count: int = Field(ge=0, description="새로 색인한 이벤트 수.")
    max_seq: int | None = Field(default=None, ge=0, description="지금 색인의 최대 seq.")


class LogsIngestedMessage(WsMessageBase):
    type: Literal["logs.ingested"]
    payload: LogsIngestedPayload


class MemoryChangedMessage(WsMessageBase):
    """메모리 모듈 토픽: 항목 하나가 바뀜(본문 없음, 1.3.0). 토픽 이름은 메모리 모듈이 정한다."""

    type: Literal["memory.changed"]
    payload: MemoryChanged


class WsServerMessage(
    RootModel[
        Annotated[
            RunEventMessage
            | ConversationUpdatedMessage
            | InteractionUpdatedMessage
            | LogsIngestedMessage
            | MemoryChangedMessage
            | ErrorMessage,
            Field(discriminator="type"),
        ]
    ]
):
    """서버 → 클라이언트 메시지 유니온."""
