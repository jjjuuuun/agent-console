"""위임 방식 `host`(X12, design §5R.6): 대상 노드를 **자기 NodeRun·세션·백엔드·설정**으로 실행한다.

위임자 모델에게 플랫폼 도구(`HostTool`) 하나를 준다. 도구 입력의 대상 값 목록은 대상 노드 id이고,
모델이 도구를 부르면 핸들러가 엔진의 `ctx.invoke_node(대상, {입력 포트: 할 일}, by_edge=...)`를
기다려 대상 결과 텍스트를 돌려준다. 대상 실행 규칙(설정 병합·리소스·되묻기·기록·취소·같은 대상
직렬)은 엔진과 대상 노드 타입이 정한다 — 이 방식은 대상을 직접 실행하지 않는다.

- 대상 실패(깊이 초과·순환 포함)는 예외가 아니라 `is_error` 도구 결과다(위임자 모델이 판단).
- 대상의 나가는 답변 연결은 엔진이 낸다(이 방식은 `emit_replies`를 부르지 않는다).
- 백엔드는 `capabilities.host_tools`가 참이어야 한다(디스크립터 `requires_backend_capability`).
- 저장 시점 정적 검사(design §5.2R.7): `static_issues`(연결 결과 모양·스키마 밖 config 규칙)와
  `declared_names`(위임 도구 이름, 묶음 `host_tool`)를 구현한다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from agent_console_contracts import (
    AgentSettings,
    DelegationStrategyDescriptor,
    ErrorInfo,
    Issue,
)
from agent_console_runtime import (
    Activation,
    AgentResult,
    DelegationContribution,
    DelegationMember,
    DelegationMemberView,
    DelegationNameGroups,
    DelegationPlan,
    HostTool,
    HostToolResult,
    NodeContext,
    NodeRunView,
    Reply,
    apply_contribution,
)

from ._config import RESULT_MODES, HostDelegationConfig, fill

__all__ = [
    "DEFAULT_RESULT_KEY",
    "HOST",
    "HostDelegation",
    "HostDelegationCodes",
    "host_descriptor",
]

HOST: Final = "host"
"""기본 위임 방식 id(레지스트리 key = entry point 이름)."""

DEFAULT_RESULT_KEY: Final = "result"
"""대상이 돌려줄 결과 모양(`text`|`reply`)을 읽는 위임 연결(엣지) config 키 기본값."""

_EXIT: Final = "exit"
"""답변 연결의 디스크립터 `scheduling` 값(계약 값)."""


class HostDelegationCodes:
    """이 방식이 내는 `Issue.code`·`ErrorInfo.code` 값."""

    NO_MEMBERS: Final = "delegation.no_members"
    DUPLICATE_MEMBER: Final = "delegation.duplicate_member"
    INVALID_CONFIG: Final = "delegation.invalid_config"
    INVALID_RESULT_MODE: Final = "delegation.invalid_result_mode"
    UNKNOWN_BACKEND: Final = "delegation.unknown_backend"
    BACKEND_UNSUPPORTED: Final = "delegation.backend_unsupported"


def host_descriptor(strategy_id: str = HOST) -> DelegationStrategyDescriptor:
    """`host` 디스크립터. 규칙은 모두 값이다(코드 분기 없음, design §5R.6·§5R.8).

    - `max_depth: null`: 깊이는 사용자 설정 `delegation.max_depth`만 정한다.
    - `allows_outgoing_flow: false`: 대상은 0~여러 번 불리므로 "끝나면 넘긴다" 시점이 없다.
    - `member_fields`: 대상의 모든 설정 필드(`AgentSettings` 전체, 대상은 자기 설정으로 돈다).
    - `member_interaction_kinds: null`: 대상 안 되묻기 제한 없음.
    - `composable: true`: 다른 composable 방식(예: 서브에이전트)과 한 위임자에서 합쳐 실행한다.
    - `shares_session: false`: 대상은 자기 세션에서 돈다. 대상의 상호작용 종류·대기 한도는
      위임자 세션 grant에 더하지 않는다(design §5.2R.7, 결정 J-10).
    """
    return DelegationStrategyDescriptor(
        id=strategy_id,
        title="독립 에이전트로 위임",
        description=(
            "위 에이전트가 판단해 위임 도구로 아래 에이전트를 부른다. 아래 에이전트는 자기 세션·"
            "백엔드·모델·리소스로 따로 실행되고 결과가 도구 결과로 돌아온다. 아래 에이전트도 다시 "
            "위임하거나 사용자에게 되물을 수 있다."
        ),
        config_schema=HostDelegationConfig.model_json_schema(),
        member_fields=list(AgentSettings.model_fields),
        max_depth=None,
        allows_outgoing_flow=False,
        requires_backend_capability="host_tools",
        member_interaction_kinds=None,
        composable=True,
        shares_session=False,
    )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _issue(code: str, message: str, **details: Any) -> Issue:
    return Issue(severity="error", code=code, message=message, details=details)


class HostDelegation:
    """위임 방식 `host`(독립 위임). `ComposableDelegation`(`contribute`)을 만족한다.

    Args:
        descriptor: 디스크립터(기본 `host_descriptor()`). 다른 id로 한 번 더 등록할 때 바꾼다.
        result_key: 결과 모양(`text`|`reply`)을 읽는 위임 연결 config 키.
        input_port: 대상에게 할 일을 넣을 입력 포트. None이면 대상 노드 타입의 첫 입력 포트.
    """

    def __init__(
        self,
        *,
        descriptor: DelegationStrategyDescriptor | None = None,
        result_key: str = DEFAULT_RESULT_KEY,
        input_port: str | None = None,
    ) -> None:
        self.descriptor = descriptor if descriptor is not None else host_descriptor()
        self._result_key = result_key
        self._input_port = input_port

    # ------------------------------------------------------------ X12

    def config_of(self, plan: DelegationPlan) -> HostDelegationConfig:
        """계획의 방식 config(비운 항목 = 스키마 기본값).

        Raises:
            pydantic.ValidationError: config가 스키마에 맞지 않을 때.
        """
        return HostDelegationConfig.model_validate(dict(plan.config))

    def validate(self, plan: DelegationPlan) -> list[Issue]:
        """대상이 있고 겹치지 않으며, 방식 config·연결 결과 모양이 맞아야 한다."""
        issues: list[Issue] = []
        if not plan.members:
            issues.append(_issue(HostDelegationCodes.NO_MEMBERS, "위임 대상이 없습니다"))
        seen: set[str] = set()
        for m in plan.members:
            if m.node_id in seen:
                issue = _issue(
                    HostDelegationCodes.DUPLICATE_MEMBER,
                    f"위임 대상 {m.node_id!r}가 두 번 연결되었습니다",
                )
                issues.append(issue.model_copy(update={"node_id": m.node_id}))
            seen.add(m.node_id)
            mode = m.config.get(self._result_key)
            if mode is not None and mode not in RESULT_MODES:
                issues.append(
                    _issue(
                        HostDelegationCodes.INVALID_RESULT_MODE,
                        f"위임 연결 {m.edge_id!r}의 결과 모양 {mode!r}를 알 수 없습니다",
                        edge_id=m.edge_id,
                        allowed=list(RESULT_MODES),
                    )
                )
        try:
            self.config_of(plan)
        except ValidationError as exc:
            issues.append(
                _issue(
                    HostDelegationCodes.INVALID_CONFIG,
                    f"독립 위임 설정이 유효하지 않습니다: {exc.error_count()}개 오류",
                    errors=[
                        {"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()
                    ],
                )
            )
        return issues

    # ------------------------------------------------------------ 저장 시점(선택 프로토콜)

    def static_issues(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> list[Issue]:
        """그래프만으로 알 수 있는 문제(`StaticDelegationChecks`).

        - 위임 연결 config의 결과 모양이 `text`|`reply`가 아니면 `delegation.invalid_result_mode`
          (연결 이슈, path = 결과 키).
        - config 스키마로 표현할 수 없는 규칙(대상·할 일 파라미터 이름이 같음)은
          `delegation.invalid_config`(path 없음). 스키마 위반은 `ac-teams` 일반 규칙이 낸다.
        """
        issues = [self._result_mode_issue(m) for m in members]
        found = [i for i in issues if i is not None]
        try:
            HostDelegationConfig.model_validate(dict(config))
        except ValidationError as exc:
            rules = [e for e in exc.errors() if e["type"] == "value_error" and not e["loc"]]
            if rules:
                found.append(
                    _issue(
                        HostDelegationCodes.INVALID_CONFIG,
                        "독립 위임 설정이 유효하지 않습니다: "
                        + "; ".join(str(e["msg"]) for e in rules),
                        errors=[{"loc": [], "msg": e["msg"]} for e in rules],
                    )
                )
        return found

    def declared_names(
        self, config: Mapping[str, Any], members: Sequence[DelegationMemberView]
    ) -> Mapping[str, list[str]]:
        """합쳐 실행할 때 겹치면 안 되는 이름: 위임 도구 이름(`host_tool`).

        config가 틀리면 빈 값이다(`delegation.invalid_config`가 따로 나온다).
        """
        try:
            cfg = HostDelegationConfig.model_validate(dict(config))
        except ValidationError:
            return {}
        return {DelegationNameGroups.HOST_TOOL: [cfg.tool_name]}

    def _result_mode_issue(self, member: DelegationMemberView) -> Issue | None:
        mode = member.config.get(self._result_key)
        if mode is None or mode in RESULT_MODES:
            return None
        issue = _issue(
            HostDelegationCodes.INVALID_RESULT_MODE,
            f"위임 연결 {member.edge_id!r}의 결과 모양 {mode!r}를 알 수 없습니다",
            edge_id=member.edge_id,
            allowed=list(RESULT_MODES),
        )
        return issue.model_copy(
            update={
                "edge_id": member.edge_id,
                "path": "/" + self._result_key.replace("~", "~0").replace("/", "~1"),
            }
        )

    def contribute(self, plan: DelegationPlan, ctx: NodeContext) -> DelegationContribution:
        """위임 도구 하나를 만든다(백엔드는 부르지 않는다).

        Raises:
            pydantic.ValidationError: 방식 config가 맞지 않을 때(`validate`가 먼저 막는다).
        """
        cfg = self.config_of(plan)
        return DelegationContribution(host_tools=[self.tool(plan, ctx, cfg)])

    async def run(self, plan: DelegationPlan, ctx: NodeContext) -> AgentResult:
        """이 방식만 쓸 때: 위임 도구를 요청에 더해 위임자 백엔드를 한 번 실행한다."""
        backend_id = plan.backend
        if backend_id is None or backend_id not in ctx.backends:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=HostDelegationCodes.UNKNOWN_BACKEND,
                    message=f"위임자 백엔드 {backend_id!r}를 찾을 수 없습니다",
                ),
            )
        backend = ctx.backends.get(backend_id)
        need = self.descriptor.requires_backend_capability
        if need and getattr(backend.descriptor.capabilities, need, None) is not True:
            return AgentResult(
                status="failed",
                error=ErrorInfo(
                    code=HostDelegationCodes.BACKEND_UNSUPPORTED,
                    message=f"백엔드 {backend_id!r}는 독립 위임 도구({need})를 지원하지 않습니다",
                    details={"backend": backend_id, "capability": need},
                ),
            )
        request = apply_contribution(plan.request, self.contribute(plan, ctx))
        return await backend.run(request, ctx, ctx.cancel)

    # ------------------------------------------------------------ 도구

    def tool(self, plan: DelegationPlan, ctx: NodeContext, cfg: HostDelegationConfig) -> HostTool:
        """위임 도구(`HostTool`): 입력 스키마의 대상 값 목록 = 대상 노드 id."""
        members = {m.node_id: m for m in plan.members}
        lines = "\n".join(
            fill(
                cfg.target_line,
                {
                    "id": m.node_id,
                    "role": m.role or m.node_id,
                    "when": m.delegate_when,
                    "agent": m.agent_id or "",
                },
            )
            for m in plan.members
        )
        description = fill(cfg.tool_description, {"targets": lines, "count": len(plan.members)})
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                cfg.target_param: {
                    "type": "string",
                    "enum": list(members),
                    "description": cfg.target_param_description,
                },
                cfg.task_param: {"type": "string", "description": cfg.task_param_description},
            },
            "required": [cfg.target_param, cfg.task_param],
            "additionalProperties": False,
        }

        async def handler(arguments: dict[str, Any]) -> HostToolResult:
            return await self._call(ctx, members, cfg, arguments)

        return HostTool(
            name=cfg.tool_name, description=description, input_schema=schema, handler=handler
        )

    async def _call(
        self,
        ctx: NodeContext,
        members: Mapping[str, DelegationMember],
        cfg: HostDelegationConfig,
        arguments: Mapping[str, Any],
    ) -> HostToolResult:
        """도구 호출 하나: 대상 확인 → `invoke_node` → 결과 텍스트(실패면 `is_error`)."""
        target = arguments.get(cfg.target_param)
        task = arguments.get(cfg.task_param)
        member = members.get(target) if isinstance(target, str) else None
        if member is None:
            text = fill(
                cfg.unknown_target_text, {"target": _as_text(target), "targets": ", ".join(members)}
            )
            return HostToolResult(text=text, is_error=True)
        if not isinstance(task, str) or not task.strip():
            return HostToolResult(
                text=fill(cfg.invalid_call_text, {"target": target}), is_error=True
            )
        try:
            port = self._input_port or _first_input_port(ctx, member.node_id)
            view = await ctx.invoke_node(
                member.node_id,
                {port: task},
                by_edge=member.edge_id,
                max_depth=self.descriptor.max_depth,
            )
        except ValueError:
            return HostToolResult(
                text=fill(cfg.invalid_call_text, {"target": target}), is_error=True
            )
        if view.status != "succeeded":
            text = self.failure_text(ctx, cfg, member.node_id, view)
            return HostToolResult(text=text, is_error=True)
        result = self.result_text(ctx, member, view)
        if not result:
            result = fill(cfg.empty_result_text, {"target": target})
        return HostToolResult(text=result)

    @staticmethod
    def failure_text(
        ctx: NodeContext, cfg: HostDelegationConfig, target: str, view: NodeRunView
    ) -> str:
        """대상 실패 → 위임자 모델에게 돌려줄 문구(config `failure_text`).

        `{code}`·`{message}`는 엔진 비밀 해석기(`ctx.secrets.redact`)로 **가린 값만** 넣는다.
        도구 결과는 위임자 모델 맥락과 백엔드 기록으로 가므로 대상 오류 원문을 내보내지 않는다.
        """
        error = view.error
        code = error.code if error is not None else ""
        message = error.message if error is not None else ""
        return fill(
            cfg.failure_text,
            {
                "target": target,
                "status": view.status,
                "code": str(ctx.secrets.redact(code)),
                "message": str(ctx.secrets.redact(message)),
            },
        )

    def result_text(self, ctx: NodeContext, member: DelegationMember, view: NodeRunView) -> str:
        """대상 결과 → 위임자에게 돌려줄 텍스트(위임 연결 config `result`).

        - `text`(기본): 대상 노드 타입의 첫 출력 포트 값(없으면 첫 출력 값).
        - `reply`: 대상의 나가는 답변 연결(디스크립터 `scheduling = exit`)이 낼 답변 텍스트를
          순서대로 이은 것. 답변 연결이 없거나 아무것도 통과하지 않으면 `text`와 같다.
        """
        if member.config.get(self._result_key) == "reply":
            replies = _reply_texts(ctx, member.node_id, view)
            if replies:
                return "\n\n".join(replies)
        return _port_text(ctx, member.node_id, view)


# ---------------------------------------------------------------- 그래프·포트 읽기


def _node_ports(ctx: NodeContext, node_id: str) -> tuple[Sequence[str], Sequence[str]]:
    spec = next((n for n in ctx.graph.nodes if n.id == node_id), None)
    if spec is None or spec.type not in ctx.registries.node_types:
        return (), ()
    ports = ctx.registries.node_types.get(spec.type, spec.type_version).resolve_ports(spec.config)
    return [p.name for p in ports.inputs], [p.name for p in ports.outputs]


def _first_input_port(ctx: NodeContext, node_id: str) -> str:
    inputs, _ = _node_ports(ctx, node_id)
    if not inputs:
        raise ValueError(f"대상 노드 {node_id!r}에 입력 포트가 없습니다")
    return inputs[0]


def _port_text(ctx: NodeContext, node_id: str, view: NodeRunView) -> str:
    _, outputs = _node_ports(ctx, node_id)
    for port in outputs:
        if port in view.outputs:
            return _as_text(view.outputs[port])
    return _as_text(next(iter(view.outputs.values()), None))


def _reply_texts(ctx: NodeContext, node_id: str, view: NodeRunView) -> list[str]:
    texts: list[str] = []
    for edge in ctx.graph.edges:
        if edge.source.node != node_id or edge.kind not in ctx.registries.edge_types:
            continue
        edge_type = ctx.registries.edge_types.get(edge.kind)
        if edge_type.descriptor.scheduling != _EXIT:
            continue
        outcome = edge_type.activates(view, edge)
        if not isinstance(outcome, Activation):
            continue
        value = outcome.value
        text = value.text if isinstance(value, Reply) else _as_text(value)
        if text:
            texts.append(text)
    return texts
