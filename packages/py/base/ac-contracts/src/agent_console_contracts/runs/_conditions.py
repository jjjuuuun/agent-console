"""선언형 조건(design §5R.3 X22·§5R.5, 0.7.0).

조건은 표현식 언어가 아니라 데이터다: 판단 대상(JSON 객체)의 값 하나를 JSON Pointer로 골라
연산자로 비교한 항목들의 목록. 연산자 종류는 확장 지점(X22, entry point
`agent_console.condition_operators`)이 정하며 계약은 연산자 이름을 모른다(`op`는 열린
문자열). 평가는 `ac-conditions`가 한다.
"""

from typing import Any, Literal

from pydantic import ConfigDict, Field

from agent_console_contracts._base import ContractModel, DefinitionModel, JsonObject, NonEmptyStr
from agent_console_contracts.common import JsonPointer, UiHints, x_ui

type ConditionMode = Literal["all", "any"]
"""조건 목록을 묶는 방식(고정 어휘). all = 모두 참, any = 하나라도 참."""


class ConditionItem(DefinitionModel):
    """조건 하나입니다. 결과의 '볼 값'을 '비교 방법'으로 '비교할 값'과 견줍니다."""

    # 판단 대상에서 `path`의 값을 연산자 `op`로 `value`와 비교한다.

    path: JsonPointer = Field(
        title="볼 값",
        description=(
            "결과에서 비교할 값의 위치입니다(예: /output, /structured/verdict, /iteration)."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="결과의 다른 값(예: 판정, 회차)을 보고 갈림길을 정하고 싶을 때 바꾸세요.",
            example="/structured/verdict",
        ),
    )
    op: NonEmptyStr = Field(
        title="비교 방법",
        description=(
            "값을 어떻게 비교할지입니다(예: 같음, 포함). 고를 수 있는 방법은 서버가 알려 줍니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="같음·포함·있음 등 비교 방법을 바꾸고 싶을 때 고르세요."
        ),
    )
    value: Any = Field(
        default=None,
        title="비교할 값",
        description="볼 값과 견줄 값입니다. 비교 방법에 따라 비워 둡니다(예: 값이 있는지 볼 때).",
        json_schema_extra=x_ui(
            tier="basic", when="어떤 값일 때 지나갈지 바꾸고 싶을 때 적으세요.", example="approve"
        ),
    )


class ConditionSpec(DefinitionModel):
    """연결을 지나갈 조건입니다.

    '모두 참'과 '하나라도 참'을 함께 쓰면 둘 다 맞아야 하고, 조건이 하나도 없으면 항상 지나갑니다.
    '결과 뒤집기'를 켜면 결과를 반대로 씁니다.
    """

    # 조건 묶음(연결 config 등에 담기는 사용자 데이터, 모르는 키 보존). `all`과 `any`가 둘 다 있으면
    # 둘 다 참이어야 한다. 둘 다 없거나 비면 항상 참이다(저장 전 검사가 경고한다). `negate`가
    # true면 최종 결과를 뒤집는다.

    model_config = ConfigDict(title="조건")

    all: list[ConditionItem] | None = Field(
        default=None,
        title="모두 참",
        description="여기 적은 조건이 모두 맞아야 지나갑니다.",
        json_schema_extra=x_ui(
            tier="basic", when="여러 조건이 모두 맞을 때만 지나가게 하고 싶을 때 더하세요."
        ),
    )
    any: list[ConditionItem] | None = Field(
        default=None,
        title="하나라도 참",
        description="여기 적은 조건 중 하나만 맞아도 지나갑니다.",
        json_schema_extra=x_ui(
            tier="basic", when="조건 중 하나만 맞아도 지나가게 하고 싶을 때 더하세요."
        ),
    )
    negate: bool | None = Field(
        default=None,
        title="결과 뒤집기",
        description="켜면 조건이 맞지 않을 때 지나갑니다. 비우면 꺼짐입니다.",
        json_schema_extra=x_ui(
            tier="advanced", when="조건이 맞지 않을 때 지나가게 하고 싶을 때 켜세요."
        ),
    )


class ConditionItemOutcome(ContractModel):
    """조건 항목 하나의 판정 근거."""

    path: str
    op: str
    value: Any = Field(default=None, description="비교한 기대 값(조건 데이터 그대로).")
    actual: Any = Field(
        default=None,
        description="비교한 실제 값(비밀이 가려지고 서버가 정한 길이 상한으로 잘린 값).",
    )
    result: bool = Field(description="이 항목의 판정.")
    mode: ConditionMode | None = Field(
        default=None, description="이 항목이 속한 목록(all·any가 함께 있을 때 구분)."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "거짓·판정 불가의 사유(열린 문자열). 알려진 값: missing(경로에 값 없음), "
            "unknown_operator(등록되지 않은 연산자), invalid_value(값이 value_schema에 맞지 않음), "
            "error(연산자 실패)."
        ),
    )


class ConditionOutcome(ContractModel):
    """조건 묶음의 판정 결과와 근거(`edge.traversed`·`edge.skipped` payload `condition`)."""

    result: bool = Field(description="최종 결과(`negate` 반영 뒤).")
    combinator: ConditionMode | None = Field(
        default=None, description="항목을 묶은 방식. all·any가 함께 있으면 null(항목의 mode)."
    )
    negate: bool | None = Field(default=None, description="결과를 뒤집었는지.")
    items: list[ConditionItemOutcome] | None = Field(
        default=None, description="항목별 근거. null = 근거를 싣지 않음."
    )


class ConditionOperatorDescriptor(ContractModel):
    """조건 연산자 디스크립터(X22, `GET /condition-operators`). 조건 편집 화면이 이것으로 그린다."""

    id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    value_schema: JsonObject = Field(
        default_factory=dict,
        description="`ConditionItem.value`의 JSON Schema. 빈 객체 = 아무 값(또는 값 없음).",
    )
    applies_to: list[str] | None = Field(
        default=None,
        description=(
            "비교할 실제 값의 JSON 형식 이름(string·number·integer·boolean·array·object·null). "
            "null = 제한 없음. 화면 힌트이며 다른 형식이면 연산자는 거짓을 돌려준다."
        ),
    )
    ui_hints: UiHints | None = None
