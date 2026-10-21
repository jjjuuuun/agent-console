"""위임 방식 `example.round_robin`: 위임 대상을 연결 순서대로 한 번씩 불러 결과를 이어 붙인다.

위임 방식(X12)은 세 가지만 갖추면 된다.

1. ``descriptor`` — 팀 검증·편집기가 이름이 아니라 이 값으로 규칙을 계산한다.
   - ``composable = false``: 다른 방식과 한 위임자에 섞을 수 없다(섞으면 팀 검증
     ``team.mixed_strategies``, 실행하면 노드 실패 ``agent.mixed_strategies``).
   - ``requires_backend_capability = null``: 위임자 백엔드를 부르지 않으므로 능력이 필요 없다.
   - ``max_depth``·``allows_outgoing_flow``·``member_fields``·``member_interaction_kinds``:
     위임 규칙.
2. ``validate(plan)`` — 실행 직전 계획 검사(error 이슈가 있으면 위임자 노드가 실패한다).
3. ``run(plan, ctx)`` — 위임자를 실행하고 결과(``AgentResult``)를 돌려준다.

대상 실행은 엔진의 ``ctx.invoke_node``가 맡는다(대상의 자기 NodeRun·설정·되묻기·기록·취소).
이 방식은 모델을 부르지 않는 **결정적** 위임이다 — 위임자의 입력을 그대로 각 대상에게 맡긴다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    AgentSettings,
    DelegationStrategyDescriptor,
    ErrorInfo,
    Issue,
    UiHints,
)
from agent_console_runtime import (
    AgentResult,
    DelegationMember,
    DelegationPlan,
    NodeContext,
    NodeRunView,
)

STRATEGY_ID: Final = "example.round_robin"
"""디스크립터 id. pyproject의 entry point 이름·위임 연결 config `strategy` 값과 같다."""


class RoundRobinCodes:
    """이 방식이 내는 `Issue.code`·`ErrorInfo.code` 값."""

    NO_MEMBERS: Final = "example.round_robin.no_members"
    INVALID_CONFIG: Final = "example.round_robin.invalid_config"
    MEMBER_FAILED: Final = "example.round_robin.member_failed"


class RoundRobinConfig(BaseModel):
    """방식 설정(위임자 노드 config `delegation.example.round_robin`). 비우면 아래 기본값."""

    model_config = ConfigDict(extra="forbid", title="차례로 맡기기 설정")

    item_template: str = Field(
        default="[{target}] {result}",
        title="결과 한 줄 형식",
        description=(
            "대상 하나의 결과를 적는 형식. 변수 {target}(노드 id)·{role}·{result}·{status}."
        ),
    )
    separator: str = Field(default="\n\n", title="구분자", description="결과 사이에 넣는 글.")
    failure_text: str = Field(
        default="(실패: {code})",
        title="실패 결과",
        description="대상이 실패했을 때 {result} 자리에 넣는 글. 변수 {code}·{message}·{status}.",
    )
    stop_on_failure: bool = Field(
        default=False,
        title="실패하면 멈춤",
        description=(
            "켜면 대상 하나가 실패하는 즉시 위임자도 실패한다. 끄면 실패 결과를 적고 계속한다."
        ),
    )


_VAR: Final = re.compile(r"\{(\w+)\}")


def fill(template: str, values: Mapping[str, Any]) -> str:
    """`{이름}`만 바꾸는 안전 치환(속성·색인 접근 없음, 모르는 이름은 그대로)."""
    return _VAR.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _issue(code: str, message: str, **details: Any) -> Issue:
    return Issue(severity="error", code=code, message=message, details=details)


class RoundRobinDelegation:
    """위임 방식 `example.round_robin`(X12 예제 구현). 백엔드를 부르지 않는다."""

    descriptor = DelegationStrategyDescriptor(
        id=STRATEGY_ID,
        title="차례로 맡기기",
        description=(
            "위임 대상을 연결 순서대로 한 번씩 불러 위 에이전트의 입력을 그대로 맡기고, 결과를 "
            "이어 붙여 위 에이전트의 결과로 낸다(예제 확장, 모델 호출 없음)."
        ),
        config_schema=RoundRobinConfig.model_json_schema(),
        member_fields=list(AgentSettings.model_fields),
        max_depth=None,
        allows_outgoing_flow=False,
        requires_backend_capability=None,
        member_interaction_kinds=None,
        composable=False,
        ui_hints=UiHints(icon="⟳"),
    )

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        """대상이 하나 이상 있고 방식 설정이 스키마에 맞아야 한다."""
        issues: list[Issue] = []
        if not plan.members:
            issues.append(_issue(RoundRobinCodes.NO_MEMBERS, "차례로 맡길 대상이 없습니다"))
        try:
            RoundRobinConfig.model_validate(dict(plan.config))
        except ValidationError as exc:
            issues.append(
                _issue(
                    RoundRobinCodes.INVALID_CONFIG,
                    f"차례로 맡기기 설정이 유효하지 않습니다: {exc.error_count()}개 오류",
                    errors=[
                        {"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()
                    ],
                )
            )
        return issues

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        """대상마다 `ctx.invoke_node`(대상 첫 입력 포트에 위임자 입력) → 결과를 이어 붙인다."""
        cfg = RoundRobinConfig.model_validate(dict(plan.config))
        parts: list[str] = []
        for member in plan.members:
            view = await self._invoke(ctx, member, plan.request.prompt)
            if view.status == "succeeded":
                result = _port_text(ctx, member.node_id, view)
            else:
                error = view.error
                if cfg.stop_on_failure:
                    return AgentResult(
                        status="failed",
                        error=ErrorInfo(
                            code=RoundRobinCodes.MEMBER_FAILED,
                            message=f"위임 대상 {member.node_id!r}가 실패했습니다",
                            details={
                                "target": member.node_id,
                                "code": error.code if error is not None else None,
                            },
                        ),
                    )
                result = fill(
                    cfg.failure_text,
                    {
                        "code": error.code if error is not None else view.status,
                        "message": error.message if error is not None else "",
                        "status": view.status,
                    },
                )
            values = {
                "target": member.node_id,
                "role": member.role or member.node_id,
                "result": result,
                "status": view.status,
            }
            parts.append(fill(cfg.item_template, values))
        return AgentResult(status="succeeded", text=cfg.separator.join(parts))

    async def _invoke(self, ctx: NodeContext, member: DelegationMember, task: str) -> NodeRunView:
        port = _first_input_port(ctx, member.node_id)
        if port is None:
            return NodeRunView(
                node_id=member.node_id,
                node_type="",
                status="failed",
                error=ErrorInfo(code=RoundRobinCodes.MEMBER_FAILED, message="입력 포트가 없습니다"),
            )
        return await ctx.invoke_node(
            member.node_id,
            {port: task},
            by_edge=member.edge_id,
            max_depth=self.descriptor.max_depth,
        )


def _ports(ctx: NodeContext, node_id: str) -> tuple[list[str], list[str]]:
    """대상 노드 타입이 정한 입력·출력 포트 이름(노드 타입 이름을 모른다)."""
    spec = next((n for n in ctx.graph.nodes if n.id == node_id), None)
    if spec is None or spec.type not in ctx.registries.node_types:
        return [], []
    ports = ctx.registries.node_types.get(spec.type, spec.type_version).resolve_ports(spec.config)
    return [p.name for p in ports.inputs], [p.name for p in ports.outputs]


def _first_input_port(ctx: NodeContext, node_id: str) -> str | None:
    inputs, _ = _ports(ctx, node_id)
    return inputs[0] if inputs else None


def _port_text(ctx: NodeContext, node_id: str, view: NodeRunView) -> str:
    _, outputs = _ports(ctx, node_id)
    for port in outputs:
        if port in view.outputs:
            return _as_text(view.outputs[port])
    return _as_text(next(iter(view.outputs.values()), None))
