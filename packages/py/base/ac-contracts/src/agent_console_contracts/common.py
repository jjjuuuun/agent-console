"""계약 하위 모듈 `common`: 모든 기능이 공유하는 작은 모델(오류, 사용량, 포트, 좌표, UI 힌트).

다른 하위 모듈을 import하지 않는다(맨 아래 층). 검증 이슈(`Issue`)는 그래프 패치를 담으므로
`definitions`에 있다.
"""

from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import ConfigDict, Field, StringConstraints

from ._base import ContractModel, JsonObject, NonEmptyStr, OmitWhenUnsetContract

JsonPointer = Annotated[str, StringConstraints(pattern=r"^(/.*)?$")]


# ---------------------------------------------------------------- 스키마 확장 x-ui(0.8.0)

X_UI: Final = "x-ui"
"""JSON Schema 속성 확장 키(ux-overhaul §5.2). 폼이 분류·설명·예시를 이 키에서 읽는다. 계약 모델과
플러그인 디스크립터(`config_schema`·`ui_schema`)가 같은 키를 쓴다."""


class XUiKeys:
    """`x-ui` 객체 안의 키 이름(ux-overhaul §5.2). 화면은 모르는 키를 무시한다."""

    TIER: Final = "tier"
    """분류: `basic`(위쪽) | `advanced`(접힘).

    없으면 폼의 폴백 규칙(required → 객체 → 기본값 유무)을 따른다."""
    WHEN: Final = "when"
    """언제 바꾸나 한 문장."""
    EXAMPLE: Final = "example"
    """예시 값(빈 칸일 때 클릭하면 값으로 채움)."""
    GROUP: Final = "group"
    """고급 영역 안의 소제목 id."""
    GROUP_TITLE: Final = "group_title"
    """소제목 문구(없으면 웹 메시지 표 또는 id)."""
    ORDER: Final = "order"
    """같은 tier 안 순서(숫자, 작을수록 앞)."""
    UNIT: Final = "unit"
    """단위 문자열(예: 초, 개, MB). 입력 오른쪽 접미사."""


type XUiTier = Literal["basic", "advanced"]
"""`x-ui.tier` 값(고정 어휘)."""

X_UI_TIERS: Final = ("basic", "advanced")
"""`x-ui.tier`의 값 목록."""

_UNSET: Any = object()


def x_ui(
    *,
    tier: XUiTier | None = None,
    when: str | None = None,
    example: Any = _UNSET,
    group: str | None = None,
    group_title: str | None = None,
    order: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Pydantic `Field(json_schema_extra=...)`에 넣을 `{"x-ui": {...}}`를 만든다.

    인자: 넘긴 것만 담는다(`example`은 None도 값으로 담는다). 다른 확장 키(`x-merge` 등)와 함께
    쓰려면 `{**x_ui(tier="advanced"), "x-merge": "replace"}`처럼 합친다.
    반환: 새 dict(호출마다 새 객체).
    예외: `tier`가 `X_UI_TIERS`에 없으면 `ValueError`.

    >>> x_ui(tier="advanced", unit="초")
    {'x-ui': {'tier': 'advanced', 'unit': '초'}}
    """
    if tier is not None and tier not in X_UI_TIERS:
        raise ValueError(f"알 수 없는 x-ui tier: {tier!r}")
    body: dict[str, Any] = {}
    for key, value in (
        (XUiKeys.TIER, tier),
        (XUiKeys.WHEN, when),
        (XUiKeys.GROUP, group),
        (XUiKeys.GROUP_TITLE, group_title),
        (XUiKeys.ORDER, order),
        (XUiKeys.UNIT, unit),
    ):
        if value is not None:
            body[key] = value
    if example is not _UNSET:
        body[XUiKeys.EXAMPLE] = example
    return {X_UI: body}


# ---------------------------------------------------------------- 오류 해결 데이터(0.8.0)


class FixTarget(ContractModel):
    """해결 버튼이 데려갈 화면. 서버는 웹 경로를 모른다.

    `role`은 웹 라우트 **역할** 문자열(정의 종류 역할, 설정 역할 등)이고 웹이 경로로 푼다. 그 역할을
    맡은 화면이 없으면(모듈 꺼짐) 웹은 버튼을 숨긴다.
    """

    role: NonEmptyStr = Field(description="웹 라우트 역할 이름(열린 문자열).")
    id: str | None = Field(default=None, description="그 화면에서 열 항목 id(예: 팀 구성 id).")
    section: str | None = Field(
        default=None, description="화면 안 위치(예: 설정 섹션 id, 노드 id). 해석은 그 화면."
    )


class FixAction(ContractModel):
    """해결 버튼 하나: 문구 + 이동할 곳 + 열었을 때 초점을 둘 필드."""

    label: NonEmptyStr = Field(description="버튼 문구(사용자 언어).")
    target: FixTarget
    focus: JsonPointer | None = Field(
        default=None,
        description="열린 폼에서 초점을 둘 필드(그 폼 문서 기준 JSON Pointer, 예: /backend).",
    )


class Fix(ContractModel):
    """오류·이슈를 고치는 방법(버튼 목록). 오류를 만드는 쪽(서버)이 채운다."""

    actions: list[FixAction] = Field(default_factory=list)


class ErrorInfo(OmitWhenUnsetContract):
    """오류 정보. REST 오류 응답, WS `error`, 노드 실패에 공통으로 쓴다.

    `code`는 기계가 읽는 문자열(고정 목록 아님, 알려진 값은 `ErrorCodes`).
    `message`는 사람이 읽는 문장.
    """

    code: NonEmptyStr
    message: str
    details: JsonObject = Field(default_factory=dict)
    fix: Fix | None = Field(
        default=None, description="해결 버튼(0.8.0). null = 제안 없음(화면은 메시지만 보인다)."
    )

    # 지정했을 때만 직렬화한다: 0.7.0 이하 오류 본문(REST·WS)과 형식이 같게.
    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("fix",),)


class ErrorResponse(ContractModel):
    """REST 오류 응답 본문. 모든 4xx/5xx가 이 형식 하나를 쓴다."""

    error: ErrorInfo


class Usage(ContractModel):
    """토큰·비용 사용량. 값을 모르면 null(화면은 대시로 표시).

    알려진 키 외에 백엔드가 숫자 키를 더 붙일 수 있다(화면은 키 이름 그대로 표시).
    """

    model_config = ConfigDict(extra="allow")

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cost_usd: float | None = None
    total_tokens: int | None = Field(
        default=None,
        description=(
            "입력·출력 구분 없는 총 토큰(예: 서브에이전트 TaskUsage). "
            "구분 값이 있으면 그쪽이 정밀하다."
        ),
    )


class PortDef(ContractModel):
    """이름 있는 입출력 포트 하나."""

    name: NonEmptyStr = Field(
        title="포트 이름",
        description="입력·출력을 가리키는 이름입니다. 연결과 실행 입력이 이 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="실행 입력이나 연결이 쓰는 이름을 바꿔야 할 때만 바꾸세요.",
            example="input",
        ),
    )
    label: str | None = Field(
        default=None,
        title="표시 이름",
        description="화면에 보일 이름입니다. 비우면 포트 이름을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="화면에 보이는 포트 이름을 알아보기 쉽게 하고 싶을 때 바꾸세요.",
            example="질문",
        ),
    )
    description: str | None = Field(
        default=None,
        title="설명",
        description="이 포트로 무엇이 오가는지 적습니다.",
        json_schema_extra=x_ui(tier="advanced", example="사용자가 처음 보내는 메시지"),
    )
    schema_: JsonObject | None = Field(
        default=None,
        alias="schema",
        title="값 형식",
        description="이 포트 값의 형식(JSON Schema)입니다. 연결이 맞지 않으면 경고합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class PortSpec(ContractModel):
    """노드의 입력·출력 포트 목록."""

    inputs: list[PortDef] = Field(default_factory=list)
    outputs: list[PortDef] = Field(default_factory=list)


class Endpoint(ContractModel):
    """연결의 한쪽 끝입니다: 노드와 그 포트 이름."""

    node: NonEmptyStr = Field(
        title="노드",
        description="연결 끝의 노드 id입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )
    port: NonEmptyStr = Field(
        title="포트",
        description="연결 끝의 포트 이름입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class Position(ContractModel):
    """캔버스 좌표."""

    x: float = Field(
        title="가로",
        description="캔버스 가로 좌표입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="px"),
    )
    y: float = Field(
        title="세로",
        description="캔버스 세로 좌표입니다.",
        json_schema_extra=x_ui(tier="advanced", unit="px"),
    )


class UiHints(ContractModel):
    """표시용 선택 힌트. 없어도 화면이 동작해야 한다(기본: 카테고리 해시 색 + 제목 첫 글자).

    값 목록은 고정하지 않는다. 화면은 해석할 수 없는 값을 무시하고 기본 표시로 돌아간다.
    """

    model_config = ConfigDict(extra="allow")

    icon: str | None = Field(
        default=None,
        title="아이콘",
        description="짧은 아바타 글자입니다(1~2자, 이모지 포함).",
        json_schema_extra=x_ui(tier="advanced", example="✓"),
    )
    color: str | None = Field(
        default=None,
        title="색",
        description="CSS 색이나 색 이름입니다. 모르는 값이면 기본 색입니다.",
        json_schema_extra=x_ui(tier="advanced", example="#3b82f6"),
    )
    dashed: bool | None = Field(
        default=None,
        title="점선",
        description="연결선을 점선으로 그립니다(연결 종류용).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    hidden: bool | None = Field(
        default=None,
        title="숨김",
        description="팔레트·목록에 보이지 않게 합니다(조립용 종류).",
        json_schema_extra=x_ui(tier="advanced"),
    )
    shape: str | None = Field(
        default=None,
        title="모양",
        description="노드 모양 힌트입니다(예: card, chip). 모르면 기본 모양입니다.",
        json_schema_extra=x_ui(tier="advanced", example="card"),
    )
    renderer: str | None = Field(
        default=None,
        title="그리기 방식",
        description="화면이 쓸 전용 그리기 방식 이름입니다. 모르는 이름이면 일반 폼으로 그립니다.",
        json_schema_extra=x_ui(tier="advanced", example=None),
    )
    direction: str | None = Field(
        default=None,
        title="기본 방향",
        description="노드 종류의 기본 방향입니다(lr, tb, rl, bt, auto). 사용자 설정이 우선합니다.",
        json_schema_extra=x_ui(tier="advanced", example="lr"),
    )
    edge_shape: str | None = Field(
        default=None,
        title="기본 연결선 모양",
        description=(
            "연결 종류의 기본 선 모양입니다. 사용자 설정이 우선하고 모르는 값은 무시합니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="smoothstep"),
    )
    badge: str | None = Field(
        default=None,
        title="배지",
        description="이름 옆에 붙는 짧은 글자입니다(예: 체험, 베타). 비우면 배지가 없습니다.",
        json_schema_extra=x_ui(tier="advanced", example="베타"),
    )


__all__ = [
    "X_UI",
    "X_UI_TIERS",
    "Endpoint",
    "ErrorInfo",
    "ErrorResponse",
    "Fix",
    "FixAction",
    "FixTarget",
    "JsonPointer",
    "PortDef",
    "PortSpec",
    "Position",
    "UiHints",
    "Usage",
    "XUiKeys",
    "XUiTier",
    "x_ui",
]
