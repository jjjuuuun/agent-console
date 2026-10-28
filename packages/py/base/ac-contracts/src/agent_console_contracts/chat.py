"""채팅 계약: 대화·턴·메시지(design §R1.4, §R5.1).

대화 한 턴 = Run 하나. 메시지 목록은 따로 저장하지 않고 Run 입력과 `run.reply` 이벤트에서 만든다.

1.2.0(0.12.1, design §PI.4.6.4·.5): 이어 가기 상태 `SessionStatus`·`ConversationSessions`
(`KnownSessionStates`), 전송 요청 `on_missing_session`, 대기열 `QueuedMessage.held_reason`
(`KnownQueueHoldReasons`).
"""

from typing import Final, Literal

from pydantic import Field

from ._base import ContractModel, JsonObject, NonEmptyStr
from .common import Usage
from .runs import Interaction, RunStatus


class SessionRef(ContractModel):
    """백엔드 세션 참조(다음 턴 이어 쓰기)."""

    backend: NonEmptyStr
    session_id: NonEmptyStr
    data: JsonObject = Field(default_factory=dict)


class Conversation(ContractModel):
    """대화. 팀 구성 하나를 골라 이어 가는 채팅."""

    id: NonEmptyStr
    graph_id: NonEmptyStr = Field(description="고른 팀 구성(그래프) id.")
    title: str = ""
    created_at: float
    updated_at: float
    last_run_id: str | None = None
    sessions: dict[str, SessionRef] = Field(
        default_factory=dict, description="노드 id → 백엔드 세션(이어 쓰기)."
    )
    archived: bool = False
    project_id: str | None = Field(
        default=None,
        description="프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음.",
    )


class ConversationSummary(ContractModel):
    """`GET /conversations` 목록 항목, WS `conversation.updated` 내용.

    목록 질의 `?project=`(0.8.0)는 같은 `project_id`인 대화만 준다.
    """

    id: NonEmptyStr
    graph_id: NonEmptyStr
    title: str = ""
    created_at: float
    updated_at: float
    last_run_id: str | None = None
    last_status: RunStatus | None = Field(default=None, description="마지막 턴 Run 상태.")
    archived: bool = False
    queued: int = Field(default=0, ge=0, description="대기열에 있는 메시지 수.")
    held: int = Field(
        default=0, ge=0, description="대기열 중 재시작으로 멈춘(held) 메시지 수(queued에 포함)."
    )
    pending_interactions: int = Field(
        default=0, ge=0, description="응답을 기다리는 상호작용 수(대화 목록·사이드바 배지)."
    )
    project_id: str | None = Field(
        default=None,
        description="프로젝트 id(0.8.0, 불투명 문자열). null = 프로젝트 없음.",
    )


class CreateConversationRequest(ContractModel):
    """`POST /conversations` 요청. 응답은 `Conversation`(201)."""

    graph_id: NonEmptyStr
    title: str | None = None
    project_id: str | None = Field(
        default=None,
        description="대화의 프로젝트 id(0.8.0, 웹의 현재 프로젝트). 생략 = 프로젝트 없음.",
    )


class UpdateConversationRequest(ContractModel):
    """`PATCH /conversations/{id}` 요청. 생략한 필드는 그대로 둔다."""

    title: str | None = None
    archived: bool | None = None
    graph_id: str | None = Field(
        default=None,
        min_length=1,
        description="팀 구성 전환. 새 팀 구성에 없는 노드의 세션은 버린다.",
    )


type MissingSessionPolicy = Literal["fail", "fresh"]
"""세션 기록이 없는 노드를 만났을 때: fail = 409 `chat.session_unavailable`, fresh = 그 노드만 맥락
없이 새 세션으로 시작(턴에 안내가 붙는다)."""


class PostMessageRequest(ContractModel):
    """`POST /conversations/{id}/messages` 요청. 응답은 `Run`(202) 또는 `QueuedMessage`(202)."""

    text: str
    on_missing_session: MissingSessionPolicy = Field(
        default="fail",
        description=(
            "이 앱에 이어 갈 세션 기록이 없는 노드가 있을 때(0.12.1). fail = 409 "
            "`chat.session_unavailable`, fresh = 그 노드는 새 세션으로 시작."
        ),
    )


class QueuedMessage(ContractModel):
    """실행 중이라 대기열에 넣은 메시지(`chat.busy_policy = queue`)."""

    queued: Literal[True] = True
    id: str | None = Field(
        default=None,
        description="대기열 항목 id. 취소: DELETE /conversations/{id}/queue/{queued_id}.",
    )
    position: int = Field(ge=1, description="대기열 순번(1 = 다음 차례).")
    text: str | None = Field(default=None, description="대기 중인 메시지 본문(목록 표시용).")
    held: bool = Field(
        default=False,
        description="재시작으로 멈춘 항목(`chat.queue_after_restart = ask`). 실행·취소를 고른다.",
    )
    held_reason: str | None = Field(
        default=None,
        description=(
            "멈춘 이유(0.12.1, `KnownQueueHoldReasons`, 열린 문자열). held가 아니면 null."
        ),
    )


class KnownQueueHoldReasons:
    """`QueuedMessage.held_reason`의 알려진 값. **문서 상수**다.

    이름 → 값 표를 스키마 `x-constants.KNOWN_QUEUE_HOLD_REASONS`로 내보낸다.
    """

    RESTART: Final = "restart"
    """서버 재시작으로 멈춤(`chat.queue_after_restart = ask`)."""
    OTHER_HOST: Final = "other_host"
    """다른 앱(`host_id`)이 넣은 항목이라 이 앱이 자동으로 꺼내지 않는다(design §PI.4.6.5)."""


class KnownSessionStates:
    """`SessionStatus.state`의 알려진 값(design §PI.4.6.4, 0.12.1). **문서 상수**다.

    이름 → 값 표를 스키마 `x-constants.KNOWN_SESSION_STATES`로 내보낸다. 화면은 이 값으로
    분기하지 않고 `ConversationSessions.continuable`로 배너·전송 선택을 정한다.
    """

    AVAILABLE: Final = "available"
    """이 앱 자격 폴더의 지금 위치에 세션 기록이 있다."""
    RELOCATABLE: Final = "relocatable"
    """이 앱 자격 폴더의 옛 위치(경로 다시 지정 전)에 있다. 이어 가기 직전에 옮겨 놓는다."""
    ARCHIVED: Final = "archived"
    """프로젝트 폴더의 세션 기록 보관 사본에 있다. 이어 가기 직전에 이 앱으로 복원한다."""
    MISSING: Final = "missing"
    """어디에도 없다(보관 끔·git 클론·옛 대화). 보내면 409 `chat.session_unavailable`."""
    NOT_APPLICABLE: Final = "not_applicable"
    """백엔드가 이어 가기를 모른다(상태와 무관하게 보낼 수 있다)."""


class SessionStatus(ContractModel):
    """대화 노드 하나의 백엔드 세션 이어 가기 상태."""

    node_id: NonEmptyStr
    backend: NonEmptyStr = Field(description="백엔드 id.")
    session_id: str | None = Field(default=None, description="백엔드 세션 id(있으면).")
    state: str = Field(description="이어 가기 상태(`KnownSessionStates`, 열린 문자열).")


class ConversationSessions(ContractModel):
    """`GET /conversations/{id}/sessions` 응답(0.12.1)."""

    conversation_id: NonEmptyStr
    continuable: bool = Field(
        description=(
            "그대로 이어 갈 수 있는가(missing인 항목이 없음). false면 화면은 배너와 [새 세션으로 "
            "계속]·[새 대화]를 보인다."
        )
    )
    items: list[SessionStatus] = Field(default_factory=list)


class ChatReply(ContractModel):
    """턴의 답변 하나(`run.reply` 이벤트에서 만든다)."""

    edge_id: NonEmptyStr
    node_id: NonEmptyStr
    agent_id: str | None = None
    label: str | None = None
    order: int | None = None
    final: bool = True
    text: str


class ChatTurn(ContractModel):
    """`GET /conversations/{id}/turns` 항목. 대화 한 턴 = Run 하나."""

    run_id: NonEmptyStr
    user_text: str
    replies: list[ChatReply] = Field(default_factory=list)
    interactions: list[Interaction] = Field(
        default_factory=list, description="이 턴에서 열린 상호작용(대기·닫힘 모두)."
    )
    status: RunStatus = Field(
        description="턴 Run 상태(RunStatus 어휘: queued·running·waiting·completed·failed 등)."
    )
    usage: Usage | None = None
    started_at: float | None = None
    ended_at: float | None = None
    resumed_from: str | None = Field(
        default=None, description="끊긴 턴을 이어 간 턴이면 원래 Run id."
    )


__all__ = [
    "ChatReply",
    "ChatTurn",
    "Conversation",
    "ConversationSessions",
    "ConversationSummary",
    "CreateConversationRequest",
    "KnownQueueHoldReasons",
    "KnownSessionStates",
    "MissingSessionPolicy",
    "PostMessageRequest",
    "QueuedMessage",
    "SessionRef",
    "SessionStatus",
    "UpdateConversationRequest",
]
