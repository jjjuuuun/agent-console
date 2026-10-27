"""기본 연결 종류(엣지 타입, X2, design §R3.1·§R1.2a).

엔진·편집기·`ac-teams`는 이 id들을 모른다. 디스크립터 속성(`scheduling`·`invocation`·`connects`·
`default_ports`)으로만 구분한다.

| id | scheduling | 의미 |
| --- | --- | --- |
| `subagent` | none + invocation `sdk-subagents` | 위 에이전트가 판단해 서브에이전트로 부른다 |
| `delegate` | none + invocation `host` | 위 에이전트가 판단해 독립 에이전트(자기 세션)로 부른다 |
| `handoff` (`data` = 이전 이름) | flow | 위 노드가 끝나면 결과를 아래 노드에 넘긴다 |
| `uses` | none | 리소스 노드를 에이전트에 붙인다 |
| `message` | entry | 사용자 메시지 → 입구 노드(config `input_key`·`template`) |
| `reply` | exit | 노드 출력 → 채팅 답변(config `label`·`order`·`final`·`stream`) |
| `ask_user` | none + interaction | 에이전트가 실행 중 사용자에게 묻거나 승인받게 허용 |
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    EdgeConnects,
    EdgeInteraction,
    EdgeInvocation,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    ReplyFields,
    UiHints,
    x_ui,
)
from agent_console_resources import render_template
from agent_console_runtime import Activation, NodeRunView, Reply

from ._common import (
    AGENT_ROLE,
    ASKS_PORT,
    DELEGATED_PORT,
    DELEGATES_PORT,
    HEARS_PORT,
    IN_PORT,
    OUT_PORT,
    PROVIDES_PORT,
    RESOURCE_ROLE,
    RESOURCES_PORT,
    SAYS_PORT,
    TEAM_ROLE,
    USER_ROLE,
    as_text,
)
from .delegation import SDK_SUBAGENTS
from .interactions import QUESTION, TOOL_PERMISSION

DEFAULT_MESSAGE_KEY: Final = "text"
"""`message` 연결이 `input_key`를 생략했을 때 Run 입력에서 꺼낼 키(메시지 본문).

대화 서비스(`ac-chat` `ChatOptions.message_input_key`) 기본값과 같다."""


def _passed_value(source: NodeRunView, edge: EdgeSpec) -> tuple[bool, Any]:
    """소스가 성공했고 소스 포트에 값을 냈으면 `(True, 값)`."""
    if source.status != "succeeded" or edge.source.port not in source.outputs:
        return False, None
    return True, source.outputs[edge.source.port]


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


# ---------------------------------------------------------------- handoff (flow)


class _EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", title="설정 없음")


class HandoffEdge:
    """연결 종류 `handoff`: 위 노드가 성공해 소스 포트에 값을 냈으면 그 값을 아래 노드에 넘긴다.

    값을 내지 않은 포트(예: 고르지 않은 검토 결정 포트)는 막힌다(dead-path).
    """

    descriptor = EdgeTypeDescriptor(
        id="handoff",
        version=1,
        title="독립 에이전트로 넘기기",
        description=(
            "위 노드가 끝나면 결과를 아래 노드에 넘긴다. 아래 노드는 별도 세션으로 실행된다."
        ),
        scheduling="flow",
        connects=EdgeConnects(
            source=[AGENT_ROLE, TEAM_ROLE, USER_ROLE], target=[AGENT_ROLE, TEAM_ROLE, USER_ROLE]
        ),
        default_ports=EdgePortPair(source=OUT_PORT, target=IN_PORT),
        config_schema=_schema(_EmptyConfig),
        ui_hints=UiHints(icon="→"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """통과하면 `Activation(값)`, 아니면 None(dead-path)."""
        ok, value = _passed_value(source, edge)
        return Activation(value) if ok else None


class DataEdge(HandoffEdge):
    """`handoff`의 이전 이름 `data`(Phase 1 그래프 호환). 팔레트에는 보이지 않는다."""

    descriptor = HandoffEdge.descriptor.model_copy(
        update={
            "id": "data",
            "title": "넘기기(이전 이름 data)",
            "description": "handoff와 같다. 새 연결에는 handoff를 쓴다.",
            "ui_hints": UiHints(icon="→", hidden=True),
        },
        deep=True,
    )


# ---------------------------------------------------------------- subagent·uses (none)


_STRATEGY_DESCRIPTION: Final = "일을 맡기는 방법입니다. 비우면 이 연결 종류의 기본 방법을 씁니다."
_STRATEGY_WHEN: Final = "맡기는 방법을 이 연결 종류의 기본값과 다르게 하고 싶을 때 고르세요."


class SubagentEdgeConfig(BaseModel):
    """서브에이전트 위임 연결 설정."""

    model_config = ConfigDict(extra="forbid", title="서브에이전트 위임 설정")

    strategy: str | None = Field(
        default=None,
        min_length=1,
        title="위임 방식",
        description=_STRATEGY_DESCRIPTION,
        json_schema_extra=x_ui(tier="basic", when=_STRATEGY_WHEN, example=None),
    )


class _NotScheduled:
    """`scheduling = none` 연결의 공통 구현: 엔진이 평가하지 않는다."""

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """엔진은 `none` 연결을 평가하지 않는다. 직접 부르면 통과하지 않는다."""
        return None


class SubagentEdge(_NotScheduled):
    """연결 종류 `subagent`: 위 에이전트가 같은 세션 안에서 아래 에이전트를 부른다."""

    descriptor = EdgeTypeDescriptor(
        id="subagent",
        version=1,
        title="서브에이전트로 위임",
        description=(
            "위 에이전트가 스스로 판단해 필요할 때 아래 에이전트를 부른다. 아래 에이전트는 위 "
            "에이전트 세션 안에서 돌고 결과는 위 에이전트에게 돌아온다."
        ),
        scheduling="none",
        invocation=EdgeInvocation(strategy=SDK_SUBAGENTS),
        connects=EdgeConnects(source=[AGENT_ROLE], target=[AGENT_ROLE]),
        default_ports=EdgePortPair(source=DELEGATES_PORT, target=DELEGATED_PORT),
        config_schema=_schema(SubagentEdgeConfig),
        ui_hints=UiHints(icon="⤵"),
    )


class UsesEdgeConfig(BaseModel):
    """리소스 연결 설정(첨부 방식)."""

    model_config = ConfigDict(extra="forbid", title="리소스 연결 설정")

    mode: str | None = Field(
        default=None,
        title="방식",
        description=(
            "더하기(add, 기본), 에이전트·팀에서 붙인 같은 자리 바꾸기(replace), 빼기(remove)입니다."
        ),
        json_schema_extra={
            "enum": ["add", "replace", "remove"],
            **x_ui(
                enum_labels={"add": "더하기", "replace": "바꾸기", "remove": "빼기"},
                tier="basic",
                when="에이전트·팀에서 붙인 리소스를 이 연결로 바꾸거나 빼고 싶을 때 바꾸세요.",
            ),
        },
    )
    config_override: dict[str, Any] | None = Field(
        default=None,
        title="설정 덮어쓰기",
        description="이 연결에서만 바꿀 리소스 설정 값입니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class UsesEdge(_NotScheduled):
    """연결 종류 `uses`: 리소스 노드를 에이전트 노드에 붙인다(노드 층 첨부)."""

    descriptor = EdgeTypeDescriptor(
        id="uses",
        version=1,
        title="리소스 사용",
        description="리소스(지침·파일·MCP 등)를 에이전트에 붙인다. 실행되지 않는다.",
        scheduling="none",
        connects=EdgeConnects(source=[RESOURCE_ROLE], target=[AGENT_ROLE]),
        default_ports=EdgePortPair(source=PROVIDES_PORT, target=RESOURCES_PORT),
        config_schema=_schema(UsesEdgeConfig),
        ui_hints=UiHints(icon="⧉", dashed=True),
    )


HOST_STRATEGY: Final = "host"
"""`delegate` 연결의 기본 위임 방식 id(디스크립터 데이터). 구현은 별도 플러그인
(`agent-console-delegation-host`)이다 — 없으면 팀 검증이 "등록되지 않은 위임 방식" 경고를 낸다."""


class DelegateEdgeConfig(BaseModel):
    """독립 위임 연결 설정."""

    model_config = ConfigDict(extra="forbid", title="독립 위임 설정")

    strategy: str | None = Field(
        default=None,
        min_length=1,
        title="위임 방식",
        description=_STRATEGY_DESCRIPTION,
        json_schema_extra=x_ui(tier="basic", when=_STRATEGY_WHEN, example=None),
    )
    result: Literal["text", "reply"] | None = Field(
        default=None,
        title="돌려줄 결과",
        description=(
            "맡은 에이전트의 결과 글 전체(text, 기본)나 답변 연결로 고른 답변(reply)을 돌려줍니다."
        ),
        json_schema_extra=x_ui(
            enum_labels={"text": "결과 글 전체", "reply": "고른 답변"},
            tier="basic",
            when="맡은 에이전트의 긴 결과 대신 정리된 답변만 받고 싶을 때 reply로 바꾸세요.",
        ),
    )


class DelegateEdge(_NotScheduled):
    """연결 종류 `delegate`: 위 에이전트가 판단해 아래 에이전트를 독립 실행으로 부른다.

    아래 에이전트는 자기 NodeRun·세션·백엔드·설정으로 돌고(엔진 `invoke_node`), 결과는 위
    에이전트의 위임 도구 결과로 돌아온다. 0~여러 번 불리므로 아래 에이전트는 흐름 연결을 내보낼 수
    없다(위임 방식 디스크립터 `allows_outgoing_flow`).
    """

    descriptor = EdgeTypeDescriptor(
        id="delegate",
        version=1,
        title="독립 에이전트로 위임",
        description=(
            "위 에이전트가 스스로 판단해 필요할 때 아래 에이전트를 부른다. 아래 에이전트는 자기 "
            "세션·모델·리소스로 따로 돌고, 다시 위임하거나 사용자에게 되물을 수 있다."
        ),
        scheduling="none",
        invocation=EdgeInvocation(strategy=HOST_STRATEGY),
        connects=EdgeConnects(source=[AGENT_ROLE], target=[AGENT_ROLE]),
        default_ports=EdgePortPair(source=DELEGATES_PORT, target=DELEGATED_PORT),
        config_schema=_schema(DelegateEdgeConfig),
        ui_hints=UiHints(icon="⇲"),
    )


# ---------------------------------------------------------------- message (entry)


class MessageEdgeConfig(BaseModel):
    """사용자 메시지(입구) 연결 설정."""

    model_config = ConfigDict(extra="forbid", title="사용자 메시지 설정")

    input_key: str | None = Field(
        default=None,
        min_length=1,
        title="입력 키",
        description=(
            f"실행 입력에서 꺼낼 키입니다. 비우면 메시지 본문({DEFAULT_MESSAGE_KEY!r})입니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="question"),
    )
    template: str | None = Field(
        default=None,
        title="형식",
        description=(
            "꺼낸 값을 감쌀 틀입니다. {message}가 꺼낸 값이고 실행 입력의 다른 키도 씁니다."
        ),
        json_schema_extra=x_ui(tier="advanced", example="사용자 질문:\n{message}"),
    )


def _config[M: BaseModel](model: type[M], raw: Mapping[str, Any]) -> M | None:
    try:
        return model.model_validate(dict(raw))
    except ValidationError:
        return None


class MessageEdge:
    """연결 종류 `message`: 사용자(채팅) → 입구 노드. Run 입력에서 값을 꺼내 넣는다.

    소스 결과는 엔진이 만든 가상 결과(`outputs = {소스 포트: Run 입력 dict}`)다.
    `input_key`(생략 = `DEFAULT_MESSAGE_KEY`)의 값이 없으면 통과하지 않는다
    (그 입구는 실행되지 않음).
    """

    descriptor = EdgeTypeDescriptor(
        id="message",
        version=1,
        title="사용자 메시지",
        description="사용자의 메시지를 이 노드로 보낸다. 도착 노드가 입구가 된다.",
        scheduling="entry",
        connects=EdgeConnects(source=[USER_ROLE], target=[AGENT_ROLE, TEAM_ROLE]),
        default_ports=EdgePortPair(source=SAYS_PORT, target=IN_PORT),
        config_schema=_schema(MessageEdgeConfig),
        ui_schema={"template": {"ui:widget": "textarea"}},
        ui_hints=UiHints(icon="✉"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """Run 입력에서 값을 꺼내 `template`을 적용한 값을 넘긴다. 없으면 None."""
        ok, run_input = _passed_value(source, edge)
        cfg = _config(MessageEdgeConfig, edge.config)
        if not ok or not isinstance(run_input, Mapping) or cfg is None:
            return None
        key = cfg.input_key or DEFAULT_MESSAGE_KEY
        if key not in run_input:
            return None
        value = run_input[key]
        if cfg.template is None:
            return Activation(value)
        variables: dict[str, Any] = {
            str(k): as_text(v) for k, v in run_input.items() if isinstance(k, str)
        }
        variables["message"] = as_text(value)
        return Activation(render_template(cfg.template, variables))


# ---------------------------------------------------------------- reply (exit)


class ReplyEdgeConfig(BaseModel):
    """답변 연결 설정."""

    model_config = ConfigDict(extra="forbid", title="답변 설정")

    label: str | None = Field(
        default=None,
        title="이름",
        description="채팅에서 답변 머리에 보일 이름입니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="팀 답변이 여러 개일 때 무엇의 답인지 구분하고 싶을 때 적으세요.",
            example="요약",
        ),
    )
    order: int | None = Field(
        default=None,
        title="순서",
        description="답변이 여러 개일 때 보일 순서입니다(작을수록 위).",
        json_schema_extra=x_ui(tier="advanced", example=1),
    )
    final: bool = Field(
        default=True,
        title="최종 답변",
        description="끄면 이 답변을 '중간 결과'로 접어 보입니다.",
        json_schema_extra=x_ui(tier="advanced", when="중간 결과를 접어 두고 싶을 때 끄세요."),
    )
    stream: bool = Field(
        default=True,
        title="실행 중 표시",
        description="실행되는 동안 글이 써지는 모습을 채팅에 보일지 정합니다.",
        json_schema_extra=x_ui(tier="advanced"),
    )


class ReplyEdge:
    """연결 종류 `reply`: 출발 노드가 성공하면 그 출력을 채팅 답변(`run.reply`)으로 낸다.

    `stream`은 화면이 읽는 연결 데이터이며 답변 값에는 들어가지 않는다.
    """

    descriptor = EdgeTypeDescriptor(
        id="reply",
        version=1,
        title="답변",
        description="이 노드의 결과를 사용자에게 답변으로 보낸다(중간 노드도 가능).",
        scheduling="exit",
        connects=EdgeConnects(source=[AGENT_ROLE, TEAM_ROLE, USER_ROLE], target=[USER_ROLE]),
        default_ports=EdgePortPair(source=OUT_PORT, target=HEARS_PORT),
        # 답변 속성의 config 위치(H1): 서버 답변 계획(`ac-teams.plan_summary`)이 이 선언으로 읽는다
        reply_fields=ReplyFields(label="/label", order="/order", final="/final", stream="/stream"),
        config_schema=_schema(ReplyEdgeConfig),
        ui_hints=UiHints.model_validate(
            {
                "icon": "↩",
                "dashed": True,
                # 편집기 선언형 칩(design "선언형 배지·칩"). 첫 칩: 답변 이름(config /label)을 종류
                # title 뒤에 붙인다(E-4, 편집기는 config 키 이름을 모른다). 값이 비면 그리지 않는다.
                # 둘째 칩: final=false면 "중간 결과".
                "chips": [
                    {"value_pointer": "/label", "placement": "title"},
                    {
                        "label_key": "intermediate",
                        "label": "중간 결과",
                        "when": {"config_path": "final", "equals": False},
                    },
                ],
            }
        ),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """소스가 성공해 소스 포트에 값을 냈으면 `Activation(Reply(...))`."""
        ok, value = _passed_value(source, edge)
        if not ok:
            return None
        cfg = _config(ReplyEdgeConfig, edge.config) or ReplyEdgeConfig()
        return Activation(
            Reply(text=as_text(value), label=cfg.label, order=cfg.order, final=cfg.final)
        )


# ---------------------------------------------------------------- ask_user (none + interaction)


class AskUserEdgeConfig(BaseModel):
    """에이전트가 일하는 도중 사용자에게 묻거나 승인을 받을 수 있게 하는 연결 설정입니다."""

    # 키 이름은 `ac-teams` `TeamConventions`와 같다(docstring은 폼 머리말로 보이므로 여기 둔다).

    model_config = ConfigDict(extra="forbid", title="되묻기·승인 설정")

    kinds: list[str] | None = Field(
        default=None,
        title="허용할 종류",
        description=(
            "에이전트가 열 수 있는 요청 종류입니다(예: 되묻기만). 비우면 이 연결의 종류 전부."
        ),
        json_schema_extra={
            "uniqueItems": True,
            **x_ui(tier="basic", when="되묻기만 또는 승인만 허용하고 싶을 때 고르세요."),
        },
    )
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        title="응답 대기 한도(초)",
        description="답을 기다리는 시간입니다. 비우면 상호작용 설정을 따릅니다.",
        json_schema_extra=x_ui(
            tier="advanced",
            when="이 연결의 질문만 기다리는 시간을 다르게 하고 싶을 때 정하세요.",
            example=600,
            unit="초",
        ),
    )
    on_timeout: str | None = Field(
        default=None,
        title="한도 초과 시",
        description=(
            "답이 없을 때 요청만 닫을지(expire) 실행을 취소할지(cancel_run)입니다. 비우면 설정값."
        ),
        json_schema_extra={
            "enum": ["expire", "cancel_run"],
            **x_ui(
                enum_labels={"expire": "요청만 닫기", "cancel_run": "실행 취소"}, tier="advanced"
            ),
        },
    )
    label: str | None = Field(
        default=None,
        title="이름",
        description="연결선에 보일 이름입니다.",
        json_schema_extra=x_ui(tier="advanced", example="확인 받기"),
    )


class AskUserEdge(_NotScheduled):
    """연결 종류 `ask_user`: 이 연결이 있는 에이전트만 실행 중 사용자에게 묻거나 승인받는다.

    엔진은 평가하지 않는다(`scheduling = none`). 허용 종류는 디스크립터 `interaction.kinds`와
    엣지 config `kinds`의 교집합이며 `ac-teams.team_plan`이 노드별 grant로 계산한다.
    """

    descriptor = EdgeTypeDescriptor(
        id="ask_user",
        version=1,
        title="되묻기·승인 받기",
        description="이 에이전트가 실행 중 사용자에게 되묻거나 도구 사용 승인을 받을 수 있게 한다.",
        scheduling="none",
        interaction=EdgeInteraction(kinds=[QUESTION.id, TOOL_PERMISSION.id]),
        connects=EdgeConnects(source=[AGENT_ROLE], target=[USER_ROLE]),
        default_ports=EdgePortPair(source=OUT_PORT, target=ASKS_PORT),
        config_schema=_schema(AskUserEdgeConfig),
        ui_hints=UiHints(icon="?", dashed=True),
    )
