"""팀 규칙: 위임(design §R3.1b, §5R.6·§5R.8).

근거는 위임 방식 디스크립터(`max_depth`·`allows_outgoing_flow`·`member_fields`·
`requires_backend_capability`·`composable`)와 설정 `delegation.max_depth`뿐이다. 한 위임자가 여러
방식을 쓰면 모두 `composable`일 때만 허용한다(혼합 위임). 깊이 한도는 방식 `max_depth`와 설정 중
작은 값이다(방식이 `max_depth: null`이면 설정만).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from agent_console_contracts import EdgeTypeDescriptor, IssueGroup, IssueSuggestion

from ._check_context import TeamCheckContext
from ._issues import TeamIssueCodes, make_issue
from ._plan import DelegationLink

_C = TeamIssueCodes

__all__ = ["check_delegation"]


def check_delegation(ctx: TeamCheckContext) -> None:
    """모르는 방식·흐름+위임 겸용·방식 섞임·백엔드 능력·깊이·순환·흐름 내보내기·무시되는 필드."""
    plan = ctx.plan
    for link in plan.delegations:
        if link.strategy not in ctx.strategies:
            ctx.add(
                make_issue(
                    "warning",
                    _C.UNKNOWN_STRATEGY,
                    f"등록되지 않은 위임 방식입니다: {link.strategy}",
                    edge_id=link.edge_id,
                    details={"strategy": link.strategy},
                )
            )
    for nid in plan.callees:
        inbound = ctx.opening_inbound(nid)  # 반복을 닫는 사이클 연결만이면 `check_loops`가 알린다
        if inbound:
            ctx.add(
                make_issue(
                    "error",
                    _C.MIXED_INVOCATION,
                    f"'{ctx.label(nid)}'은(는) 흐름·입구로 받으면서 위임으로도 불립니다. "
                    "같은 에이전트를 노드 두 개로 나눠 주세요",
                    node_id=nid,
                    details={
                        "flow_edges": list(inbound),
                        "delegation_edges": [link.edge_id for link in plan.callers_of.get(nid, ())],
                    },
                )
            )
    for nid, links in plan.delegates_of.items():
        used = list(dict.fromkeys(link.strategy for link in links))
        if len(used) > 1:
            _check_mixed(ctx, nid, links, used)
        _check_capability(ctx, nid, used)
    _check_depth_and_cycles(ctx)
    _check_outgoing_flow(ctx)
    _check_member_fields(ctx)


def _composable(ctx: TeamCheckContext, strategy: str) -> bool:
    desc = ctx.strategies.get(strategy)
    return desc is not None and desc.composable


def _title(ctx: TeamCheckContext, strategy: str) -> str:
    desc = ctx.strategies.get(strategy)
    return desc.title if desc is not None else strategy


def _relabel(member: str) -> Callable[[EdgeTypeDescriptor], str]:
    def label(desc: EdgeTypeDescriptor) -> str:
        return f"'{member}' 연결을 '{desc.title}'(으)로 바꾸기"

    return label


def _check_mixed(
    ctx: TeamCheckContext, delegator: str, links: tuple[DelegationLink, ...], used: list[str]
) -> None:
    """방식이 여럿이면 모두 `composable`일 때만 허용(design §5R.6 혼합 위임).

    모르는 방식은 합칠 수 있는지 알 수 없으므로 합칠 수 없는 방식으로 본다.
    """
    blocked = [s for s in used if not _composable(ctx, s)]
    if not blocked:
        return
    joinable = {s for s in used if _composable(ctx, s)}

    def accept(desc: EdgeTypeDescriptor) -> bool:
        return desc.invocation is not None and _composable(ctx, desc.invocation.strategy)

    def prefer(desc: EdgeTypeDescriptor) -> bool:
        return desc.invocation is not None and desc.invocation.strategy in joinable

    suggestions: list[IssueSuggestion | None] = []
    for link in links:
        edge = ctx.plan.edge(link.edge_id)
        if link.strategy not in blocked or edge is None:
            continue
        suggestions.append(
            ctx.suggest.replace_kind(
                edge,
                accept=accept,
                prefer=prefer,
                drop_keys=(ctx.c.edge_strategy_key,),
                suggestion_id=f"compose:{link.edge_id}",
                label=_relabel(ctx.label(link.member)),
            )
        )
    ctx.add(
        make_issue(
            "error",
            _C.MIXED_STRATEGIES,
            f"'{ctx.label(delegator)}'의 위임 대상에 함께 쓸 수 없는 위임 방식이 섞여 있습니다: "
            f"{', '.join(_title(ctx, s) for s in used)}. "
            f"'{', '.join(_title(ctx, s) for s in blocked)}'은(는) 다른 방식과 한 번에 합쳐 "
            "실행할 수 없습니다.",
            node_id=delegator,
            details={"strategies": used, "not_composable": blocked},
            suggestions=suggestions,
        )
    )


def _check_capability(ctx: TeamCheckContext, delegator: str, used: list[str]) -> None:
    backend = ctx.backend_of(delegator)
    caps = ctx.backends.get(backend) if backend is not None else None
    if caps is None:
        return
    for sid in used:
        desc = ctx.strategies.get(sid)
        need = desc.requires_backend_capability if desc is not None else None
        if need and getattr(caps, need, None) is not True:
            ctx.add(
                make_issue(
                    "error",
                    _C.BACKEND_CAPABILITY_MISSING,
                    f"'{ctx.label(delegator)}'의 백엔드가 위임 방식 "
                    f"'{desc.title if desc else sid}'에 필요한 능력({need})을 "
                    "지원하지 않습니다",
                    node_id=delegator,
                    details={"backend": backend, "strategy": sid, "capability": need},
                )
            )


def _limit(ctx: TeamCheckContext, strategy: str) -> int | None:
    """위임 깊이 한도 = 방식 `max_depth`와 설정 `delegation.max_depth` 중 작은 값."""
    desc = ctx.strategies.get(strategy)
    setting = ctx.max_depth_setting
    hard = desc.max_depth if desc is not None else None
    if hard is None:
        return setting
    return hard if setting is None else min(hard, setting)


def _check_depth_and_cycles(ctx: TeamCheckContext) -> None:
    plan = ctx.plan
    depth: dict[str, int] = {}
    chains: dict[str, list[str]] = {}  # 노드까지 가장 깊은 위임 경로(위임자 → … → 노드)
    state: dict[str, int] = {}  # 1 = 방문 중, 2 = 끝
    reported_cycles: set[frozenset[str]] = set()

    def visit(node: str, stack: list[str]) -> int:
        if state.get(node) == 2:
            return depth[node]
        state[node] = 1
        best = 0
        best_chain = [node]
        for link in plan.callers_of.get(node, ()):
            caller = link.delegator
            if state.get(caller) == 1:
                cycle = stack[stack.index(caller) :] if caller in stack else [caller, node]
                key = frozenset(cycle)
                if key not in reported_cycles:
                    reported_cycles.add(key)
                    ctx.add(
                        make_issue(
                            "error",
                            _C.DELEGATION_CYCLE,
                            "위임 연결이 순환합니다",
                            edge_id=link.edge_id,
                            details={"nodes": cycle},
                        )
                    )
                continue
            d = visit(caller, [*stack, caller]) + 1
            chain = [*chains.get(caller, [caller]), node]
            limit = _limit(ctx, link.strategy)
            if limit is not None and d > limit:
                ctx.add(
                    make_issue(
                        "error",
                        _C.DELEGATION_DEPTH_EXCEEDED,
                        f"위임이 {d}단계로 한도({limit})를 넘었습니다: "
                        + " → ".join(ctx.label(n) for n in chain)
                        + ".",
                        edge_id=link.edge_id,
                        node_id=node,
                        details={
                            "depth": d,
                            "max_depth": limit,
                            "strategy": link.strategy,
                            "path": chain,
                        },
                    )
                )
            if d > best:
                best, best_chain = d, chain
        state[node] = 2
        depth[node] = best
        chains[node] = best_chain
        return best

    for nid in ctx.node_order():
        if nid in plan.callees:
            visit(nid, [nid])


def _check_outgoing_flow(ctx: TeamCheckContext) -> None:
    plan = ctx.plan
    for nid in plan.callees:
        blocked = [
            link.strategy
            for link in plan.callers_of.get(nid, ())
            if (desc := ctx.strategies.get(link.strategy)) is not None
            and not desc.allows_outgoing_flow
        ]
        if not blocked:
            continue
        for eid in plan.view.outgoing.get(nid, ()):
            ctx.add(
                make_issue(
                    "error",
                    _C.FLOW_FROM_DELEGATE,
                    f"위임받는 '{ctx.label(nid)}'은(는) 이 위임 방식에서 흐름 연결을 "
                    "내보낼 수 없습니다(결과는 위임자 안으로만 돌아갑니다)",
                    edge_id=eid,
                    node_id=nid,
                    details={"strategies": list(dict.fromkeys(blocked))},
                )
            )


MEMBER_FIELD_HINT = "이 값은 실행에 쓰이지 않습니다. 비워도 결과는 같습니다."
"""`team.member_field_ignored`의 해결 안내(`Issue.hint`)."""

VALUE_SOURCE_NODE = "node"
"""`details.value_source`: 값이 이 팀의 노드 설정(노드 층)에서 왔다."""
VALUE_SOURCE_AGENT = "agent"
"""`details.value_source`: 값이 에이전트 정의(에이전트 층)에서 왔다."""


def _backend_ok(ctx: TeamCheckContext, delegator: str, strategy: str) -> bool:
    """위임자 백엔드가 방식에 필요한 능력을 가졌는지(능력을 모르면 참)."""
    desc = ctx.strategies.get(strategy)
    need = desc.requires_backend_capability if desc is not None else None
    backend = ctx.backend_of(delegator)
    caps = ctx.backends.get(backend) if backend is not None else None
    return not need or caps is None or getattr(caps, need, None) is True


def _check_member_fields(ctx: TeamCheckContext) -> None:
    """위임받는 노드의 값 중 방식이 쓰지 않는 필드(위임자 값과 다를 때)를 정보 이슈로 알린다.

    실행 결과는 달라지지 않으므로 `info`·`blocks_run: false`다(5.7R.38). 같은 위임자·방식·필드는
    `group`으로 묶이고, 제안은 값의 출처(`value_source`)에 맞춘다: 노드 층이면 [값 비우기]
    (`unset_node_fields`), 에이전트 층이면 해결 버튼(`fix`, 연동 쪽 데이터 표가 붙인다). 그 필드를
    쓰는(`member_fields`) 다른 위임 방식이 있으면 방식 바꾸기 제안을 더한다.
    """
    c = ctx.c
    for link in ctx.plan.delegations:
        desc = ctx.strategies.get(link.strategy)
        if desc is None:
            continue
        mine = ctx.settings(link.member)
        boss = ctx.settings(link.delegator)
        fields = type(mine).model_fields
        for name in fields:
            if name in desc.member_fields:
                continue
            value = getattr(mine, name)
            if value is None or value == getattr(boss, name):
                continue
            layers = ctx.field_layers(link.member, name)
            details: dict[str, object] = {
                "field": name,
                "strategy": link.strategy,
                "delegator": link.delegator,
            }
            from_node = c.node_layer.id in layers
            from_agent = c.agent_layer.id in layers
            if from_node:
                details["value_source"] = VALUE_SOURCE_NODE
            elif from_agent:
                details["value_source"] = VALUE_SOURCE_AGENT
            agent_id = ctx.plan.agent_refs.get(link.member)
            if from_agent and agent_id is not None:
                details["agent"] = agent_id
                details["agent_kind"] = c.agent_kind
            key = f"{link.delegator}|{link.strategy}|{name}"
            title = fields[name].title or name
            pointer = f"/{c.node_settings_key}/{name}"
            node = ctx.plan.node(link.member)
            raw = node.config.get(c.node_settings_key) if node is not None else None
            unset = (
                ctx.suggest.unset_fields(
                    [(link.member, pointer)], suggestion_id=f"unset:{key}", label="값 비우기"
                )
                if isinstance(raw, Mapping) and name in raw
                else None
            )
            suggestions: list[IssueSuggestion | None] = [unset]
            edge = ctx.plan.edge(link.edge_id)
            if edge is not None:
                for sid, alt in ctx.strategies.items():
                    if (
                        sid == link.strategy
                        or name not in alt.member_fields
                        or not _backend_ok(ctx, link.delegator, sid)
                    ):
                        continue
                    suggestions.append(
                        ctx.suggest.switch_strategy(
                            edge,
                            sid,
                            strategy_key=c.edge_strategy_key,
                            suggestion_id=f"strategy:{key}:{sid}",
                            label=f"위임 방식을 '{alt.title}'(으)로 바꾸기",
                        )
                    )
            ctx.add(
                make_issue(
                    "info",
                    _C.MEMBER_FIELD_IGNORED,
                    f"'{ctx.label(link.member)}'의 '{name}' 설정은 이 위임 방식에서 "
                    f"적용되지 않습니다(위임자 '{ctx.label(link.delegator)}'의 값을 씁니다)",
                    node_id=link.member,
                    edge_id=link.edge_id,
                    path=pointer,
                    details=details,
                    suggestions=suggestions,
                    blocks_run=False,
                    hint=MEMBER_FIELD_HINT,
                    group=IssueGroup(
                        key=key,
                        message=(
                            f"'{title}' 설정은 위임 방식 '{desc.title}'에서 쓰이지 않습니다. "
                            f"위임자 '{ctx.label(link.delegator)}'의 값을 씁니다."
                        ),
                    ),
                )
            )
