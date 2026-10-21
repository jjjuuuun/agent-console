"""위임 방식 `sdk-subagents`(X12, design §R3.3).

위임자 요청에 대상들을 `AgentRequest.subagents`로 실어 위임자 백엔드 한 세션에서 실행한다
(백엔드 `capabilities.subagents`가 참이어야 한다). 위임자 모델이 대상 설명(`description`)을 보고
스스로 부른다.

대상의 답변(대상 노드에서 나가는 답변 연결)은 위임 결과마다 낸다(design §R3.1b, §R3.7): 백엔드에
넘기는 sink가 선택 능력 `SubagentResultListener`(ac-runtime,
`on_subagent_result(name, *, text, status, actor, tool_use_id)`)를 만족하며
(claude-sdk·fake가 위임 도구 결과 전문으로 부른다), 받으면 `ctx.emit_replies`로
답변 연결을 평가한다.
결과 포트 이름은 대상 노드 타입의 포트에서 읽는다. 알림을 주지 않는 백엔드에서는 대상 답변이 없다.

혼합 위임: 디스크립터 `composable = true`이고 `contribute`(ac-runtime
`ComposableDelegation`)로 하위 에이전트 목록과 답변 sink 감싸기를 내준다. 다른 composable 방식
(예: 독립 위임 `host`)과 한 위임자에서 합쳐 실행된다.

저장 시점 정적 검사(design §5.2R.7): `static_issues`(방식 고유 정적 규칙 없음)와
`declared_names`(하위 에이전트 이름 = 대상 노드 id, 묶음 `subagent`)를 구현한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import BaseModel

from agent_console_contracts import (
    DelegationStrategyDescriptor,
    ErrorInfo,
    Issue,
    KnownInteractionKinds,
    RunEvent,
)
from agent_console_runtime import (
    AgentResult,
    BackendEventSink,
    DelegationContribution,
    DelegationMember,
    DelegationMemberView,
    DelegationNameGroups,
    DelegationPlan,
    InteractionOutcome,
    InteractionRequest,
    NodeContext,
    SubagentResultListener,
    SubagentSpec,
    apply_contribution,
)

from ._common import OUT_PORT, NodesCoreErrorCodes

__all__ = ["SDK_SUBAGENTS", "SdkSubagentsStrategy", "result_port", "subagent_specs"]

SDK_SUBAGENTS: Final = "sdk-subagents"
"""이 위임 방식의 id(레지스트리 key)."""

_COMPLETED: Final = frozenset({"completed", "succeeded", "success"})


def _description(member: DelegationMember) -> str:
    role, when = (member.role or "").strip(), member.delegate_when.strip()
    if role and when:
        return f"{role} — {when}"
    return when or role


def subagent_specs(members: Sequence[DelegationMember]) -> list[SubagentSpec]:
    """위임 대상 → `SubagentSpec`(대상의 유효 설정 중 `member_fields`만 쓴다)."""
    specs: list[SubagentSpec] = []
    for m in members:
        s = m.settings
        specs.append(
            SubagentSpec(
                name=m.node_id,
                description=_description(m),
                prompt=s.system_prompt or "",
                actor=m.agent_id,
                tools=s.tools,
                disallowed_tools=s.disallowed_tools,
                model=s.model,
                bundle=m.bundle,
            )
        )
    return specs


def result_port(ctx: NodeContext, node_id: str) -> str:
    """대상 노드의 결과 포트: 노드 타입 디스크립터의 첫 출력 포트(없으면 `out`)."""
    spec = next((n for n in ctx.graph.nodes if n.id == node_id), None)
    if spec is not None and spec.type in ctx.registries.node_types:
        impl = ctx.registries.node_types.get(spec.type, spec.type_version)
        ports = impl.resolve_ports(spec.config)
        if ports.outputs:
            return ports.outputs[0].name
    return OUT_PORT


class _ReplySink(SubagentResultListener):
    """백엔드 sink를 감싼 sink. `emit`·`child_path`는 감싼 sink(`inner`, 기본 `ctx`)로 넘기고,
    백엔드의 선택 알림 `on_subagent_result`(`SubagentResultListener`)를 받으면 대상 노드의 답변
    연결을 평가한다(`ctx.emit_replies`).

    모르는 속성(예: 상호작용 `request_input`)은 `inner`로 넘긴다.
    """

    def __init__(
        self,
        ctx: NodeContext,
        members: Sequence[DelegationMember],
        inner: BackendEventSink | None = None,
    ) -> None:
        self._ctx = ctx
        self._inner: Any = inner if inner is not None else ctx
        self._members = {m.node_id: m for m in members}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def child_path(self, node_id: str) -> list[str]:
        path: list[str] = self._inner.child_path(node_id)
        return path

    async def request_input(self, req: InteractionRequest) -> InteractionOutcome:
        """상호작용 열기(`InteractivePort`)는 감싼 sink로 넘긴다. 명시 메서드여야 백엔드의
        `isinstance(sink, InteractivePort)` 검사(정적 속성 조회)를 통과한다."""
        outcome: InteractionOutcome = await self._inner.request_input(req)
        return outcome

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        raw: Any = None,
        evidence: str = "observed",
        actor: str | None = None,
        node_path: Sequence[str] | None = None,
    ) -> RunEvent:
        event: RunEvent = await self._inner.emit(
            type, payload, raw=raw, evidence=evidence, actor=actor, node_path=node_path
        )
        return event

    async def on_subagent_result(
        self, name: str, *, text: str, status: str, actor: str | None, tool_use_id: str
    ) -> None:
        """백엔드 알림: 위임 하나가 끝났다(결과 전문). 대상의 답변 연결을 평가한다."""
        member = self._members.get(name)
        if member is None:
            return
        await self._ctx.emit_replies(
            name,
            {result_port(self._ctx, name): text},
            status="succeeded" if status in _COMPLETED else "failed",
            actor=actor if actor is not None else member.agent_id,
        )


class SdkSubagentsStrategy:
    """위임 방식 `sdk-subagents`: 위임자 세션 안 SDK 서브에이전트."""

    descriptor = DelegationStrategyDescriptor(
        id=SDK_SUBAGENTS,
        title="SDK 서브에이전트",
        description=(
            "위임자 세션 안에서 대상을 서브에이전트로 실행한다. 위임자가 판단해 부르고 결과는 "
            "위임자 맥락으로 돌아온다. 대상은 위임자 백엔드로 실행된다."
        ),
        # 서브에이전트 정의(SubagentSpec)로 전달되는 필드만. resources는 칸별로 백엔드가 나눠
        # 싣는다(지침·도구·MCP·skill은 서브에이전트별, files·hooks는 세션 공유 — design §R12.5).
        member_fields=["model", "system_prompt", "tools", "disallowed_tools", "resources"],
        max_depth=1,
        allows_outgoing_flow=False,
        requires_backend_capability="subagents",
        member_interaction_kinds=[KnownInteractionKinds.TOOL_PERMISSION],
        # 하위 에이전트 목록 + 답변 sink만 더하므로 다른 composable 방식과 합칠 수 있다(§5R.6).
        composable=True,
        # 대상은 위임자 세션 안에서 돈다 — 대상의 상호작용 종류가 위임자 세션 grant에 더해진다.
        shares_session=True,
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        """대상이 있고 대상 노드 id가 겹치지 않아야 한다."""
        if not plan.members:
            return [
                Issue(
                    severity="error",
                    code=NodesCoreErrorCodes.DELEGATION_NO_MEMBERS,
                    message="위임 대상이 없습니다",
                )
            ]
        seen: set[str] = set()
        issues: list[Issue] = []
        for m in plan.members:
            if m.node_id in seen:
                issues.append(
                    Issue(
                        severity="error",
                        code=NodesCoreErrorCodes.DELEGATION_DUPLICATE_MEMBER,
                        message=f"위임 대상 {m.node_id!r}가 두 번 연결되었습니다",
                        node_id=m.node_id,
                    )
                )
            seen.add(m.node_id)
        return issues

    def static_issues(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> list[Issue]:
        """저장 시점 방식 고유 검사(`StaticDelegationChecks`). 이 방식은 config가 없고 대상 중복은
        `ac-teams` 일반 규칙이 내므로 더할 것이 없다."""
        return []

    def declared_names(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> Mapping[str, list[str]]:
        """합쳐 실행할 때 겹치면 안 되는 이름: 하위 에이전트 이름(`subagent_specs`와 같은 대상
        노드 id)."""
        return {DelegationNameGroups.SUBAGENT: [m.node_id for m in members]}

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        """위임자 백엔드로 `subagents`를 실은 요청을 실행하고, 대상 결과마다 답변을 낸다."""
        backend_id = plan.backend
        if backend_id is None or backend_id not in ctx.backends:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=NodesCoreErrorCodes.DELEGATION_UNKNOWN_BACKEND,
                    message=f"위임자 백엔드 {backend_id!r}를 찾을 수 없습니다",
                ),
            )
        backend = ctx.backends.get(backend_id)
        if not backend.descriptor.capabilities.subagents:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=NodesCoreErrorCodes.DELEGATION_BACKEND_UNSUPPORTED,
                    message=f"백엔드 {backend_id!r}는 서브에이전트를 실행할 수 없습니다",
                    details={"backend": backend_id},
                ),
            )
        contribution = self.contribute(plan, ctx)
        request = apply_contribution(plan.request, contribution)
        sink = contribution.wrap_sink(ctx) if contribution.wrap_sink is not None else ctx
        return await backend.run(request, sink, ctx.cancel)

    def contribute(self, plan: DelegationPlan, ctx: NodeContext) -> DelegationContribution:
        """합쳐 실행할 때 요청에 더할 것: 하위 에이전트 목록 + 대상 답변을 내는 sink 감싸기."""
        members = list(plan.members)

        def wrap(sink: BackendEventSink) -> BackendEventSink:
            return _ReplySink(ctx, members, inner=sink)

        return DelegationContribution(subagents=subagent_specs(members), wrap_sink=wrap)
