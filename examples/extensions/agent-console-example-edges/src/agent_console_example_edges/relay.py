"""연결 종류 `example.relay`: 위 노드 결과 앞에 접두어를 붙여 아래 노드에 넘긴다.

EdgeType(X2)은 두 가지만 갖추면 된다.

1. ``descriptor`` — 엔진·편집기·검증은 이름이 아니라 이 속성으로 연결을 다룬다.
   - ``scheduling``: 엔진 어휘(`flow` = 위 노드가 끝나면 값을 흘린다).
   - ``connects``: 어떤 노드 역할(`NodeTypeDescriptor.role`)끼리 이을 수 있는지.
   - ``default_ports``: 편집기가 새 연결을 만들 때 쓰는 포트.
   - ``config_schema``·``ui_hints``: 연결 설정 폼과 선 모양.
2. ``activates(source, edge)`` — 통과하면 ``Activation(값)``, 막으면 None(dead-path).

동작은 결정적이다(외부 호출·시간·환경에 의존하지 않는다).
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    EdgeConnects,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    UiHints,
)
from agent_console_runtime import Activation, NodeRunView

EDGE_TYPE_ID: Final = "example.relay"
"""디스크립터 id. pyproject의 entry point 이름·그래프 엣지 `kind`와 같다."""

AGENT_ROLE: Final = "agent"
"""이을 수 있는 노드 역할 문자열(기본 에이전트 노드 타입의 `role` 값). 고정 목록이 아니다."""


class RelayConfig(BaseModel):
    """넘길 값 앞에 붙일 글."""

    model_config = ConfigDict(extra="forbid", title="중계 설정")

    prefix: str = Field(
        default="[중계] ",
        title="접두어",
        description="위 노드 결과 앞에 붙인다. 결과가 문자열이 아니면 붙이지 않고 그대로 넘긴다.",
    )


class RelayEdge:
    """연결 종류 `example.relay`(X2 예제 구현)."""

    descriptor = EdgeTypeDescriptor(
        id=EDGE_TYPE_ID,
        version=1,
        title="접두어 붙여 넘기기",
        description="위 노드가 끝나면 결과 앞에 접두어를 붙여 아래 노드에 넘긴다(예제 확장).",
        scheduling="flow",
        connects=EdgeConnects(source=[AGENT_ROLE], target=[AGENT_ROLE]),
        default_ports=EdgePortPair(source="out", target="in"),
        config_schema=RelayConfig.model_json_schema(),
        ui_hints=UiHints(icon="⇒"),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """위 노드가 성공해 소스 포트에 값을 냈으면 통과. 설정이 틀리면 기본값을 쓴다."""
        if source.status != "succeeded" or edge.source.port not in source.outputs:
            return None
        value = source.outputs[edge.source.port]
        try:
            prefix = RelayConfig.model_validate(dict(edge.config)).prefix
        except ValidationError:
            prefix = RelayConfig().prefix  # 형식 오류는 그래프 검증(JSON Schema)이 보고한다
        return Activation(f"{prefix}{value}" if isinstance(value, str) else value)
