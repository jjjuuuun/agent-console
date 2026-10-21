"""팀 규칙: 반복(사이클 연결, design §5R.4·§5R.8).

근거는 연결 종류 디스크립터 `cycle`(사이클 연결)과 설정 `flow.max_iterations`뿐이다. 반복 영역은
`ac-graph.loop_regions`, 유효 최대 반복은 `ac-graph.effective_max_iterations`(엔진과 같은 함수)로
계산한다. 흐름 사이클을 사이클 연결이 닫았는지는 그래프 검사(`validate_graph(cycle_edge=
descriptor_cycle_edge)`)가 본다.
"""

from __future__ import annotations

from agent_console_graph import CYCLE_LIMIT_CONFIG_KEY, effective_max_iterations

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue

_C = TeamIssueCodes

__all__ = ["check_loops"]


def check_loops(ctx: TeamCheckContext) -> None:
    """사이클 연결의 최대 반복이 올바르지 않음·반복 영역 안 위임으로만 불리는 노드."""
    _check_max_iterations(ctx)
    _check_invoked_in_region(ctx)


def _edge_name(ctx: TeamCheckContext, edge_id: str) -> str:
    edge = ctx.plan.edge(edge_id)
    if edge is None:
        return edge_id
    return f"{ctx.label(edge.source.node)} → {ctx.label(edge.target.node)}"


def _check_max_iterations(ctx: TeamCheckContext) -> None:
    plan = ctx.plan
    seen: set[str] = set()
    for edge in plan.graph.edges:
        desc = plan.edge_descriptors.get(edge.id)
        if desc is None or desc.cycle is None or edge.id in seen:
            continue
        seen.add(edge.id)
        value = effective_max_iterations(edge, desc, ctx.max_iterations_setting)
        if value is not None and value >= 1:
            continue
        raw = edge.config.get(CYCLE_LIMIT_CONFIG_KEY)
        shown = "없음" if value is None else str(value)
        ctx.add(
            make_issue(
                "error",
                _C.MAX_ITERATIONS_INVALID,
                f"'{_edge_name(ctx, edge.id)}' 반복 연결의 최대 반복 횟수가 올바르지 않습니다. "
                f"1 이상의 정수여야 합니다(현재 유효 값: {shown}).",
                edge_id=edge.id,
                path=f"/{CYCLE_LIMIT_CONFIG_KEY}" if raw is not None else None,
                details={"value": raw, "effective": value},
            )
        )


def _check_invoked_in_region(ctx: TeamCheckContext) -> None:
    plan = ctx.plan
    reported: set[str] = set()
    for region in ctx.regions.values():
        for nid in region.nodes:
            if nid in reported or nid not in plan.callees or ctx.opening_inbound(nid):
                continue
            reported.add(nid)
            ctx.add(
                make_issue(
                    "error",
                    _C.LOOP_INVOKED_ONLY,
                    f"'{ctx.label(nid)}'은(는) 위임으로만 불려서 반복 영역 안에서 실행되지 "
                    "않습니다. 반복 영역 밖으로 옮기거나 이 노드로 들어오는 흐름 연결을 "
                    "추가하세요.",
                    node_id=nid,
                    edge_id=region.edge_id,
                    details={
                        "loop_edge": region.edge_id,
                        "region": list(region.nodes),
                        "delegation_edges": [link.edge_id for link in plan.callers_of.get(nid, ())],
                    },
                )
            )
