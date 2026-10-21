"""팀 규칙: 연결 규칙(`connects`)과 정의 참조(에이전트·리소스)."""

from __future__ import annotations

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue

_C = TeamIssueCodes

__all__ = ["check_connects", "check_refs"]


def check_connects(ctx: TeamCheckContext) -> None:
    """엣지 디스크립터 `connects`가 허용하지 않는 역할끼리 이은 연결(error)."""
    plan = ctx.plan
    for eid, desc in plan.edge_descriptors.items():
        edge = plan.edge(eid)
        if edge is None or desc.connects is None:
            continue
        src_role = plan.role_of(edge.source.node)
        dst_role = plan.role_of(edge.target.node)
        bad = []
        if desc.connects.source and src_role not in desc.connects.source:
            bad.append("source")
        if desc.connects.target and dst_role not in desc.connects.target:
            bad.append("target")
        if bad:
            ctx.add(
                make_issue(
                    "error",
                    _C.CONNECTS_MISMATCH,
                    f"연결 종류 '{desc.title}'은(는) 이 노드끼리 이을 수 없습니다",
                    edge_id=eid,
                    details={
                        "sides": bad,
                        "source_role": src_role,
                        "target_role": dst_role,
                        "allowed": desc.connects.model_dump(),
                    },
                )
            )


def check_refs(ctx: TeamCheckContext) -> None:
    """노드가 묶은 에이전트(error)·리소스(warning) 정의가 없음. 조회 수단이 없으면 건너뛴다."""
    plan = ctx.plan
    if ctx.agents is not None:
        for nid, ref in plan.agent_refs.items():
            if ref not in ctx.agents:
                ctx.add(
                    make_issue(
                        "error",
                        _C.AGENT_NOT_FOUND,
                        f"'{ctx.label(nid)}' 노드의 에이전트 정의를 찾을 수 없습니다",
                        node_id=nid,
                        details={"agent": ref},
                    )
                )
    if ctx.resources is not None:
        for nid, ref in plan.resource_refs.items():
            if ctx.resources.get_resource(ref) is None:
                ctx.add(
                    make_issue(
                        "warning",
                        _C.RESOURCE_NOT_FOUND,
                        f"'{ctx.label(nid)}' 노드의 리소스를 찾을 수 없습니다",
                        node_id=nid,
                        details={"resource": ref},
                    )
                )
