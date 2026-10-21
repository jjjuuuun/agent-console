"""연결 종류 `loop`(사이클 연결, design §5R.4).

엔진·검증·편집기는 이 이름을 모른다. 디스크립터 `cycle`이 있으면 흐름 사이클을 닫을 수 있고, 지나갈
때 엔진이 반복 영역을 새 회차로 다시 연다. 최대 반복은 엣지 config `max_iterations` → 설정
`flow.max_iterations` → 디스크립터 `cycle.max_iterations` 순이다(엔진 `ac-graph.
effective_max_iterations`).
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import (
    CyclePolicy,
    EdgeConnects,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_runtime import Activation, NodeRunView

from ._common import AGENT_ROLE, IN_PORT, OUT_PORT, TEAM_ROLE, USER_ROLE

DEFAULT_LOOP_MAX_ITERATIONS: Final = 3
"""`loop` 연결 종류의 기본 최대 반복(디스크립터 `cycle.max_iterations` 데이터)."""


class LoopEdgeConfig(BaseModel):
    """반복 연결 설정."""

    model_config = ConfigDict(extra="forbid", title="반복 설정")

    # 키 이름은 엔진이 읽는 약속(`ac-graph.CYCLE_LIMIT_CONFIG_KEY`, 이슈 path `/max_iterations`).
    max_iterations: int | None = Field(
        default=None,
        ge=1,
        title="최대 반복 횟수",
        description=(
            "이 연결로 되돌아가는 최대 횟수입니다. 비우면 흐름 설정, 그다음 기본값을 씁니다."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="고쳐 쓰기 반복을 이 연결에서만 더 허용하거나 줄이고 싶을 때 바꾸세요.",
            example=3,
            unit="회",
        ),
    )


class LoopEdge:
    """연결 종류 `loop`: 위 노드가 성공해 소스 포트에 값을 냈으면 앞 단계로 되돌려 다시 실행한다.

    예: 검토 노드의 `rejected` 결정 포트 → 작성자 `in`. 작성자의 다음 회차 입력은 반려 내용이다.
    값을 내지 않은 포트(고르지 않은 결정)는 지나가지 않는다.
    """

    descriptor = EdgeTypeDescriptor(
        id="loop",
        version=1,
        title="반복",
        description=(
            "위 노드의 결과를 앞 단계로 되돌려 그 사이 노드들을 다시 실행한다. 최대 반복 횟수에 "
            "닿으면 더 되돌리지 않고 위 노드의 다른 연결이 이어진다."
        ),
        scheduling="flow",
        cycle=CyclePolicy(max_iterations=DEFAULT_LOOP_MAX_ITERATIONS, title="반복"),
        connects=EdgeConnects(
            source=[AGENT_ROLE, TEAM_ROLE, USER_ROLE], target=[AGENT_ROLE, TEAM_ROLE, USER_ROLE]
        ),
        default_ports=EdgePortPair(source=OUT_PORT, target=IN_PORT),
        config_schema=LoopEdgeConfig.model_json_schema(),
        ui_hints=UiHints(icon="↻"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """소스가 성공해 소스 포트에 값을 냈으면 그 값을 넘긴다(반복 여부·한도는 엔진이 정한다)."""
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        value: Any = source.outputs[edge.source.port]
        return Activation(value)
