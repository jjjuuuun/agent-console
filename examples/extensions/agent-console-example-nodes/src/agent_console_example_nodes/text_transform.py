"""노드 타입 `example.text_transform`: 입력을 텍스트로 바꿔 대소문자 변환·접두어를 적용한다.

NodeType(X1)은 네 가지만 갖추면 된다.

1. ``descriptor`` — 팔레트·노드 모양·설정 폼은 이것만으로 그려진다
   (config_schema·ui_schema·ui_hints).
2. ``resolve_ports(config)`` — 포트 목록. 여기서는 고정 포트(`in` → `out`).
3. ``validate(config, ctx)`` — JSON Schema 밖의 의미 검증. 이슈 목록을 돌려준다.
4. ``async execute(ctx, inputs)`` — 실제 동작. ``NodeResult``를 돌려준다.

팀 구성에서의 의미(design §R1.2·§R9.3):

- ``role`` — 연결 규칙(엣지 디스크립터 `connects`)이 보는 역할 문자열. 이 노드는 에이전트 자리에
  놓이는 처리 단계라 기본 연결 종류(사용자 메시지·넘기기·답변)가 받는 `agent`를 쓴다. 역할은 고정
  목록이 아니다 — 새 역할을 쓰면 그 역할을 `connects`에 적은 연결 종류로만 이을 수 있다.
- ``binds`` — 정의(에이전트·리소스) 하나에서 만들어지는 노드가 아니므로 두지 않는다. 그래서 팀
  구성의 에이전트 목록·설정 층·리소스 첨부 대상이 되지 않고, 설정은 노드 config뿐이다.
- ``rerunnable`` — 결정적이라 끊긴 실행을 이어 갈 때 저장된 입력으로 다시 실행해도 안전하다.

동작은 결정적이다(외부 호출·시간·환경에 의존하지 않는다).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    ErrorInfo,
    Issue,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    UiHints,
)
from agent_console_runtime import NodeContext, NodeResult, ValidationContext

NODE_TYPE_ID: Final = "example.text_transform"
"""디스크립터 id. pyproject의 entry point 이름과 같아야 한다."""
IN_PORT: Final = "in"
"""입력 포트 이름."""
OUT_PORT: Final = "out"
"""출력 포트 이름."""
TEAM_ROLE: Final = "agent"
"""노드 역할(연결 규칙 근거). 기본 에이전트 노드 타입과 같은 문자열이라 같은 연결 종류로 잇는다."""

CaseMode = Literal["upper", "lower", "title", "keep"]
"""대소문자 변환 방식(설정 폼의 선택지)."""


class ExampleErrorCodes:
    """이 플러그인이 쓰는 `ErrorInfo.code`·`Issue.code` 값."""

    INVALID_CONFIG: Final = "example.invalid_config"
    NOOP: Final = "example.noop"


class TextTransformConfig(BaseModel):
    """입력 텍스트의 대소문자를 바꾸고 앞에 글을 붙인다."""

    model_config = ConfigDict(extra="forbid", title="텍스트 변환 설정")

    mode: CaseMode = Field(
        default="upper",
        title="대소문자",
        description="upper: 대문자, lower: 소문자, title: 단어 첫 글자 대문자, keep: 그대로",
    )
    prefix: str = Field(
        default="",
        title="앞에 붙일 글",
        description="변환한 텍스트 앞에 붙인다(변환 대상 아님).",
    )
    strip: bool = Field(
        default=True,
        title="앞뒤 공백 제거",
        description="변환 전에 앞뒤 공백을 지운다.",
    )


def _as_text(value: Any) -> str:
    """입력 값 → 텍스트: 문자열은 그대로, None은 빈 문자열, 그 밖은 JSON."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def transform_text(value: Any, config: TextTransformConfig) -> str:
    """노드와 같은 변환을 순수 함수로 제공한다(노드 없이 재사용 가능).

    Args:
        value: 변환할 값. 문자열이 아니면 JSON 텍스트로 바꾼다(None은 빈 문자열).
        config: 변환 설정.

    Returns:
        ``prefix + 대소문자변환(strip 적용 텍스트)``.
    """
    text = _as_text(value)
    if config.strip:
        text = text.strip()
    if config.mode == "upper":
        text = text.upper()
    elif config.mode == "lower":
        text = text.lower()
    elif config.mode == "title":
        text = text.title()
    return config.prefix + text


_PORTS: Final = PortSpec(
    inputs=[PortDef(name=IN_PORT, label="텍스트")],
    outputs=[PortDef(name=OUT_PORT, label="변환 결과")],
)


class TextTransformNode:
    """노드 타입 `example.text_transform`(X1 예제 구현)."""

    descriptor = NodeTypeDescriptor(
        id=NODE_TYPE_ID,
        version=1,
        title="텍스트 변환",
        description="입력 텍스트의 대소문자를 바꾸고 앞에 글을 붙여 다음 노드로 보낸다(예제 확장).",
        category="예제",
        role=TEAM_ROLE,
        rerunnable=True,
        config_schema=TextTransformConfig.model_json_schema(),
        ui_schema={
            "ui:order": ["mode", "prefix", "strip"],
            "mode": {"ui:widget": "radio"},
            "prefix": {"ui:placeholder": "예: [변환] "},
        },
        static_ports=_PORTS,
        ui_hints=UiHints(icon="Aa", color="#0ea5e9"),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트(입력 `in`, 출력 `out`)."""
        return _PORTS

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """아무 변환도 하지 않는 설정(keep + 접두어 없음 + strip 끔)이면 경고."""
        try:
            cfg = TextTransformConfig.model_validate(dict(config))
        except ValidationError:
            return []  # 형식 오류는 엔진의 JSON Schema 검증이 보고한다
        if cfg.mode == "keep" and not cfg.prefix and not cfg.strip:
            return [
                Issue(
                    severity="warning",
                    code=ExampleErrorCodes.NOOP,
                    message="이 설정은 입력을 바꾸지 않습니다",
                    path="/mode",
                )
            ]
        return []

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """`in`의 값을 변환해 `out`으로 낸다. config가 유효하지 않으면 실패."""
        try:
            cfg = TextTransformConfig.model_validate(dict(ctx.config))
        except ValidationError as exc:
            return NodeResult(
                status="failed",
                error=ErrorInfo(
                    code=ExampleErrorCodes.INVALID_CONFIG,
                    message=f"config가 유효하지 않습니다: {exc.error_count()}개 오류",
                    details={
                        "errors": [
                            {"loc": list(map(str, e["loc"])), "msg": e["msg"]} for e in exc.errors()
                        ]
                    },
                ),
            )
        return NodeResult(
            status="succeeded", outputs={OUT_PORT: transform_text(inputs.get(IN_PORT), cfg)}
        )
