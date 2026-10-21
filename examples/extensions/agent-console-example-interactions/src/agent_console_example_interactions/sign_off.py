"""상호작용 종류 `example.sign_off`(서명 받기)와 허용 연결 `example.ask_sign_off`.

상호작용 종류(X15)는 **디스크립터 데이터 하나**다. 엔진·서버·웹은 다음만 본다.

- ``request_schema``: 요청 payload 모양(화면이 요청 내용을 보여 줄 때 참고).
- ``response_schema``: 응답 검증 스키마. 웹은 모르는 ``ui_hints.renderer``면 이 스키마로
  폼을 만든다.
- ``free_text_path``: 자유 입력 답을 넣을 응답 위치(없으면 폼만).
- ``expire_response``: 시간이 지나 닫힐 때 쓸 응답(없으면 만료 응답 없음).

노드가 이 종류를 열 수 있는지는 노드에서 나가는 연결 종류의 ``interaction.kinds``가 정한다.
그래서 허용 연결(``scheduling = none``, 엔진이 평가하지 않음)을 함께 둔다.
"""

from __future__ import annotations

from typing import Final

from agent_console_contracts import (
    EdgeConnects,
    EdgeInteraction,
    EdgePortPair,
    EdgeSpec,
    EdgeTypeDescriptor,
    InteractionKindDescriptor,
    UiHints,
)
from agent_console_runtime import Activation, NodeRunView

INTERACTION_KIND_ID: Final = "example.sign_off"
"""상호작용 종류 id(entry point 이름과 같다)."""
EDGE_TYPE_ID: Final = "example.ask_sign_off"
"""허용 연결 종류 id(entry point 이름·그래프 엣지 `kind`와 같다)."""
RENDERER: Final = "example-sign-off"
"""화면 힌트 renderer 이름. 웹이 모르는 이름이라 응답 스키마 폼으로 대신 그린다."""

SIGN_OFF = InteractionKindDescriptor(
    id=INTERACTION_KIND_ID,
    version=1,
    title="서명 받기",
    description="문서·결과물에 사용자의 승인과 메모를 받는다(예제 확장).",
    request_schema={
        "type": "object",
        "properties": {"text": {"type": "string", "title": "서명 대상"}},
    },
    response_schema={
        "type": "object",
        "properties": {
            "approved": {"type": "boolean", "title": "승인함"},
            "note": {"type": "string", "title": "메모"},
        },
        "required": ["approved"],
        "additionalProperties": False,
    },
    free_text_path=None,
    expire_response=None,
    ui_hints=UiHints(renderer=RENDERER, icon="S"),
)
"""상호작용 종류 `example.sign_off` 디스크립터. entry point가 이 객체를 직접 가리킨다."""


class AskSignOffEdge:
    """연결 종류 `example.ask_sign_off`: 이 연결이 나가는 에이전트만 서명 요청을 열 수 있다."""

    descriptor = EdgeTypeDescriptor(
        id=EDGE_TYPE_ID,
        version=1,
        title="서명 받기 허용",
        description="에이전트가 실행 중 사용자에게 서명(승인·메모)을 받을 수 있게 한다(예제 확장).",
        scheduling="none",
        interaction=EdgeInteraction(kinds=[INTERACTION_KIND_ID]),
        connects=EdgeConnects(source=["agent"], target=["user"]),
        default_ports=EdgePortPair(source="out", target="asks"),
        config_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ui_hints=UiHints(icon="S", dashed=True),
    )

    def activates(self, source: NodeRunView, edge: EdgeSpec) -> Activation | None:
        """`scheduling = none` 연결은 엔진이 평가하지 않는다. 직접 불러도 통과하지 않는다."""
        return None
