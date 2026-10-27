"""`agent` 노드: 팀 구성 안 에이전트 하나의 자리(design §R3.2).

순서:
    1. 팀 구성 해석: `ac-teams.team_plan`(등록된 디스크립터만으로, 연결 종류 이름 없이).
    2. 유효 설정: 공통(`WORKSPACE_SETTINGS`) → 팀 구성 → 에이전트(`AGENT_LOOKUP`) → 노드(config
       `settings` + 리소스 연결 첨부). `ac-teams.node_settings`.
    3. 백엔드: 유효 설정 `backend` → `DEFAULT_BACKEND`. 레지스트리에서 찾는다.
    4. 실행 묶음: 첨부 → `node_bundle`(백엔드 `resource_slots`로 받지 못하는 칸 경고, 이유는
       `slot_notes`) → 파일 칸은 `<RUN_FILES_ROOT>/<run>/<node>/`에, 다른 칸 항목의 `files` 트리
       (skill 등)는 `<…>/<node>/_bundle/<node>/<칸>/<name>/`에 쓰고 경로로 바꾼다. 문제는
       `log.warning`으로 남긴다.
    5. 요청: 정의(식별) + 유효 설정, 비밀 참조 해석, 프롬프트(`in` 값, `prompt_template`), 세션
       (`session` continue/fresh, `SESSIONS` 서비스), 허용 상호작용(`session_grant`). 요청을 만든 뒤
       `agent.context_prepared`(붙은 리소스 id·종류·바이트 수·해시와 프롬프트 조각 수, 본문 없음,
       `context.context_prepared_payload`)를 낸다.
    6. 위임 대상(디스크립터 `invocation` 연결)이 있으면 대상을 위임 방식별로 묶고, 묶음마다 유효
       설정·묶음·역할·언제 맡길지와 방식 config(노드 config `delegation[방식 id]`)로
       `DelegationPlan`을 만든다. 방식이 하나면 그 방식(X12)의 `run`, 여럿이면 모두 composable일
       때 각 방식의 `contribute`를 합쳐(`merge_contributions`) 백엔드를 한 번 부른다(혼합 위임,
       design §5R.6). 위임 대상이 없으면 `backend.run`.
    7. 결과 텍스트 → `out`, usage·`backend_session_id`.

에이전트 도구 공급자(X30, `tools`): 서비스 `TOOL_PROVIDERS`가 있으면 4의 묶음 계산 뒤 공급자마다
`provide`를 부르고, 공급 도구를 위임 기여 도구 뒤에 붙이며(이름이 겹치면 공급 도구를 뺀다), 소비한
칸을 백엔드 요청 묶음에서 뺀다. 백엔드에 `host_tools` 능력이 없으면 공급 도구를 빼고 경고한다.
위임 대상(`sdk-subagents`)은 위임자 세션 안이라 따로 공급받지 않고, 자기 NodeRun으로 실행되는
대상(`host`)은 자기 묶음으로 공급받는다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_console_contracts import (
    Agent,
    AgentSettings,
    BackendCapabilities,
    DefinitionBinding,
    DelegationStrategyDescriptor,
    ErrorInfo,
    Issue,
    NodeTypeDescriptor,
    PortDef,
    PortSpec,
    ResourceBundle,
    UiHints,
    x_ui,
)
from agent_console_registry import Registry
from agent_console_resources import (
    SLOT_UNSUPPORTED,
    ComposedBundle,
    ResourceLookup,
    ResourceType,
    render_template,
)
from agent_console_runtime import (
    AgentRequest,
    AgentResult,
    ComposableDelegation,
    DelegationMember,
    DelegationNameDeclarer,
    DelegationNameGroups,
    DelegationPlan,
    HostTool,
    NodeContext,
    NodeResult,
    SecretNotFoundError,
    Services,
    SessionRef,
    ValidationContext,
    apply_contribution,
    edge_type_descriptors,
    merge_contributions,
    node_type_descriptors,
)
from agent_console_teams import (
    NodeSettings,
    TeamPlan,
    delegation_static_issues,
    describe_member,
    node_bundle,
    node_settings,
    session_grant,
    team_plan,
)

from ._common import (
    AGENT_LOOKUP_UNAVAILABLE_MESSAGE,
    AGENT_ROLE,
    DELEGATED_PORT,
    DELEGATES_PORT,
    IN_PORT,
    OUT_PORT,
    RESOURCES_PORT,
    NodesCoreErrorCodes,
    as_text,
    failed,
    issue,
    parse_config,
    validation_errors,
    warn,
)
from .context import CONTEXT_PREPARED_EVENT, context_prepared_payload
from .files import (
    DEFAULT_FILES_SLOT,
    ITEM_FILES_KEY,
    ITEM_TREES_DIR,
    run_folder,
    write_files,
    write_item_trees,
)
from .services import (
    AGENT_LOOKUP,
    DEFAULT_BACKEND,
    ERROR_FIXES,
    RESOURCE_LOOKUP,
    RESOURCE_TYPES_EXTENSION,
    RUN_FILES_ROOT,
    SCOPE_LAYERS,
    SESSIONS,
    TOOL_PROVIDERS,
    WORKING_DIRECTORY,
    WORKSPACE_SETTINGS,
    AgentLookup,
)
from .tools import (
    ToolProviderCodes,
    ToolProvision,
    ToolProvisionContext,
    drop_taken,
    provide_tools,
)

_log = logging.getLogger("agent_console_nodes_core.agent")

__all__ = ["AgentNode", "AgentNodeConfig", "PromptFormat", "PromptInput", "assemble_prompt"]

_IDENTITY_FIELDS = tuple(
    name for name in Agent.model_fields if name not in AgentSettings.model_fields
)


class AgentNodeConfig(BaseModel):
    """팀 구성 안 에이전트 자리. 정의를 참조하고, 이 팀에서만 쓸 역할·설정을 덧붙인다."""

    model_config = ConfigDict(extra="forbid", title="에이전트 노드 설정")

    agent_ref: str = Field(
        min_length=1,
        title="에이전트",
        description="이 자리에 놓을 에이전트입니다.",
        json_schema_extra=x_ui(
            tier="basic", when="이 자리에 다른 에이전트를 놓고 싶을 때 고르세요."
        ),
    )
    role: str | None = Field(
        default=None,
        title="이 팀의 역할",
        description="이 팀 안에서 맡는 일입니다. 비우면 에이전트의 역할을 씁니다.",
        json_schema_extra=x_ui(
            tier="basic",
            when="같은 에이전트가 이 팀에서는 다른 일을 맡을 때 적으세요.",
            example="최종 검토자",
        ),
    )
    delegate_when: str | None = Field(
        default=None,
        title="언제 맡길지",
        description=(
            "다른 에이전트가 이 에이전트에게 맡길지 고를 때 보는 설명입니다. 비우면 에이전트 설명."
        ),
        json_schema_extra=x_ui(
            tier="basic",
            when="다른 에이전트가 이 에이전트에게 일을 잘못 맡기거나 안 맡길 때 고치세요.",
            example="보안 관련 변경이 있을 때 맡깁니다.",
        ),
    )
    settings: AgentSettings | None = Field(
        default=None,
        title="이 팀의 노드 설정",
        description=(
            "이 팀 안에서만 덮어쓸 에이전트 설정입니다. 비운 항목은 에이전트·팀·공통 설정을 "
            "따릅니다."
        ),
        json_schema_extra=x_ui(
            tier="advanced",
            when="같은 에이전트를 이 팀에서만 다른 모델·도구로 쓰고 싶을 때 바꾸세요.",
        ),
    )
    delegation: dict[str, dict[str, Any]] | None = Field(
        default=None,
        title="위임 방식 설정",
        description=(
            "이 에이전트가 일을 맡길 때 위임 방식마다 쓸 설정입니다. 비우면 방식 기본값입니다."
        ),
        json_schema_extra=x_ui(tier="advanced"),
    )


_PORTS = PortSpec(
    inputs=[
        PortDef(name=IN_PORT, label="받는 값"),
        PortDef(name=DELEGATED_PORT, label="위임받음"),
        PortDef(name=RESOURCES_PORT, label="리소스"),
    ],
    outputs=[PortDef(name=OUT_PORT, label="결과"), PortDef(name=DELEGATES_PORT, label="위임")],
)


@dataclass(frozen=True, slots=True)
class PromptInput:
    """프롬프트로 합칠 넘겨받은 값 하나(엣지 하나)."""

    value: Any
    node: str | None = None
    label: str | None = None
    port: str | None = None
    edge: str | None = None


_SETTING_DEFAULTS = AgentSettings()
"""값별 형식 기본값의 출처 = 계약 `AgentSettings` 필드 기본값(데이터). 코드에 따로 두지 않는다."""


@dataclass(frozen=True, slots=True)
class PromptFormat:
    """넘겨받은 값들을 `{inputs}`로 만드는 형식(유효 설정 `prompt_input_*`, design §R3.2-4).

    None인 항목은 계약 기본값(`AgentSettings` 필드 기본값)을 쓴다.
    템플릿 변수: `source`(보낸 노드 이름, 없으면 id, 둘 다 없으면 빈 문자열), `source_id`,
    `port`, `edge`, `value`(텍스트), `index`(1부터).
    """

    item: str | None = None
    single: str | None = None
    separator: str | None = None

    @classmethod
    def of(cls, settings: AgentSettings) -> PromptFormat:
        """유효 설정에서 형식을 읽는다."""
        return cls(
            item=settings.prompt_input_template,
            single=settings.prompt_single_input_template,
            separator=settings.prompt_input_separator,
        )

    def join(self, items: Sequence[PromptInput]) -> str:
        """값들을 형식대로 합친다(값 하나면 `single`, 여럿이면 `item`을 `separator`로 잇는다)."""
        if not items:
            return ""
        d = _SETTING_DEFAULTS
        if len(items) == 1:
            template = _pick(self.single, d.prompt_single_input_template)
        else:
            template = _pick(self.item, d.prompt_input_template)
        separator = _pick(self.separator, d.prompt_input_separator)
        return separator.join(
            render_template(template, _item_values(item, index))
            for index, item in enumerate(items, start=1)
        )


def _pick(value: str | None, default: str | None) -> str:
    return value if value is not None else (default or "")


def _item_values(item: PromptInput, index: int) -> dict[str, Any]:
    return {
        "source": item.label or item.node or "",
        "source_id": item.node or "",
        "port": item.port or "",
        "edge": item.edge or "",
        "value": as_text(item.value),
        "index": index,
    }


def assemble_prompt(
    items: Sequence[PromptInput],
    template: str | None = None,
    *,
    message: str = "",
    node: str = "",
    fmt: PromptFormat | None = None,
) -> str:
    """넘겨받은 값들을 프롬프트로 합친다(design §R2.2 `prompt_template`, §R3.2-4).

    Args:
        items: 넘겨받은 값(엣지마다 하나, 보낸 노드·이름 포함). 비면 빈 프롬프트.
        template: 안전 치환 형식. 변수 `{inputs}`(값들을 `fmt`로 합친 것), `{message}`, `{node}`.
            None이면 `{inputs}` 그대로.
        message: 사용자 메시지(Run 입력).
        node: 이 노드 이름.
        fmt: 값별 형식·구분자(유효 설정 `prompt_input_*`). None이면 계약 기본값.
    """
    joined = (fmt or PromptFormat()).join(items)
    if template is None:
        return joined
    return render_template(template, {"inputs": joined, "message": message, "node": node})


def _lookup(lookup: AgentLookup, ref: str) -> Agent | None:
    try:
        return lookup(ref)
    except LookupError:
        return None


def _message_of(run_input: Mapping[str, Any]) -> str:
    if len(run_input) == 1:
        return as_text(next(iter(run_input.values())))
    return as_text(dict(run_input)) if run_input else ""


def _prompt_inputs(
    ctx: NodeContext, plan: TeamPlan, value: Any, *, fresh_only: bool = False
) -> list[PromptInput]:
    """`in` 포트로 들어온 값들 → 프롬프트 입력(엣지마다 하나, 보낸 노드 이름 포함).

    엔진이 주는 엣지별 값(`ctx.incoming`, design §4.3)을 쓰므로 join `all` 합류 값이 모두 들어간다.
    엣지별 값이 없으면(엔진 밖 맥락) 첫 값(`inputs["in"]`)만 쓴다. `fresh_only`면 이전 회차 전에
    도착해 남아 있던 값(`Incoming.carried`)을 뺀다 — 직전 회차 세션을 이어 쓰면 이미 본 값이다
    (design §5R.4). 새 값이 하나도 없으면 남아 있던 값을 쓴다.
    """
    received = [i for i in ctx.incoming(IN_PORT) if i.value is not None]
    if fresh_only:
        received = [i for i in received if not i.carried] or received
    if received:
        return [
            PromptInput(
                i.value, i.source_node, plan.label_of(i.source_node), port=i.port, edge=i.edge_id
            )
            for i in received
        ]
    return [] if value is None else [PromptInput(value)]


class AgentNode:
    """노드 타입 `agent`."""

    descriptor = NodeTypeDescriptor(
        id="agent",
        version=1,
        title="에이전트",
        description="에이전트 정의 하나의 자리. 층 설정·리소스·위임으로 실행 백엔드를 호출한다.",
        category="에이전트",
        role=AGENT_ROLE,
        executable=True,
        binds=DefinitionBinding(kind="agent", field="agent_ref"),
        config_schema=AgentNodeConfig.model_json_schema(),
        ui_schema={
            "ui:order": ["agent_ref", "role", "delegate_when", "settings", "delegation"],
            "delegate_when": {"ui:widget": "textarea"},
        },
        static_ports=_PORTS,
        # 같은 입력으로 다시 실행할 수 있다(세션 정책은 노드 설정 그대로, 비용이 들 수 있다 §2R.10).
        rerunnable=True,
        ui_hints=UiHints(shape="card"),
    )

    def resolve_ports(self, config: Mapping[str, Any]) -> PortSpec:
        """고정 포트(`in`·`delegated`·`resources` → `out`·`delegates`)."""
        return _PORTS

    def actor_of(self, config: Mapping[str, Any]) -> str | None:
        """이 자리의 에이전트 정의 id(이벤트 `actor`, 엔진 선택 훅)."""
        ref = config.get("agent_ref")
        return ref if isinstance(ref, str) and ref else None

    def validate(self, config: Mapping[str, Any], ctx: ValidationContext) -> list[Issue]:
        """`agent_ref` 존재(조회 서비스가 있을 때)·노드 설정 `backend` 등록·위임 방식 정적 검사.

        이 노드가 위임자이면 등록된 위임 방식(X12)의 선택 메서드 `static_issues`·`declared_names`를
        부른다(`ac-teams.delegation_static_issues`, design §5.2R.7). 방식 config 스키마·같은 대상
        중복은 팀 규칙(`validate_team`)이 낸다.
        """
        issues: list[Issue] = []
        ref = config.get("agent_ref")
        lookup = ctx.services.get(AGENT_LOOKUP)
        if isinstance(ref, str) and lookup is not None and _lookup(lookup, ref) is None:
            issues.append(
                issue(
                    NodesCoreErrorCodes.AGENT_NOT_FOUND,
                    f"에이전트 {ref!r}가 없습니다",
                    "/agent_ref",
                )
            )
        settings = config.get("settings")
        backend = settings.get("backend") if isinstance(settings, Mapping) else None
        if isinstance(backend, str) and backend not in ctx.registries.backends:
            issues.append(
                issue(
                    NodesCoreErrorCodes.AGENT_UNKNOWN_BACKEND,
                    f"등록되지 않은 실행 백엔드 {backend!r}",
                    "/settings/backend",
                )
            )
        issues.extend(_static_delegation_issues(ctx, lookup))
        return issues

    def display_name(self, config: Mapping[str, Any], services: Services | None) -> str | None:
        """사용자 문구의 노드 이름(엔진 선택 훅 `display_name`): 묶인 에이전트 정의의 `name`.

        조회 서비스가 없거나 정의가 없으면 None(엔진이 노드 타입 제목을 쓴다)."""
        ref = config.get("agent_ref")
        lookup = services.get(AGENT_LOOKUP) if services is not None else None
        if not isinstance(ref, str) or not ref or lookup is None:
            return None
        agent = _lookup(lookup, ref)
        return agent.name if agent is not None and agent.name else None

    async def execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        """에이전트를 실행한다(위임 대상이 있으면 위임 방식으로). 문제는 원인별 코드로 실패한다.

        실패에 해결 버튼이 없고 서비스 `ERROR_FIXES`가 있으면 그 코드의 버튼을 붙인다."""
        result = await self._execute(ctx, inputs)
        error = result.error
        fixer = ctx.services.get(ERROR_FIXES)
        if result.status != "failed" or error is None or error.fix is not None or fixer is None:
            return result
        try:
            fix = fixer(error.code, ctx.graph, ctx.node.id)
        except Exception:  # 버튼 계산 실패가 실패 결과를 가리지 않게
            _log.exception("노드 실패 해결 버튼 계산 실패: %s", error.code)
            return result
        if fix is None:
            return result
        return result.model_copy(update={"error": error.model_copy(update={"fix": fix})})

    async def _execute(self, ctx: NodeContext, inputs: Mapping[str, Any]) -> NodeResult:
        cfg = parse_config(AgentNodeConfig, ctx.config)
        if isinstance(cfg, NodeResult):
            return cfg
        lookup = ctx.services.get(AGENT_LOOKUP)
        if lookup is None:
            return failed(
                NodesCoreErrorCodes.AGENT_LOOKUP_UNAVAILABLE,
                AGENT_LOOKUP_UNAVAILABLE_MESSAGE,
                agent_ref=cfg.agent_ref,
            )
        plan = team_plan(
            ctx.graph,
            node_types=node_type_descriptors(ctx.registries),
            edge_types=edge_type_descriptors(ctx.registries),
        )
        links = plan.delegates_of.get(ctx.node.id, ())
        agents: dict[str, Agent] = {}
        for ref in [cfg.agent_ref, *(plan.agent_refs.get(link.member) for link in links)]:
            if ref is None or ref in agents:
                continue
            found = _lookup(lookup, ref)
            if found is None:
                return failed(
                    NodesCoreErrorCodes.AGENT_NOT_FOUND,
                    f"에이전트 {ref!r}가 없습니다",
                    agent_ref=ref,
                )
            agents[ref] = found
        run = _Runner(ctx, plan, agents)
        ns = run.settings_of(ctx.node.id)
        settings = ns.effective.value

        backend_id = settings.backend or ctx.services.get(DEFAULT_BACKEND)
        if not backend_id:
            # 실행 전 사전 점검(`backend.unresolved`)을 거치지 않은 실행(자식 Run 등)만 여기 온다.
            # 문구는 노드를 이름으로 부르고 id는 상세에만 둔다.
            name = ctx.node.label or agents[cfg.agent_ref].name or cfg.agent_ref
            return failed(
                NodesCoreErrorCodes.AGENT_NO_BACKEND,
                f"'{name}'을(를) 실행할 백엔드가 정해지지 않았습니다. "
                "노드 설정이나 설정의 공통 기본값에서 실행 백엔드를 고르세요.",
                node_id=ctx.node.id,
                agent_ref=cfg.agent_ref,
            )
        if backend_id not in ctx.backends:
            return failed(
                NodesCoreErrorCodes.AGENT_UNKNOWN_BACKEND,
                f"등록되지 않은 실행 백엔드 {backend_id!r}",
                backend=backend_id,
            )
        backend = ctx.backends.get(backend_id)
        caps = backend.descriptor.capabilities

        definition = _definition(agents[cfg.agent_ref], settings, backend_id)
        if isinstance(definition, NodeResult):
            return definition
        try:
            resolved = Agent.model_validate(
                ctx.secrets.resolve_refs(definition.model_dump(mode="json", exclude_unset=True))
            )
        except SecretNotFoundError as exc:
            return failed(
                NodesCoreErrorCodes.AGENT_SECRET_NOT_FOUND,
                f"비밀 {exc.name!r}를 찾을 수 없습니다",
                secret=exc.name,
            )

        session = _session(ctx, settings, backend_id)
        continuing = session is not None and session.session_id == ctx.previous_session_id
        items = _prompt_inputs(ctx, plan, inputs.get(IN_PORT), fresh_only=continuing)
        prompt = assemble_prompt(
            items,
            settings.prompt_template,
            message=_message_of(ctx.run.input),
            node=plan.label_of(ctx.node.id),
            fmt=PromptFormat.of(settings),
        )
        composed = await run.compose(ctx.node.id, ns, caps)
        provision = await _provision(ctx, cfg.agent_ref, composed, caps)
        bundle = await run.finish(ctx.node.id, composed, provision.consumed_slots)
        provided = list(provision.host_tools)
        request = AgentRequest(
            agent=resolved,
            prompt=prompt,
            cwd=settings.working_directory or ctx.services.get(WORKING_DIRECTORY),
            limits=resolved.limits,
            session=session,
            bundle=bundle,
            interactions=session_grant(plan, ctx.node.id, run.strategies) or ctx.interaction_grant,
            observe=settings.observe.model_dump(mode="json", exclude_none=True)
            if settings.observe is not None
            else {},
            **_run_location(ctx),
        )
        if provided and not links:
            request = request.model_copy(update={"host_tools": provided})
        # C1(design §5.5R.1): 붙은 리소스 표지·조각 수만(본문 없음). 본문 읽기는 스레드에서.
        await ctx.emit(
            CONTEXT_PREPARED_EVENT,
            await asyncio.to_thread(
                context_prepared_payload,
                bundle,
                run.resources,
                resource_types=run.resource_types,
                fragments=len(items),
            ),
        )

        if links:
            outcome = await run.delegate(
                links, request, backend_id, caps, cfg.delegation or {}, provided=provided
            )
            if isinstance(outcome, NodeResult):
                return outcome
            result = outcome
        else:
            result = await backend.run(request, ctx, ctx.cancel)
        return _node_result(result, backend_id)


async def _provision(
    ctx: NodeContext, agent_id: str, composed: ComposedBundle | None, caps: BackendCapabilities
) -> ToolProvision:
    """서비스 `TOOL_PROVIDERS`의 공급자를 불러 이 노드에 줄 도구를 모은다(X30). 경고는 여기서 낸다.

    공급자가 없으면 빈 결과(기존 실행과 같다). 백엔드에 `host_tools` 능력이 없으면 도구를 빼고
    `tools.backend_capability_missing` 경고를 낸다(소비한 칸은 그대로 뺀다).
    """
    providers = ctx.services.get(TOOL_PROVIDERS)
    if not providers:
        return ToolProvision()

    async def emit(type: str, payload: Mapping[str, Any]) -> None:
        await ctx.emit(type, payload)

    tctx = ToolProvisionContext(
        run_id=ctx.run.id,
        root_run_id=ctx.run.root_run_id or ctx.run.id,
        graph_id=ctx.graph.id,
        node_id=ctx.node.id,
        node_path=tuple(ctx.node_path),
        agent_id=ctx.actor or agent_id,
        call=ctx.call,
        iteration=ctx.iteration,
        bundle=composed.bundle if composed is not None else ResourceBundle(),
        backend_capabilities=caps,
        emit=emit,
        cancel=ctx.cancel,
    )
    provision = provide_tools(providers, tctx)
    issues = list(provision.warnings)
    tools = provision.host_tools
    if tools and not caps.host_tools:
        names = [t.name for t in tools]
        issues.append(
            Issue(
                severity="warning",
                code=ToolProviderCodes.BACKEND_CAPABILITY_MISSING,
                message="실행 백엔드가 플랫폼 도구를 지원하지 않아 공급 도구를 주지 않습니다",
                details={"tools": names},
            )
        )
        tools = ()
    await warn(ctx, issues, node=ctx.node.id)
    return ToolProvision(host_tools=tools, consumed_slots=provision.consumed_slots)


def _delegation_tool_names(strategy: Any, plan: DelegationPlan, ctx: NodeContext) -> list[str]:
    """방식 하나로 위임할 때 그 방식이 더할 플랫폼 도구 이름(공급 도구 이름 충돌 검사용).

    선택 프로토콜 `declared_names`(묶음 `host_tool`)를 먼저 보고, 없으면 `contribute` 결과에서
    읽는다. 둘 다 없거나 실패하면 모른다(빈 목록).
    """
    try:
        if isinstance(strategy, DelegationNameDeclarer):
            names = strategy.declared_names(plan.config, plan.members)
            return list(names.get(DelegationNameGroups.HOST_TOOL, []))
        if isinstance(strategy, ComposableDelegation):
            return [t.name for t in strategy.contribute(plan, ctx).host_tools]
    except Exception:  # 이름을 몰라도 실행은 계속(방식의 run이 자기 오류를 낸다)
        _log.debug("위임 도구 이름을 읽지 못했습니다: %s", plan.strategy, exc_info=True)
    return []


def _strip_slots(bundle: ResourceBundle, consumed: frozenset[str]) -> ResourceBundle:
    """소비된 칸(값·출처)을 뺀 묶음 사본."""
    if not consumed or not (consumed & (bundle.slots.keys() | bundle.sources.keys())):
        return bundle
    return bundle.model_copy(
        update={
            "slots": {k: v for k, v in bundle.slots.items() if k not in consumed},
            "sources": {k: v for k, v in bundle.sources.items() if k not in consumed},
        }
    )


def _static_delegation_issues(ctx: ValidationContext, lookup: AgentLookup | None) -> list[Issue]:
    """이 노드가 위임자일 때 등록된 위임 방식의 저장 시점 정적 검사(design §5.2R.7)."""
    registry = ctx.registries.delegation_strategies
    if not len(registry):
        return []
    plan = team_plan(
        ctx.graph,
        node_types=node_type_descriptors(ctx.registries),
        edge_types=edge_type_descriptors(ctx.registries),
    )
    links = plan.delegates_of.get(ctx.node.id, ())
    if not links:
        return []
    agents: dict[str, Agent] = {}
    if lookup is not None:
        for link in links:
            ref = plan.agent_refs.get(link.member)
            if ref is not None and ref not in agents:
                found = _lookup(lookup, ref)
                if found is not None:
                    agents[ref] = found
    checks = {e.key: e.item for e in registry.list()}
    return delegation_static_issues(plan, checks, delegators=[ctx.node.id], agents=agents)


def _run_location(ctx: NodeContext) -> dict[str, Any]:
    """`AgentRequest.run_folder`·`run_context`: 실행 폴더(`<RUN_FILES_ROOT>/<run>/<node>`, 서비스가
    없거나 id가 폴더 이름으로 안전하지 않으면 None)와 산출물 맥락(run_id·node_path). 폴더는 만들지
    않는다(백엔드가 쓸 때 만든다)."""
    root = ctx.services.get(RUN_FILES_ROOT)
    folder = run_folder(root, ctx.run.id, ctx.node.id) if root else None
    return {
        "run_folder": str(folder) if folder is not None else None,
        "run_context": {"run_id": ctx.run.id, "node_path": "/".join(ctx.node_path)},
    }


def _definition(base: Agent, settings: AgentSettings, backend_id: str) -> Agent | NodeResult:
    """정의 식별 필드 + 유효 설정(지정한 필드만) + 정한 백엔드."""
    identity = base.model_dump(mode="json", include=set(_IDENTITY_FIELDS))
    data = {**identity, **settings.model_dump(mode="json", exclude_unset=True)}
    data["backend"] = backend_id
    try:
        return Agent.model_validate(data)
    except ValidationError as exc:
        return failed(
            NodesCoreErrorCodes.AGENT_INVALID_DEFINITION,
            f"에이전트 정의가 유효하지 않습니다: {exc.error_count()}개 오류",
            errors=validation_errors(exc),
        )


def _session(ctx: NodeContext, settings: AgentSettings, backend_id: str) -> SessionRef | None:
    """이어 쓸 세션: `session`이 `fresh`가 아닐 때, 같은 노드 직전 반복 회차의 세션
    (`ctx.previous_session_id`, design §5R.4) 또는 주입된 같은 백엔드의 세션."""
    if settings.session == "fresh":
        return None
    if ctx.previous_session_id:
        return SessionRef(backend=backend_id, session_id=ctx.previous_session_id)
    sessions = ctx.services.get(SESSIONS)
    found = sessions.get(ctx.node.id) if sessions is not None else None
    if found is None or found.backend != backend_id:
        return None
    return found


def _node_result(result: AgentResult, backend_id: str) -> NodeResult:
    session_id = result.session.session_id if result.session is not None else None
    if result.status == "succeeded":
        return NodeResult(
            status="succeeded",
            outputs={OUT_PORT: result.text},
            usage=result.usage,
            backend_session_id=session_id,
            structured=result.structured,
        )
    error = result.error or ErrorInfo(
        code=NodesCoreErrorCodes.AGENT_CANCELLED
        if result.status == "cancelled"
        else NodesCoreErrorCodes.AGENT_BACKEND_FAILED,
        message=f"실행 백엔드 {backend_id!r} 결과: {result.status}",
    )
    return NodeResult(
        status="failed", error=error, usage=result.usage, backend_session_id=session_id
    )


class _Runner:
    """한 번의 agent 노드 실행에서 설정·묶음·위임 계획을 만드는 도우미."""

    def __init__(self, ctx: NodeContext, plan: TeamPlan, agents: Mapping[str, Agent]) -> None:
        self.ctx = ctx
        self.plan = plan
        self.agents = agents
        self.strategies: dict[str, DelegationStrategyDescriptor] = {
            e.key: e.item.descriptor for e in ctx.registries.delegation_strategies.list()
        }
        self.resources: ResourceLookup | None = ctx.services.get(RESOURCE_LOOKUP)
        self.resource_types = cast(
            Registry[ResourceType], ctx.registries.extension(RESOURCE_TYPES_EXTENSION)
        )

    def settings_of(self, node_id: str) -> NodeSettings:
        return node_settings(
            self.plan,
            node_id,
            agents=self.agents,
            workspace=self.ctx.services.get(WORKSPACE_SETTINGS),
            strategies=self.strategies,
            resource_types=self.resource_types if self.resources is not None else None,
            resources=self.resources,
            scope_layers=self.ctx.services.get(SCOPE_LAYERS) or (),
        )

    async def bundle_of(
        self, node_id: str, ns: NodeSettings, caps: BackendCapabilities
    ) -> ResourceBundle | None:
        """첨부 → 실행 묶음(파일 칸은 실행 폴더에 써서 경로로). 첨부가 없으면 None."""
        return await self.finish(node_id, await self.compose(node_id, ns, caps), frozenset())

    async def compose(
        self, node_id: str, ns: NodeSettings, caps: BackendCapabilities
    ) -> ComposedBundle | None:
        """첨부 → 묶음 계산(경고는 아직 내지 않는다). 첨부가 없거나 리소스 조회가 없으면 None."""
        ctx = self.ctx
        if not ns.attachments:
            return None
        if self.resources is None:
            await warn(
                ctx,
                [
                    Issue(
                        severity="warning",
                        code=NodesCoreErrorCodes.AGENT_RESOURCES_UNAVAILABLE,
                        message="리소스 조회 서비스가 없어 붙은 리소스를 전달하지 않습니다",
                    )
                ],
                node=node_id,
            )
            return None
        return node_bundle(
            ns,
            resource_types=self.resource_types,
            resources=self.resources,
            accepted_slots=caps.resource_slots,
            slot_notes=caps.slot_notes,
        )

    async def finish(
        self, node_id: str, composed: ComposedBundle | None, consumed: frozenset[str]
    ) -> ResourceBundle | None:
        """묶음 경고를 내고, 소비된 칸(X30)을 빼고, 파일 칸을 실행 폴더에 써서 경로로 바꾼다.

        소비된 칸의 "백엔드가 받지 않는 칸" 경고(`resource.slot_unsupported`)는 내지 않는다.
        """
        ctx = self.ctx
        if composed is None:
            return None
        await warn(
            ctx,
            [
                i
                for i in composed.issues
                if i.severity != "info"
                and not (i.code == SLOT_UNSUPPORTED and i.details.get("slot") in consumed)
            ],
            node=node_id,
        )
        bundle = _strip_slots(composed.bundle, consumed)
        has_files = bool(bundle.slots.get(DEFAULT_FILES_SLOT))
        has_trees = any(
            slot != DEFAULT_FILES_SLOT
            and isinstance(value, list)
            and any(isinstance(i, dict) and ITEM_FILES_KEY in i for i in value)
            for slot, value in bundle.slots.items()
        )
        if not has_files and not has_trees:
            return bundle
        root = ctx.services.get(RUN_FILES_ROOT)
        folder = run_folder(root, ctx.run.id, node_id) if root else None
        if folder is None:
            await warn(
                ctx,
                [
                    Issue(
                        severity="warning",
                        code=NodesCoreErrorCodes.FILES_UNAVAILABLE,
                        message="실행 폴더를 정할 수 없어 파일을 전달하지 않습니다",
                    )
                ],
                node=node_id,
            )
            slots = {
                k: _without_tree_files(v)
                for k, v in bundle.slots.items()
                if k != DEFAULT_FILES_SLOT
            }
            return bundle.model_copy(update={"slots": slots})
        if has_files:
            bundle, issues = await asyncio.to_thread(
                write_files, bundle, folder, reserved=(ITEM_TREES_DIR,)
            )
            await warn(ctx, issues, node=node_id)
        if has_trees:
            bundle, issues = await asyncio.to_thread(
                write_item_trees, bundle, folder / ITEM_TREES_DIR / node_id
            )
            await warn(ctx, issues, node=node_id)
        return bundle

    async def members_of(
        self, links: Sequence[Any], caps: BackendCapabilities
    ) -> list[DelegationMember]:
        """위임 연결 → 대상(유효 설정·묶음·역할·언제 맡길지·엣지 config)."""
        members: list[DelegationMember] = []
        for link in links:
            ref = self.plan.agent_refs.get(link.member)
            agent = self.agents.get(ref) if ref is not None else None
            profile = describe_member(link, agent)
            mns = self.settings_of(link.member)
            edge = self.plan.edge(link.edge_id)
            members.append(
                DelegationMember(
                    node_id=link.member,
                    edge_id=link.edge_id,
                    agent_id=ref,
                    role=profile.role or None,
                    delegate_when=profile.delegate_when,
                    settings=mns.effective.value,
                    bundle=await self.bundle_of(link.member, mns, caps),
                    config=dict(edge.config) if edge is not None else {},
                )
            )
        return members

    async def delegate(
        self,
        links: Sequence[Any],
        request: AgentRequest,
        backend_id: str,
        caps: BackendCapabilities,
        configs: Mapping[str, Mapping[str, Any]],
        *,
        provided: Sequence[HostTool] = (),
    ) -> AgentResult | NodeResult:
        """위임 대상을 방식별로 묶어 실행한다. 계획 단계 문제는 `NodeResult`(실패).

        `provided`(X30 공급 도구)는 위임 도구와 이름이 겹치는 것을 빼고 위임자 요청에 붙인다.

        - 방식 하나: 그 방식의 `run`.
        - 방식 여럿: 모두 디스크립터 `composable`이고 `contribute`가 있어야 한다. 각 방식의 필요
          백엔드 능력을 확인하고 `contribute` 결과를 합쳐(이름 충돌은 실패) 백엔드를 한 번 부른다.
        """
        ctx = self.ctx
        registry = ctx.registries.delegation_strategies
        groups: dict[str, list[Any]] = {}
        for link in links:
            groups.setdefault(link.strategy, []).append(link)
        ids = list(groups)
        for strategy_id in ids:
            if strategy_id not in registry:
                return failed(
                    NodesCoreErrorCodes.AGENT_UNKNOWN_STRATEGY,
                    f"등록되지 않은 위임 방식 {strategy_id!r}",
                    strategy=strategy_id,
                )
        strategies = {sid: registry.get(sid) for sid in ids}
        if len(ids) > 1:
            blocked = [
                sid
                for sid, impl in strategies.items()
                if not (impl.descriptor.composable and isinstance(impl, ComposableDelegation))
            ]
            if blocked:
                return failed(
                    NodesCoreErrorCodes.AGENT_MIXED_STRATEGIES,
                    "한 노드의 위임 대상에 함께 실행할 수 없는 위임 방식이 섞여 있습니다",
                    strategies=ids,
                    not_composable=blocked,
                )
        plans: list[DelegationPlan] = []
        for sid in ids:
            plan = DelegationPlan(
                strategy=sid,
                delegator_node_id=ctx.node.id,
                backend=backend_id,
                request=request,
                members=await self.members_of(groups[sid], caps),
                config=dict(configs.get(sid) or {}),
            )
            errors = [i for i in strategies[sid].validate(plan) if i.severity == "error"]
            if errors:
                return failed(
                    NodesCoreErrorCodes.AGENT_DELEGATION_INVALID,
                    errors[0].message,
                    strategy=sid,
                    issues=[i.model_dump(mode="json", exclude_none=True) for i in errors],
                )
            plans.append(plan)
        if len(plans) == 1:
            plan = plans[0]
            if provided:
                taken = [
                    *(t.name for t in request.host_tools),
                    *_delegation_tool_names(strategies[ids[0]], plan, ctx),
                ]
                kept, issues = drop_taken(provided, taken)
                await warn(ctx, issues, node=ctx.node.id)
                tools = [*request.host_tools, *kept]
                plan = plan.model_copy(
                    update={"request": request.model_copy(update={"host_tools": tools})}
                )
            return await strategies[ids[0]].run(plan, ctx)
        return await self._run_composed(
            plans, strategies, request, backend_id, caps, provided=provided
        )

    async def _run_composed(
        self,
        plans: Sequence[DelegationPlan],
        strategies: Mapping[str, Any],
        request: AgentRequest,
        backend_id: str,
        caps: BackendCapabilities,
        *,
        provided: Sequence[HostTool] = (),
    ) -> AgentResult | NodeResult:
        """혼합 위임: 방식마다 `contribute` → 합치기 → 백엔드 한 번(공급 도구는 위임 도구 뒤)."""
        ctx = self.ctx
        for plan in plans:
            need = strategies[plan.strategy].descriptor.requires_backend_capability
            if need and getattr(caps, need, None) is not True:
                return failed(
                    NodesCoreErrorCodes.DELEGATION_BACKEND_UNSUPPORTED,
                    f"백엔드 {backend_id!r}는 위임 방식 {plan.strategy!r}에 필요한 능력({need})을 "
                    "지원하지 않습니다",
                    backend=backend_id,
                    strategy=plan.strategy,
                    capability=need,
                )
        contributions = [strategies[p.strategy].contribute(p, ctx) for p in plans]
        merged, issues = merge_contributions(contributions)
        if issues:
            return failed(
                issues[0].code,
                issues[0].message,
                strategies=[p.strategy for p in plans],
                issues=[i.model_dump(mode="json", exclude_none=True) for i in issues],
            )
        backend = ctx.backends.get(backend_id)
        sink = merged.wrap_sink(ctx) if merged.wrap_sink is not None else ctx
        final = apply_contribution(request, merged)
        if provided:
            kept, dropped = drop_taken(provided, [t.name for t in final.host_tools])
            await warn(ctx, dropped, node=ctx.node.id)
            final = final.model_copy(update={"host_tools": [*final.host_tools, *kept]})
        return await backend.run(final, sink, ctx.cancel)


def _without_tree_files(value: Any) -> Any:
    """칸 값 항목에서 본문 `files`를 뺀다(실행 폴더가 없어 쓰지 못할 때 본문을 넘기지 않게)."""
    if not isinstance(value, list):
        return value
    return [
        {k: v for k, v in item.items() if k != ITEM_FILES_KEY} if isinstance(item, dict) else item
        for item in value
    ]
