"""팀 규칙: 상호작용(design §R14) — 허용 종류 좁힘, 위임·백엔드 제약, 백엔드 훅, 검토 결정."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_console_contracts import (
    EdgeTypeDescriptor,
    InteractionGrant,
    Issue,
    IssueSuggestion,
)
from agent_console_settings import get_at

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue
from ._plan import runs_in_own_session, session_grant

_C = TeamIssueCodes

__all__ = ["check_interactions"]


def check_interactions(ctx: TeamCheckContext) -> None:
    """허용하지 않는 종류 좁힘·위임 방식/백엔드가 못 받는 종류·백엔드 훅·막힌 검토 결정."""
    plan = ctx.plan
    for eid in (e for ids in plan.grant_edges.values() for e in ids):
        edge = plan.edge(eid)
        desc = plan.edge_descriptors.get(eid)
        narrowed = edge.config.get(ctx.c.edge_kinds_key) if edge is not None else None
        if desc is None or desc.interaction is None or not isinstance(narrowed, list):
            continue
        unknown = [k for k in narrowed if k not in desc.interaction.kinds]
        if unknown:
            ctx.add(
                make_issue(
                    "warning",
                    _C.INTERACTION_KINDS_NOT_ALLOWED,
                    f"연결 종류 '{desc.title}'이(가) 허용하지 않는 상호작용 종류는 무시됩니다",
                    edge_id=eid,
                    details={"kinds": [str(k) for k in unknown]},
                )
            )
    for nid in plan.grants:
        for link in plan.callers_of.get(nid, ()):
            sdesc = ctx.strategies.get(link.strategy)
            if sdesc is None or sdesc.member_interaction_kinds is None:
                continue
            _narrow_issues(
                ctx,
                nid,
                list(sdesc.member_interaction_kinds),
                _C.INTERACTION_UNSUPPORTED_IN_DELEGATE,
                f"위임받는 '{ctx.label(nid)}'은(는) 위임 방식 '{sdesc.title}'에서 "
                "일부 상호작용을 열 수 없습니다",
                {"strategy": link.strategy},
            )
        owner = ctx.session_owner(nid)
        backend = ctx.backend_of(owner)
        caps = ctx.backends.get(backend) if backend is not None else None
        if caps is not None and caps.interactions is not None:
            _narrow_issues(
                ctx,
                nid,
                list(caps.interactions),
                _C.INTERACTION_UNSUPPORTED_BY_BACKEND,
                f"'{ctx.label(nid)}'의 백엔드가 일부 상호작용 종류를 받을 수 없습니다",
                {"backend": backend},
            )
    _run_hooks(ctx)
    _check_review(ctx)


def _narrow_issues(
    ctx: TeamCheckContext,
    node_id: str,
    allowed: list[str],
    code: str,
    message: str,
    details: dict[str, Any],
) -> None:
    for edge in ctx.grant_edges(node_id):
        kinds = ctx.edge_kinds(edge.id)
        extra = [k for k in kinds if k not in allowed]
        if not extra:
            continue
        keep = [k for k in kinds if k in allowed]
        ctx.add(
            make_issue(
                "warning",
                code,
                message,
                node_id=node_id,
                edge_id=edge.id,
                details={**details, "kinds": extra},
                suggestions=[
                    ctx.suggest.narrow(
                        edge,
                        keep,
                        kinds_key=ctx.c.edge_kinds_key,
                        suggestion_id=f"narrow:{edge.id}",
                    )
                ],
            )
        )


def _run_hooks(ctx: TeamCheckContext) -> None:
    """백엔드 `validate_settings` 훅(세션 단위). 훅 예외는 `team.validator_failed` 경고.

    같은 세션 방식으로만 불리는 위임 대상은 위임자 세션의 일부라 건너뛴다. 자기 세션에서 도는
    대상(`shares_session` false 방식)은 자기 grant로 따로 검사한다.
    """
    plan = ctx.plan
    if not ctx.validators:
        return
    for nid in ctx.node_order():
        if nid not in plan.agent_refs or not runs_in_own_session(plan, nid, ctx.strategies):
            continue
        backend = ctx.backend_of(nid)
        hook = ctx.validators.get(backend) if backend is not None else None
        if hook is None:
            continue
        grant = session_grant(plan, nid, ctx.strategies) or InteractionGrant()
        try:
            found = list(hook.validate_settings(ctx.settings(nid), grant))
        except Exception as exc:
            ctx.add(
                make_issue(
                    "warning",
                    _C.VALIDATOR_FAILED,
                    f"백엔드 설정 검사 중 오류: {type(exc).__name__}",
                    node_id=nid,
                    details={"backend": backend},
                )
            )
            continue
        for i, issue in enumerate(found):
            update: dict[str, Any] = {}
            if issue.node_id is None:
                update["node_id"] = nid
            if issue.code == _C.INTERACTION_NO_PATH and not issue.suggestions:
                update["suggestions"] = [
                    s for s in [_ask_suggestion(ctx, nid, issue, i)] if s is not None
                ]
            ctx.add(issue.model_copy(update=update) if update else issue)


def _ask_suggestion(
    ctx: TeamCheckContext, node_id: str, issue: Issue, n: int
) -> IssueSuggestion | None:
    need = issue.details.get("kinds")
    wanted = [k for k in need if isinstance(k, str)] if isinstance(need, list) else []

    def accept(desc: EdgeTypeDescriptor) -> bool:
        if desc.interaction is None:
            return False
        return all(k in desc.interaction.kinds for k in wanted)

    return ctx.suggest.connect(
        node_id=node_id,
        node_is_source=True,
        accept=accept,
        suggestion_id=f"ask:{node_id}:{n}",
        label=f"'{ctx.label(node_id)}'에 되묻기·승인 연결 추가",
    )


def _check_review(ctx: TeamCheckContext) -> None:
    """검토 결정(노드 config의 `review_decisions_pointer`) 중 이어지지 않는 것."""
    plan = ctx.plan
    pointer = ctx.c.review_decisions_pointer
    for nid in plan.view.scheduled:
        node = plan.node(nid)
        if node is None:
            continue
        decisions = get_at(node.config, pointer, None)
        if not isinstance(decisions, list):
            continue
        used_ports = {e.source.port for e in plan.edges_from(nid)}
        for i, item in enumerate(decisions):
            did = item.get("id") if isinstance(item, Mapping) else None
            if not isinstance(did, str) or not did or did in used_ports:
                continue
            ctx.add(
                make_issue(
                    "warning",
                    _C.REVIEW_DEAD_END,
                    f"검토 결정 '{item.get('label') or did}'이(가) 아무 데도 "
                    "이어지지 않습니다. 이 결정을 고르면 흐름이 끝납니다",
                    node_id=nid,
                    details={"decision": did, "path": f"{pointer}/{i}"},
                    suggestions=[ctx.reply_suggestion(nid, i, port=did)],
                )
            )
