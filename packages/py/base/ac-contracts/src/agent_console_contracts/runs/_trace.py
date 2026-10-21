"""위임 흐름(트레이스): 실행 이벤트에서 만든 "누가 누구에게 일을 넘겼나"(design §R4.2).

span 사이 관계는 명시 id(`tool_use_id`·`node_path`·`edge.traversed`·`interaction_id`)로만 잇는다.
시간상 이웃을 인과로 잇지 않는다.
"""

from typing import Any

from pydantic import Field, model_validator

from agent_console_contracts._base import ContractModel, NonEmptyStr
from agent_console_contracts.common import Usage


class TraceSpan(ContractModel):
    """위임 흐름의 구간 하나."""

    id: NonEmptyStr
    kind: NonEmptyStr = Field(
        description="구간 종류 문자열. 알려진 값: node(자기 NodeRun), delegated(위 세션 안 위임), "
        "interaction(사용자 대기). 다른 값도 허용(호출 NodeRun·자식 Run 묶음 등, 해석은 화면)."
    )
    parent_id: str | None = Field(default=None, description="부모 span id(같은 세션 안 위임).")
    node_id: str | None = None
    node_path: list[str] = Field(default_factory=list)
    actor: str | None = Field(default=None, description="에이전트 정의 id.")
    attempt: int | None = None
    iteration: int | None = Field(default=None, ge=0, description="반복 회차.")
    call: int | None = Field(
        default=None, ge=0, description="호출 회차(위임자가 부른 NodeRun이면)."
    )
    run_id: str | None = Field(
        default=None,
        description="이 span이 속한 Run이 trace의 Run과 다르면(자식 Run) 그 Run id.",
    )
    status: str | None = None
    started_at: float | None = None
    ended_at: float | None = None
    usage: Usage | None = None
    session_id: str | None = Field(default=None, description="백엔드 세션 id(같은/별도 세션 표시).")
    tool_use_id: str | None = None
    interaction_id: str | None = None
    order: int | None = Field(default=None, ge=1, description="넘기기 순번(그래프 강조 배지).")
    task_preview: str | None = None
    result_preview: str | None = None


class TraceLink(ContractModel):
    """span 사이 화살표(넘기기 등). 부모-자식 관계는 `TraceSpan.parent_id`로 표현한다."""

    source: NonEmptyStr = Field(description="출발 span id.")
    target: NonEmptyStr = Field(description="도착 span id.")
    edge_id: str | None = None
    kind: str | None = Field(default=None, description="연결 종류 id(엣지 kind).")
    run_id: str | None = Field(default=None, description="도착 span이 자식 Run에 있으면 그 Run id.")


class Trace(ContractModel):
    """`GET /runs/{id}/trace` 응답."""

    run_id: NonEmptyStr
    spans: list[TraceSpan] = Field(default_factory=list)
    links: list[TraceLink] = Field(default_factory=list)


class HandoffCount(ContractModel):
    """여러 실행 집계 "누가 누구에게 몇 번" 한 칸.

    0.6.0부터 셀 모양 `{from, to, via?, count}`(로그 handoff)도 함께 싣는다.
    `from`=`source`, `to`=`target`, `via`=`kind`이고 한쪽만 주면 다른 쪽을 채운다(하위 호환).
    """

    source: NonEmptyStr = Field(description="넘긴 쪽 에이전트 정의 id(없으면 노드 id).")
    target: NonEmptyStr = Field(description="받은 쪽 에이전트 정의 id(없으면 노드 id).")
    kind: str | None = Field(default=None, description="연결 종류 id 또는 span 종류.")
    count: int = Field(ge=0)
    from_: str | None = Field(default=None, alias="from", description="= source(셀 모양 별칭).")
    to: str | None = Field(default=None, description="= target(셀 모양 별칭).")
    via: str | None = Field(default=None, description="= kind(전달 수단, 셀 모양 별칭).")

    @model_validator(mode="before")
    @classmethod
    def _fill_pairs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for old, new, new_name in (
            ("source", "from", "from_"),
            ("target", "to", "to"),
            ("kind", "via", "via"),
        ):
            new_value = out.get(new, out.get(new_name))
            if out.get(old) is None and new_value is not None:
                out[old] = new_value
            elif new_value is None and out.get(old) is not None:
                out[new] = out[old]
        return out


class HandoffMatrix(ContractModel):
    """`GET /runs/handoffs` 응답: 여러 실행의 위임·넘기기 집계."""

    cells: list[HandoffCount] = Field(default_factory=list)
    runs: int = Field(default=0, ge=0, description="집계에 쓴 실행 수.")
