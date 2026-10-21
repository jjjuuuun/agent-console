"""실행 중 상호작용(되묻기·승인·검토…)의 공개 타입(design §R14.3·§R14.5, X15).

엔진은 상호작용 종류 이름을 모른다. 종류는 `registries.interaction_kinds`
(= `extension(INTERACTION_KINDS_EXTENSION)`)에 등록된 `InteractionKind`의 디스크립터로만 다룬다.
"""

from __future__ import annotations

import builtins
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import (
    Interaction,
    InteractionKindDescriptor,
    InteractionStatus,
    Issue,
    OnTimeout,
)

INTERACTION_KINDS_EXTENSION = "interaction_kinds"
"""X15 상호작용 종류 레지스트리 이름(`registries.extension(INTERACTION_KINDS_EXTENSION)`)."""
INTERACTION_KINDS_GROUP = "agent_console.interaction_kinds"
"""X15 entry point 그룹."""

INTERACTION_CLOSED_CODE = "interaction_closed"
"""이미 닫힌 상호작용을 닫으려 할 때 저장소가 내는 예외의 `code` 값(구조적 약속)."""


class InteractionCloseReasons:
    """엔진이 쓰는 `Interaction.close_reason` 값."""

    CANCELLED = "cancelled"
    """Run 취소·노드 취소로 닫혔다."""
    TIMEOUT = "timeout"
    """응답 대기 한도를 넘었다."""
    INTERRUPTED = "interrupted"
    """서버 재시작으로 끊겼다(`recover_unfinished_runs`)."""
    NODE_FINISHED = "node_finished"
    """요청한 노드가 대기 중에 끝났다."""


class InteractionAnsweredBy:
    """엔진이 쓰는 `Interaction.answered_by` 값(응답은 `respond(by=)`가 정한다)."""

    USER = "user"
    TIMEOUT = "timeout"
    SYSTEM = "system"


@runtime_checkable
class InteractionKind(Protocol):
    """상호작용 종류(X15). 엔진·서버·웹은 `descriptor`(요청·응답 스키마, 화면 힌트)만 본다."""

    descriptor: InteractionKindDescriptor


class StaticInteractionKind:
    """디스크립터만으로 된 종류(entry point가 디스크립터 객체를 가리킬 때 감싼다)."""

    def __init__(self, descriptor: InteractionKindDescriptor) -> None:
        self.descriptor = descriptor

    def __repr__(self) -> str:
        return f"StaticInteractionKind({self.descriptor.id!r})"


def as_interaction_kind(obj: Any) -> InteractionKind:
    """로드한 객체를 `InteractionKind`로 검사한다(`load_*`의 validate).

    클래스면 인자 없이 인스턴스화하고, `InteractionKindDescriptor`(또는 같은 모양의 dict)면 감싼다.

    Raises:
        TypeError: 종류로 볼 수 없는 객체.
    """
    item = obj() if isinstance(obj, type) else obj
    if isinstance(item, InteractionKindDescriptor):
        return StaticInteractionKind(item)
    if isinstance(item, dict):
        return StaticInteractionKind(InteractionKindDescriptor.model_validate(item))
    if not isinstance(getattr(item, "descriptor", None), InteractionKindDescriptor):
        raise TypeError(f"interaction_kind가 아니다: {obj!r}")
    return item  # type: ignore[no-any-return]


class InteractionRequest(BaseModel):
    """노드(또는 노드가 넘긴 백엔드)가 사용자에게 보내는 요청 하나.

    - `response_schema`: None이면 종류 디스크립터의 기본값.
    - `timeout_seconds`·`on_timeout`: None이면 노드 grant → 실행 설정(`interaction.*`) 순.
      모두 없으면 무기한·`expire`.
    - `actor`·`node_path`: 서브에이전트 요청 귀속. 생략하면 노드의 값.
      `node_path`는 노드 경로로 시작해야 한다(`ctx.child_path(대상)`).
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    title: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
    on_timeout: OnTimeout | None = None
    actor: str | None = None
    node_path: list[str] | None = None


class InteractionOutcome(BaseModel):
    """요청 결과. 만료·취소도 예외가 아니라 결과다.

    `response`: answered면 사용자의 응답(원문, 비밀이 가려지지 않음),
    expired·cancelled면 종류 디스크립터의 `expire_response`(없으면 None).
    `reason`: 닫힌 이유(`InteractionCloseReasons`, answered면 None).
    """

    interaction_id: str
    status: Literal["answered", "expired", "cancelled"]
    response: dict[str, Any] | None = None
    reason: str | None = None


@runtime_checkable
class InteractivePort(Protocol):
    """사용자에게 요청을 열 수 있는 곳. `NodeContext`가 만족한다.

    백엔드는 받은 sink가 이 프로토콜을 만족할 때만 요청을 연다(`isinstance(sink, InteractivePort)`).
    """

    async def request_input(self, req: InteractionRequest) -> InteractionOutcome: ...


class InteractionWriter(Protocol):
    """상호작용 저장(동기). `agent_console_store`의 `InteractionRepository`가 구조적으로 만족한다.

    `close`는 `status='pending'` 조건부 갱신이어야 한다. 이미 닫혀 있으면 `code` 속성이
    `INTERACTION_CLOSED_CODE`이고 `interaction` 속성(먼저 닫은 쪽의 상태)이 있는 예외를 던진다.
    """

    def save(self, interaction: Interaction) -> bool: ...

    def get(self, interaction_id: str) -> Interaction | None: ...

    def close(
        self,
        interaction_id: str,
        *,
        status: InteractionStatus,
        closed_at: float,
        response: dict[str, Any] | None = None,
        answered_by: str | None = None,
        close_reason: str | None = None,
    ) -> Interaction: ...

    def close_pending(
        self,
        *,
        status: InteractionStatus,
        closed_at: float,
        run_id: str | None = None,
        answered_by: str | None = "system",
        close_reason: str | None = None,
    ) -> builtins.list[Interaction]: ...


class UnknownInteractionError(LookupError):
    """그런 상호작용이 없다(서버: 404)."""

    def __init__(self, run_id: str, interaction_id: str) -> None:
        super().__init__(f"Run {run_id!r}에 상호작용 {interaction_id!r}가 없습니다")
        self.run_id = run_id
        self.interaction_id = interaction_id


class InteractionClosedError(Exception):
    """이미 닫힌 상호작용에 응답했다(서버: 409 `interaction_closed`).

    `interaction`은 지금 상태(먼저 닫은 쪽, 비밀 가린 저장본)이다.
    """

    code = INTERACTION_CLOSED_CODE

    def __init__(self, interaction: Interaction) -> None:
        super().__init__(f"상호작용 {interaction.id}는 이미 {interaction.status} 상태입니다")
        self.interaction = interaction


class ResponseValidationError(ValueError):
    """응답이 그 상호작용의 `response_schema`에 맞지 않는다(서버: 422 `validation_failed`).

    `issues`의 `path`는 응답 기준 JSON Pointer.
    """

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__(f"응답 검증 실패: {len(issues)}개")
        self.issues = issues


def is_closed_error(exc: BaseException) -> bool:
    """저장소의 "이미 닫힘" 예외인지(구조적 약속: `code`·`interaction` 속성)."""
    return getattr(exc, "code", None) == INTERACTION_CLOSED_CODE and isinstance(
        getattr(exc, "interaction", None), Interaction
    )
