"""`user`(사용자·채팅) 노드 타입과 사용자 중간 검토(design §R1.2a, §R14.6).

- 포트: 입력 `hears`(답변), `asks`(되묻기·승인 받는 쪽), `review`(검토할 값), 출력 `says`(메시지) +
  config `review.decisions`의 결정마다 출력 포트 하나(포트 이름 = 결정 id, `resolve_ports`).
- `executable=true`이지만 엔진은 `entry`·`flow`로 들어오는 연결이 있을 때만 스케줄한다. 입구·답변만
  있는 사용자 노드는 실행되지 않는다.
- 흐름으로 실행되면(A → 사용자 → B) `review` 값을 내용으로 상호작용(기본 종류 `review`)을 연다.
  응답한 결정의 포트에만 값을 낸다(나머지 결정 포트는 엔진 dead-path 규칙대로 하류가 skipped).
  `edit`가 허용된 결정이면 고친 내용이 내용을 대신하고, 값은 `output_template`(안전 치환, 변수
  `content`(고쳤으면 고친 내용)·`original`(고치기 전)·`edited`·`feedback`·`decision`·`source_node`·
  `title`)으로 만든다. 만료면 `review.expired`, 취소면
  `review.cancelled`로 실패한다. `review` 설정이 없으면 `user.not_reviewable`로 실패한다.
- 결정 목록·라벨·포트 이름·편집·의견 여부·출력 형식·상호작용 종류는 모두 config 데이터다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent_console_contracts import (
    Issue,
    NodeTypeDescriptor,
    OnTimeout,
    PortDef,
    PortSpec,
    ReviewDecision,
    UiHints,
    x_ui,
)
from agent_console_resources import render_template
from agent_console_runtime import (
    InteractionRequest,
    NodeContext,
    NodeResult,
    ValidationContext,
)

from ._common import (
    ASKS_PORT,
    HEARS_PORT,
    REVIEW_PORT,
    SAYS_PORT,
    USER_ROLE,
    NodesCoreErrorCodes,
    as_text,
    failed,
    issue,
)
from .interactions import REVIEW, review_response_schema

__all__ = ["ReviewConfig", "UserNode", "UserNodeConfig"]

_RESERVED_OUTPUTS: Final = frozenset({SAYS_PORT})
"""결정 id로 쓸 수 없는 이름 = 고정 **출력** 포트.

입력 포트(`hears`·`asks`·`review`)와는 이름 공간이 달라 결정 id로 써도 된다."""


class ReviewConfig(BaseModel):
    """사용자 중간 검토 설정."""

    model_config = ConfigDict(extra="forbid", title="검토 설정")

    title: str = Field(
        default="",
        title="제목",
        description="검토 카드 맨 위에 보일 제목입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="검토하는 사람이 무엇을 보는지 알아보기 쉽게 하고 싶을 때 바꾸세요.",
            example="초안 검토",
        ),
    )
    message: str = Field(
        default="",
        title="안내",
        description="검토하는 사람에게 보일 안내 문구입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="검토하는 사람에게 확인할 점을 알려 주고 싶을 때 적으세요.",
            example="내용을 확인하고 승인하거나 고쳐 주세요.",
        ),
    )
    decisions: list[ReviewDecision] = Field(
        min_length=1,
        title="결정",
        description="고를 수 있는 결정입니다(예: 승인·반려). 결정마다 출력 포트가 하나 생깁니다.",
        json_schema_extra=x_ui(
            tier="basic", when="승인·반려 말고 다른 선택지가 필요할 때 더하세요."
        ),
    )
    output_template: str | None = Field(
        default=None,
        title="출력 형식",
        description=(
            "결정 포트로 낼 값의 틀입니다. {content}·{edited}·{feedback} 등을 씁니다. 비우면 "
            "내용 그대로."
        ),
        json_schema_extra=x_ui(tier="advanced", example="{decision}: {feedback}\n\n{content}"),
    )
    kind: str = Field(
        default=REVIEW.id,
        min_length=1,
        title="상호작용 종류",
        description="검토 카드를 어떤 모양으로 열지입니다. 보통은 바꾸지 않습니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        title="응답 대기 한도(초)",
        description="검토를 기다리는 시간입니다. 비우면 상호작용 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="검토를 너무 오래 기다리지 않게 하고 싶을 때 정하세요.",
            example=3600,
            unit="초",
        ),
    )
    on_timeout: OnTimeout | None = Field(
        default=None,
        title="한도 초과 시",
        description="답이 없을 때 요청만 닫을지(expire) 실행을 취소할지(cancel_run) 정합니다.",
        json_schema_extra=x_ui(
            enum_labels={"expire": "요청만 닫기", "cancel_run": "실행 취소"}, tier="advanced"
        ),
    )

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [d.id for d in self.decisions]
        if len(set(ids)) != len(ids):
            raise ValueError("결정 id가 겹칩니다")
        return self


class UserNodeConfig(BaseModel):
    """사용자 자리 설정입니다. 중간 검토를 켜면 흐름으로 들어온 값을 사람이 확인한 뒤 넘깁니다."""

    model_config = ConfigDict(extra="forbid", title="사용자 노드 설정")

    review: ReviewConfig | None = Field(
        default=None,
        title="중간 검토",
        description="흐름으로 들어온 값을 사람이 보고 승인·반려·수정하게 합니다.",
        json_schema_extra=x_ui(
            tier="basic", when="에이전트 결과를 사람이 확인한 뒤 넘기고 싶을 때 켜세요."
        ),
    )


_BASE_INPUTS: Final = [
    PortDef(name=HEARS_PORT, label="답변"),
    PortDef(name=ASKS_PORT, label="묻기·승인"),
    PortDef(name=REVIEW_PORT, label="검토"),
]
_BASE_PORTS: Final = PortSpec(
    inputs=_BASE_INPUTS, outputs=[PortDef(name=SAYS_PORT, label="메시지")]
)


def _review_of(config: Mapping[str, Any]) -> ReviewConfig | None:
    raw = config.get("review")
    if raw is None:
        return None
    try:
        return ReviewConfig.model_validate(raw)
    except ValidationError:
        return None


class UserNode:
    """노드 타입 `user`: 대화하는 사용자의 자리. 여러 개 두어도 같은 대화를 뜻한다(그림 정리용)."""

    descriptor = NodeTypeDescriptor(
        id="user",
        version=1,
        title="사용자",
        description="채팅하는 사용자. 메시지·답변·되묻기 연결의 끝이고, 흐름 중간에 두면 검토한다.",
        category="대화",
        role=USER_ROLE,
        executable=True,
        config_schema=UserNodeConfig.model_json_schema(),
        ui_schema={"review": {"message": {"ui:widget": "textarea"}}},
        static_ports=_BASE_PORTS,
        dynamic_ports=True,
        # 끊긴 실행을 이어 갈 때 저장된 입력으로 같은 검토 요청을 다시 연다(§2R.10).
        rerunnable=True,
        ui_hints=UiHints.model_validate(
            {
                "icon": "나",
                "shape": "chip",
                # 편집기 선언형 배지(design "선언형 배지·칩"): 검토 설정이 있고 흐름 입력이 있으면
                "badges": [
                    {
                        "label_key": "review",
                        "label": "검토",
                        "when": {"config_path": "review", "incoming_scheduling": "flow"},
                    }
                ],
            }
        ),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트 + 결정 포트(결정 id, 고정 출력 포트 이름과 겹치는 것은 뺀다)."""
        review = _review_of(config)
        if review is None:
            return _BASE_PORTS
        decisions = [
            PortDef(name=d.id, label=d.label or d.id)
            for d in review.decisions
            if d.id not in _RESERVED_OUTPUTS
        ]
        return PortSpec(inputs=list(_BASE_INPUTS), outputs=[*_BASE_PORTS.outputs, *decisions])

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """결정 id가 고정 출력 포트 이름과 겹치는지, 상호작용 종류가 등록됐는지."""
        review = _review_of(config)
        if review is None:
            return []
        issues: list[Issue] = []
        for i, d in enumerate(review.decisions):
            if d.id in _RESERVED_OUTPUTS:
                issues.append(
                    issue(
                        NodesCoreErrorCodes.REVIEW_RESERVED_PORT,
                        f"결정 id {d.id!r}는 사용자 노드 출력 포트 이름과 겹칩니다",
                        f"/review/decisions/{i}/id",
                    )
                )
        if review.kind not in ctx.registries.interaction_kinds:
            issues.append(
                issue(
                    NodesCoreErrorCodes.REVIEW_UNKNOWN_KIND,
                    f"등록되지 않은 상호작용 종류 {review.kind!r}",
                    "/review/kind",
                )
            )
        return issues

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """검토 요청을 열고, 응답한 결정의 포트에만 값을 낸다."""
        raw = ctx.config.get("review")
        if raw is None:
            return failed(
                NodesCoreErrorCodes.USER_NOT_REVIEWABLE,
                "이 사용자 노드에는 검토 설정(review)이 없어 흐름 입력을 처리하지 못합니다",
            )
        try:
            review = ReviewConfig.model_validate(raw)
        except ValidationError as exc:
            return failed(
                NodesCoreErrorCodes.INVALID_CONFIG,
                f"검토 설정이 유효하지 않습니다: {exc.error_count()}개 오류",
            )
        content = as_text(
            inputs[REVIEW_PORT] if REVIEW_PORT in inputs else next(iter(inputs.values()), None)
        )
        payload: dict[str, Any] = {
            "content": content,
            "decisions": [d.model_dump(mode="json", exclude_none=True) for d in review.decisions],
        }
        if review.title:
            payload["title"] = review.title
        source = _source_node(ctx)
        if source is not None:
            payload["source_node"] = source
        outcome = await ctx.request_input(
            InteractionRequest(
                kind=review.kind,
                title=review.title,
                message=review.message,
                payload=payload,
                response_schema=review_response_schema([d.id for d in review.decisions]),
                timeout_seconds=review.timeout_seconds,
                on_timeout=review.on_timeout,
            )
        )
        if outcome.status == "expired":
            return failed(
                NodesCoreErrorCodes.REVIEW_EXPIRED,
                "검토 응답 대기 시간이 지났습니다",
                interaction_id=outcome.interaction_id,
            )
        if outcome.status != "answered" or outcome.response is None:
            return failed(
                NodesCoreErrorCodes.REVIEW_CANCELLED,
                "검토 요청이 취소되었습니다",
                interaction_id=outcome.interaction_id,
                reason=outcome.reason,
            )
        response = outcome.response
        chosen = next((d for d in review.decisions if d.id == response.get("decision")), None)
        if chosen is None:  # 응답 스키마가 막지만 엔진 밖 응답 대비
            return failed(
                NodesCoreErrorCodes.REVIEW_UNKNOWN_DECISION,
                "알 수 없는 검토 결정입니다",
                interaction_id=outcome.interaction_id,
            )
        edited = response.get("edited") if chosen.edit else None
        edited_text = edited if isinstance(edited, str) else ""
        feedback = response.get("feedback") if chosen.feedback else None
        feedback_text = feedback if isinstance(feedback, str) else ""
        result = edited_text if isinstance(edited, str) else content
        if review.output_template is not None:
            result = render_template(
                review.output_template,
                {
                    "content": result,
                    "original": content,
                    "edited": edited_text,
                    "feedback": feedback_text,
                    "decision": chosen.id,
                    "source_node": source or "",
                    "title": review.title,
                },
            )
        return NodeResult(status="succeeded", outputs={chosen.id: result})


def _source_node(ctx: NodeContext) -> str | None:
    """`review` 포트로 들어오는 연결이 하나면 그 출발 노드 id."""
    sources = {
        e.source.node
        for e in ctx.graph.edges
        if e.target.node == ctx.node.id and e.target.port == REVIEW_PORT
    }
    return next(iter(sources)) if len(sources) == 1 else None
