"""팀 규칙: 리소스 칸 — 붙인 리소스가 채우는 칸을 실행 백엔드가 받지 않으면 경고(design §2R.8).

칸 판정은 묶음 미리보기(`_preview.compose_preview`)와 같은 함수(`node_bundle` + 백엔드
`resource_slots`·`slot_notes`)로 한다. 위임받는 노드는 세션 주인 노드의 백엔드로 판정한다.
칸 이름·백엔드 이름·리소스 종류 이름은 이 모듈에 없다. 리소스 종류·조회가 없으면 건너뛴다.
"""

from __future__ import annotations

from agent_console_contracts import KnownIssueCodes

from ._check_context import TeamCheckContext
from ._settings import node_bundle, node_settings

__all__ = ["check_resource_slots"]


def check_resource_slots(ctx: TeamCheckContext) -> None:
    """에이전트 노드마다 묶음을 조립해 받지 않는 칸 경고(`resource.slot_unsupported`)를 낸다."""
    if ctx.resource_types is None or ctx.resources is None:
        return
    plan = ctx.plan
    for nid in ctx.node_order():
        if nid not in plan.agent_refs and not plan.attachments_of.get(nid):
            continue
        backend = ctx.backend_of(ctx.session_owner(nid))
        caps = ctx.backends.get(backend) if backend else None
        if caps is None:
            continue
        settings = node_settings(
            plan,
            nid,
            agents=ctx.agents,
            workspace=ctx.workspace,
            strategies=ctx.strategies,
            resource_types=ctx.resource_types,
            resources=ctx.resources,
        )
        if not settings.attachments:
            continue
        composed = node_bundle(
            settings,
            resource_types=ctx.resource_types,
            resources=ctx.resources,
            accepted_slots=caps.resource_slots,
            slot_notes=caps.slot_notes,
        )
        for issue in composed.issues:
            if issue.code != KnownIssueCodes.RESOURCE_SLOT_UNSUPPORTED:
                continue
            ctx.add(
                issue.model_copy(
                    update={"node_id": nid, "details": {**issue.details, "backend": backend}}
                )
            )
