"""팀 규칙: 입구·답변·도달(design §R1.2a — 명시된 연결만, 모양으로 추론하지 않는다)."""

from __future__ import annotations

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue

_C = TeamIssueCodes

__all__ = ["check_entry_reply"]


def _no_inbound(ctx: TeamCheckContext) -> list[str]:
    """실행 가능한데 흐름·입구로 들어오는 엣지가 없고 위임받지도 않는 노드(사용자 쪽 제외).

    반복을 닫는 사이클 연결만 들어오는 노드도 여기 든다(첫 회차에 지나가지 않으므로).
    """
    plan = ctx.plan
    return [
        nid
        for nid in ctx.node_order()
        if nid in plan.view.executable
        and not ctx.opening_inbound(nid)
        and nid not in plan.callees
        and not ctx.is_outside(nid)
    ]


def check_entry_reply(ctx: TeamCheckContext) -> None:
    """입구 없음(error, 실행 차단)·답변 없음(warning)·도달 불가(warning)·실행 안 되는 입구."""
    plan = ctx.plan
    for eid in plan.entries:
        edge = plan.edge(eid)
        if edge is not None and edge.target.node not in plan.view.executable:
            ctx.add(
                make_issue(
                    "warning",
                    _C.ENTRY_NOT_EXECUTABLE,
                    f"입구 연결이 실행되지 않는 노드 '{ctx.label(edge.target.node)}'로 갑니다",
                    edge_id=eid,
                )
            )
    unreachable = _no_inbound(ctx)
    if not plan.entry_nodes:
        candidates = unreachable or [
            n
            for n in ctx.node_order()
            if n in plan.view.executable and n not in plan.callees and not ctx.is_outside(n)
        ]
        ctx.add(
            make_issue(
                "error",
                _C.NO_ENTRY,
                "입구가 없습니다. 사용자 메시지를 받을 노드로 입구 연결을 그려 주세요",
                suggestions=[ctx.entry_suggestion(n, i) for i, n in enumerate(candidates)],
                blocks_run=True,
            )
        )
    if not plan.answers:
        sinks = [
            n
            for n in ctx.node_order()
            if n in plan.view.executable
            and n not in plan.callees
            and not plan.view.outgoing.get(n)
            and not ctx.is_outside(n)
        ]
        ctx.add(
            make_issue(
                "warning",
                _C.NO_REPLY,
                "답변 연결이 없습니다. 실행은 되지만 채팅에 답변이 나오지 않습니다",
                suggestions=[ctx.reply_suggestion(n, i) for i, n in enumerate(sinks)],
                blocks_run=False,
            )
        )
    for i, nid in enumerate(unreachable):
        ctx.add(
            make_issue(
                "warning",
                _C.UNREACHABLE,
                f"'{ctx.label(nid)}'은(는) 들어오는 흐름·입구·위임 연결이 없어 실행되지 않습니다",
                node_id=nid,
                suggestions=[ctx.entry_suggestion(nid, i)],
            )
        )
