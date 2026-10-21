"""조건·실패 연결 종류(X2, design §5R.5): `when`, `on_error`.

엔진·편집기·`ac-teams`는 이 id들을 모른다. 엔진은 `activates`의 결과(`Activation`·`Blocked`·None)만
보고, 편집기는 디스크립터(`handles_failure`)와 config 스키마(`ui_schema`의 `condition-list` 위젯)로
그린다. 선 모양은 화면이 디스크립터 속성 기본값으로 정하므로 `ui_hints`를 두지 않는다.
조건 평가는 `ac-conditions`(연산자 레지스트리 X22)가 한다.

| id | scheduling | 의미 |
| --- | --- | --- |
| `when` | flow | 출발 노드가 성공해 포트에 값을 냈고 조건(config `conditions`)이 참이면 넘긴다 |
| `on_error` | flow, `handles_failure` | 출발 노드가 실패했을 때만 `{error, node_id}`를 넘긴다 |
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_conditions import (
    DEFAULT_MAX_ACTUAL_CHARS,
    ConditionIssueCodes,
    ConditionOperator,
    ConditionReasons,
    Redactor,
    condition_issues,
    default_operators,
    evaluate_conditions,
)
from agent_console_contracts import (
    ConditionSpec,
    EdgeConnects,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    Issue,
    LogWarningPayload,
    x_ui,
)
from agent_console_runtime import Activation, Blocked, EdgeValidationContext, NodeRunView

from ._common import AGENT_ROLE, IN_PORT, OUT_PORT, TEAM_ROLE, USER_ROLE

CONDITION_FALSE: Final = "condition_false"
"""`edge.skipped.reason`: 조건이 거짓이라 지나가지 않았다."""

CONDITIONS_KEY: Final = "conditions"
"""`when` config에서 조건(`ConditionSpec`)이 있는 키."""

CONDITION_WIDGET: Final = "condition-list"
"""조건 편집 위젯 이름(`ui:widget`, 화면 명세 screen-delegation §2.4.3). 이름은 데이터다."""

# 판단 대상 경로 제안(화면 콤보박스, 스키마 `examples`)과 그 제목(`ui:options.path_titles`).
# 판단 대상 모양은 `condition_subject`가 정한다(design §5R.5).
SUBJECT_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("/output", "출력"),
    ("/structured", "구조화 결과"),
    ("/status", "상태"),
    ("/iteration", "반복 회차"),
    ("/error/code", "오류 코드"),
    ("/error/message", "오류 메시지"),
)

type OperatorSource = (
    Mapping[str, ConditionOperator] | Callable[[], Mapping[str, ConditionOperator]]
)
"""연산자 공급: 고정 사전 또는 부를 때마다 지금 목록을 주는 함수(레지스트리 보기)."""


def condition_subject(source: NodeRunView, edge: EdgeSpec) -> dict[str, Any]:
    """조건 판단 대상(design §5R.5): `{output?, structured?, status, iteration, error?}`.

    - `output`: 출발 포트 값(값을 냈을 때만).
    - `structured`: 노드 구조화 결과(`NodeRunView.structured`가 있을 때만).
    - `status`·`iteration`: 출발 NodeRun의 상태·반복 회차(0부터).
    - `error`: 실패였으면 `{code, message}`.
    """
    subject: dict[str, Any] = {"status": source.status, "iteration": source.iteration}
    if edge.source.port in source.outputs:
        subject["output"] = source.outputs[edge.source.port]
    if source.structured is not None:
        subject["structured"] = source.structured
    if source.error is not None:
        subject["error"] = {"code": source.error.code, "message": source.error.message}
    return subject


# ---------------------------------------------------------------- when


class WhenEdgeConfig(BaseModel):
    """조건 연결 설정. 조건을 비우면 항상 지나간다(저장 전 검사 warning)."""

    model_config = ConfigDict(extra="forbid", title="조건 연결 설정")

    conditions: ConditionSpec | None = Field(
        default=None,
        title="조건",
        description=(
            "앞 노드 결과(출력·구조화 결과·반복 회차)로 지나갈지 정하는 조건입니다. 비우면 항상 "
            "지나갑니다."
        ),
        json_schema_extra=x_ui(
            tier="basic", when="결과에 따라 다른 길로 보내고 싶을 때 조건을 더하세요."
        ),
    )


def _when_schema() -> dict[str, Any]:
    """config 스키마 + 조건 항목 경로 필드의 제안 `examples`(화면 명세 §12 S4)."""
    schema = copy.deepcopy(WhenEdgeConfig.model_json_schema())
    item = schema.get("$defs", {}).get("ConditionItem", {})
    path = item.get("properties", {}).get("path")
    if isinstance(path, dict):
        path["examples"] = [p for p, _ in SUBJECT_PATHS]
    return schema


def _parse_when(raw: Mapping[str, Any]) -> WhenEdgeConfig | None:
    try:
        return WhenEdgeConfig.model_validate(dict(raw))
    except ValidationError:
        return None


class WhenEdge:
    """연결 종류 `when`: 조건이 참일 때만 지나가는 흐름 연결.

    - 출발 노드가 성공하고 출발 포트에 값을 냈을 때만 조건을 평가한다(아니면 None = 이벤트 없는
      dead-path, `handoff`와 같다). 실패 처리는 `on_error` 같은 실패 처리 연결의 몫이다.
    - 참이면 `Activation(포트 값, condition=근거)`, 거짓이면 `Blocked("condition_false", 근거)`.
      근거의 실제 값은 가림 함수(`redact`)를 건 **뒤에** `max_actual_chars`에서 잘린다 — 잘린
      비밀 조각은 엔진 기록 단계의 가림이 알아보지 못하기 때문이다(design §5.2R.7).
    - 모르는 연산자 항목은 거짓이고 항목마다 경고(`log.warning`, `details.code` =
      `condition.unknown_operator`)를 단다.

    Args:
        operators: 연산자 공급. 생략하면 처음 쓸 때 설치된 entry point
            (`agent_console.condition_operators`)를 읽는다(`ac-conditions.default_operators`).
            만든 뒤 `use_operators`로 바꿀 수 있다(앱이 자기 연산자 레지스트리를 줄 때).
        max_actual_chars: 판정 근거 `actual` 길이 상한.
        redact: 판정 근거의 실제 값을 자르기 전에 거는 가림 함수(예: 엔진
            `SecretResolver.redact`). 만든 뒤 `use_redactor`로 바꿀 수 있다
            (`ac-conditions.RedactorConsumer`, 실행 모듈이 부른다).
    """

    descriptor = EdgeTypeDescriptor(
        id="when",
        version=1,
        title="조건에 따라 지나감",
        description=(
            "위 노드가 끝나면 결과를 조건으로 확인해, 조건이 맞을 때만 아래 노드에 넘긴다 "
            "(예: 출력에 'PASS'가 있으면)."
        ),
        scheduling="flow",
        connects=EdgeConnects(
            source=[AGENT_ROLE, TEAM_ROLE, USER_ROLE], target=[AGENT_ROLE, TEAM_ROLE, USER_ROLE]
        ),
        default_ports=EdgePortPair(source=OUT_PORT, target=IN_PORT),
        config_schema=_when_schema(),
        ui_schema={
            CONDITIONS_KEY: {
                "ui:widget": CONDITION_WIDGET,
                "ui:options": {"path_titles": dict(SUBJECT_PATHS)},
            }
        },
    )

    def __init__(
        self,
        operators: OperatorSource | None = None,
        *,
        max_actual_chars: int = DEFAULT_MAX_ACTUAL_CHARS,
        redact: Redactor | None = None,
    ) -> None:
        self._source = operators
        self._loaded: Mapping[str, ConditionOperator] | None = None
        self._max_actual_chars = max_actual_chars
        self._redact = redact

    def use_operators(self, source: Callable[[], Mapping[str, ConditionOperator]]) -> None:
        """앱의 연산자 레지스트리를 쓴다(`ac-conditions.OperatorConsumer`, 실행 모듈이 부른다)."""
        self._source = source
        self._loaded = None

    def use_redactor(self, redact: Redactor | None) -> None:
        """판정 근거를 자르기 전에 `redact`로 가린다(`ac-conditions.RedactorConsumer`)."""
        self._redact = redact

    def operators(self) -> Mapping[str, ConditionOperator]:
        """지금 쓰는 연산자(id → 연산자)."""
        if callable(self._source):
            return self._source()
        if self._source is not None:
            return self._source
        if self._loaded is None:
            self._loaded, _reports = default_operators()
        return self._loaded

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | Blocked | None:
        """조건이 참이면 통과(근거 포함), 거짓이면 `Blocked`(근거 포함)."""
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        cfg = _parse_when(edge.config)
        if cfg is None:
            return None
        spec = cfg.conditions or ConditionSpec()
        outcome = evaluate_conditions(
            spec,
            condition_subject(source, edge),
            self.operators(),
            redact=self._redact,
            max_actual_chars=self._max_actual_chars,
        )
        warnings = tuple(
            LogWarningPayload(
                message=(
                    f"조건 연산자 {item.op!r}이(가) 등록되어 있지 않아 이 항목을 거짓으로 봅니다"
                ),
                details={
                    "code": ConditionIssueCodes.UNKNOWN_OPERATOR,
                    "op": item.op,
                    "path": item.path,
                },
            )
            for item in outcome.items or []
            if item.reason == ConditionReasons.UNKNOWN_OPERATOR
        )
        if outcome.result:
            value = source.outputs[edge.source.port]
            return Activation(value, condition=outcome, warnings=warnings)
        return Blocked(reason=CONDITION_FALSE, condition=outcome, warnings=warnings)

    def validate_edge(self, edge: EdgeSpec, ctx: EdgeValidationContext) -> list[Issue]:
        """저장 전 검사: `condition_issues`(모르는 연산자 warning, 값 error, 빈 조건 warning)."""
        cfg = _parse_when(edge.config)
        if cfg is None:
            return []
        return condition_issues(
            cfg.conditions or ConditionSpec(),
            self.operators(),
            base_path=f"/{CONDITIONS_KEY}",
            edge_id=edge.id,
        )


# ---------------------------------------------------------------- on_error


class _EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", title="설정 없음")


class OnErrorEdge:
    """연결 종류 `on_error`: 출발 노드가 실패했을 때만 지나간다(`handles_failure`).

    넘기는 값은 `{"error": {"code", "message"}, "node_id": 출발 노드}`이다. 지나가면 엔진은
    그 실패를 처리됨으로 보고(design §4.3 종료 판정 3) Run을 실패로 끝내지 않는다.
    출발 노드가 성공하면 None.
    """

    descriptor = EdgeTypeDescriptor(
        id="on_error",
        version=1,
        title="실패하면 넘기기",
        description=(
            "위 노드가 실패했을 때만 오류 정보를 아래 노드에 넘긴다. 이 연결이 지나가면 실패는 "
            "처리된 것으로 본다."
        ),
        scheduling="flow",
        handles_failure=True,
        connects=EdgeConnects(
            source=[AGENT_ROLE, TEAM_ROLE, USER_ROLE], target=[AGENT_ROLE, TEAM_ROLE, USER_ROLE]
        ),
        default_ports=EdgePortPair(source=OUT_PORT, target=IN_PORT),
        config_schema=_EmptyConfig.model_json_schema(),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """출발 노드가 실패했으면 `Activation({error, node_id})`, 아니면 None."""
        if source.status != "failed":
            return None
        error = (
            {"code": source.error.code, "message": source.error.message}
            if source.error is not None
            else {"code": "", "message": ""}
        )
        return Activation({"error": error, "node_id": source.node_id})
