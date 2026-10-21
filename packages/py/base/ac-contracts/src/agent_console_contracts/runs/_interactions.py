"""실행 중 상호작용(되묻기·도구 승인·사용자 중간 검토…, design §R14).

상호작용 = 실행 중 노드 하나가 사용자에게 보낸 요청 하나와 그 응답. 종류(`kind`)는 X15
디스크립터의 id(임의 문자열)이며 계약은 종류 목록을 모른다. 알려진 종류 id는 문서 상수
`KnownInteractionKinds`에만 있다.
"""

from typing import Literal

from pydantic import Field

from agent_console_contracts._base import ContractModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import UiHints, x_ui
from agent_console_contracts.definitions import OnTimeout

type InteractionStatus = Literal["pending", "answered", "expired", "cancelled"]
"""상호작용 상태(고정 어휘). pending만 열린 상태이고 나머지는 닫힌 상태다."""

INTERACTION_CLOSED_STATUSES: tuple[str, ...] = ("answered", "expired", "cancelled")
"""닫힌 상태 목록. 닫힌 상호작용에는 다시 응답할 수 없다(`interaction_closed`)."""


class Interaction(ContractModel):
    """상호작용 하나. payload·response는 저장 전에 비밀이 가려진 값이다."""

    id: NonEmptyStr
    run_id: NonEmptyStr
    root_run_id: str | None = Field(
        default=None,
        description=(
            "자식 Run(중첩 팀) 안의 요청이면 맨 위 Run id(0.7.0). 응답 대기 목록은 "
            "`root_run_id or run_id` 기준으로 모은다."
        ),
    )
    conversation_id: str | None = None
    node_id: NonEmptyStr
    node_label: str | None = Field(
        default=None,
        description="요청 시점의 노드 표시 이름(표시용, 없으면 node_id를 보인다).",
    )
    node_path: list[str] = Field(
        default_factory=list,
        description="요청한 노드 경로. 서브에이전트 요청이면 [위임자 노드, 대상 노드].",
    )
    attempt: int = Field(default=1, ge=1)
    actor: str | None = Field(default=None, description="요청한 에이전트 정의 id.")
    kind: NonEmptyStr = Field(description="상호작용 종류 id(X15 디스크립터, 고정 목록 아님).")
    status: InteractionStatus
    title: str = ""
    message: str = ""
    payload: JsonObject = Field(default_factory=dict, description="종류의 request_schema 형식.")
    response_schema: JsonObject = Field(
        default_factory=dict, description="이 요청의 응답 JSON Schema(응답 검증 기준)."
    )
    response: JsonObject | None = None
    answered_by: str | None = Field(
        default=None, description="닫은 주체. 알려진 값: user, timeout, system."
    )
    close_reason: str | None = Field(
        default=None,
        description="닫힌 이유. 알려진 값: cancelled, timeout, interrupted, node_finished.",
    )
    created_at: float = Field(description="Unix epoch 초.")
    expires_at: float | None = None
    closed_at: float | None = None


class InteractionGrant(ContractModel):
    """노드가 열 수 있는 상호작용(나가는 연결의 `interaction` 속성에서 계산)."""

    kinds: list[str] = Field(default_factory=list, description="허용 상호작용 종류 id.")
    timeout_seconds: float | None = Field(
        default=None, gt=0, description="응답 대기 한도. null = 설정값을 따른다."
    )
    on_timeout: OnTimeout | None = Field(
        default=None, description="한도 초과 시 동작. null = 설정값을 따른다."
    )


class RespondInteractionRequest(ContractModel):
    """`POST /runs/{run_id}/interactions/{interaction_id}/respond` 요청. 응답은 `Interaction`.

    `response`는 그 상호작용의 `response_schema`로 검증된다(아니면 422 `validation_failed`).
    이미 닫혔으면 409 `interaction_closed`.
    """

    response: JsonObject


class ReviewDecision(ContractModel):
    """검토하는 사람이 고를 결정 하나입니다(예: 승인, 반려). 결정마다 다음 갈 곳을 정합니다."""

    # 쓰임: 사용자 노드 config `review.decisions`와 검토 요청 payload의 `decisions`.
    # 결정 목록·라벨·포트 이름(= `id`)은 사용자가 정하는 데이터다. `ui_hints.color`에는 디자인 토큰
    # 이름 문자열만 넣는다(예: 강조 단계). 해석은 화면 몫이며 모르는 값은 기본 스타일.
    # (docstring은 설정 폼 머리말로 보이므로 개발자 메모는 이 주석에 둔다.)

    id: NonEmptyStr = Field(
        title="결정 id",
        description="결정을 가리키는 이름입니다. 같은 이름의 출력 포트가 생깁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="결정에 따라 다른 곳으로 보내야 할 때 이름을 정하세요.",
            example="approved",
        ),
    )
    label: str = Field(
        default="",
        title="버튼 이름",
        description="검토 카드 버튼에 보일 이름입니다. 비우면 결정 id를 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="검토 버튼 이름을 알아보기 쉽게 하고 싶을 때 바꾸세요.",
            example="승인",
        ),
    )
    edit: bool = Field(
        default=False,
        title="내용 고치기",
        description="켜면 이 결정을 고를 때 내용을 고쳐 보낼 수 있습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    feedback: bool = Field(
        default=False,
        title="의견 칸",
        description="켜면 이 결정을 고를 때 의견을 적을 칸을 보입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    ui_hints: UiHints | None = Field(
        default=None,
        title="표시 힌트",
        description="버튼 색 등 표시용 힌트입니다. 화면이 모르는 값은 무시합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
