"""`host` 위임 방식 config(디스크립터 `config_schema`의 출처, design §5R.6).

도구 이름·파라미터 이름·모델에게 보이는 문구는 모두 이 모델의 **스키마 기본값(데이터)** 이다.
사용자는 위임자 노드의 방식별 config로 바꾼다. 코드에는 이름별 분기가 없다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_console_contracts import x_ui

__all__ = [
    "RESULT_MODES",
    "HostDelegationConfig",
    "ResultMode",
    "fill",
]

TOOL_NAME_PATTERN: Final = r"^[A-Za-z0-9_-]{1,64}$"
"""도구·파라미터 이름 규칙(백엔드 공통: MCP 도구 이름 문자 집합)."""

type ResultMode = Literal["text", "reply"]
RESULT_MODES: Final[tuple[str, ...]] = ("text", "reply")
"""엣지 config 결과 모양 값: `text` = 대상 결과 포트 텍스트, `reply` = 대상의 답변 연결 텍스트."""


class HostDelegationConfig(BaseModel):
    """다른 에이전트에게 일을 맡기는 위임 도구의 이름·안내 문구입니다. 비우면 기본 문구를 씁니다."""

    # 개발자 메모(docstring은 설정 폼 머리말로 보이므로 여기 둔다):
    # 독립 위임 도구 설정. 비운 항목은 아래 기본값(스키마 기본값)을 쓴다.
    #
    # 문구 템플릿 변수(`{이름}` 안전 치환, 모르는 변수는 그대로):
    #     - `tool_description`: `{targets}`(대상 줄 목록), `{count}`(대상 수)
    #     - `target_line`: `{id}`(대상 노드 id), `{role}`, `{when}`(언제 맡길지), `{agent}`
    #     - `unknown_target_text`: `{target}`, `{targets}`(허용 id 쉼표 목록)
    #     - `failure_text`: `{target}`, `{status}`, `{code}`, `{message}`
    #     - `invalid_call_text`: `{target}`

    model_config = ConfigDict(extra="forbid", title="독립 위임 설정")

    tool_name: str = Field(
        default="delegate",
        pattern=TOOL_NAME_PATTERN,
        title="도구 이름",
        description="에이전트가 일을 맡길 때 부르는 도구 이름입니다(영문·숫자·_·-, 64자 이하).",
        json_schema_extra=x_ui(
            tier="basic", when="다른 도구 이름과 겹치거나 에이전트가 알아보기 어려울 때 바꾸세요."
        ),
    )
    tool_description: str = Field(
        default=(
            "다른 에이전트에게 일을 맡기고 그 결과를 받는다. 맡길 대상과 할 일을 정해 부른다. "
            "대상은 자기 세션에서 따로 실행된다.\n대상:\n{targets}"
        ),
        title="도구 설명",
        description=(
            "에이전트에게 보이는 도구 설명입니다. {targets}는 대상 목록, {count}는 대상 수입니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="에이전트가 언제 일을 맡길지 헷갈려 할 때 고치세요."
        ),
    )
    target_line: str = Field(
        default="- {id}: {role} — {when}",
        title="대상 한 줄 형식",
        description=(
            "도구 설명의 {targets}에 들어갈 대상 한 줄입니다. {id}·{role}·{when}·{agent}를 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    target_param: str = Field(
        default="target",
        pattern=TOOL_NAME_PATTERN,
        title="대상 파라미터 이름",
        description="도구 입력에서 맡길 대상을 받는 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    target_param_description: str = Field(
        default="일을 맡길 대상 id(도구 설명의 대상 목록 중 하나).",
        title="대상 파라미터 설명",
        description="에이전트에게 보이는 대상 입력 칸 설명입니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    task_param: str = Field(
        default="task",
        pattern=TOOL_NAME_PATTERN,
        title="할 일 파라미터 이름",
        description="도구 입력에서 맡길 일을 받는 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    task_param_description: str = Field(
        default="대상에게 맡길 일. 대상은 이 글만 보고 일하므로 필요한 맥락을 함께 적는다.",
        title="할 일 파라미터 설명",
        description="에이전트에게 보이는 할 일 입력 칸 설명입니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    unknown_target_text: str = Field(
        default="알 수 없는 대상입니다: {target}. 고를 수 있는 대상: {targets}",
        title="모르는 대상 결과 문구",
        description=(
            "없는 대상을 불렀을 때 에이전트에게 돌려줄 문구입니다. {target}·{targets}를 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    invalid_call_text: str = Field(
        default="대상 {target}을(를) 부를 수 없습니다(할 일이 비었거나 연결이 맞지 않습니다).",
        title="잘못된 호출 결과 문구",
        description="부를 수 없는 호출일 때 돌려줄 문구입니다. {target}을 씁니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    failure_text: str = Field(
        default="대상 {target} 실행이 끝나지 못했습니다({status}, {code}): {message}",
        title="대상 실패 결과 문구",
        description=(
            "대상 실행이 실패했을 때 돌려줄 문구입니다. {target}·{status}·{message} 등을 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )
    empty_result_text: str = Field(
        default="(대상 {target}이(가) 결과 텍스트를 내지 않았습니다)",
        title="빈 결과 문구",
        description="대상이 결과 글을 내지 않았을 때 돌려줄 문구입니다.",
        json_schema_extra=x_ui(tier="advanced", group="text", group_title="도구 문구"),
    )

    @model_validator(mode="after")
    def _distinct_params(self) -> HostDelegationConfig:
        if self.target_param == self.task_param:
            raise ValueError("대상 파라미터와 할 일 파라미터 이름이 같습니다")
        return self


_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def fill(template: str, values: Mapping[str, object]) -> str:
    """`{이름}`을 값으로 바꾼다(안전 치환: 속성 접근·형식 지정 없음, 모르는 이름은 그대로)."""

    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return _VAR.sub(sub, template)
